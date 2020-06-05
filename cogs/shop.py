from functools import cached_property

import discord
from discord.ext import commands, flags
from mongoengine import DoesNotExist

from .database import Database
from .helpers import checks, mongo
from .helpers.models import GameData, SpeciesNotFoundError
from .helpers.constants import *


class Shop(commands.Cog):
    """Shop-related commands."""

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
        embed.title = f"Pokétwo Shop — {self.balance(ctx.author)} credits"
        embed.description = "Use `p!buy <item>` to buy an item!"

        for item in GameData.all_items():
            embed.add_field(name=item.name, value=f"{item.cost} credits")

        await ctx.send(embed=embed)

    @commands.command()
    async def buy(self, ctx: commands.Context, *, item: str):
        """View the starter pokémon."""

        try:
            item = GameData.item_by_name(item)
        except SpeciesNotFoundError:
            return await ctx.send(f"Couldn't find an item called `{item}`.")

        member = self.db.fetch_member(ctx.author)

        if member.balance < item.cost:
            return await ctx.send("You don't have enough credits for that!")

        if (
            member.selected_pokemon.species.evolution_to is None
            or member.selected_pokemon.species.evolution_to.trigger.item != item
        ):
            return await ctx.send(
                "This item can't be used on your selected pokémon! Please select a different pokémon using `p!select` and try again."
            )

        # embed = discord.Embed()
        # embed.color = 0xF44336
        # embed.title = f"Pokétwo Shop — {self.balance(ctx.author)} credits"
        # embed.description = "Use `p!buy <item>` to buy an item!"

        # for item in GameData.all_items():
        #     embed.add_field(name=item.name, value=f"{item.cost} credits")

        # await ctx.send(embed=embed)
