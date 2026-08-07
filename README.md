# Aya Lite 
discord bot for twitch notifs

# TODO 
- 
- deduplication for when a channel goes offline for a short period of time (<120s)

# current functionality 
- twitch client: authorizes against the Helix API and resolves channel logins to user IDs (twitch_client.py)
- discord sender: logs in with the bot token and can send a message to a channel by ID (discord_sender.py)
- conduit store: persists a Twitch EventSub conduit ID to disk (twitch_conduit_store.py)

# planned features
- check if a channel is live and send a message in a discord channel when it does go live
- give users an embed that shows the current stream title and game
- edit the message to "was live" once the channel goes offline
- make sure that short offline blips don't show up as offline
