import logging

from twitch import HTTPException, Unauthorized
from twitch.eventsub import ClientApp
from twitch.models import Conduit, Subscription

from ayalite.twitch_conduit_store import ConduitStore

_log = logging.getLogger(__name__)

class Client:
    def __init__(self):
        pass

    async def build_client(self, client_id: str, client_secret: str) -> ClientApp:
        client = ClientApp(client_id, client_secret, ignore_conflict=True)
        await client.authorize()
        return client

    async def resolve_streamer_ids(self, client: ClientApp, logins: list[str]) -> dict[str, str]:
        if client.application is None:
            raise RuntimeError("client is not authorized - call build_client first!!")

        users_info = await client.application.get_users(user_logins=set(logins))
        resolved = {u.identity.login: u.identity.id for u in users_info}
        # missing = set(logins) - resolved.keys()

        return resolved

    async def get_conduit(self, client: ClientApp, store: ConduitStore, shard_count: int = 1) -> Conduit:
        if client.application is None:
            raise RuntimeError("client is not authorized - call build_client first!!")

        app = client.application
        stored = store.read_id()

        if stored is not None:
            existing = await app.get_conduits()
            match = next((c for c in existing if c.id == stored), None)

            if match is not None:
                if match.shard_count != shard_count:
                    return await app.update_conduit(match.id, shard_count=shard_count)
                return match

        # no stored id, or the stored one no longer exists on Twitch
        conduit = await app.create_conduit(shard_count)
        store.save_id(conduit.id)
        return conduit

    async def sub_stream_events(self, client: ClientApp, streamer_ids: dict[str, str]) -> None:
        subscribe_to = (client.eventsub.stream_online, client.eventsub.stream_offline)

        created: list[Subscription] = []
        for login, streamer_id in streamer_ids.items():
            for subscribe in subscribe_to:
                try:
                    created.append(await subscribe(streamer_id))
                except Unauthorized:
                    raise 
                except HTTPException:
                    _log.exception("%s failed for %s", subscribe.__name__, login)
        return tuple(created)
