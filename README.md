# Aya Lite 
discord bot for twitch notifs

# TODO 
- build Helix polling for when a channel goes live
- build database or a json for storing channels to monitor and channels to send events into 
- deduplication for when a channel goes offline for a short period of time (<120s)

# current functionality 
- check Twitch API for the token and store it
- query Twitch API for channel(s) and report the findings back to the user 

# planned features
- check if a channel is live and send a message in a discord channel when it does go live
- give users an embed that shows the current stream title and game
- edit the message to "was live" once the channel goes offline
