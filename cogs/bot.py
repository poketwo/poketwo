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
