from datetime import datetime
from functools import cached_property

import discord
from discord.ext import commands, flags
from mongoengine import DoesNotExist

from .database import Database
from .helpers import checks, mongo
from .helpers.constants import *
from .helpers.models import GameData, ItemTrigger, SpeciesNotFoundError

from datetime import datetime, timedelta


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
    async def shop(self, ctx: commands.Context, *, page: int = 0):
        """View the Pokétwo item shop."""

        embed = discord.Embed()
        embed.color = 0xF44336
        embed.title = f"Pokétwo Shop — {self.balance(ctx.author)} credits"

        if page == 0:
            embed.description = "Use `p!shop <page>` to view different pages."

            embed.add_field(name="Page 1", value="XP Boosters", inline=False)
            embed.add_field(name="Page 2", value="Evolution Candies", inline=False)
            embed.add_field(name="Page 3", value="Nature Mints", inline=False)

        else:
            embed.description = "We have a variety of items you can buy in the shop. Some will evolve your pokémon, some will change the nature of your pokémon, and some will give you other bonuses. Use `p!buy <item>` to buy an item!"

            items = [i for i in GameData.all_items() if i.page == page]

            for item in items:
                embed.add_field(
                    name=f"{item.name} – {item.cost} credits",
                    value=f"{item.description}",
                )

            for i in range(-len(items) % 3):
                embed.add_field(name="‎", value="‎")

        await ctx.send(embed=embed)

    @commands.command()
    async def buy(self, ctx: commands.Context, *, item: str):
        """Buy an item from the shop."""

        try:
            item = GameData.item_by_name(item)
        except SpeciesNotFoundError:
            return await ctx.send(f"Couldn't find an item called `{item}`.")

        member = self.db.fetch_member(ctx.author)

        if member.balance < item.cost:
            return await ctx.send("You don't have enough credits for that!")

        if item.action == "evolve":

            if member.selected_pokemon.species.evolution_to is not None:
                try:
                    evoto = next(
                        filter(
                            lambda evo: isinstance(evo.trigger, ItemTrigger)
                            and evo.trigger.item == item,
                            member.selected_pokemon.species.evolution_to.items,
                        )
                    )
                except StopIteration:
                    return await ctx.send(
                        "This item can't be used on your selected pokémon! Please select a different pokémon using `p!select` and try again."
                    )
            else:
                return await ctx.send(
                    "This item can't be used on your selected pokémon! Please select a different pokémon using `p!select` and try again."
                )

        if "xpboost" in item.action:
            if member.boost_active:
                return await ctx.send(
                    "You already have an XP booster active! Please wait for it to expire before purchasing another one."
                )

            await ctx.send(f"You purchased {item.name}!")
        else:
            await ctx.send(
                f"You purchased a {item.name} for your {member.selected_pokemon.species}!"
            )

        member.balance -= item.cost
        member.save()

        if item.action == "evolve":
            embed = discord.Embed()
            embed.color = 0xF44336
            embed.title = f"Congratulations {ctx.author.name}!"

            embed.add_field(
                name=f"Your {member.selected_pokemon.species} is evolving!",
                value=f"Your {member.selected_pokemon.species} has turned into a {evoto.target}!",
            )
            member.selected_pokemon.species_id = evoto.target_id
            member.save()

            await ctx.send(embed=embed)

        if "xpboost" in item.action:
            mins = int(item.action.split("_")[1])
            member.boost_expires = datetime.now() + timedelta(minutes=mins)
            member.save()

        if "nature" in item.action:
            idx = int(item.action.split("_")[1])

            member.selected_pokemon.nature = NATURES[idx]
            member.save()

            await ctx.send(
                f"You changed your selected pokémon's nature to {NATURES[idx]}!"
            )
