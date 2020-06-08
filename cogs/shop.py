from datetime import datetime, timedelta
from functools import cached_property

import discord
import humanfriendly
from discord.ext import commands, flags

from .database import Database
from .helpers import checks, mongo
from .helpers.constants import *
from .helpers.models import GameData, ItemTrigger, SpeciesNotFoundError


class Shop(commands.Cog):
    """Shop-related commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @property
    def db(self) -> Database:
        return self.bot.get_cog("Database")

    async def balance(self, member: discord.Member):
        member = await self.db.fetch_member(member)
        return member.balance

    @checks.has_started()
    @commands.command(aliases=["balance"])
    async def bal(self, ctx: commands.Context):
        await ctx.send(f"You have {await self.balance(ctx.author)} credits.")

    @commands.command()
    async def shop(self, ctx: commands.Context, *, page: int = 0):
        """View the Pokétwo item shop."""

        member = await self.db.fetch_member(ctx.author)

        embed = discord.Embed()
        embed.color = 0xF44336
        embed.title = f"Pokétwo Shop — {member.balance} credits"

        if page == 0:
            embed.description = "Use `p!shop <page>` to view different pages."

            embed.add_field(name="Page 1", value="XP Boosters", inline=False)
            embed.add_field(name="Page 2", value="Evolution Candies", inline=False)
            embed.add_field(name="Page 3", value="Nature Mints", inline=False)
            embed.add_field(name="Page 4", value="Mega Evolutions", inline=False)

        else:
            embed.description = "We have a variety of items you can buy in the shop. Some will evolve your pokémon, some will change the nature of your pokémon, and some will give you other bonuses. Use `p!buy <item>` to buy an item!"

            items = [i for i in GameData.all_items() if i.page == page]

            for item in items:
                embed.add_field(
                    name=f"{item.name} – {item.cost} credits",
                    value=f"{item.description}",
                    inline=item.inline,
                )

            for i in range(-len(items) % 3):
                embed.add_field(name="‎", value="‎")

        if member.boost_active:
            timespan = member.boost_expires - datetime.now()
            timespan = humanfriendly.format_timespan(timespan.total_seconds())
            embed.set_footer(
                text=f"You have an XP Booster active that expires in {timespan}."
            )

        await ctx.send(embed=embed)

    @commands.command()
    async def buy(self, ctx: commands.Context, *, item: str):
        """Buy an item from the shop."""

        try:
            item = GameData.item_by_name(item)
        except SpeciesNotFoundError:
            return await ctx.send(f"Couldn't find an item called `{item}`.")

        member = await self.db.fetch_member(ctx.author)

        if member.balance < item.cost:
            return await ctx.send("You don't have enough credits for that!")

        if item.action == "evolve_mega":
            if member.selected_pokemon.species.mega is None:
                return await ctx.send(
                    "This item can't be used on your selected pokémon! Please select a different pokémon using `p!select` and try again."
                )

            evoto = member.selected_pokemon.species.mega

        if item.action == "evolve_megax":
            if member.selected_pokemon.species.mega_x is None:
                return await ctx.send(
                    "This item can't be used on your selected pokémon! Please select a different pokémon using `p!select` and try again."
                )

            evoto = member.selected_pokemon.species.mega_x

        if item.action == "evolve_megay":
            if member.selected_pokemon.species.mega_y is None:
                return await ctx.send(
                    "This item can't be used on your selected pokémon! Please select a different pokémon using `p!select` and try again."
                )

            evoto = member.selected_pokemon.species.mega_y

        if item.action == "evolve_normal":

            if member.selected_pokemon.species.evolution_to is not None:
                try:
                    evoto = next(
                        filter(
                            lambda evo: isinstance(evo.trigger, ItemTrigger)
                            and evo.trigger.item == item,
                            member.selected_pokemon.species.evolution_to.items,
                        )
                    ).target
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

        await self.db.update_member(
            ctx.author, {"$inc": {"balance": -item.cost},},
        )

        if "evolve" in item.action:
            embed = discord.Embed()
            embed.color = 0xF44336
            embed.title = f"Congratulations {ctx.author.name}!"

            embed.add_field(
                name=f"Your {member.selected_pokemon.species} is evolving!",
                value=f"Your {member.selected_pokemon.species} has turned into a {evoto}!",
            )

            await self.db.update_pokemon(
                ctx.author,
                member.selected,
                {"$set": {"pokemon.$.species_id": evoto.id}},
            )

            await ctx.send(embed=embed)

        if "xpboost" in item.action:
            mins = int(item.action.split("_")[1])

            await self.db.update_member(
                ctx.author,
                {"$set": {"boost_expires": datetime.now() + timedelta(minutes=mins)},},
            )

        if "nature" in item.action:
            idx = int(item.action.split("_")[1])

            await self.db.update_pokemon(
                ctx.author,
                member.selected,
                {"$set": {"pokemon.$.nature": NATURES[idx]}},
            )

            await ctx.send(
                f"You changed your selected pokémon's nature to {NATURES[idx]}!"
            )
