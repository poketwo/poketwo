from functools import cached_property

import discord
from discord.ext import commands, flags
from mongoengine import DoesNotExist

from .database import Database
from .helpers import checks, mongo
from .helpers.models import GameData, SpeciesNotFoundError
from .helpers.constants import *


class Pokemon(commands.Cog):
    """Pokémon-related commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @cached_property
    def db(self) -> Database:
        return self.bot.get_cog("Database")

    def balance(self, member: discord.Member):
        return self.db.fetch_member(member).balance

    def add_balance(self, member: discord.Member, amount: int):
        self.db.update_member(member, inc__balance=amount)

    def remove_balance(self, member: discord.Member, amount: int):
        self.db.update_member(member, dec__balance=amount)

    @checks.has_started()
    @commands.command(aliases=["balance"])
    async def bal(self, ctx: commands.Context):
        await ctx.send(f"You have {self.balance(ctx.author)} credits.")

    @commands.command()
    async def shop(self, ctx: commands.Context):
        """View the starter pokémon."""

        embed = discord.Embed()
        embed.color = 0xF44336
        embed.title = f"Shop — Balance: {self.balance(ctx.author)}"
        embed.description = (
            "Browse the different pages in the shop using `p!shop <page>`."
        )

        await ctx.send(embed=embed)
