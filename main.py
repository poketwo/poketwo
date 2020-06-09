import os

from discord.ext import commands
from dotenv import load_dotenv
from cogs import *
from data import load_data

# Setup

bot_token = os.getenv("BOT_TOKEN")
env = os.getenv("ENV")


# Instantiate Discord Bot

load_data()


async def determine_prefix(bot, message):
    cog = bot.get_cog("Bot")
    return await cog.determine_prefix(message)


bot = commands.AutoShardedBot(
    command_prefix=determine_prefix, help_command=None, case_insensitive=True,
)
bot.env = env
bot.add_cog(Bot(bot))
bot.add_cog(Database(bot))
bot.add_cog(Pokedex(bot))
bot.add_cog(Pokemon(bot))
bot.add_cog(Shop(bot))
bot.add_cog(Spawning(bot))


@bot.event
async def on_message(message):
    message.content = message.content.replace("—", "--")
    await bot.process_commands(message)


# Run Discord Bot

print("Starting bot...")

try:
    bot.run(bot_token)
except KeyboardInterrupt:
    bot.logout()
