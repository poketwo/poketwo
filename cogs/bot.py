from functools import cached_property

import discord
from discord.ext import commands, flags

from .database import Database
from .helpers import checks
from .helpers.models import *


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

        if isinstance(error, commands.CheckAnyFailure):
            await ctx.send(error)

        raise error

    @commands.command()
    async def invite(self, ctx: commands.Context):
        """Get the invite link for the bot."""

        await ctx.send(
            "Want to add me to your server? Use the link below!\n\n"
            "Invite Bot: https://discord.com/api/oauth2/authorize?client_id=716390085896962058&permissions=126016&scope=bot\n"
            "Join Server: https://discord.gg/KZe4F4t\n\n"
            "This bot is still in development and has limited functionality. Please report bugs to the server."
        )

    @checks.is_admin()
    @commands.command()
    async def prefix(self, ctx: commands.Context, *, prefix: str):
        """Change the bot prefix."""

        if prefix == "reset":
            guild = self.db.fetch_guild(ctx.guild)
            guild.update(unset__prefix=True)

            return await ctx.send("Reset prefix to `p!` for this server.")

        if len(prefix) > 100:
            return await ctx.send("Prefix must not be longer than 100 characters.")

        guild = self.db.fetch_guild(ctx.guild)
        guild.update(prefix=prefix)

        await ctx.send(f"Changed prefix to `{prefix}` for this server.")

    @commands.is_owner()
    @commands.command()
    async def eval(self, ctx: commands.Context, *, code: str):
        result = eval(code)
        await ctx.send(result)
