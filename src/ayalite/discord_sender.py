import asyncio
import logging

import discord

_log = logging.getLogger(__name__)


class DiscordSender:
    def __init__(self, token: str, watching: str | None = None) -> None:
        self._token = token
        self._gateway_task: asyncio.Task[None] | None = None
        # the activity rides along with the gateway IDENTIFY, so it has to be
        # decided before we connect rather than pushed afterwards
        activity = (
            discord.Activity(type=discord.ActivityType.watching, name=watching)
            if watching is not None
            else None
        )
        self.client = discord.Client(
            intents=discord.Intents.none(),
            activity=activity,
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

    async def send(self, channel_id: int, content: str) -> discord.Message:
        # send message to channel with the provided ID
        channel = self.client.get_partial_messageable(channel_id)
        return await channel.send(content)

    async def close(self) -> None:
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
