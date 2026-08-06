import time

TOKEN_URL = "https://id.twitch.tv/oauth2/token"

class TokenManager:
    def __init__(self, client_id, client_secret, session) -> None:
        self.client = client_id
        self._secret = client_secret
        self.session = session
        self._token = None
        self._expiry = 0

    async def get(self) -> str | None:
        if self._token is None or time.monotonic() > self._expiry:
            await self._fetch()
        return self._token

    async def _fetch(self) -> None:
        payload = {
            "client_id": self.client,
            "client_secret": self._secret,
            "grant_type": "client_credentials",
        }

        async with self.session.post(TOKEN_URL, data=payload) as response:
            body = await response.json()

            # if I get anything but a successful request, raise an error with the contents of the response
            if response.status != 200:
                raise RuntimeError(f"token request failed ({response.status}): {body}")

            # parse the response. subtract 300 seconds from the expiry to make sure the token is always valid.
            self._token = body["access_token"]
            self._expiry = time.monotonic() + body["expires_in"] - 300

    def invalidate(self):
        self._token = None
