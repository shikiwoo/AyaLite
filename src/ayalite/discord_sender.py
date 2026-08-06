import discord


class DiscordSender:
    def __init__(self, token: str) -> None:
        self._token = token
        self.client = discord_py.Client(intents=discord_py.Intents.none())

    async def start(self):
        # login() call to validate the token
        await self.client.login(self._token)

    async def send(self, channel_id: int, content: str) -> discord_py.Message:
        # send message to channel with the provided ID
        channel = self.client.get_partial_messageable(channel_id)
        return await channel.send(content)

    async def close(self) -> None:
        await self.client.close()
