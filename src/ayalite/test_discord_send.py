import asyncio
import os
import tomllib
from pathlib import Path

from dotenv import load_dotenv

from ayalite.discord_sender import DiscordSender

load_dotenv()

def load_config(path: Path) -> dict:
    with path.open("rb") as f:
        return tomllib.load(f)

CONFIG_PATH = Path(os.getenv("AYALITE CONFIG", "config.toml"))
CONFIG = load_config(CONFIG_PATH)

async def main():
    sender = DiscordSender(os.environ["DISCORD_BOT_TOKEN"])
    await sender.start()

    channel_id = CONFIG["announce_channel_id"]
    message = await sender.send(channel_id, "AyaLite test message - Discord sending works!")
    print(f"Sent message to channel ID {channel_id}")

    await sender.close()

asyncio.run(main())
