import asyncio
import logging
from collections import deque
from dataclasses import dataclass

import discord
from twitch.eventsub import ClientApp, Event, StreamOfflineEvent, StreamOnlineEvent

from ayalite.discord_sender import DiscordSender

_log = logging.getLogger(__name__)

OFFLINE_GRACE_PERIOD = 120 # seconds, blip window of 2min

@dataclass
class LiveState:
    stream_id: str
    message_id: int
    offline_task: asyncio.Task | None = None

class EventHandlers:
    def __init__(self, client: ClientApp, sender: DiscordSender, announce_channel_id: int) -> None:
        self._client = client
        self._sender = sender
        self._announce_channel_id = announce_channel_id
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
        msg = await self._sender.send_embed(self._announce_channel_id, embed)
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

    @staticmethod
    def _build_live_embed(event: StreamOnlineEvent, stream) -> discord.Embed:
        embed = discord.Embed(
            title=stream.title if stream else "Live on Twitch!",
            description=f"{event.broadcaster.name} is now live!",
            color=discord.Color.purple(),
        )
        if stream:
            embed.add_field(name="Playing", value=stream.category.name)
        embed.set_author(name=event.broadcaster.name)
        return embed
