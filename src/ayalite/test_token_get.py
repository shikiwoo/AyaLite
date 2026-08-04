import asyncio
import os

import aiohttp
from dotenv import load_dotenv

from ayalite.twitch_token import TokenManager

load_dotenv()

async def main():
    async with aiohttp.ClientSession() as session:
        tokens = TokenManager(
            os.environ["TWITCH_CLIENT_ID"],
            os.environ["TWITCH_CLIENT_SECRET"],
            session,
        )
        token = await tokens.get()
        print(f"got token: {token[:8]}... (len {len(token)})")

        # second call to check if the caching works
        again = await tokens.get()
        print(f"cached: {token == again}")

asyncio.run(main())
