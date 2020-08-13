import math

import discord
from discord.ext import commands, flags
from umongo import fields
import bson

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
    @flags.add_flag(
        "--order",
        choices=["iv+", "iv-", "price+", "price-", "level+", "level-"],
        default="price-",
    )
    @flags.add_flag("--mine", "--listings", action="store_true")
    @checks.has_started()
    @commands.has_role(721825360827777043)
    @flags.group(aliases=["marketplace", "m"], invoke_without_command=True)
    @commands.bot_has_permissions(manage_messages=True, use_external_emojis=True)
    async def market(self, ctx: commands.Context, **flags):
        """View or filter the pokémon in your collection."""

        if flags["page"] < 1:
            return await ctx.send("Page must be positive!")

        member = await self.db.fetch_member_info(ctx.author)

        aggregations = await self.bot.get_cog("Pokemon").create_filter(
            flags, ctx, order_by=flags["order"]
        )

        if aggregations is None:
            return

        # Filter pokemon

        do_emojis = (
            ctx.channel.permissions_for(
                ctx.guild.get_member(self.bot.user.id)
            ).external_emojis
            and constants.EMOJIS.get_status()
        )

        def nick(p):
            if do_emojis:
                name = (
                    str(constants.EMOJIS.get(p.species.dex_number, shiny=p.shiny))
                    .replace("pokemon_sprite_", "")
                    .replace("_shiny", "")
                    + " "
                )
            else:
                name = ""

            name += f"L{p.level} {p.species}"

            if p.shiny:
                name += " ✨"

            return name

        def padn(p, idx, n):
            return " " * (len(str(n)) - len(str(idx))) + str(idx)

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

            maxn = max(idx for x, idx, price in pokemon)
            page = [
                f"`{padn(p, idx, maxn)}`　**{nick(p)}**　•　{p.iv_percentage * 100:.2f}%　•　{price:,} pc"
                for p, idx, price in pokemon
            ]

            # Send embed

            embed = discord.Embed()
            embed.color = 0xF44336
            embed.title = f"Pokétwo Marketplace"
            embed.description = "\n".join(page)[:2048]

            embed.set_footer(
                text=f"Showing {pgstart + 1}–{min(pgstart + 20, num)} out of {num}."
            )

            return embed

        paginator = pagination.Paginator(get_page, num_pages=math.ceil(num / 20))
        await paginator.send(self.bot, ctx, flags["page"] - 1)

    @checks.has_started()
    @commands.has_role(721825360827777043)
    @market.command(aliases=["list", "a", "l"])
    async def add(self, ctx: commands.Context, pokemon: converters.Pokemon, price: int):
        """List a pokémon on the marketplace."""

        if ctx.author.id in self.bot.trades:
            return await ctx.send("You can't do that in a trade!")

        pokemon, idx = pokemon

        if pokemon is None:
            return await ctx.send("Couldn't find that pokémon!")

        if price < 1:
            return await ctx.send("The price must be positive!")

        if price > 1000000000:
            return await ctx.send("Price is too high!")

        member = await self.db.fetch_member_info(ctx.author)

        # confirm

        await ctx.send(
            f"Are you sure you want to list your **{pokemon.iv_percentage:.2%} {pokemon.species} No. {idx + 1}** for **{price:,}** Pokécoins? [y/N]"
        )

        def check(m):
            return m.channel.id == ctx.channel.id and m.author.id == ctx.author.id

        try:
            msg = await self.bot.wait_for("message", timeout=30, check=check)
        except asyncio.TimeoutError:
            return await ctx.send("Time's up. Aborted.")

        if msg.content.lower() != "y":
            return await ctx.send("Aborted.")

        # create listing

        counter = await mongo.db.counter.find_one_and_update(
            {"_id": "listing"}, {"$inc": {"next": 1}}, upsert=True
        )
        if counter is None:
            counter = {"next": 0}
        listing = mongo.Listing(
            id=counter["next"], pokemon=pokemon, user_id=ctx.author.id, price=price
        )
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

    @checks.has_started()
    @commands.has_role(721825360827777043)
    @market.command(aliases=["unlist", "r", "u"])
    async def remove(self, ctx: commands.Context, id: int):
        """Remove a pokémon from the marketplace."""

        try:
            listing = await mongo.db.listing.find_one({"_id": id})
        except bson.errors.InvalidId:
            return await ctx.send("Couldn't find that listing!")

        if listing is None:
            return await ctx.send("Couldn't find that listing!")

        if listing["user_id"] != ctx.author.id:
            return await ctx.send("That's not your listing!")

        await self.db.update_member(
            ctx.author, {"$push": {f"pokemon": listing["pokemon"]}},
        )
        await mongo.db.listing.delete_one({"_id": id})

        pokemon = mongo.Pokemon.build_from_mongo(listing["pokemon"])
        await ctx.send(
            f"Removed your **{pokemon.iv_percentage:.2%} {pokemon.species}** from the market."
        )

    @checks.has_started()
    @commands.has_role(721825360827777043)
    @market.command(aliases=["purchase", "b", "p"])
    async def buy(self, ctx: commands.Context, id: int):
        """Buy a pokémon on the marketplace."""

        try:
            listing = await mongo.db.listing.find_one({"_id": id})
        except bson.errors.InvalidId:
            return await ctx.send("Couldn't find that listing!")

        if listing is None:
            return await ctx.send("Couldn't find that listing!")

        member = await self.db.fetch_member_info(ctx.author)

        if listing["user_id"] == ctx.author.id:
            return await ctx.send("You can't purchase your own listing!")

        if member.balance < listing["price"]:
            return await ctx.send("You don't have enough Pokécoins for that!")

        pokemon = mongo.Pokemon.build_from_mongo(listing["pokemon"])

        # confirm

        await ctx.send(
            f"Are you sure you want to buy this **{pokemon.iv_percentage:.2%} {pokemon.species}** for **{listing['price']:,}** Pokécoins? [y/N]"
        )

        def check(m):
            return m.channel.id == ctx.channel.id and m.author.id == ctx.author.id

        try:
            msg = await self.bot.wait_for("message", timeout=30, check=check)
        except asyncio.TimeoutError:
            return await ctx.send("Time's up. Aborted.")

        if msg.content.lower() != "y":
            return await ctx.send("Aborted.")

        # buy

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
        await mongo.db.listing.delete_one({"_id": id})

        await ctx.send(
            f"You purchased a **{pokemon.iv_percentage:.2%} {pokemon.species}** from the market for {listing['price']} Pokécoins. Do `{ctx.prefix}info latest` to view it!"
        )

        seller = self.bot.get_user(listing["user_id"])
        await seller.send(
            f"Someone purchased your **{pokemon.iv_percentage:.2%} {pokemon.species}** from the market. You received {listing['price']} Pokécoins!"
        )

    @checks.has_started()
    @commands.has_role(721825360827777043)
    @market.command(aliases=["i"])
    async def info(self, ctx: commands.Context, id: int):
        """View a pokémon from the market."""

        try:
            listing = await mongo.db.listing.find_one({"_id": id})
        except bson.errors.InvalidId:
            return await ctx.send("Couldn't find that listing!")

        if listing is None:
            return await ctx.send("Couldn't find that listing!")

        pokemon = mongo.Pokemon.build_from_mongo(listing["pokemon"])

        embed = discord.Embed()
        embed.color = 0xF44336
        embed.title = f"Level {pokemon.level} {pokemon.species}"

        extrafooter = ""

        if pokemon.shiny:
            embed.title += " ✨"
            embed.set_image(url=pokemon.species.shiny_image_url)
            extrafooter = " Note that we don't have artwork for all shiny pokémon yet! We're working hard to make all the shiny pokémon look shiny."
        else:
            embed.set_image(url=pokemon.species.image_url)

        embed.set_thumbnail(url=self.bot.user.avatar_url)

        info = (
            f"**XP:** {pokemon.xp}/{pokemon.max_xp}",
            f"**Nature:** {pokemon.nature}",
        )

        embed.add_field(name="Details", value="\n".join(info), inline=False)

        stats = (
            f"**HP:** {pokemon.hp} – IV: {pokemon.iv_hp}/31",
            f"**Attack:** {pokemon.atk} – IV: {pokemon.iv_atk}/31",
            f"**Defense:** {pokemon.defn} – IV: {pokemon.iv_defn}/31",
            f"**Sp. Atk:** {pokemon.satk} – IV: {pokemon.iv_satk}/31",
            f"**Sp. Def:** {pokemon.sdef} – IV: {pokemon.iv_sdef}/31",
            f"**Speed:** {pokemon.spd} – IV: {pokemon.iv_spd}/31",
            f"**Total IV:** {pokemon.iv_percentage * 100:.2f}%",
        )

        embed.add_field(name="Stats", value="\n".join(stats), inline=False)

        if pokemon.held_item:
            item = models.GameData.item_by_number(pokemon.held_item)
            gguild = self.bot.get_guild(725819081835544596)
            emote = ""
            if item.emote is not None:
                try:
                    e = next(filter(lambda x: x.name == item.emote, gguild.emojis))
                    emote = f"{e} "
                except StopIteration:
                    pass
            embed.add_field(name="Held Item", value=f"{emote}{item.name}", inline=False)

        embed.set_footer(text=f"Displaying listing {id} from market." + extrafooter)

        await ctx.send(embed=embed)


def setup(bot: commands.Bot):
    bot.add_cog(Market(bot))
