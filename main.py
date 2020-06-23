import asyncio
import logging
import os
import subprocess
from importlib import reload

import discord
from discord.ext import commands
from dotenv import load_dotenv

import data
import cogs
from cogs.helpers import checks, constants, converters, models, mongo, pagination

# Setup

logging.basicConfig(level=logging.INFO)

bot_token = os.getenv("BOT_TOKEN")
env = os.getenv("ENV")


# Instantiate Discord Bot

data.load_data()


async def determine_prefix(bot, message):
    cog = bot.get_cog("Bot")
    return await cog.determine_prefix(message)


client = commands.AutoShardedBot(
    command_prefix=determine_prefix, help_command=None, case_insensitive=True,
)
client.env = env
client.enabled = False

for cog in cogs.ALL_COGS:
    client.load_extension(f"cogs.{cog}")


# Reloading


async def reload_modules():
    client.enabled = False

    for x in (
        cogs,
        models,
        data,
        mongo,
        checks,
        constants,
        converters,
        pagination,
    ):
        reload(x)

    data.load_data()

    for cog in cogs.ALL_COGS:
        client.reload_extension(f"cogs.{cog}")

    await constants.EMOJIS.init_emojis(client)

    client.enabled = True


@commands.is_owner()
@client.command()
async def disable(ctx: commands.Context):
    client.enabled = False
    await ctx.send("Disabling bot...")


@commands.is_owner()
@client.command()
async def enable(ctx: commands.Context):
    client.enabled = True
    await ctx.send("Enabling bot...")


@commands.is_owner()
@client.command()
async def reloadcog(ctx: commands.Context, cog: str):
    client.reload_extension(f"cogs.{cog}")
    await ctx.send("Disabling bot...")


@commands.is_owner()
@client.command()
async def reloadall(ctx: commands.Context):
    message = await ctx.send("Reloading all modules...")
    await reload_modules()
    await message.edit(content="All modules have been reloaded.")


@client.event
async def on_message(message: discord.Message):
    await client.wait_until_ready()
    message.content = (
        message.content.replace("—", "--")
        .replace("'", "′")
        .replace("‘", "′")
        .replace("’", "′")
    )
    await client.process_commands(message)


@client.event
async def on_ready():
    await constants.EMOJIS.init_emojis(client)
    print(f"Logged in as {client.user}")
    client.enabled = True


client.add_check(checks.enabled(client))


# Run Discord Bot

print("Starting bot...")

try:
    client.run(bot_token)
except KeyboardInterrupt:
    client.logout()
