import asyncio
import math

import bson
import pymongo
from discord.ext import commands, flags

from helpers import checks, converters, pagination


class Market(commands.Cog):
    """A marketplace to buy and sell pokémon."""

    def __init__(self, bot):
        self.bot = bot

    @commands.group(
        aliases=("marketplace", "m"), invoke_without_command=True, case_insensitive=True
    )
    async def market(self, ctx, **flags):
        """Buy or sell pokémon on the Pokétwo marketplace."""

        await ctx.send_help(ctx.command)

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
    @market.command(aliases=("s",), cls=flags.FlagCommand)
    async def search(self, ctx, **flags):
        """Search pokémon from the marketplace."""

        if flags["page"] < 1:
            return await ctx.send("Page must be positive!")

        aggregations = await self.bot.get_cog("Pokemon").create_filter(
            flags, ctx, order_by=flags["order"]
        )

        if aggregations is None:
            return

        # Filter pokemon

        def padn(p, idx, n):
            return " " * (len(str(n)) - len(str(idx))) + str(idx)

        num = await self.bot.mongo.fetch_market_count(aggregations=aggregations)

        if num == 0:
            return await ctx.send("Found no pokémon matching this search.")

        async def get_page(pidx, clear):

            pgstart = pidx * 20
            pokemon = await self.bot.mongo.fetch_market_list(
                pgstart, 20, aggregations=aggregations
            )

            pokemon = [
                (
                    self.bot.mongo.EmbeddedPokemon.build_from_mongo(x["pokemon"]),
                    x["_id"],
                    x["price"],
                )
                for x in pokemon
            ]

            if len(pokemon) == 0:
                return await clear("There are no pokémon on this page!")

            maxn = max(idx for x, idx, price in pokemon)
            page = [
                f"`{padn(p, idx, maxn)}`　**{p:li}**　•　{p.iv_percentage * 100:.2f}%　•　{price:,} pc"
                for p, idx, price in pokemon
            ]

            # Send embed

            embed = self.bot.Embed(color=0x9CCFFF)
            embed.title = f"Pokétwo Marketplace"
            embed.description = "\n".join(page)[:2048]

            embed.set_footer(
                text=f"Showing {pgstart + 1}–{min(pgstart + 20, num)} out of {num}. (Page {pidx+1} of {math.ceil(num / 20)})"
            )

            return embed

        paginator = pagination.Paginator(get_page, num_pages=math.ceil(num / 20))
        await paginator.send(self.bot, ctx, flags["page"] - 1)

    @checks.has_started()
    @commands.max_concurrency(1, commands.BucketType.member)
    @market.command(aliases=("list", "a", "l"))
    async def add(self, ctx, pokemon: converters.PokemonConverter, price: int):
        """List a pokémon on the marketplace."""

        if await self.bot.get_cog("Trading").is_in_trade(ctx.author):
            return await ctx.send("You can't do that in a trade!")

        if pokemon is None:
            return await ctx.send("Couldn't find that pokémon!")

        if price < 1:
            return await ctx.send("The price must be positive!")

        if price > 1000000000:
            return await ctx.send("Price is too high!")

        member = await self.bot.mongo.fetch_member_info(ctx.author)

        # confirm

        await ctx.send(
            f"Are you sure you want to list your **{pokemon.iv_percentage:.2%} {pokemon.species} "
            f"No. {pokemon.idx}** for **{price:,}** Pokécoins? [y/N]"
        )

        def check(m):
            return m.channel.id == ctx.channel.id and m.author.id == ctx.author.id

        try:
            msg = await self.bot.wait_for("message", timeout=30, check=check)
        except asyncio.TimeoutError:
            return await ctx.send("Time's up. Aborted.")

        if msg.content.lower() != "y":
            return await ctx.send("Aborted.")

        if await self.bot.get_cog("Trading").is_in_trade(ctx.author):
            return await ctx.send("You can't do that in a trade!")

        # create listing

        counter = await self.bot.mongo.db.counter.find_one_and_update(
            {"_id": "listing"}, {"$inc": {"next": 1}}, upsert=True
        )
        if counter is None:
            counter = {"next": 0}

        await self.bot.mongo.db.listing.insert_one(
            {
                "_id": counter["next"],
                "pokemon": pokemon.to_mongo(),
                "user_id": ctx.author.id,
                "price": price,
            }
        )

        await self.bot.mongo.db.pokemon.delete_one({"_id": pokemon.id})

        await ctx.send(
            f"Listed your **{pokemon.iv_percentage:.2%} {pokemon.species} "
            f"No. {pokemon.idx}** on the market for **{price:,}** Pokécoins."
        )

    @checks.has_started()
    @commands.max_concurrency(1, commands.BucketType.member)
    @market.command(aliases=("unlist", "r", "u"))
    async def remove(self, ctx, id: int):
        """Remove a pokémon from the marketplace."""

        if await self.bot.get_cog("Trading").is_in_trade(ctx.author):
            return await ctx.send("You can't do that in a trade!")

        try:
            listing = await self.bot.mongo.db.listing.find_one({"_id": id})
        except bson.errors.InvalidId:
            return await ctx.send("Couldn't find that listing!")

        if listing is None:
            return await ctx.send("Couldn't find that listing!")

        if listing["user_id"] != ctx.author.id:
            return await ctx.send("That's not your listing!")

        # confirm
        pokemon = self.bot.mongo.EmbeddedPokemon.build_from_mongo(listing["pokemon"])
        await ctx.send(
            f"Are you sure you want to remove this listing **{pokemon.iv_percentage:.2%} {pokemon.species}** "
            f"for **{listing['price']:,}** Pokécoins? [y/N]"
        )

        def check(m):
            return m.channel.id == ctx.channel.id and m.author.id == ctx.author.id

        try:
            msg = await self.bot.wait_for("message", timeout=30, check=check)
        except asyncio.TimeoutError:
            return await ctx.send("Time's up. Aborted removal of listing.")

        if msg.content.lower() != "y":
            return await ctx.send("Aborted.")

        try:
            await self.bot.mongo.db.pokemon.insert_one(
                {
                    **listing["pokemon"],
                    "idx": await self.bot.mongo.fetch_next_idx(ctx.author),
                }
            )
        except pymongo.errors.DuplicateKeyError:
            return await ctx.send("Couldn't remove that pokémon.")

        await self.bot.mongo.db.listing.delete_one({"_id": id})

        await ctx.send(
            f"Removed your **{pokemon.iv_percentage:.2%} {pokemon.species}** from the market."
        )

    @checks.has_started()
    @commands.max_concurrency(1, commands.BucketType.member)
    @market.command(aliases=("purchase", "b", "p"))
    async def buy(self, ctx, id: int):
        """Buy a pokémon on the marketplace."""

        if await self.bot.get_cog("Trading").is_in_trade(ctx.author):
            return await ctx.send("You can't do that in a trade!")

        try:
            listing = await self.bot.mongo.db.listing.find_one({"_id": id})
        except bson.errors.InvalidId:
            return await ctx.send("Couldn't find that listing!")

        if listing is None:
            return await ctx.send("Couldn't find that listing!")

        member = await self.bot.mongo.fetch_member_info(ctx.author)

        if listing["user_id"] == ctx.author.id:
            return await ctx.send("You can't purchase your own listing!")

        if member.balance < listing["price"]:
            return await ctx.send("You don't have enough Pokécoins for that!")

        pokemon = self.bot.mongo.EmbeddedPokemon.build_from_mongo(listing["pokemon"])

        # confirm

        await ctx.send(
            f"Are you sure you want to buy this **{pokemon.iv_percentage:.2%} {pokemon.species}** "
            f"for **{listing['price']:,}** Pokécoins? [y/N]"
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

        listing = await self.bot.mongo.db.listing.find_one({"_id": id})

        if listing is None:
            return await ctx.send("That listing no longer exists.")

        member = await self.bot.mongo.fetch_member_info(ctx.author)
        if member.balance < listing["price"]:
            return await ctx.send("You don't have enough Pokécoins for that!")

        try:
            await self.bot.mongo.db.pokemon.insert_one(
                {
                    **listing["pokemon"],
                    "owner_id": ctx.author.id,
                    "idx": await self.bot.mongo.fetch_next_idx(ctx.author),
                }
            )
        except pymongo.errors.DuplicateKeyError:
            return await ctx.send("Couldn't buy that pokémon.")

        await self.bot.mongo.db.listing.delete_one({"_id": id})
        await self.bot.mongo.update_member(
            ctx.author, {"$inc": {"balance": -listing["price"]}}
        )

        await self.bot.mongo.update_member(
            listing["user_id"], {"$inc": {"balance": listing["price"]}}
        )
        await ctx.send(
            f"You purchased a **{pokemon.iv_percentage:.2%} {pokemon.species}** from the market for {listing['price']} Pokécoins. Do `{ctx.prefix}info latest` to view it!"
        )

        seller = self.bot.get_user(listing["user_id"]) or await self.bot.fetch_user(
            listing["user_id"]
        )
        await seller.send(
            f"Someone purchased your **{pokemon.iv_percentage:.2%} {pokemon.species}** from the market. You received {listing['price']} Pokécoins!"
        )

        self.bot.dispatch("market_buy", ctx.author, listing)

        try:
            await self.bot.mongo.db.logs.insert_one(
                {
                    "event": "market",
                    "user": ctx.author.id,
                    "item": listing["pokemon"]["_id"],
                    "seller_id": listing["user_id"],
                    "price": listing["price"],
                }
            )
        except:
            print("Error trading market logs.")

    @checks.has_started()
    @market.command(aliases=("i",))
    async def info(self, ctx, id: int):
        """View a pokémon from the market."""

        try:
            listing = await self.bot.mongo.db.listing.find_one({"_id": id})
        except bson.errors.InvalidId:
            return await ctx.send("Couldn't find that listing!")

        if listing is None:
            return await ctx.send("Couldn't find that listing!")

        pokemon = self.bot.mongo.EmbeddedPokemon.build_from_mongo(listing["pokemon"])

        embed = self.bot.Embed(color=0x9CCFFF)
        embed.title = f"{pokemon:ln}"

        if pokemon.shiny:
            embed.set_image(url=pokemon.species.shiny_image_url)
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
            item = self.bot.data.item_by_number(pokemon.held_item)
            emote = ""
            if item.emote is not None:
                emote = getattr(self.bot.sprites, item.emote) + " "
            embed.add_field(name="Held Item", value=f"{emote}{item.name}", inline=False)

        embed.set_footer(text=f"Displaying listing {id} from market.")

        await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(Market(bot))
