import asyncio
import logging
import os
import subprocess
from importlib import reload
from itertools import chain

import discord
from discord.ext import commands
from dotenv import load_dotenv

import cogs
import data
import helpers

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
    command_prefix=determine_prefix, case_insensitive=True,
)
client.env = env
client.enabled = False

client.load_extension("jishaku")


for i in dir(cogs):
    if not i.startswith("_"):
        client.load_extension(f"cogs.{i}")


# Reloading


async def reload_modules():
    client.enabled = False

    reload(cogs)
    reload(helpers)

    for i in dir(helpers):
        if not i.startswith("_"):
            reload(getattr(helpers, i))

    data.load_data()

    for i in dir(cogs):
        if not i.startswith("_"):
            client.reload_extension(f"cogs.{i}")

    await helpers.constants.EMOJIS.init_emojis(client)

    client.enabled = True


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


client.add_check(helpers.checks.enabled(client))


# Run Discord Bot

print("Starting bot...")

try:

    async def do_tasks():
        await client.wait_until_ready()
        await helpers.constants.EMOJIS.init_emojis(client)
        print(f"Logged in as {client.user}")
        client.enabled = True

    client.loop.create_task(do_tasks())
    client.run(bot_token)

except KeyboardInterrupt:
    client.logout()
