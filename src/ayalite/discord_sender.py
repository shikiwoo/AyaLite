import asyncio
import logging
import random
from collections.abc import Iterator, Sequence
from contextlib import suppress

import discord

_log = logging.getLogger(__name__)

# shutdown is often already running under a cancelled task; don't let a wedged
# socket hold the process open waiting on a presence frame nobody will read
PRESENCE_TIMEOUT = 5.0

PRESENCE_ROTATE_INTERVAL = 20 * 60  # seconds


def _watching(name: str) -> discord.Activity:
    return discord.Activity(type=discord.ActivityType.watching, name=name)


def _rotation(names: Sequence[str]) -> Iterator[str]:
    """Yield names in a shuffled order, reshuffling after every full pass.

    Picking independently at random each time would repeat the same streamer
    back to back often enough to look stuck, and would starve the tail of a
    long list. A reshuffled pass gives everyone equal airtime.
    """
    pool = list(names)
    previous: str | None = None
    while True:
        random.shuffle(pool)
        if len(pool) > 1 and pool[0] == previous:
            # ...and don't repeat across the seam between two passes either
            pool.append(pool.pop(0))
        yield from pool
        previous = pool[-1]


class DiscordSender:
    def __init__(self, token: str, watching: Sequence[str] = ()) -> None:
        self._token = token
        self._gateway_task: asyncio.Task[None] | None = None
        self._rotate_task: asyncio.Task[None] | None = None
        self._names = tuple(watching)
        self._rotation = _rotation(self._names) if self._names else None

        # the activity rides along with the gateway IDENTIFY, so the first pick
        # has to be made before we connect rather than pushed afterwards
        self.current = next(self._rotation) if self._rotation else None
        self.client = discord.Client(
            intents=discord.Intents.none(),
            activity=_watching(self.current) if self.current else None,
            status=discord.Status.online,
        )

    async def start(self):
        # login() call to validate the token
        await self.client.login(self._token)

        # presence only exists over the gateway - a REST login alone leaves the
        # bot showing as offline - so keep the websocket alive in the background
        # for as long as the bot runs. connect() never returns on its own.
        self._gateway_task = asyncio.create_task(self.client.connect(reconnect=True))

        ready = asyncio.ensure_future(self.client.wait_until_ready())
        done, _ = await asyncio.wait(
            (ready, self._gateway_task), return_when=asyncio.FIRST_COMPLETED
        )
        if self._gateway_task in done:
            # connect() only finishes when the session is unrecoverable; raise
            # that here instead of waiting on a ready that will never fire
            ready.cancel()
            self._gateway_task.result()  # re-raises if it failed
            raise RuntimeError("discord gateway closed before the client was ready")

        _log.info("presence: watching %s", self.current)
        # nothing to rotate through with a single channel - the status would
        # just be rewritten with the name it already has
        if len(self._names) > 1:
            self._rotate_task = asyncio.create_task(self._rotate_presence())

    async def _rotate_presence(self) -> None:
        assert self._rotation is not None
        while True:
            await asyncio.sleep(PRESENCE_ROTATE_INTERVAL)
            name = next(self._rotation)
            activity = _watching(name)
            try:
                await self.client.change_presence(activity=activity)
            except (OSError, discord.DiscordException):
                # the next tick will try again; a reconnect in the meantime
                # re-sends whatever presence is on the client
                _log.warning("could not rotate presence to %s", name, exc_info=True)
                continue

            # change_presence only touches the live socket. the reconnect
            # IDENTIFY reads client.activity, so without this a dropped gateway
            # would silently revert the status to the one picked at startup.
            self.client.activity = activity
            self.current = name
            _log.info("presence: watching %s", name)

    async def send(self, channel_id: int, content: str) -> discord.Message:
        # send message to channel with the provided ID
        channel = self.client.get_partial_messageable(channel_id)
        return await channel.send(content)

    async def close(self) -> None:
        # stop rotating first, so it can't push a fresh "watching" frame in
        # between the offline push below and the socket actually closing
        rotate, self._rotate_task = self._rotate_task, None
        if rotate is not None:
            rotate.cancel()
            with suppress(asyncio.CancelledError):
                await rotate

        # go offline while the socket is still up. closing the gateway cleanly
        # gets there on its own, but the explicit push is immediate rather than
        # leaving a ghost "online" bot until discord times the session out
        if self.client.is_ready():
            try:
                await asyncio.wait_for(
                    self.client.change_presence(status=discord.Status.offline),
                    timeout=PRESENCE_TIMEOUT,
                )
            except (TimeoutError, OSError, discord.DiscordException):
                _log.warning("could not clear presence before shutdown", exc_info=True)

        await self.client.close()  # makes connect() unwind

        task, self._gateway_task = self._gateway_task, None
        if task is None:
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        except Exception:
            # close() runs from a finally block, so never let gateway teardown
            # mask whatever actually brought the bot down
            _log.exception("discord gateway failed during shutdown")

    async def send_embed(self, channel_id: int, embed: discord.Embed) -> discord.Message:
        channel = self.client.get_partial_messageable(channel_id)
        return await channel.send(embed=embed)

    async def mark_offline(self, channel_id: int, message_id: int) -> None:
        channel = self.client.get_partial_messageable(channel_id)
        # need the full Message here (not a PartialMessage) so we can read its
        # existing embed back and mutate it, rather than rebuilding from scratch
        message = await channel.fetch_message(message_id)
        embed = message.embeds[0]
        embed.color = discord.Color.greyple()  # dim it
        embed.set_footer(text="Offline")
        await message.edit(embed=embed)
