import contextlib
from datetime import datetime, timedelta

import discord
import humanfriendly
from discord.ext import commands, tasks

from helpers import checks, constants, converters, flags, pagination
from helpers.utils import FakeUser, add_moves_field


class AuctionConverter(commands.Converter):
    async def convert(self, ctx, arg):
        try:
            auction = await ctx.bot.mongo.db.pokemon.find_one(
                {"owned_by": "auction", "auction_data.guild_id": ctx.guild.id, "auction_data._id": int(arg)}
            )
        except ValueError:
            raise commands.BadArgument("Invalid auction ID.")

        if auction is None:
            raise commands.BadArgument("Could not find auction with that ID.")

        return auction


class Auctions(commands.Cog):
    """For auctions."""

    def __init__(self, bot):
        self.bot = bot
        self.check_auctions.start()

    @tasks.loop(seconds=20)
    async def check_auctions(self):
        auctions = self.bot.mongo.db.pokemon.find(
            {"owned_by": "auction", "auction_data.ends": {"$lt": datetime.utcnow()}}
        )
        async for auction in auctions:
            try:
                async with await self.bot.mongo.client.start_session() as s:
                    async with s.start_transaction():
                        await self.end_auction(auction)
            except Exception as e:
                raise
                self.bot.log.error("check_auctions.error", auction=auction)

    @check_auctions.before_loop
    async def before_check_auctions(self):
        await self.bot.wait_until_ready()

    async def try_get_member(self, guild, id):
        if user := self.bot.get_user(id):
            return user
        with contextlib.suppress(discord.HTTPException):
            return await guild.fetch_member(id)
        with contextlib.suppress(discord.HTTPException):
            return await self.bot.fetch_user(id)
        return FakeUser(id)

    async def end_auction(self, auction):
        if (auction_guild := self.bot.get_guild(auction["auction_data"]["guild_id"])) is None:
            return

        guild = await self.bot.mongo.fetch_guild(auction_guild)
        pokemon = self.bot.mongo.Pokemon.build_from_mongo(auction)
        host = await self.try_get_member(auction_guild, auction["owner_id"])
        new_owner = host

        if auction["auction_data"]["bidder_id"] is not None:
            bidder = await self.try_get_member(auction_guild, auction["auction_data"]["bidder_id"])
            new_owner = bidder

            embed = self.make_base_embed(host, pokemon, auction["auction_data"]["_id"])
            embed.title = f"[SOLD] {embed.title}"
            auction_info = (
                f"**Winning Bid:** {auction['auction_data']['current_bid']:,} Pokécoins",
                f"**Bidder:** {bidder.mention}",
            )
            embed.add_field(name="Auction Details", value="\n".join(auction_info))
            embed.set_footer(text=f"The auction has ended.")

            if auction_channel := auction_guild.get_channel(guild.auction_channel):
                with contextlib.suppress(discord.HTTPException):
                    await auction_channel.send(embed=embed)
            with contextlib.suppress(discord.HTTPException):
                msg = f"The auction for your **{pokemon:pl}** ended with a highest bid of **{auction['auction_data']['current_bid']:,}** Pokécoins (Auction #{auction['auction_data']['_id']})."
                await host.send(msg)
            with contextlib.suppress(discord.HTTPException):
                msg = f"You won the auction for the **{pokemon:pl}** with a bid of **{auction['auction_data']['current_bid']:,}** Pokécoins (Auction #{auction['auction_data']['_id']})."
                await bidder.send(msg)

            await self.bot.mongo.update_member(host, {"$inc": {"balance": auction["auction_data"]["current_bid"]}})
            await self.bot.mongo.db.logs.insert_one(
                {
                    "event": "auction",
                    "user": auction["auction_data"]["bidder_id"],
                    "item": auction["_id"],
                    "seller_id": auction["owner_id"],
                    "listing_id": auction["auction_data"]["_id"],
                    "price": auction["auction_data"]["current_bid"],
                }
            )
        else:
            with contextlib.suppress(discord.HTTPException):
                msg = f"The auction for your **{pokemon:pl}** ended with no bids (Auction #{auction['auction_data']['_id']})."
                await host.send(msg)

        # ok, bid

        await self.bot.mongo.db.pokemon.update_one(
            {"owned_by": "auction", "auction_data._id": auction["auction_data"]["_id"]},
            {
                "$set": {
                    "owner_id": new_owner.id,
                    "owned_by": "user",
                    "idx": await self.bot.mongo.fetch_next_idx(new_owner),
                },
                "$unset": {"auction_data": 1},
            },
        )

    def make_base_embed(self, author, pokemon, auction_id):
        embed = self.bot.Embed(
            title=f"Auction #{auction_id} • {pokemon:l}",
        )
        embed.color = pokemon.color or embed.color
        embed.set_author(name=str(author), icon_url=author.display_avatar.url)

        if pokemon.shiny:
            embed.set_thumbnail(url=pokemon.species.shiny_image_url)
        else:
            embed.set_thumbnail(url=pokemon.species.image_url)

        info = (
            f"**XP:** {pokemon.xp}/{pokemon.max_xp}",
            f"**Nature:** {pokemon.nature}",
            f"**HP:** {pokemon.hp} – IV: {pokemon.iv_hp}/31",
            f"**Attack:** {pokemon.atk} – IV: {pokemon.iv_atk}/31",
            f"**Defense:** {pokemon.defn} – IV: {pokemon.iv_defn}/31",
            f"**Sp. Atk:** {pokemon.satk} – IV: {pokemon.iv_satk}/31",
            f"**Sp. Def:** {pokemon.sdef} – IV: {pokemon.iv_sdef}/31",
            f"**Speed:** {pokemon.spd} – IV: {pokemon.iv_spd}/31",
            f"**Total IV:** {pokemon.iv_percentage * 100:.2f}%",
        )
        if pokemon.held_item:
            item = self.bot.data.item_by_number(pokemon.held_item)
            emote = ""
            if item.emote is not None:
                emote = getattr(self.bot.sprites, item.emote) + " "
            info += (f"**Held Item:** {emote}{item.name}",)

        embed.add_field(name="Pokémon Details", value="\n".join(info))

        add_moves_field(pokemon.moves, embed, self.bot)

        return embed

    @commands.group(aliases=("auctions", "a"), invoke_without_command=True, case_insensitive=True)
    async def auction(self, ctx):
        """Auction pokémon."""

        await ctx.send_help(ctx.command)

    @commands.has_permissions(administrator=True)
    @auction.command()
    async def channel(self, ctx, channel: discord.TextChannel):
        """Change the auctions channel."""

        await self.bot.mongo.update_guild(ctx.guild, {"$set": {"auction_channel": channel.id}})
        await ctx.send(f"Changed auctions channel to **{channel}**.")

    @checks.has_started()
    @checks.is_not_in_trade()
    @commands.max_concurrency(1, per=commands.BucketType.user)
    @auction.command()
    async def start(
        self,
        ctx,
        pokemon: converters.PokemonConverter,
        duration: converters.TimeDelta,
        starting_bid: int,
        bid_increment: int,
    ):
        """Start an auction."""

        if ctx.guild.id != 716390832034414685:
            return await ctx.send("Sorry, you cannot start auctions outside of the main server at this time.")

        if pokemon is None:
            return await ctx.send("Couldn't find that pokémon!")

        if not (0 < starting_bid <= 1000000):
            return await ctx.send("The starting bid is not valid.")

        if not (0 < bid_increment <= starting_bid):
            return await ctx.send("The bid increment is not valid.")

        if duration > timedelta(weeks=1):
            return await ctx.send("The max duration is 1 week.")

        guild = await self.bot.mongo.fetch_guild(ctx.guild)
        if guild.auction_channel is None or (auction_channel := ctx.guild.get_channel(guild.auction_channel)) is None:
            return await ctx.send(
                f"Auctions have not been set up in this server. Have a server administrator do `{ctx.clean_prefix}auction channel #channel`."
            )

        member = await self.bot.mongo.fetch_member_info(ctx.author)

        if member.selected_id == pokemon.id:
            return await ctx.send(f"{pokemon.idx}: You can't auction your selected pokémon!")

        if pokemon.favorite:
            return await ctx.send(f"{pokemon.idx}: You can't auction a favorited pokémon!")

        # confirm

        result = await ctx.confirm(
            f"You are auctioning your **{pokemon.iv_percentage:.2%} {pokemon.species} No. {pokemon.idx}**:\n"
            f"**Starting Bid:** {starting_bid:,} Pokécoins\n"
            f"**Bid Increment:** {bid_increment:,} Pokécoins\n"
            f"**Duration:** {humanfriendly.format_timespan(duration.total_seconds())}\n"
            "Auctions are server-specific and cannot be canceled. Are you sure?"
        )
        if result is None:
            return await ctx.send("Time's up. Aborted.")
        if result is False:
            return await ctx.send("Aborted.")

        # create auction

        if await self.bot.get_cog("Trading").is_in_trade(ctx.author):
            return await ctx.send("You can't do that in a trade!")

        # TODO put counters in mongo cog

        ends = datetime.utcnow() + duration

        counter = await self.bot.mongo.db.counter.find_one_and_update(
            {"_id": f"auction"}, {"$inc": {"next": 1}}, upsert=True
        )
        if counter is None:
            counter = {"next": 0}

        await self.bot.mongo.db.pokemon.update_one(
            {"_id": pokemon.id},
            {
                "$set": {
                    "owned_by": "auction",
                    "auction_data": {
                        "_id": counter["next"],
                        "guild_id": ctx.guild.id,
                        "current_bid": starting_bid - bid_increment,
                        "bid_increment": bid_increment,
                        "bidder_id": None,
                        "ends": ends,
                    },
                }
            },
        )

        embed = self.make_base_embed(ctx.author, pokemon, counter["next"])
        auction_info = (
            f"**Starting Bid:** {starting_bid:,} Pokécoins",
            f"**Bid Increment:** {bid_increment:,} Pokécoins",
        )
        embed.add_field(name="Auction Details", value="\n".join(auction_info))
        embed.set_footer(
            text=f"Bid with `{ctx.clean_prefix}auction bid {counter['next']} <bid>`\n"
            f"Ends in {converters.strfdelta(ends - datetime.utcnow())} at"
        )
        embed.timestamp = ends

        await auction_channel.send(embed=embed)
        await ctx.send(f"Auctioning your **{pokemon.iv_percentage:.2%} {pokemon.species} No. {pokemon.idx}**.")

    @checks.has_started()
    @auction.command()
    async def lowerstart(self, ctx, auction: AuctionConverter, new_start: int):
        """Lower the starting bid for your auction."""

        if ctx.author.id != auction["owner_id"]:
            return await ctx.send("You can only lower the starting bid on your own auction.")
        if auction["auction_data"]["bidder_id"] is not None:
            return await ctx.send("Someone has already bid on this auction.")
        if auction["auction_data"]["current_bid"] + auction["auction_data"]["bid_increment"] < new_start:
            return await ctx.send("You may only lower the starting bid, not increase it.")
        if auction["auction_data"]["bid_increment"] > new_start:
            return await ctx.send("You may not set the new starting bid to a value less than your bid increment.")

        # Verification

        pokemon = self.bot.mongo.Pokemon.build_from_mongo(auction)
        result = await ctx.confirm(
            f"Do you want to lower starting bid to **{new_start} Pokécoins** on the **{pokemon:pl}**?"
        )
        if result is None:
            return await ctx.send("Time's up. Aborted.")
        if result is False:
            return await ctx.send("Aborted.")

        # Go
        guild = await self.bot.mongo.fetch_guild(ctx.guild)

        embed = self.make_base_embed(ctx.author, pokemon, auction["auction_data"]["_id"])
        auction_info = (
            f"**Starting Bid:** {new_start:,} Pokécoins",
            f"**Bid Increment:** {auction['auction_data']['bid_increment']:,} Pokécoins",
        )
        embed.add_field(name="Auction Details", value="\n".join(auction_info))
        embed.set_footer(
            text=f"Bid with `{ctx.clean_prefix}auction bid {auction['auction_data']['_id']} <bid>`\n"
            f"Ends in {converters.strfdelta(auction['auction_data']['ends'] - datetime.utcnow())} at"
        )
        embed.timestamp = auction["auction_data"]["ends"]

        auction_channel = ctx.guild.get_channel(guild.auction_channel)
        if auction_channel is not None:
            self.bot.loop.create_task(auction_channel.send(embed=embed))

        await self.bot.mongo.db.pokemon.update_one(
            {"owned_by": "auction", "auction_data._id": auction["auction_data"]["_id"]},
            {"$set": {"auction_data.current_bid": new_start - auction["auction_data"]["bid_increment"]}},
        )
        await ctx.send(f"Lowered the starting bid on your auction to **{new_start:,} Pokécoins**.")

    @checks.has_started()
    @checks.is_not_in_trade()
    @commands.max_concurrency(1, per=commands.BucketType.user)
    @auction.command(aliases=("b",))
    async def bid(self, ctx, auction: AuctionConverter, bid: int):
        """Bid on an auction."""

        if ctx.author.id == auction["owner_id"]:
            return await ctx.send("You can't bid on your own auction.")
        if ctx.author.id == auction["auction_data"]["bidder_id"]:
            return await ctx.send("You are already the highest bidder.")
        if bid < auction["auction_data"]["current_bid"] + auction["auction_data"]["bid_increment"]:
            return await ctx.send(
                f"Your bid must be at least {auction['auction_data']['current_bid'] + auction['auction_data']['bid_increment']:,} Pokécoins."
            )

        guild = await self.bot.mongo.fetch_guild(ctx.guild)
        member = await self.bot.mongo.fetch_member_info(ctx.author)
        if member.balance < bid:
            return await ctx.send("You don't have enough Pokécoins for that!")
        pokemon = self.bot.mongo.Pokemon.build_from_mongo(auction)

        # confirm

        result = await ctx.confirm(f"Do you want to bid **{bid:,} Pokécoins** on the **{pokemon:pl}**?")
        if result is None:
            return await ctx.send("Time's up. Aborted.")
        if result is False:
            return await ctx.send("Aborted.")

        # go!

        auction = await self.bot.mongo.db.pokemon.find_one(
            {"owned_by": "auction", "auction_data._id": auction["auction_data"]["_id"]}
        )

        if auction is None:
            return await ctx.send("Couldn't find that auction!")

        if bid < auction["auction_data"]["current_bid"] + auction["auction_data"]["bid_increment"]:
            return await ctx.send(
                f"Your bid must be at least {auction['auction_data']['current_bid'] + auction['auction_data']['bid_increment']:,} Pokécoins."
            )

        if auction["auction_data"]["ends"] < datetime.utcnow():
            return await ctx.send("This auction has ended.")

        member = await self.bot.mongo.fetch_member_info(ctx.author)
        if member.balance < bid:
            return await ctx.send("You don't have enough Pokécoins for that!")

        # ok, bid

        res = await self.bot.mongo.db.member.find_one_and_update({"_id": ctx.author.id}, {"$inc": {"balance": -bid}})
        await self.bot.redis.hdel("db:member", ctx.author.id)
        if res["balance"] < bid:
            await self.bot.mongo.update_member(ctx.author, {"$inc": {"balance": bid}})
            return await ctx.send("You don't have enough Pokécoins for that!")

        # check to make sure still there

        update = {
            "$set": {
                "auction_data.current_bid": bid,
                "auction_data.bidder_id": ctx.author.id,
            }
        }

        if datetime.utcnow() + timedelta(minutes=5) > auction["auction_data"]["ends"]:
            update["$set"]["auction_data.ends"] = datetime.utcnow() + timedelta(minutes=5)

        r = await self.bot.mongo.db.pokemon.update_one(
            {"owned_by": "auction", "auction_data._id": auction["auction_data"]["_id"]}, update
        )

        if r.modified_count == 0:
            await self.bot.mongo.update_member(ctx.author, {"$inc": {"balance": bid}})
            return await ctx.send("That auction has already ended.")

        if auction["auction_data"]["bidder_id"] is not None:
            await self.bot.mongo.update_member(
                auction["auction_data"]["bidder_id"], {"$inc": {"balance": auction["auction_data"]["current_bid"]}}
            )
            self.bot.loop.create_task(
                self.bot.send_dm(
                    auction["auction_data"]["bidder_id"],
                    f"You have been outbid on the **{pokemon:pl}** (Auction #{auction['auction_data']['_id']}). New bid: {bid} pokécoins.",
                )
            )

        await ctx.send(
            f"You bid **{bid:,} Pokécoins** on the **{pokemon:pl}** (Auction #{auction['auction_data']['_id']})."
        )

        # send embed

        host = await self.try_get_member(ctx.guild, auction["owner_id"])

        embed = self.make_base_embed(host, pokemon, auction["auction_data"]["_id"])

        auction_info = (
            f"**Current Bid:** {bid:,} Pokécoins",
            f"**Bidder:** {ctx.author.mention}",
            f"**Bid Increment:** {auction['auction_data']['bid_increment']:,} Pokécoins",
        )
        embed.add_field(name="Auction Details", value="\n".join(auction_info))
        embed.set_footer(
            text=f"Bid with `{ctx.clean_prefix}auction bid {auction['auction_data']['_id']} <bid>`\n"
            f"Ends in {converters.strfdelta(auction['auction_data']['ends'] - datetime.utcnow())} at"
        )
        embed.timestamp = auction["auction_data"]["ends"]

        auction_channel = ctx.guild.get_channel(guild.auction_channel)
        if auction_channel is not None:
            self.bot.loop.create_task(auction_channel.send(embed=embed))

    # TODO put all these flags into a single decorator

    # Filter
    @flags.add_flag("page", nargs="?", type=int, default=1)
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
    @flags.add_flag("--move", nargs="+", action="append")
    @flags.add_flag("--learns", nargs="*", action="append")

    # IV
    @flags.add_flag("--level", nargs="+", action="append")
    @flags.add_flag("--hpiv", nargs="+", action="append")
    @flags.add_flag("--atkiv", nargs="+", action="append")
    @flags.add_flag("--defiv", nargs="+", action="append")
    @flags.add_flag("--spatkiv", nargs="+", action="append")
    @flags.add_flag("--spdefiv", nargs="+", action="append")
    @flags.add_flag("--spdiv", nargs="+", action="append")
    @flags.add_flag("--iv", nargs="+", action="append")

    # Duplcate IV's
    @flags.add_flag("--triple", "--three", type=int)
    @flags.add_flag("--quadruple", "--four", "--quadra", "--quad", "--tetra", type=int)
    @flags.add_flag("--pentuple", "--quintuple", "--penta", "--pent", "--five", type=int)
    @flags.add_flag("--hextuple", "--sextuple", "--hexa", "--hex", "--six", type=int)

    # Skip/limit
    @flags.add_flag("--skip", type=int)
    @flags.add_flag("--limit", type=int)

    # Auctions
    @flags.add_flag(
        "--order",
        choices=[a + b for a in ("iv", "bid", "level", "ends") for b in ("+", "-", "")],
        default="ends+",
    )
    @flags.add_flag("--mine", "--listings", action="store_true")
    @flags.add_flag("--bids", action="store_true")
    @flags.add_flag("--ends", type=converters.to_timedelta)
    @checks.has_started()
    @commands.cooldown(1, 5, commands.BucketType.user)
    @auction.command(aliases=("s",), cls=flags.FlagCommand)
    async def search(self, ctx, **flags):
        """Search pokémon from auctions."""

        if flags["page"] < 1:
            return await ctx.send("Page must be positive!")

        def map_field(field):
            if field == "_id":
                return "auction_data._id"
            return field

        aggregations = await self.bot.get_cog("Pokemon").create_filter(
            flags, ctx, order_by=flags["order"], map_field=map_field
        )

        if aggregations is None:
            return

        # Filter pokemon

        now = datetime.utcnow()

        def padn(p, n):
            return " " * (len(str(n)) - len(str(p))) + str(p)

        def prepare_page(menu, items):
            menu.maxn = max(auction["auction_data"]["_id"] for auction in items)

        def format_item(menu, auction):
            pokemon = self.bot.mongo.Pokemon.build_from_mongo(auction)
            if auction["auction_data"]["bidder_id"] is not None:
                return (
                    f"`{padn(auction['auction_data']['_id'], menu.maxn)}`　**{pokemon:Li}**　•　"
                    f"{pokemon.iv_total / 186:.2%}　•　CB: {auction['auction_data']['current_bid']:,}　•　"
                    f"BI: {auction['auction_data']['bid_increment']:,} pc　•　{converters.strfdelta(auction['auction_data']['ends'] - now, max_len=1)}"
                )
            else:
                return (
                    f"`{padn(auction['auction_data']['_id'], menu.maxn)}`　**{pokemon:Li}**　•　"
                    f"{pokemon.iv_total / 186:.2%}　•　SB: {auction['auction_data']['current_bid'] + auction['auction_data']['bid_increment']:,} pc　•　"
                    f"{converters.strfdelta(auction['auction_data']['ends'] - now, max_len=1)}"
                )

        count = await self.bot.mongo.fetch_auction_count(ctx.guild, aggregations)
        pokemon = self.bot.mongo.fetch_auction_list(ctx.guild, aggregations)

        pages = pagination.ContinuablePages(
            pagination.AsyncListPageSource(
                pokemon,
                title=f"Auctions in {ctx.guild.name}",
                prepare_page=prepare_page,
                format_item=format_item,
                per_page=15,
                count=count,
            )
        )
        pages.current_page = flags["page"] - 1
        self.bot.menus[ctx.author.id] = pages

        try:
            await pages.start(ctx)
        except IndexError:
            await ctx.send("No auctions found.")

    # TODO make all groups case insensitive

    @checks.has_started()
    @commands.cooldown(3, 5, commands.BucketType.user)
    @auction.command(aliases=("i",))
    async def info(self, ctx, auction: AuctionConverter):
        """View a pokémon from an auction."""

        pokemon = self.bot.mongo.Pokemon.build_from_mongo(auction)
        host = await self.try_get_member(ctx.guild, auction["owner_id"])
        embed = self.make_base_embed(host, pokemon, auction["auction_data"]["_id"])

        if auction["auction_data"]["bidder_id"] is None:
            auction_info = (
                f"**Starting Bid:** {auction['auction_data']['current_bid'] + auction['auction_data']['bid_increment']:,} Pokécoins",
                f"**Bid Increment:** {auction['auction_data']['bid_increment']:,} Pokécoins",
            )
        else:
            bidder = await self.try_get_member(ctx.guild, auction["auction_data"]["bidder_id"])
            auction_info = (
                f"**Current Bid:** {auction['auction_data']['current_bid']:,} Pokécoins",
                f"**Bidder:** {bidder.mention}",
                f"**Bid Increment:** {auction['auction_data']['bid_increment']:,} Pokécoins",
            )

        add_moves_field(pokemon.moves, embed, self.bot)

        embed.add_field(name="Auction Details", value="\n".join(auction_info))
        embed.set_footer(
            text=f"Bid with `{ctx.clean_prefix}auction bid {auction['auction_data']['_id']} <bid>`\n"
            f"Ends in {converters.strfdelta(auction['auction_data']['ends'] - datetime.utcnow())} at"
        )
        embed.timestamp = auction["auction_data"]["ends"]

        await ctx.send(embed=embed)

    def cog_unload(self):
        self.check_auctions.cancel()


async def setup(bot: commands.Bot):
    await bot.add_cog(Auctions(bot))
