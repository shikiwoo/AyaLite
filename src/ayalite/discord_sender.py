import discord


class DiscordSender:
    def __init__(self, token: str) -> None:
        self._token = token
        self.client = discord.Client(intents=discord.Intents.none())

    async def start(self):
        # login() call to validate the token
        await self.client.login(self._token)

    async def send(self, channel_id: int, content: str) -> discord.Message:
        # send message to channel with the provided ID
        channel = self.client.get_partial_messageable(channel_id)
        return await channel.send(content)

    async def close(self) -> None:
        await self.client.close()

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
