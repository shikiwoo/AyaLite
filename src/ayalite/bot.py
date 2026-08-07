import logging
import os
import random
import tomllib
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from ayalite.discord_sender import DiscordSender
from ayalite.twitch_client import Client
from ayalite.twitch_conduit_store import ConduitStore
from ayalite.twitch_events import EventHandlers

_log = logging.getLogger(__name__)

# anchored outside the cwd so launching from a different directory doesn't
# silently orphan the stored conduit and create a new one (5 per client max)
STATE_DIR = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state")) / "ayalite"
CONDUIT_STORE_PATH = STATE_DIR / "conduit_id"


@dataclass
class Config:
    discord_token: str
    twitch_client_id: str
    twitch_client_secret: str
    announce_channel_id: int
    channels: list[str]


def load_config(config_path: Path = Path("config.toml")) -> Config:
    load_dotenv()

    try:
        with config_path.open("rb") as f:
            toml_data = tomllib.load(f)
    except FileNotFoundError as exc:
        raise RuntimeError(f"config file not found: {config_path}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise RuntimeError(f"could not parse {config_path}: {exc}") from exc

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
    # picked before connecting: the presence goes out with the gateway IDENTIFY
    watching = random.choice(config.channels) if config.channels else None
    sender = DiscordSender(config.discord_token, watching=watching)

    try:
        # validate the discord token before creating any twitch subscriptions
        await sender.start()
        _log.info("presence: watching %s", watching)

        streamer_ids = await helper.resolve_streamer_ids(client, config.channels)

        STATE_DIR.mkdir(parents=True, exist_ok=True)
        store = ConduitStore(CONDUIT_STORE_PATH)
        conduit = await helper.get_conduit(client, store)

        # rebind eventsub to the real conduit id. build_client authorized without
        # one, so client.eventsub currently has conduit_id=None and every
        # subscription would be rejected with a 400 that log-and-continue hides.
        await client.authorize(conduit_id=conduit.id)
        await helper.sub_stream_events(client, streamer_ids)

        handlers = EventHandlers(client, sender, config.announce_channel_id)
        handlers.register()

        _log.info("watching for stream events: %s", ", ".join(streamer_ids))
        await client.connect(conduit.id, shard_ids=(0,))
    finally:
        await sender.close()
        await client.close()