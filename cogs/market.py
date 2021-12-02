import asyncio

import bson
import pymongo
from discord.ext import commands
from helpers import checks, constants, converters, flags, pagination


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
    @flags.add_flag("--shiny", action="store_true")
    @flags.add_flag("--alolan", action="store_true")
    @flags.add_flag("--galarian", action="store_true")
    @flags.add_flag("--mythical", action="store_true")
    @flags.add_flag("--legendary", action="store_true")
    @flags.add_flag("--ub", action="store_true")
    @flags.add_flag("--event", action="store_true")
    @flags.add_flag("--mega", action="store_true")
    @flags.add_flag("--embedcolor", "--ec", action="store_true")
    @flags.add_flag("--name", "--n", nargs="+", action="append")
    @flags.add_flag("--type", "--t", type=str, action="append")
    @flags.add_flag("--region", "--r", type=str, action="append")

    # IV
    @flags.add_flag("--level", nargs="+", action="append")
    @flags.add_flag("--hpiv", nargs="+", action="append")
    @flags.add_flag("--atkiv", nargs="+", action="append")
    @flags.add_flag("--defiv", nargs="+", action="append")
    @flags.add_flag("--spatkiv", nargs="+", action="append")
    @flags.add_flag("--spdefiv", nargs="+", action="append")
    @flags.add_flag("--spdiv", nargs="+", action="append")
    @flags.add_flag("--iv", nargs="+", action="append")

    # Duplicate IV's
    @flags.add_flag("--triple", "--three", type=int)
    @flags.add_flag("--quadruple", "--four", "--quadra", "--quad", "--tetra", type=int)
    @flags.add_flag("--pentuple", "--quintuple", "--penta", "--pent", "--five", type=int)
    @flags.add_flag("--hextuple", "--sextuple", "--hexa", "--hex", "--six", type=int)

    # Skip/limit
    @flags.add_flag("--skip", type=int)
    @flags.add_flag("--limit", type=int)

    # Market
    @flags.add_flag(
        "--order",
        choices=[a + b for a in ("iv", "price", "level", "id") for b in ("+", "-", "")],
        default="id-",
    )
    @flags.add_flag("--mine", "--listings", action="store_true")
    @checks.has_started()
    @commands.cooldown(3, 8, commands.BucketType.user)
    @market.command(aliases=("s",), cls=flags.FlagCommand)
    async def search(self, ctx, **flags):
        """Search pokémon from the marketplace."""

        aggregations = await self.bot.get_cog("Pokemon").create_filter(
            flags, ctx, order_by=flags["order"]
        )

        if aggregations is None:
            return

        # Filter pokemon

        def padn(p, n):
            return " " * (len(str(n)) - len(str(p))) + str(p)

        def prepare_page(menu, items):
            menu.maxn = max(x["market_data"]["_id"] for x in items)

        def format_item(menu, x):
            pokemon = self.bot.mongo.Pokemon.build_from_mongo(x)
            return f"`{padn(x['market_data']['_id'], menu.maxn)}`　**{pokemon:li}**　•　{pokemon.iv_total / 186:.2%}　•　{x['market_data']['price']:,} pc"

        pokemon = self.bot.mongo.fetch_market_list(aggregations)

        pages = pagination.ContinuablePages(
            pagination.AsyncListPageSource(
                pokemon,
                title=f"Pokétwo Marketplace",
                prepare_page=prepare_page,
                format_item=format_item,
                per_page=20,
            ),
            allow_last=False,
            allow_go=False,
        )
        self.bot.menus[ctx.author.id] = pages

        try:
            await pages.start(ctx)
        except IndexError:
            await ctx.send("No listings found.")

    @checks.has_started()
    @checks.is_not_in_trade()
    @commands.max_concurrency(1, commands.BucketType.member)
    @market.command(aliases=("list", "a", "l"))
    async def add(self, ctx, pokemon: converters.PokemonConverter, price: int):
        """List a pokémon on the marketplace."""

        if pokemon is None:
            return await ctx.send("Couldn't find that pokémon!")

        if price < 1:
            return await ctx.send("The price must be positive!")

        if price > 1000000000:
            return await ctx.send("Price is too high!")

        member = await self.bot.mongo.fetch_member_info(ctx.author)

        if member.selected_id == pokemon.id:
            return await ctx.send(f"{pokemon.idx}: You can't list your selected pokémon!")

        if pokemon.favorite:
            return await ctx.send(f"{pokemon.idx}: You can't list a favorited pokémon!")

        # confirm

        result = await ctx.confirm(
            f"Are you sure you want to list your **{pokemon.iv_percentage:.2%} {pokemon:s} "
            f"No. {pokemon.idx}** for **{price:,}** Pokécoins?"
        )
        if result is None:
            return await ctx.send("Time's up. Aborted.")
        if result is False:
            return await ctx.send("Aborted.")

        if await self.bot.get_cog("Trading").is_in_trade(ctx.author):
            return await ctx.send("You can't do that in a trade!")

        # create listing

        counter = await self.bot.mongo.db.counter.find_one_and_update(
            {"_id": "listing"}, {"$inc": {"next": 1}}, upsert=True
        )
        if counter is None:
            counter = {"next": 0}

        await self.bot.mongo.db.pokemon.update_one(
            {"_id": pokemon.id},
            {
                "$set": {
                    "owned_by": "market",
                    "market_data": {"_id": counter["next"], "price": price},
                }
            },
        )

        await ctx.send(
            f"Listed your **{pokemon.iv_percentage:.2%} {pokemon.species} "
            f"No. {pokemon.idx}** on the market for **{price:,}** Pokécoins."
        )

    @checks.has_started()
    @checks.is_not_in_trade()
    @commands.max_concurrency(1, commands.BucketType.member)
    @market.command(aliases=("unlist", "r", "u"))
    async def remove(self, ctx, id: int):
        """Remove a pokémon from the marketplace."""

        listing = await self.bot.mongo.db.pokemon.find_one(
            {"owned_by": "market", "market_data._id": id}
        )
        if listing is None:
            return await ctx.send("Couldn't find that listing!")
        if listing["owner_id"] != ctx.author.id:
            return await ctx.send("That's not your listing!")

        # confirm
        pokemon = self.bot.mongo.Pokemon.build_from_mongo(listing)

        result = await ctx.confirm(
            f"Are you sure you want to remove your **{pokemon.iv_percentage:.2%} {pokemon:s}** "
            f"from the market?"
        )
        if result is None:
            return await ctx.send("Time's up. Aborted.")
        if result is False:
            return await ctx.send("Aborted.")

        await self.bot.mongo.db.pokemon.update_one(
            {"_id": listing["_id"]},
            {"$set": {"owned_by": "user"}, "$unset": {"market_data": 1}},
        )

        await ctx.send(
            f"Removed your **{pokemon.iv_percentage:.2%} {pokemon.species}** from the market."
        )

    @checks.has_started()
    @checks.is_not_in_trade()
    @commands.max_concurrency(1, commands.BucketType.member)
    @market.command(aliases=("purchase", "b", "p"))
    async def buy(self, ctx, id: int):
        """Buy a pokémon on the marketplace."""

        listing = await self.bot.mongo.db.pokemon.find_one(
            {"owned_by": "market", "market_data._id": id}
        )
        if listing is None:
            return await ctx.send("Couldn't find that listing!")

        member = await self.bot.mongo.fetch_member_info(ctx.author)

        if listing["owner_id"] == ctx.author.id:
            return await ctx.send("You can't purchase your own listing!")

        if member.balance < listing["market_data"]["price"]:
            return await ctx.send("You don't have enough Pokécoins for that!")

        pokemon = self.bot.mongo.Pokemon.build_from_mongo(listing)

        # confirm

        result = await ctx.confirm(
            f"Are you sure you want to buy this **{pokemon.iv_percentage:.2%} {pokemon:s}** "
            f"for **{listing['market_data']['price']:,}** Pokécoins?"
        )
        if result is None:
            return await ctx.send("Time's up. Aborted.")
        if result is False:
            return await ctx.send("Aborted.")

        # buy

        listing = await self.bot.mongo.db.pokemon.find_one(
            {"owned_by": "market", "market_data._id": id}
        )
        if listing is None:
            return await ctx.send("That listing no longer exists.")

        member = await self.bot.mongo.fetch_member_info(ctx.author)
        if member.balance < listing["market_data"]["price"]:
            return await ctx.send("You don't have enough Pokécoins for that!")

        await self.bot.mongo.db.pokemon.update_one(
            {"_id": listing["_id"]},
            {
                "$set": {"owner_id": ctx.author.id, "owned_by": "user"},
                "$unset": {"market_data": 1},
            },
        )
        await self.bot.mongo.update_member(
            ctx.author, {"$inc": {"balance": -listing["market_data"]["price"]}}
        )
        await self.bot.mongo.update_member(
            listing["owner_id"], {"$inc": {"balance": listing["market_data"]["price"]}}
        )
        await ctx.send(
            f"You purchased a **{pokemon.iv_percentage:.2%} {pokemon.species}** from the market for {listing['market_data']['price']} Pokécoins. Do `{ctx.prefix}info latest` to view it!"
        )

        self.bot.loop.create_task(
            self.bot.send_dm(
                listing["owner_id"],
                f"Someone purchased your **{pokemon.iv_percentage:.2%} {pokemon.species}** from the market. You received {listing['market_data']['price']} Pokécoins!",
            )
        )

        self.bot.dispatch("market_buy", ctx.author, listing)

        try:
            await self.bot.mongo.db.logs.insert_one(
                {
                    "event": "market",
                    "user": ctx.author.id,
                    "item": listing["_id"],
                    "seller_id": listing["owner_id"],
                    "price": listing["market_data"]["price"],
                    "listing_id": listing["market_data"]["_id"],
                }
            )
        except:
            print("Error trading market logs.")

    @checks.has_started()
    @commands.cooldown(3, 5, commands.BucketType.user)
    @market.command(aliases=("i",))
    async def info(self, ctx, id: int):
        """View a pokémon from the market."""

        listing = await self.bot.mongo.db.pokemon.find_one(
            {"owned_by": "market", "market_data._id": id}
        )
        if listing is None:
            return await ctx.send("Couldn't find that listing!")

        pokemon = self.bot.mongo.Pokemon.build_from_mongo(listing)

        embed = self.bot.Embed(title=f"{pokemon:ln}", color=pokemon.color or constants.PINK)

        if pokemon.shiny:
            embed.set_image(url=pokemon.species.shiny_image_url)
        else:
            embed.set_image(url=pokemon.species.image_url)

        embed.set_thumbnail(url=self.bot.user.display_avatar.url)

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

        embed.add_field(
            name="Market Listing",
            value=f"**ID:** {id}\n**Price:** {listing['market_data']['price']:,} pc",
            inline=False,
        )

        embed.set_footer(text=f"Displaying listing {id} from market.")

        await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(Market(bot))
