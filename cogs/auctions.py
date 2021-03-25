import asyncio
from itertools import starmap

from discord.errors import HTTPException
from helpers.utils import FakeUser
import math
from datetime import datetime, timedelta

import discord
import humanfriendly
import pymongo
from discord.ext import commands, flags, tasks

from helpers import checks, converters, pagination


async def query_member(guild, id):
    r = await guild.query_members(user_ids=(id,))
    if len(r) == 0:
        return None
    return r[0]


class AuctionConverter(commands.Converter):
    async def convert(self, ctx, arg):
        try:
            auction = await ctx.bot.mongo.Auction.find_one(
                {"guild_id": ctx.guild.id, "_id": int(arg)}
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
        self.sem = asyncio.Semaphore(1)

    @tasks.loop(minutes=1)
    async def check_auctions(self):
        await self.bot.wait_until_ready()
        auctions = self.bot.mongo.Auction.find({"ends": {"$lt": datetime.utcnow()}})
        async for auction in auctions:
            try:
                await self.end_auction(auction)
            except Exception as e:
                print(e)
                continue

    async def end_auction(self, auction):
        if (auction_guild := self.bot.get_guild(auction.guild_id)) is None:
            return

        guild = await self.bot.mongo.fetch_guild(auction_guild)

        if auction.bidder_id is None:
            auction.bidder_id = auction.user_id
            auction.current_bid = 0

        host = (
            self.bot.get_user(auction.user_id)
            or await query_member(auction_guild, auction.user_id)
            or FakeUser(auction.user_id)
        )
        bidder = (
            self.bot.get_user(auction.bidder_id)
            or await query_member(auction_guild, auction.bidder_id)
            or FakeUser(auction.bidder_id)
        )

        embed = self.make_base_embed(host, auction.pokemon, auction.id)
        embed.title = "[SOLD] " + embed.title
        auction_info = (
            f"**Winning Bid:** {auction.current_bid:,} Pokécoins",
            f"**Bidder:** {bidder.mention}",
        )
        embed.add_field(name="Auction Details", value="\n".join(auction_info))
        embed.set_footer(text=f"The auction has ended.")

        auction_channel = auction_guild.get_channel(guild.auction_channel)
        if auction_channel is not None:
            self.bot.loop.create_task(auction_channel.send(embed=embed))

        # ok, bid

        try:
            await self.bot.mongo.db.pokemon.insert_one(
                {
                    **auction.pokemon.to_mongo(),
                    "owner_id": auction.bidder_id,
                    "idx": await self.bot.mongo.fetch_next_idx(bidder),
                }
            )
        except pymongo.errors.DuplicateKeyError:
            return
        await self.bot.mongo.db.auction.delete_one({"_id": auction.id})
        await self.bot.mongo.update_member(host, {"$inc": {"balance": auction.current_bid}})

        self.bot.loop.create_task(
            host.send(
                f"The auction for your **{auction.pokemon.iv_percentage:.2%} {auction.pokemon.species}** ended with a highest bid of **{auction.current_bid:,}** Pokécoins (Auction #{auction.id})."
            )
        )
        self.bot.loop.create_task(
            bidder.send(
                f"You won the auction for the **{auction.pokemon.iv_percentage:.2%} {auction.pokemon.species}** with a bid of **{auction.current_bid:,}** Pokécoins (Auction #{auction.id})."
            )
        )

        if auction.current_bid > 0:
            try:
                await self.bot.mongo.db.logs.insert_one(
                    {
                        "event": "auction",
                        "user": auction.bidder_id,
                        "item": auction.pokemon.id,
                        "seller_id": auction.user_id,
                        "price": auction.current_bid,
                    }
                )
            except:
                print("Error trading auction logs.")

    def make_base_embed(self, author, pokemon, auction_id):
        embed = discord.Embed(color=0x9CCFFF)
        embed.set_author(name=str(author), icon_url=author.avatar_url)
        embed.title = f"Auction #{auction_id} • {pokemon:ln}"

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
            return await ctx.send(
                "Sorry, you cannot start auctions outside of the main server at this time."
            )

        if pokemon is None:
            return await ctx.send("Couldn't find that pokémon!")

        if not (0 < starting_bid <= 1000000):
            return await ctx.send("The starting bid is not valid.")

        if not (0 < bid_increment <= starting_bid):
            return await ctx.send("The bid increment is not valid.")

        if duration > timedelta(weeks=1):
            return await ctx.send("The max duration is 1 week.")

        guild = await self.bot.mongo.fetch_guild(ctx.guild)
        if (
            guild.auction_channel is None
            or (auction_channel := ctx.guild.get_channel(guild.auction_channel)) is None
        ):
            return await ctx.send(
                "Auctions have not been set up in this server. Have a server administrator do `p!auction channel #channel`."
            )

        member = await self.bot.mongo.fetch_member_info(ctx.author)

        if member.selected_id == pokemon.id:
            return await ctx.send(f"{pokemon.idx}: You can't auction your selected pokémon!")

        if pokemon.favorite:
            return await ctx.send(f"{pokemon.idx}: You can't auction a favorited pokémon!")

        # confirm

        await ctx.send(
            f"You are auctioning your **{pokemon.iv_percentage:.2%} {pokemon.species} No. {pokemon.idx}**:\n"
            f"**Starting Bid:** {starting_bid:,} Pokécoins\n"
            f"**Bid Increment:** {bid_increment:,} Pokécoins\n"
            f"**Duration:** {humanfriendly.format_timespan(duration.total_seconds())}\n"
            "Auctions are server-specific and cannot be canceled. Are you sure? [y/N]"
        )

        # TODO factor confirmations into custom context

        def check(m):
            return m.channel.id == ctx.channel.id and m.author.id == ctx.author.id

        try:
            msg = await self.bot.wait_for("message", timeout=30, check=check)
        except asyncio.TimeoutError:
            return await ctx.send("Time's up. Aborted.")

        if msg.content.lower() != "y":
            return await ctx.send("Aborted.")

        # create auction

        if await self.bot.get_cog("Trading").is_in_trade(ctx.author):
            return await ctx.send("You can't do that in a trade!")

        # TODO put counters in mongo cog

        counter = await self.bot.mongo.db.counter.find_one_and_update(
            {"_id": f"auction"}, {"$inc": {"next": 1}}, upsert=True
        )
        if counter is None:
            counter = {"next": 0}

        ends = datetime.utcnow() + duration

        embed = self.make_base_embed(ctx.author, pokemon, counter["next"])
        auction_info = (
            f"**Starting Bid:** {starting_bid:,} Pokécoins",
            f"**Bid Increment:** {bid_increment:,} Pokécoins",
        )
        embed.add_field(name="Auction Details", value="\n".join(auction_info))
        embed.set_footer(
            text=f"Bid with `{ctx.prefix}auction bid {counter['next']} <bid>`\n"
            f"Ends in {converters.strfdelta(ends - datetime.utcnow())} at"
        )
        embed.timestamp = ends

        await self.bot.mongo.db.auction.insert_one(
            {
                "_id": counter["next"],
                "guild_id": ctx.guild.id,
                "pokemon": pokemon.to_mongo(),
                "user_id": ctx.author.id,
                "current_bid": starting_bid - bid_increment,
                "bid_increment": bid_increment,
                "bidder_id": None,
                "ends": ends,
            }
        )
        await self.bot.mongo.db.pokemon.delete_one({"_id": pokemon.id})

        await auction_channel.send(embed=embed)
        await ctx.send(
            f"Auctioning your **{pokemon.iv_percentage:.2%} {pokemon.species} No. {pokemon.idx}**."
        )

    @checks.has_started()
    @auction.command()
    async def lowerstart(self, ctx, auction: AuctionConverter, new_start: int):
        """Lower the starting bid for your auction."""

        if ctx.author.id != auction.user_id:
            return await ctx.send("You can only lower the starting bid on your own auction.")
        if auction.bidder_id is not None:
            return await ctx.send("Someone has already bid on this auction.")
        if auction.current_bid + auction.bid_increment < new_start:
            return await ctx.send("You may only lower the starting bid, not increase it.")
        if auction.bid_increment > new_start:
            return await ctx.send(
                "You may not set the new starting bid to a value less than your bid increment."
            )

        # Verification

        await ctx.send(
            f"Do you want to lower starting bid to **{new_start} Pokécoins** on the **{auction.pokemon.iv_percentage:.2%} {auction.pokemon:s}**? [y/N]"
        )

        def check(m):
            return m.channel.id == ctx.channel.id and m.author.id == ctx.author.id

        try:
            msg = await self.bot.wait_for("message", timeout=30, check=check)
        except asyncio.TimeoutError:
            return await ctx.send("Time's up. Aborted.")

        if msg.content.lower() != "y":
            return await ctx.send("Aborted.")

        # Go
        guild = await self.bot.mongo.fetch_guild(ctx.guild)

        embed = self.make_base_embed(ctx.author, auction.pokemon, auction.id)
        auction_info = (
            f"**Starting Bid:** {new_start:,} Pokécoins",
            f"**Bid Increment:** {auction.bid_increment:,} Pokécoins",
        )
        embed.add_field(name="Auction Details", value="\n".join(auction_info))
        embed.set_footer(
            text=f"Bid with `{ctx.prefix}auction bid {auction.id} <bid>`\n"
            f"Ends in {converters.strfdelta(auction.ends - datetime.utcnow())} at"
        )
        embed.timestamp = auction.ends

        auction_channel = ctx.guild.get_channel(guild.auction_channel)
        if auction_channel is not None:
            self.bot.loop.create_task(auction_channel.send(embed=embed))

        await self.bot.mongo.db.auction.update_one(
            {"_id": auction.id},
            {"$set": {"current_bid": new_start - auction.bid_increment}},
        )
        await ctx.send(f"Lowered the starting bid on your auction to **{new_start:,} Pokécoins**.")

    @checks.has_started()
    @commands.max_concurrency(1, per=commands.BucketType.user)
    @auction.command(aliases=("b",))
    async def bid(self, ctx, auction: AuctionConverter, bid: int):
        """Bid on an auction."""

        if ctx.author.id == auction.user_id:
            return await ctx.send("You can't bid on your own auction.")
        if ctx.author.id == auction.bidder_id:
            return await ctx.send("You are already the highest bidder.")
        if bid < auction.current_bid + auction.bid_increment:
            return await ctx.send(
                f"Your bid must be at least {auction.current_bid + auction.bid_increment:,} Pokécoins."
            )

        guild = await self.bot.mongo.fetch_guild(ctx.guild)
        member = await self.bot.mongo.fetch_member_info(ctx.author)
        if member.balance < bid:
            return await ctx.send("You don't have enough Pokécoins for that!")

        # confirm

        await ctx.send(
            f"Do you want to bid **{bid:,} Pokécoins** on the **{auction.pokemon.iv_percentage:.2%} {auction.pokemon:s}**? [y/N]"
        )

        def check(m):
            return m.channel.id == ctx.channel.id and m.author.id == ctx.author.id

        try:
            msg = await self.bot.wait_for("message", timeout=30, check=check)
        except asyncio.TimeoutError:
            return await ctx.send("Time's up. Aborted.")

        if msg.content.lower() != "y":
            return await ctx.send("Aborted.")

        # go!

        async with self.sem:
            auction = await self.bot.mongo.Auction.find_one(
                {"guild_id": ctx.guild.id, "_id": auction.id}
            )

            if auction is None:
                return await ctx.send("Couldn't find that auction!")

            if bid < auction.current_bid + auction.bid_increment:
                return await ctx.send(
                    f"Your bid must be at least {auction.current_bid + auction.bid_increment:,} Pokécoins."
                )

            member = await self.bot.mongo.fetch_member_info(ctx.author)
            if member.balance < bid:
                return await ctx.send("You don't have enough Pokécoins for that!")

            # send embed

            host = (
                self.bot.get_user(auction.user_id)
                or await query_member(ctx.guild, auction.user_id)
                or FakeUser(auction.user_id)
            )

            embed = self.make_base_embed(host, auction.pokemon, auction.id)

            auction_info = (
                f"**Current Bid:** {bid:,} Pokécoins",
                f"**Bidder:** {ctx.author.mention}",
                f"**Bid Increment:** {auction.bid_increment:,} Pokécoins",
            )
            embed.add_field(name="Auction Details", value="\n".join(auction_info))
            embed.set_footer(
                text=f"Bid with `{ctx.prefix}auction bid {auction.id} <bid>`\n"
                f"Ends in {converters.strfdelta(auction.ends - datetime.utcnow())} at"
            )
            embed.timestamp = auction.ends

            update = {
                "$set": {
                    "current_bid": bid,
                    "bidder_id": ctx.author.id,
                }
            }

            if datetime.utcnow() + timedelta(minutes=5) > auction.ends:
                update["$set"]["ends"] = datetime.utcnow() + timedelta(minutes=5)

            # check to make sure still there

            r = await self.bot.mongo.db.auction.update_one({"_id": auction.id}, update)

            if r.modified_count == 0:
                return await ctx.send("That auction has already ended.")

            auction_channel = ctx.guild.get_channel(guild.auction_channel)
            if auction_channel is not None:
                self.bot.loop.create_task(auction_channel.send(embed=embed))

            # ok, bid

            await self.bot.mongo.update_member(ctx.author, {"$inc": {"balance": -bid}})

            if auction.bidder_id is not None:
                await self.bot.mongo.update_member(
                    auction.bidder_id, {"$inc": {"balance": auction.current_bid}}
                )
                priv = await self.bot.http.start_private_message(auction.bidder_id)
                self.bot.loop.create_task(
                    self.bot.http.send_message(
                        priv["id"],
                        f"You have been outbid on the **{auction.pokemon.iv_percentage:.2%} {auction.pokemon.species}** (Auction #{auction.id}).",
                    )
                )
            self.bot.loop.create_task(
                ctx.send(
                    f"You bid **{bid:,} Pokécoins** on the **{auction.pokemon.iv_percentage:.2%} {auction.pokemon.species}** (Auction #{auction.id})."
                )
            )

    # TODO put all these flags into a single decorator

    # Filter
    @flags.add_flag("page", nargs="?", type=int, default=1)
    @flags.add_flag("--shiny", action="store_true")
    @flags.add_flag("--alolan", action="store_true")
    @flags.add_flag("--mythical", action="store_true")
    @flags.add_flag("--legendary", action="store_true")
    @flags.add_flag("--ub", action="store_true")
    @flags.add_flag("--event", action="store_true")
    @flags.add_flag("--mega", action="store_true")
    @flags.add_flag("--embedcolor", "--ec", action="store_true")
    @flags.add_flag("--name", "--n", nargs="+", action="append")
    @flags.add_flag("--type", "--t", type=str, action="append")

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

        aggregations = await self.bot.get_cog("Pokemon").create_filter(
            flags, ctx, order_by=flags["order"]
        )

        if aggregations is None:
            return

        # Filter pokemon

        now = datetime.utcnow()

        def padn(p, n):
            return " " * (len(str(n)) - len(str(p.id))) + str(p.id)

        def prepare_page(menu, items):
            menu.maxn = max(x.id for x in items)

        def format_item(menu, x):
            if x.bidder_id is not None:
                return (
                    f"`{padn(x, menu.maxn)}`　**{x.pokemon:Li}**　•　"
                    f"{x.pokemon.iv_total / 186:.2%}　•　CB: {x.current_bid:,}　•　"
                    f"BI: {x.bid_increment:,} pc　•　{converters.strfdelta(x.ends - now, max_len=1)}"
                )
            else:
                return (
                    f"`{padn(x, menu.maxn)}`　**{x.pokemon:Li}**　•　"
                    f"{x.pokemon.iv_total / 186:.2%}　•　SB: {x.current_bid + x.bid_increment:,} pc　•　"
                    f"{converters.strfdelta(x.ends - now, max_len=1)}"
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

        host = (
            self.bot.get_user(auction.user_id)
            or await query_member(ctx.guild, auction.user_id)
            or FakeUser(auction.user_id)
        )

        embed = self.make_base_embed(host, auction.pokemon, auction.id)

        if auction.bidder_id is None:
            auction_info = (
                f"**Starting Bid:** {auction.current_bid + auction.bid_increment:,} Pokécoins",
                f"**Bid Increment:** {auction.bid_increment:,} Pokécoins",
            )
        else:
            bidder = (
                self.bot.get_user(auction.bidder_id)
                or await query_member(ctx.guild, auction.bidder_id)
                or FakeUser(auction.bidder_id)
            )

            auction_info = (
                f"**Current Bid:** {auction.current_bid:,} Pokécoins",
                f"**Bidder:** {bidder.mention}",
                f"**Bid Increment:** {auction.bid_increment:,} Pokécoins",
            )
        embed.add_field(name="Auction Details", value="\n".join(auction_info))
        embed.set_footer(
            text=f"Bid with `{ctx.prefix}auction bid {auction.id} <bid>`\n"
            f"Ends in {converters.strfdelta(auction.ends - datetime.utcnow())} at"
        )
        embed.timestamp = auction.ends

        await ctx.send(embed=embed)

    def cog_unload(self):
        self.check_auctions.cancel()


def setup(bot):
    bot.add_cog(Auctions(bot))
