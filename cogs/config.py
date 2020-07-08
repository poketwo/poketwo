import typing
import asyncio
import math
import random

import discord
from discord.ext import commands, flags

from .database import Database
from helpers import checks, constants, converters, models, mongo, pagination


def setup(bot: commands.Bot):
    bot.add_cog(Configuration(bot))


class Configuration(commands.Cog):
    """Configuration commands to change bot behavior."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @property
    def db(self) -> Database:
        return self.bot.get_cog("Database")

    @checks.is_admin()
    @commands.command()
    async def prefix(self, ctx: commands.Context, *, prefix: str = None):
        """Change the bot prefix."""

        if prefix is None:
            current = await self.bot.get_cog("Bot").determine_prefix(ctx.message)
            if type(current) == list:
                current = current[0]
            return await ctx.send(f"My prefix is `{current}` in this server.")

        if prefix == "reset" or prefix == "p!":
            await self.db.update_guild(ctx.guild, {"$set": {"prefix": None}})
            self.bot.prefixes[ctx.guild.id] = None

            return await ctx.send("Reset prefix to `p!` for this server.")

        if len(prefix) > 100:
            return await ctx.send("Prefix must not be longer than 100 characters.")

        await self.db.update_guild(ctx.guild, {"$set": {"prefix": prefix}})
        self.bot.prefixes[ctx.guild.id] = prefix

        await ctx.send(f"Changed prefix to `{prefix}` for this server.")

    @checks.has_started()
    @commands.command()
    async def silence(self, ctx: commands.Context):
        """Silence level up messages for yourself."""

        member = await self.db.fetch_member_info(ctx.author)

        await self.db.update_member(
            ctx.author, {"$set": {"silence": not member.silence}}
        )

        if member.silence:
            await ctx.send(f"Reverting to normal level up behavior.")
        else:
            await ctx.send(
                f"I'll no longer send level up messages. You'll receive a DM when your pokémon evolves or reaches level 100."
            )

    @checks.is_admin()
    @commands.command()
    async def serversilence(self, ctx: commands.Context):
        """Silence level up messages server-wide."""

        guild = await self.db.fetch_guild(ctx.guild)

        await self.db.update_guild(ctx.guild, {"$set": {"silence": not guild.silence}})

        if guild.silence:
            await ctx.send(f"Level up messages are no longer disabled in this server.")
        else:
            await ctx.send(
                f"Disabled level up messages in this server. I'll send a DM when pokémon evolve or reach level 100."
            )

    @checks.is_admin()
    @commands.command()
    async def redirect(
        self, ctx: commands.Context, *, channel: typing.Union[discord.TextChannel, str]
    ):
        """Redirect pokémon catches to one channel."""

        if channel == "reset":
            id = None
            await ctx.send(f"No longer redirecting spawns.")
        elif type(channel) == str:
            return await ctx.send("That's not a valid option!")
        else:
            id = channel.id
            await ctx.send(f"Now redirecting all pokémon spawns to {channel.mention}")

        await self.db.update_guild(ctx.guild, {"$set": {"channel": id}})
