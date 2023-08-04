import asyncio

from discord.ext import commands

from helpers import checks, constants, converters, flags, pagination


class Market(commands.Cog):
    """A marketplace to buy and sell pokémon."""

    def __init__(self, bot):
        self.bot = bot

    @commands.group(aliases=("marketplace", "m"), invoke_without_command=True, case_insensitive=True)
    async def market(self, ctx, **flags):
        """Buy or sell pokémon on the Pokétwo marketplace."""

        await ctx.send_help(ctx.command)

    # Filter
    @flags.add_flag("--shiny", action="store_true")
    @flags.add_flag("--alolan", action="store_true")
    @flags.add_flag("--galarian", action="store_true")
    @flags.add_flag("--hisuian", action="store_true")
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

        def map_field(field):
            if field == "_id":
                return f"market_data._id"
            return field

        aggregations = await self.bot.get_cog("Pokemon").create_filter(
            flags, ctx, order_by=flags["order"], map_field=map_field
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
                title=ctx._("marketplace-title"),
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
            await ctx.send(ctx._("no-listings-found"))

    @checks.has_started()
    @checks.is_not_in_trade()
    @commands.max_concurrency(1, commands.BucketType.member)
    @market.command(aliases=("list", "a", "l"))
    async def add(self, ctx, pokemon: converters.PokemonConverter, price: int):
        """List a pokémon on the marketplace."""

        if pokemon is None:
            return await ctx.send(ctx._("unknown-pokemon"))

        if price < 1:
            return await ctx.send(ctx._("price-must-be-positive"))

        if price > 1000000000:
            return await ctx.send(ctx._("price-too-high"))

        member = await self.bot.mongo.fetch_member_info(ctx.author)

        if member.selected_id == pokemon.id:
            return await ctx.send(ctx._("cannot-list-selected", index=pokemon.idx))

        if pokemon.favorite:
            return await ctx.send(ctx._("cannot-list-favorited", index=pokemon.idx))

        # confirm

        result = await ctx.confirm(
            ctx._(
                "add-confirmation",
                ivPercentage=pokemon.iv_percentage * 100,
                pokemon=f"{pokemon:s}",
                index=pokemon.idx,
                price=price,
            )
        )
        if result is None:
            return await ctx.send(ctx._("times-up"))
        if result is False:
            return await ctx.send(ctx._("aborted"))

        if await self.bot.get_cog("Trading").is_in_trade(ctx.author):
            return await ctx.send(ctx._("forbidden-during-trade"))

        # create listing

        counter = await self.bot.mongo.db.counter.find_one_and_update(
            {"_id": "listing"}, {"$inc": {"next": 1}}, upsert=True
        )
        if counter is None:
            counter = {"next": 0}

        pokemon_dict = await self.bot.mongo.db.pokemon.find_one_and_update(
            {"_id": pokemon.id},
            {
                "$set": {
                    "owned_by": "market",
                    "market_data": {"_id": counter["next"], "price": price},
                }
            },
        )

        self.bot.dispatch("market_add", ctx.author, pokemon_dict)

        await ctx.send(
            ctx._(
                "add-completed",
                ivPercentage=pokemon.iv_percentage * 100,
                pokemon=pokemon.species,
                index=pokemon.index,
                price=price,
            )
        )

    @checks.has_started()
    @checks.is_not_in_trade()
    @commands.max_concurrency(1, commands.BucketType.member)
    @market.command(aliases=("unlist", "r", "u"))
    async def remove(self, ctx, id: int):
        """Remove a pokémon from the marketplace."""

        listing = await self.bot.mongo.db.pokemon.find_one({"owned_by": "market", "market_data._id": id})
        if listing is None:
            return await ctx.send(ctx._("unknown-listing"))
        if listing["owner_id"] != ctx.author.id:
            return await ctx.send(ctx._("not-your-listing"))

        # confirm
        pokemon = self.bot.mongo.Pokemon.build_from_mongo(listing)

        result = await ctx.confirm(
            ctx._("market-remove-confirmation", pokemon=f"{pokemon:s}", ivPercentage=pokemon.iv_percentage * 100)
        )
        if result is None:
            return await ctx.send(ctx._("times-up"))
        if result is False:
            return await ctx.send(ctx._("aborted"))

        await self.bot.mongo.db.pokemon.update_one(
            {"_id": listing["_id"]},
            {
                "$set": {"owned_by": "user", "idx": await self.bot.mongo.fetch_next_idx(ctx.author)},
                "$unset": {"market_data": 1},
            },
        )

        await ctx.send(
            ctx._("market-remove-completed", ivPercentage=pokemon.iv_percentage * 100, pokemon=pokemon.species)
        )

    @checks.has_started()
    @checks.is_not_in_trade()
    @commands.max_concurrency(1, commands.BucketType.member)
    @market.command(aliases=("purchase", "b", "p"))
    async def buy(self, ctx, id: int):
        """Buy a pokémon on the marketplace."""

        listing = await self.bot.mongo.db.pokemon.find_one({"owned_by": "market", "market_data._id": id})
        if listing is None:
            return await ctx.send(ctx._("unknown-listing"))

        member = await self.bot.mongo.fetch_member_info(ctx.author)

        if listing["owner_id"] == ctx.author.id:
            return await ctx.send(ctx._("cannot-self-buy-listing"))

        if member.balance < listing["market_data"]["price"]:
            return await ctx.send(ctx._("not-enough-coins"))

        pokemon = self.bot.mongo.Pokemon.build_from_mongo(listing)

        # confirm

        result = await ctx.confirm(
            ctx._(
                "buy-confirmation",
                ivPercentage=pokemon.iv_percentage * 100,
                pokemon=f"{pokemon:s}",
                price=listing["market_data"]["price"],
            )
        )
        if result is None:
            return await ctx.send(ctx._("times-up"))
        if result is False:
            return await ctx.send(ctx._("aborted"))

        # buy

        listing = await self.bot.mongo.db.pokemon.find_one({"owned_by": "market", "market_data._id": id})
        if listing is None:
            return await ctx.send(ctx._("listing-no-longer-exists"))

        member = await self.bot.mongo.fetch_member_info(ctx.author)
        if member.balance < listing["market_data"]["price"]:
            return await ctx.send(ctx._("not-enough-coins"))

        # to try to avoid race conditions
        await asyncio.sleep(1)

        listing = await self.bot.mongo.db.pokemon.find_one({"owned_by": "market", "market_data._id": id})
        if listing is None:
            return await ctx.send(ctx._("listing-no-longer-exists"))

        member = await self.bot.mongo.fetch_member_info(ctx.author)
        if member.balance < listing["market_data"]["price"]:
            return await ctx.send(ctx._("not-enough-coins"))

        listing = await self.bot.mongo.db.pokemon.find_one_and_update(
            {"_id": listing["_id"], "owned_by": "market"},
            {
                "$set": {
                    "owner_id": ctx.author.id,
                    "owned_by": "user",
                    "idx": await self.bot.mongo.fetch_next_idx(ctx.author),
                },
                "$unset": {"market_data": 1},
            },
        )
        if listing is None:
            return await ctx.send(ctx._("listing-no-longer-exists"))

        res = await self.bot.mongo.db.member.find_one_and_update(
            {"_id": ctx.author.id}, {"$inc": {"balance": -listing["market_data"]["price"]}}
        )
        await self.bot.redis.hdel("db:member", ctx.author.id)
        if res["balance"] < listing["market_data"]["price"]:
            await self.bot.mongo.update_member(ctx.author, {"$inc": {"balance": listing["market_data"]["price"]}})
            return await ctx.send(ctx._("not-enough-coins"))

        await self.bot.mongo.update_member(listing["owner_id"], {"$inc": {"balance": listing["market_data"]["price"]}})
        await ctx.send(
            ctx._(
                "buy-completed",
                ivPercentage=pokemon.iv_percentage * 100,
                price=listing["market_data"]["price"],
                pokemon=pokemon.species,
            )
        )

        self.bot.loop.create_task(
            self.bot.send_dm(
                listing["owner_id"],
                ctx._(
                    "someone-purchased-your-listing",
                    price=listing["market_data"]["price"],
                    pokemon=pokemon.species,
                    ivPercentage=pokemon.iv_percentage * 100,
                ),
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
            pass

    @checks.has_started()
    @commands.cooldown(3, 5, commands.BucketType.user)
    @market.command(aliases=("i",))
    async def info(self, ctx, id: int):
        """View a pokémon from the market."""

        listing = await self.bot.mongo.db.pokemon.find_one({"owned_by": "market", "market_data._id": id})
        if listing is None:
            return await ctx.send(ctx._("unknown-listing"))

        pokemon = self.bot.mongo.Pokemon.build_from_mongo(listing)

        held_item_value = None
        if pokemon.held_item:
            item = self.bot.data.item_by_number(pokemon.held_item)
            emote = ""
            if item.emote is not None:
                emote = getattr(self.bot.sprites, item.emote) + " "
            held_item_value = f"{emote}{item.name}"

        embed = ctx.localized_embed(
            "market-info-embed",
            field_ordering=["details", "stats", "held-item", "market-listing"],
            block_fields=["details", "stats", "market-listing"],
            field_values={"held-item": held_item_value},
            droppable_fields=["held-item"],
            pokemon=f"{pokemon:l}",
            xp=pokemon.xp,
            maxXp=pokemon.max_xp,
            nature=pokemon.nature,
            hp=pokemon.hp,
            ivHp=pokemon.iv_hp,
            atk=pokemon.atk,
            ivAtk=pokemon.iv_atk,
            defn=pokemon.defn,
            ivDefn=pokemon.iv_defn,
            satk=pokemon.satk,
            ivSatk=pokemon.iv_satk,
            sdef=pokemon.sdef,
            ivSdef=pokemon.iv_sdef,
            spd=pokemon.spd,
            ivSpd=pokemon.iv_spd,
            ivPercentage=pokemon.iv_percentage * 100,
            id=id,
            price=listing["market_data"]["price"],
        )
        embed.color = pokemon.color or constants.PINK

        if pokemon.shiny:
            embed.set_image(url=pokemon.species.shiny_image_url)
        else:
            embed.set_image(url=pokemon.species.image_url)

        embed.set_thumbnail(url=self.bot.user.display_avatar.url)

        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Market(bot))
