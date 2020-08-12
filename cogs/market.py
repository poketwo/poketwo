import math

import discord
from discord.ext import commands, flags
from umongo import fields

from helpers import checks, constants, converters, models, mongo, pagination

from .database import Database


class Market(commands.Cog):
    """A marketplace to buy and sell pokémon."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @property
    def db(self) -> Database:
        return self.bot.get_cog("Database")

    # Filter
    @flags.add_flag("page", nargs="?", type=int, default=1)
    @flags.add_flag("--shiny", action="store_true")
    @flags.add_flag("--alolan", action="store_true")
    @flags.add_flag("--mythical", action="store_true")
    @flags.add_flag("--legendary", action="store_true")
    @flags.add_flag("--ub", action="store_true")
    @flags.add_flag("--mega", action="store_true")
    @flags.add_flag("--name", "--n", nargs="+", action="append")
    @flags.add_flag("--type", type=str, action="append")

    # IV
    @flags.add_flag("--level", nargs="+", action="append")
    @flags.add_flag("--hpiv", nargs="+", action="append")
    @flags.add_flag("--atkiv", nargs="+", action="append")
    @flags.add_flag("--defiv", nargs="+", action="append")
    @flags.add_flag("--spatkiv", nargs="+", action="append")
    @flags.add_flag("--spdefiv", nargs="+", action="append")
    @flags.add_flag("--spdiv", nargs="+", action="append")
    @flags.add_flag("--iv", nargs="+", action="append")

    # Skip/limit
    @flags.add_flag("--skip", type=int)
    @flags.add_flag("--limit", type=int)

    # Market
    @flags.add_flag("--mine", action="store_true")
    @checks.has_started()
    @flags.group(invoke_without_command=True)
    @commands.bot_has_permissions(manage_messages=True)
    async def market(self, ctx: commands.Context, **flags):
        """View or filter the pokémon in your collection."""

        if flags["page"] < 1:
            return await ctx.send("Page must be positive!")

        member = await self.db.fetch_member_info(ctx.author)

        aggregations = await self.bot.get_cog("Pokemon").create_filter(flags, ctx)

        if aggregations is None:
            return

        # Filter pokemon

        fixed_pokemon = False

        async def fix_pokemon():
            # TODO This is janky way of removing bad database entries, I should fix this

            nonlocal fixed_pokemon

            if fixed_pokemon:
                return

            await self.db.update_member(
                ctx.author, {"$pull": {f"pokemon": {"species_id": {"$exists": False}}}},
            )
            await self.db.update_member(ctx.author, {"$pull": {f"pokemon": None}})

            fixed_pokemon = True

        def nick(p):
            name = str(p.species)

            if p.shiny:
                name += " ✨"

            return name

        num = await self.db.fetch_market_count(aggregations=aggregations)

        if num == 0:
            return await ctx.send("Found no pokémon matching this search.")

        async def get_page(pidx, clear):

            pgstart = pidx * 20
            pokemon = await self.db.fetch_market_list(
                pgstart, 20, aggregations=aggregations
            )

            pokemon = [
                (mongo.Pokemon.build_from_mongo(x["pokemon"]), x["_id"], x["price"])
                for x in pokemon
            ]

            if len(pokemon) == 0:
                return await clear("There are no pokémon on this page!")

            page = [
                f"`{id}`　**L{p.level} {nick(p)}**　•　{p.iv_percentage:.2%}　•　**{price:,} pc**"
                for p, id, price in pokemon
            ]

            # Send embed

            embed = discord.Embed()
            embed.color = 0xF44336
            embed.title = f"Market"
            embed.description = "\n".join(page)[:2048]

            embed.set_footer(
                text=f"Showing {pgstart + 1}–{min(pgstart + 20, num)} out of {num}."
            )

            return embed

        paginator = pagination.Paginator(get_page, num_pages=math.ceil(num / 20))
        await paginator.send(self.bot, ctx, flags["page"] - 1)

    @market.command(aliases=["list"])
    async def add(self, ctx: commands.Context, pokemon: converters.Pokemon, price: int):
        """List a pokémon on the marketplace."""

        pokemon, idx = pokemon

        if pokemon is None:
            return await ctx.send("Couldn't find that pokémon!")

        member = await self.db.fetch_member_info(ctx.author)

        # create listing

        listing = mongo.Listing(pokemon=pokemon, user_id=ctx.author.id, price=price)
        await listing.commit()

        await self.db.update_member(ctx.author, {"$unset": {f"pokemon.{idx}": 1}})
        await self.db.update_member(
            ctx.author,
            {
                "$pull": {f"pokemon": None},
                "$inc": {f"selected": -1 if idx < member.selected else 0},
            },
        )

        message = f"Listed your **{pokemon.iv_percentage:.2%} {pokemon.species} No. {idx + 1}** on the market for **{price:,}** Pokécoins."

        await ctx.send(message)

    @market.command(aliases=["unlist"])
    async def remove(self, ctx: commands.Context, id: str):
        """List a pokémon on the marketplace."""

        listing = await mongo.db.listing.find_one({"_id": fields.ObjectId(id)})

        if listing["user_id"] != ctx.author.id:
            return await ctx.send("That's not your listing!")

        await self.db.update_member(
            ctx.author, {"$push": {f"pokemon": listing["pokemon"]}},
        )
        await mongo.db.listing.delete_one({"_id": fields.ObjectId(id)})

        pokemon = mongo.Pokemon.build_from_mongo(listing["pokemon"])
        await ctx.send(
            f"Removed your **{pokemon.iv_percentage:.2%} {pokemon.species}** from the market."
        )

    @market.command(aliases=["purchase"])
    async def buy(self, ctx: commands.Context, id: str):
        """List a pokémon on the marketplace."""

        listing = await mongo.db.listing.find_one({"_id": fields.ObjectId(id)})
        member = await self.db.fetch_member_info(ctx.author)

        if listing["user_id"] == ctx.author.id:
            return await ctx.send("You can't purchase your own listing!")

        if member.balance < listing["price"]:
            return await ctx.send("You don't have enough Pokécoins for that!")

        await self.db.update_member(
            ctx.author,
            {
                "$push": {f"pokemon": listing["pokemon"]},
                "$inc": {"balance": -listing["price"]},
            },
        )
        await self.db.update_member(
            listing["user_id"], {"$inc": {"balance": listing["price"]}}
        )
        await mongo.db.listing.delete_one({"_id": fields.ObjectId(id)})

        pokemon = mongo.Pokemon.build_from_mongo(listing["pokemon"])
        await ctx.send(
            f"You purchased a **{pokemon.iv_percentage:.2%} {pokemon.species}** from the market for {listing['price']} Pokécoins. Do `{ctx.prefix}info latest` to view it!"
        )

        seller = self.bot.get_user(listing["user_id"])
        await seller.send(
            f"Someone purchased your **{pokemon.iv_percentage:.2%} {pokemon.species}** from the market. You received {listing['price']} Pokécoins!"
        )


def setup(bot: commands.Bot):
    bot.add_cog(Market(bot))
