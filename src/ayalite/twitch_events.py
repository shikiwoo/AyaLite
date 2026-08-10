import asyncio
import logging
import string
from collections import deque
from dataclasses import dataclass

import discord
from twitch import HTTPException
from twitch.eventsub import ClientApp, Event, StreamOfflineEvent, StreamOnlineEvent

from ayalite.discord_sender import DiscordSender

_log = logging.getLogger(__name__)

OFFLINE_GRACE_PERIOD = 120 # seconds, blip window of 2min

DEFAULT_GOING_LIVE_TEXT = "{name} is now live!"
# everything here comes off the event itself, so rendering never needs an extra
# helix call on the hot path
GOING_LIVE_FIELDS = frozenset({"name", "login", "url"})

# twitch hands back the preview URL with size placeholders in it. 1280x720 is
# the largest size it renders; discord scales it down to the embed width.
PREVIEW_SIZE = (1280, 720)
PREVIEW_URL_TEMPLATE = (
    "https://static-cdn.jtvnw.net/previews-ttv/live_user_{login}-{width}x{height}.jpg"
)


def channel_url(login: str) -> str:
    return f"https://twitch.tv/{login}"


def _preview_url(login: str, stream, cache_key: str) -> str:
    """Full-size stream preview, tagged so discord re-fetches it per stream.

    Twitch serves every channel's preview from one permanent URL, and discord's
    image proxy caches by URL - without something unique on the end, the second
    and every later announcement for a channel would show the frame captured
    for the first one.
    """
    width, height = PREVIEW_SIZE
    raw = getattr(stream, "thumbnail_url", "") if stream is not None else ""
    if not raw:
        # get_streams can still be empty in the seconds after the event fires,
        # and the preview path is derivable from the login anyway
        raw = PREVIEW_URL_TEMPLATE
    url = (
        raw.replace("{login}", login)
        .replace("%{width}", str(width))
        .replace("%{height}", str(height))
        .replace("{width}", str(width))
        .replace("{height}", str(height))
    )
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}t={cache_key}"


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
    # looked up while announcing so the offline edit, which runs from a delayed
    # task with nothing to catch its exceptions, needs no helix call of its own
    offline_image_url: str | None = None

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
        streams, user = await asyncio.gather(
            self._client.application.get_streams(user_ids={event.broadcaster.id}),
            self._fetch_user(event.broadcaster.id),
        )
        stream = next(iter(streams), None)

        embed = self._build_live_embed(event, stream, user)
        msg = await self._sender.send_embed(
            self._announce_channel_id, embed, self._ping_role_id
        )
        self._live[login] = LiveState(
            stream_id=event.id,
            message_id=msg.id,
            # empty for channels that never uploaded an offline banner; the
            # offline edit drops the image entirely in that case
            offline_image_url=(user.offline_image_url or None) if user else None,
        )

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
        await self._sender.mark_offline(
            self._announce_channel_id, state.message_id, state.offline_image_url
        )

    async def _fetch_user(self, broadcaster_id: str):
        """Channel profile/offline art, or None if helix won't say.

        Only feeds decoration - the author icon and the offline banner - so a
        failure here must not cost us the announcement itself.
        """
        if self._client.application is None:
            raise RuntimeError("client is not authorized")
        try:
            users = await self._client.application.get_users(user_ids={broadcaster_id})
        except HTTPException:
            _log.warning("could not look up user %s", broadcaster_id, exc_info=True)
            return None
        return next(iter(users), None)

    def _render_going_live(self, event: StreamOnlineEvent) -> str:
        broadcaster = event.broadcaster
        try:
            return self._going_live_text.format(
                name=broadcaster.name,
                login=broadcaster.login,
                url=channel_url(broadcaster.login),
            )
        except (KeyError, IndexError, ValueError, AttributeError):
            # load_config already validated this, so reaching here means the
            # template is odd in a way parsing missed. a plain announcement
            # beats dropping the notification entirely.
            _log.exception("could not render going_live_text, using the default")
            return DEFAULT_GOING_LIVE_TEXT.format(name=broadcaster.name)

    def _build_live_embed(self, event: StreamOnlineEvent, stream, user=None) -> discord.Embed:
        login = event.broadcaster.login
        url = channel_url(login)
        embed = discord.Embed(
            title=stream.title if stream else "Live on Twitch!",
            # makes the title itself the watch link, on top of the explicit one
            # in the field below - the whole embed should be clickable
            url=url,
            description=self._render_going_live(event),
            color=discord.Color.purple(),
        )
        if stream:
            embed.add_field(name="Playing", value=stream.category.name)
        embed.add_field(name="Watch", value=f"[twitch.tv/{login}]({url})")
        embed.set_author(
            name=event.broadcaster.name,
            url=url,
            icon_url=user.profile_image_url if user else None,
        )
        # the capture can lag a minute or two behind the event, so an early
        # announcement may show the tail of the previous broadcast
        embed.set_image(url=_preview_url(login, stream, event.id))
        return embed
