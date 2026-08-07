# Aya Lite

A small Discord bot that posts a notification when the Twitch channels you follow go live, and updates that message once they go offline.

## Features

- **Live announcements** — posts an embed with the stream title and category when a channel goes live
- **Offline updates** — edits the original message rather than posting again, greying the embed and adding an "Offline" footer
- **Blip tolerance** — a 120-second grace period means a brief disconnect doesn't mark the stream offline
- **No duplicate pings** — EventSub delivers at least once, so repeat deliveries are filtered by message ID
- **Reruns ignored** — Twitch fires `stream.online` for reruns, premieres and watch parties; only genuine live broadcasts are announced

## Requirements

- Python 3.13+
- [uv](https://docs.astral.sh/uv/)
- A Twitch application (client ID + secret)
- A Discord bot token

## Setup

### 1. Install

```fish
git clone shikiwoo/AyaLite
cd AyaLite
uv sync
```

### 2. Register a Twitch application

Go to the [Twitch Developer Console](https://dev.twitch.tv/console) and register an application. The OAuth redirect URL isn't used — the bot authenticates with the client-credentials flow — but the console requires one, so `http://localhost:3000` is fine.

Copy the **Client ID** and generate a **Client Secret**.

### 3. Create a Discord bot

In the [Discord Developer Portal](https://discord.com/developers/applications), create an application, add a bot, and copy its token. Invite it to your server with permission to **View Channel**, **Send Messages** and **Embed Links** in the channel you want announcements in.

No privileged intents are required — the bot only talks to the REST API and never opens a gateway connection.

To get the channel ID, enable **Settings → Advanced → Developer Mode** in Discord, then right-click the channel and choose **Copy Channel ID**.

### 4. Configure

Copy both samples and fill them in:

```fish
cp sample.env .env
cp config.toml.sample config.toml
```

`.env` holds the secrets:

```
DISCORD_BOT_TOKEN = ...
TWITCH_CLIENT_ID = ...
TWITCH_CLIENT_SECRET = ...
```

`config.toml` holds everything else:

```toml
announce_channel_id = 123456789012345678

channels = [
    "shikiwoo",
]
```

Both files are gitignored.

## Running

```fish
uv run ayalite
```

or equivalently:

```fish
uv run python -m ayalite
```

Stop it with Ctrl-C.

## How it works

Twitch EventSub is consumed through a **conduit** — a transport that holds your subscriptions independently of any single connection. The bot creates one conduit with a single shard, attaches a WebSocket to it, and subscribes to `stream.online` and `stream.offline` for each configured channel.

The advantage is that subscriptions live on Twitch's side rather than in the process, so they survive restarts. The conduit ID is cached at:

```
~/.local/state/ayalite/conduit_id
```

(or under `$XDG_STATE_HOME` if set). On startup the bot verifies that the stored conduit still exists and reuses it, creating a fresh one only when it's gone. Twitch deletes a conduit after 72 hours with no active shard, so a long shutdown means a rebuild — this is handled automatically.

Deleting that file is safe; the bot simply creates a new conduit. Note that Twitch allows **five conduits per client ID**, so repeatedly losing the file without deleting the old conduits will eventually hit that ceiling.

## Project layout

| File | Responsibility |
| --- | --- |
| `bot.py` | Config loading and startup wiring |
| `twitch_client.py` | Helix auth, login → user ID resolution, conduit management, subscriptions |
| `twitch_events.py` | EventSub handlers, dedup, offline grace period, embed building |
| `twitch_conduit_store.py` | Reads/writes the cached conduit ID |
| `discord_sender.py` | Posting and editing Discord messages |
| `__init__.py` | Entry point and logging setup |

## Logging

Logs go to stdout at INFO. The `twitch` and `discord` loggers are pinned to WARNING because both are extremely noisy below that — raise them in `__init__.py` when debugging connection problems.

## Known gaps

- `resolve_streamer_ids` doesn't chunk requests, so the channel list is capped at 100
- `_mark_offline_after_delay` has no error handling; if editing the Discord message fails, the failure surfaces as an unretrieved asyncio task exception
- An online event for a channel that's already live (with no pending offline task) posts a second announcement and orphans the first message
- `_build_live_embed`'s `stream` parameter is untyped, so its attribute access is unchecked
- `deprecated_modules/` is dead code from earlier iterations
- No tests
