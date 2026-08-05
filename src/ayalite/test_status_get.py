import asyncio
import os

import aiohttp
from dotenv import load_dotenv

from ayalite.twitch_status import TwitchGetter
from ayalite.twitch_token import TokenManager

import tomllib
from pathlib import Path

# for importing config.toml
def load_config(path: Path) -> dict:
    with path.open("rb") as f:
        return tomllib.load(f)
# would be a good idea to also implement validation in the finished bot

load_dotenv()

CONFIG_PATH = Path(os.getenv("AYALITE_CONFIG", "config.toml"))
CONFIG = load_config(CONFIG_PATH)
CHANNELS = CONFIG["channels"]

async def main():
    async with aiohttp.ClientSession() as session:
        tokens = TokenManager(
            os.environ["TWITCH_CLIENT_ID"],
            os.environ["TWITCH_CLIENT_SECRET"],
            session,
        )
        twitch = TwitchGetter(tokens, session)

        streams = await twitch.get_live_streams(CHANNELS)

        print(f"Asked about {len(CHANNELS)}, {len(streams)} live.")

        for s in streams:
            print(f"{s['user_name']}")
            print(f"  game:    {s['game_name']}")
            print(f"  title:   {s['title']}")
            print(f"  viewers: {s['viewer_count']}")
            print(f"  started: {s['started_at']}\n")

        live = {s["user_login"] for s in streams}
        offline = [c for c in CHANNELS if c.lower() not in live]
        print(f"offline: {offline}")

asyncio.run(main())
