import asyncio
import logging
import string
from collections import deque
from dataclasses import dataclass

import discord
from twitch.eventsub import ClientApp, Event, StreamOfflineEvent, StreamOnlineEvent

from ayalite.discord_sender import DiscordSender

_log = logging.getLogger(__name__)

OFFLINE_GRACE_PERIOD = 120 # seconds, blip window of 2min

DEFAULT_GOING_LIVE_TEXT = "{name} is now live!"
# everything here comes off the event itself, so rendering never needs an extra
# helix call on the hot path
GOING_LIVE_FIELDS = frozenset({"name", "login", "url"})


def validate_going_live_text(text: str) -> str:
    """Reject a bad template at startup rather than when someone goes live.

    An unknown placeholder only blows up at .format() time, which would be the
    middle of the night and one missed announcement later.
    """
    try:
        parsed = list(string.Formatter().parse(text))
    except ValueError as exc:
        raise RuntimeError(f"going_live_text is not a valid template: {exc}") from exc

    # strip any .attr / [index] suffix so {name.upper} validates on "name"
    used = {
        field.split(".")[0].split("[")[0]
        for _, field, _, _ in parsed
        if field is not None
    }
    unknown = used - GOING_LIVE_FIELDS
    if unknown:
        placeholders = ", ".join(sorted(f"{{{u}}}" for u in unknown))
        allowed = ", ".join(sorted(f"{{{f}}}" for f in GOING_LIVE_FIELDS))
        raise RuntimeError(
            f"going_live_text uses unknown placeholder(s) {placeholders}; "
            f"available: {allowed}"
        )
    return text

@dataclass
class LiveState:
    stream_id: str
    message_id: int
    offline_task: asyncio.Task | None = None

class EventHandlers:
    def __init__(
        self,
        client: ClientApp,
        sender: DiscordSender,
        announce_channel_id: int,
        going_live_text: str = DEFAULT_GOING_LIVE_TEXT,
        ping_role_id: int | None = None,
    ) -> None:
        self._client = client
        self._sender = sender
        self._announce_channel_id = announce_channel_id
        self._going_live_text = going_live_text
        self._ping_role_id = ping_role_id
        self._live: dict[str, LiveState] = {}
        self._seen: deque[str] = deque(maxlen=512)

    def register(self) -> None:
        self._client.event(self.on_stream_online_v1)
        self._client.event(self.on_stream_offline_v1)

    async def on_stream_online_v1(self, message: Event[StreamOnlineEvent]) -> None:
        if message.id in self._seen:
            _log.debug("duplicate message %s, ignoring", message.id)
            return
        self._seen.append(message.id)

        event = message.event
        login = event.broadcaster.login
        state = self._live.get(login)

        if event.type != "live":
            _log.debug("ignoring %s for %s", event.type, login)
            return

        if state is not None and state.offline_task is not None:
            # for short cutouts in the stream, shorter than the grace period
            state.offline_task.cancel()
            state.offline_task = None
            _log.info("%s came back before the grace period elapsed", login)
            return

        if self._client.application is None:
            raise RuntimeError("client is not authorized")
        streams = await self._client.application.get_streams(user_ids={event.broadcaster.id})
        stream = next(iter(streams), None)

        embed = self._build_live_embed(event, stream)
        msg = await self._sender.send_embed(
            self._announce_channel_id, embed, self._ping_role_id
        )
        self._live[login] = LiveState(stream_id=event.id, message_id=msg.id)

    async def on_stream_offline_v1(self, message: Event[StreamOfflineEvent]) -> None:
        if message.id in self._seen:
            _log.debug("duplicate message %s, ignoring", message.id)
            return
        self._seen.append(message.id)
        event = message.event
        login = event.broadcaster.login
        state = self._live.get(login)

        if state is None:
            # if we never saw the streamer go online (bot restarts...)
            return

        state.offline_task = asyncio.create_task(self._mark_offline_after_delay(login))

    async def _mark_offline_after_delay(self, login: str, delay: float = OFFLINE_GRACE_PERIOD) -> None:
        await asyncio.sleep(delay)
        state = self._live.pop(login, None)
        if state is None:
            return
        await self._sender.mark_offline(self._announce_channel_id, state.message_id)

    def _render_going_live(self, event: StreamOnlineEvent) -> str:
        broadcaster = event.broadcaster
        try:
            return self._going_live_text.format(
                name=broadcaster.name,
                login=broadcaster.login,
                url=f"https://twitch.tv/{broadcaster.login}",
            )
        except (KeyError, IndexError, ValueError, AttributeError):
            # load_config already validated this, so reaching here means the
            # template is odd in a way parsing missed. a plain announcement
            # beats dropping the notification entirely.
            _log.exception("could not render going_live_text, using the default")
            return DEFAULT_GOING_LIVE_TEXT.format(name=broadcaster.name)

    def _build_live_embed(self, event: StreamOnlineEvent, stream) -> discord.Embed:
        embed = discord.Embed(
            title=stream.title if stream else "Live on Twitch!",
            description=self._render_going_live(event),
            color=discord.Color.purple(),
        )
        if stream:
            embed.add_field(name="Playing", value=stream.category.name)
        embed.set_author(name=event.broadcaster.name)
        return embed
