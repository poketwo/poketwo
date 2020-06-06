import os

import mongoengine
from discord.ext import commands
from dotenv import load_dotenv

from cogs import *
from data import load_data

# Setup

load_dotenv()
bot_token = os.getenv("BOT_TOKEN")
database_uri = os.getenv("DATABASE_URI")
env = os.getenv("ENV")

mongoengine.connect(host=database_uri)

# Instantiate Discord Bot

load_data()


async def determine_prefix(bot, message):
    cog = bot.get_cog("Bot")

    if message.guild.id not in cog.prefixes:
        print("query")
        try:
            guild = mongo.Guild.objects.get(id=message.guild.id)
        except mongoengine.DoesNotExist:
            guild = mongo.Guild.objects.create(id=message.guild.id)

        cog.prefixes[message.guild.id] = guild.prefix

    return cog.prefixes[message.guild.id] or ["p!", "P!"]


bot = commands.Bot(
    command_prefix=determine_prefix,
    help_command=commands.MinimalHelpCommand(),
    case_insensitive=True,
)
bot.env = env
bot.add_cog(Bot(bot))
bot.add_cog(Database(bot))
bot.add_cog(Pokedex(bot))
bot.add_cog(Pokemon(bot))
bot.add_cog(Shop(bot))
bot.add_cog(Spawning(bot))

# Run Discord Bot

print("Starting bot...")

try:
    bot.run(bot_token)
except KeyboardInterrupt:
    bot.logout()
