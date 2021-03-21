# VTuber Discord Bot
Track VTuber live stream and post it on Discord!
Utilize the [ihateani.me v2 API](https://api.ihateani.me/v2/graphql)

## Requirements
- Python 3.6+
- Discord Bot Token
- A Discord Server with Channels Setup

## Configuration
Rename `config.json.example` to `config.json`
```json
{
    "bot_token": "your.bot.token",
    "channels": {
        "holo": null,
        "niji": null,
        "other": null
    },
    "ignore": {
        "groups": []
    }
}
```
Register your bot and put it in `bot_token` variable<br>
Get the Text Channels IDs for every groups and put it in the `channels` part.<br>
You can ignore it by just setting it to `null`

Then if you want no groups in the channels, put the `group` key from the API and put it in the `groups` list.

To get list of groups, you can do a `groups` fetch to the GraphQL API on the explorer here: [GraphQL Explorer](https://api.ihateani.me/v2/graphql)<br>
Then put this GraphQL Query and press `Send Request`
```graphql
query VTuberGroups {
  vtuber {
    groups {
      items
    }
  }
}
```

## Run
1. Create a virtual environment for your bot
2. Use the virtualenv by typing `source your_env/bin/activate` on Linux
3. Run `pip install -r requirements.txt`
4. Config your bot in [Configuration](#configuration)
5. Run by `python bot.py`
6. After the bot up and running, run this command on discord ONLY ONCE: `vt!initialize`
7. Enjoy!

## License
MIT License