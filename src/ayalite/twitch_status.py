import aiohttp

from ayalite.twitch_token import TokenManager

HELIX_STREAMS = "https://api.twitch.tv/helix/streams"

class TwitchGetter:
    def __init__(self, tokens: TokenManager, session: aiohttp.ClientSession) -> None:
        self.tokens = tokens
        self.session = session

    async def _headers(self) -> dict[str, str]:
        token = await self.tokens.get()
        return {
            "Authorization": f"Bearer {token}",
            "Client-Id": self.tokens.client,
        }

    async def get_live_streams(self, logins: list[str]) -> list[dict]:
        params = [("user_login", name) for name in logins]

        async with self.session.get(HELIX_STREAMS, headers=await self._headers(), params=params) as response:
           
            # if the token gets rejected with a 401, invalidate the current token and try again: 
            if response.status == 401: 
                self.tokens.invalidate()
                return await self._retry(params)

            # reading body before catching the status, so that I can get the error message back 
            body = await response.json()

            # if getting anything but a success or 401
            if response.status != 200: 
                raise RuntimeError(f"helix request failed ({response.status}): {body}")

            return body["data"]

    async def _retry(self, params: list[tuple[str, str]]) -> list[dict]:
        # but shiki, why don't you just loop? 
        # because I need this to run exactly once and fail LOUD if failing instead of constantly polling twitch with invalid credentials
        
        # call headers again with the (hopefully) fresh token
        async with self.session.get(HELIX_STREAMS, headers=await self._headers(), params=params) as response: 
            body = await response.json()

            # no handling 401 because read first comment. this isn't a loop. 
            if response.status != 200: 
                raise RuntimeError(f"helix retry failed ({response.status}): {body}")

            return body["data"]

            