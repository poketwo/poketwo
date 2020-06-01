import os

import mongoengine
from discord.ext import commands
from dotenv import load_dotenv

from cogs import *
from data import load_data

# Setup

load_dotenv()
mongoengine.connect(host=os.getenv("DATABASE_URI"))

# Instantiate Discord Bot

load_data()

bot = commands.Bot(
    command_prefix=os.getenv("COMMAND_PREFIX"),
    help_command=commands.MinimalHelpCommand(),
)
bot.add_cog(Bot(bot))
bot.add_cog(Pokedex(bot))

# Run Discord Bot

print("Starting bot...")

try:
    bot.run(os.getenv("BOT_TOKEN"))
except KeyboardInterrupt:
    bot.logout()
