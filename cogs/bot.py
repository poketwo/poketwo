from functools import cached_property

import discord
from discord.ext import commands, flags

from .database import Database
from .helpers import checks


class Bot(commands.Cog):
    """For basic bot operation."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @cached_property
    def db(self) -> Database:
        return self.bot.get_cog("Database")

    @commands.Cog.listener()
    async def on_ready(self):
        print(f"Logged in as {self.bot.user}")

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send_help(ctx.command)

        if isinstance(error, checks.MustHaveStarted):
            await ctx.send(
                "Please pick a starter pokémon by typing `p!start` before using this command!"
            )

        if isinstance(error, flags.ArgumentParsingError):
            await ctx.send(error)

        raise error
