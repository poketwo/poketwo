import os

import mongoengine
from discord.ext import commands
from dotenv import load_dotenv
from google.cloud import secretmanager

from cogs import *
from data import load_data

# Setup

load_dotenv()

if os.getenv("ENV") == "prod":
    client = secretmanager.SecretManagerServiceClient()
    parent = client.project_path("poketwo-279018")

    bot_token = client.access_secret_version("bot-token")
    bot_token = bot_token.payload.data.decode("utf-8")

    database_uri = client.access_secret_version("bot-token")
    database_uri = database_uri.payload.data.decode("utf-8")
else:
    bot_token = os.getenv("BOT_TOKEN")
    database_uri = os.getenv("DATABASE_URI")

mongoengine.connect(host=database_uri)

# Instantiate Discord Bot

load_data()

bot = commands.Bot(
    command_prefix=["p!", "P!"],
    help_command=commands.MinimalHelpCommand(),
    case_insensitive=True,
)
bot.add_cog(Bot(bot))
bot.add_cog(Database(bot))
bot.add_cog(Pokedex(bot))
bot.add_cog(Pokemon(bot))
bot.add_cog(Spawning(bot))

# Run Discord Bot

print("Starting bot...")

try:
    bot.run(bot_token)
except KeyboardInterrupt:
    bot.logout()
