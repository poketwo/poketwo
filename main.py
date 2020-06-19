import asyncio
import logging
import os
import subprocess

from discord.ext import commands
from dotenv import load_dotenv

from cogs import *
from cogs.helpers import constants
from data import load_data

# Setup

logging.basicConfig(level=logging.INFO)

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
bot.enabled = False

for cog in ALL_COGS:
    bot.load_extension(f"cogs.{cog}")


@commands.is_owner()
@bot.command()
async def disable(ctx: commands.Context):
    bot.enabled = False
    await ctx.send("Disabling bot...")


@commands.is_owner()
@bot.command()
async def enable(ctx: commands.Context):
    bot.enabled = True
    await ctx.send("Enabling bot...")


@commands.is_owner()
@bot.command()
async def reloadcog(ctx: commands.Context, cog: str):
    bot.reload_extension(f"cogs.{cog}")
    await ctx.send("Disabling bot...")


@commands.is_owner()
@bot.command()
async def reloadall(ctx: commands.Context):
    message = await ctx.send("Reloading all cogs...")
    for cog in ALL_COGS:
        bot.reload_extension(f"cogs.{cog}")
    await message.edit(content="All cogs have been reloaded.")


@bot.event
async def on_message(message: discord.Message):
    message.content = (
        message.content.replace("—", "--")
        .replace("'", "′")
        .replace("‘", "′")
        .replace("’", "′")
    )
    await bot.process_commands(message)


@bot.event
async def on_ready():
    await constants.EMOJIS.init_emojis(bot)
    print(f"Logged in as {bot.user}")
    bot.enabled = True


bot.add_check(checks.enabled(bot))


# Run Discord Bot

print("Starting bot...")

try:
    bot.run(bot_token)
except KeyboardInterrupt:
    bot.logout()
