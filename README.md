# Aya Lite

A small Discord bot that posts a notification when the Twitch channels you follow go live, and updates that message once they go offline.

## Features

- **Live announcements** — posts an embed with the stream title, category, a watch link and a preview of the stream when a channel goes live
- **Offline updates** — edits the original message rather than posting again, greying the embed, adding an "Offline" footer and swapping the preview for the channel's offline banner
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

No privileged intents are required — the bot connects with none of them enabled. It does hold a gateway connection open for the whole run, but only to keep its "watching" presence alive; announcements themselves are posted and edited over the REST API.

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

### The announcement lifecycle

`stream.online` carries only the broadcaster and a stream ID, so the announcement fills in the rest with two Helix calls made in parallel:

| Call | Supplies |
| --- | --- |
| `get_streams` | Stream title, category, preview URL |
| `get_users` | Profile picture for the embed author, offline banner for later |

Only the first is load-bearing. If `get_users` fails the announcement still goes out, just without the avatar and with no banner to swap in afterwards.

The embed links to the channel in three places — the title, the author name, and an explicit **Watch** field — and carries a full-size preview of the stream as its image.

The offline banner is fetched up front and kept in `LiveState` rather than looked up when the stream ends, because the offline edit runs from a delayed task where a raised exception has nothing to catch it. When the grace period elapses, the embed is greyed, footed with "Offline", and its live preview replaced by that banner. Channels that never uploaded one have the image removed instead — a frozen frame of a finished stream reads as though the channel is still live.

#### Why the preview URL has a `?t=` on the end

Twitch serves every channel's preview from one permanent URL, and Discord's image proxy caches by URL. Without something unique appended, every announcement after the first would show the frame Discord cached for the first one. The stream ID is used, so it's unique per broadcast but stable if the same announcement is rendered twice.

The offline banner gets no such parameter — it's genuinely the same image every time, so caching it is the desirable behavior.

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
- `_build_live_embed`'s `stream` and `user` parameters are untyped, so their attribute access is unchecked
- Twitch's stream preview can lag a minute or two behind the `stream.online` event, so an announcement may briefly show a frame from the end of the previous broadcast
- Channels with no offline banner uploaded lose their image entirely when the embed is marked offline
- `deprecated_modules/` is dead code from earlier iterations
- No tests
- last stretch was vibe coded

## Use of AI in this project
I'm by no means a developer, and I do not claim any expertise in development. Hence, why I've been relying a lot on Claude to review files for me, and in the last stretch (entirety of bot.py and most of twitch_events were vibe coded. I just wanted to get this over with, as I was getting quite burnt out from this. 
