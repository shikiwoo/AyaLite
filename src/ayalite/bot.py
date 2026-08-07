import logging
import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from ayalite.discord_sender import DiscordSender
from ayalite.twitch_client import Client
from ayalite.twitch_conduit_store import ConduitStore
from ayalite.twitch_events import EventHandlers

_log = logging.getLogger(__name__)

CONDUIT_STORE_PATH = Path(".conduit_id")


@dataclass
class Config:
    discord_token: str
    twitch_client_id: str
    twitch_client_secret: str
    announce_channel_id: int
    channels: list[str]


def load_config(config_path: Path = Path("config.toml")) -> Config:
    load_dotenv()

    with config_path.open("rb") as f:
        toml_data = tomllib.load(f)

    try:
        return Config(
            discord_token=os.environ["DISCORD_BOT_TOKEN"],
            twitch_client_id=os.environ["TWITCH_CLIENT_ID"],
            twitch_client_secret=os.environ["TWITCH_CLIENT_SECRET"],
            announce_channel_id=int(toml_data["announce_channel_id"]),
            channels=list(toml_data["channels"]),
        )
    except KeyError as exc:
        raise RuntimeError(f"missing required config value: {exc}") from exc

async def run() -> None:
    config = load_config()

    helper = Client()
    client = await helper.build_client(config.twitch_client_id, config.twitch_client_secret)
    streamer_ids = await helper.resolve_streamer_ids(client, config.channels)

    store = ConduitStore(CONDUIT_STORE_PATH)
    conduit = await helper.get_conduit(client, store)
    await helper.sub_stream_events(client, streamer_ids)

    sender = DiscordSender(config.discord_token)
    await sender.start()

    handlers = EventHandlers(client, sender, config.announce_channel_id)
    handlers.register()

    _log.info("watching for stream events: %s", ", ".join(streamer_ids))
    try:
        await client.connect(conduit.id, shard_ids=(0,))
    finally:
        await sender.close()
        await client.close()