import contextlib
from datetime import datetime, timedelta

import discord
import humanfriendly
from discord.ext import commands, tasks

from helpers import checks, constants, converters, flags, pagination
from helpers.utils import FakeUser


class AuctionConverter(commands.Converter):
    async def convert(self, ctx, arg):
        try:
            auction = await ctx.bot.mongo.db.pokemon.find_one(
                {"owned_by": "auction", "auction_data.guild_id": ctx.guild.id, "auction_data._id": int(arg)}
            )
        except ValueError:
            raise commands.BadArgument(ctx._("invalid-auction-id"))

        if auction is None:
            raise commands.BadArgument(ctx._("no-such-auction-with-id"))

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
            embed.title = self.bot._("auction-title-sold", pokemon=f"{pokemon:l}", id=auction["auction_data"]["_id"])
            auction_ended_info = self.bot._(
                "auction-ended-details", coins=auction["auction_data"]["current_bid"], bidder=bidder.mention
            )
            embed.add_field(name=self.bot._("auction-details"), value="\n".join(auction_ended_info))
            embed.set_footer(text=self.bot._("auction-ended"))

            if auction_channel := auction_guild.get_channel(guild.auction_channel):
                with contextlib.suppress(discord.HTTPException):
                    await auction_channel.send(embed=embed)
            with contextlib.suppress(discord.HTTPException):
                msg = self.bot._(
                    "auction-ended",
                    id=auction["auction_data"]["_id"],
                    bid=f"{auction['auction_data']['current_bid']:,}",
                    pokemon=f"{pokemon:pl}",
                )
                await host.send(msg)
            with contextlib.suppress(discord.HTTPException):
                msg = self.bot._(
                    "won-auction",
                    pokemon=f"{pokemon:pl}",
                    bid=f"{auction['auction_data']['current_bid']:,}",
                    id=auction["auction_data"]["_id"],
                )
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
                msg = self.bot._("auction-ended-no-bids", id=auction["auction_data"]["_id"], pokemon=f"{pokemon:pl}")
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
            title=self.bot._("auction-title", id=auction_id, pokemon=f"{pokemon:l}"),
            color=pokemon.color or constants.PINK,
        )
        embed.set_author(name=str(author), icon_url=author.display_avatar.url)

        if pokemon.shiny:
            embed.set_thumbnail(url=pokemon.species.shiny_image_url)
        else:
            embed.set_thumbnail(url=pokemon.species.image_url)

        info = self.bot._(
            "auction-info",
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
        )

        if pokemon.held_item:
            item = self.bot.data.item_by_number(pokemon.held_item)
            emote = ""
            if item.emote is not None:
                emote = getattr(self.bot.sprites, item.emote) + " "
            info += self.bot._("auction-info-held-item", item=f"{emote}{item.name}")

        embed.add_field(name=self.bot._("auction-pokemon-details-field-name"), value="\n".join(info))

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
        await ctx.send(ctx._("changed-auction-channel", channel=channel))

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
            return await ctx.send(ctx._("must-start-auctions-in-main-server"))

        if pokemon is None:
            return await ctx.send(ctx._("unknown-pokemon"))

        if not (0 < starting_bid <= 1000000):
            return await ctx.send(ctx._("invalid-starting-bid"))

        if not (0 < bid_increment <= starting_bid):
            return await ctx.send(ctx._("invalid-bid-increment"))

        if duration > timedelta(weeks=1):
            return await ctx.send(ctx._("max-auction-duration", weeks=1))

        guild = await self.bot.mongo.fetch_guild(ctx.guild)
        if guild.auction_channel is None or (auction_channel := ctx.guild.get_channel(guild.auction_channel)) is None:
            return await ctx.send(ctx._("auctions-not-set-up"))

        member = await self.bot.mongo.fetch_member_info(ctx.author)

        if member.selected_id == pokemon.id:
            return await ctx.send(ctx._("cannot-auction-selected", index=pokemon.idx))

        if pokemon.favorite:
            return await ctx.send(ctx._("cannot-auction-favorited", index=pokemon.idx))

        # confirm

        result = await ctx.confirm(
            ctx._(
                "auction-confirmation",
                ivPercentage=pokemon.iv_percentage * 100,
                pokemon=str(pokemon.species),
                index=pokemon.idx,
                startingBid=starting_bid,
                increment=bid_increment,
                duration=humanfriendly.format_timespan(duration.total_seconds()),
            )
        )
        if result is None:
            return await ctx.send(ctx._("times-up"))
        if result is False:
            return await ctx.send(ctx._("aborted"))

        # create auction

        if await self.bot.get_cog("Trading").is_in_trade(ctx.author):
            return await ctx.send(ctx._("forbidden-during-trade"))

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
        embed.add_field(
            name=ctx._("auction-details"),
            value=ctx._("auction-info-bidding", startingBid=starting_bid, increment=bid_increment),
        )
        embed.set_footer(
            ctx._(
                "auction-bid-cta",
                command=f"auction bid {counter['next']}",
                delta=converters.strfdelta(ends - datetime.utcnow()),
            )
        )
        embed.timestamp = ends

        await auction_channel.send(embed=embed)

        await ctx.send(
            ctx._(
                "auction-confirmed",
                index=pokemon.idx,
                pokemon=str(pokemon.species),
                ivPercentage=pokemon.iv_percentage * 100,
            )
        )

    @checks.has_started()
    @auction.command()
    async def lowerstart(self, ctx, auction: AuctionConverter, new_start: int):
        """Lower the starting bid for your auction."""

        if ctx.author.id != auction["owner_id"]:
            return await ctx.send(ctx._("can-only-lower-own-auctions"))
        if auction["auction_data"]["bidder_id"] is not None:
            return await ctx.send(ctx._("someone-already-bid"))
        if auction["auction_data"]["current_bid"] + auction["auction_data"]["bid_increment"] < new_start:
            return await ctx.send(ctx._("cannot-increase-starting-bid"))
        if auction["auction_data"]["bid_increment"] > new_start:
            return await ctx.send(ctx._("starting-bid-cannot-be-lower-than-increment"))

        # Verification

        pokemon = self.bot.mongo.Pokemon.build_from_mongo(auction)
        result = await ctx.confirm(ctx._("lowerstart-confirmation", newStart=new_start, pokemon=f"{pokemon:pl}"))
        if result is None:
            return await ctx.send(ctx._("times-up"))
        if result is False:
            return await ctx.send(ctx._("aborted"))

        # Go
        guild = await self.bot.mongo.fetch_guild(ctx.guild)

        embed = self.make_base_embed(ctx.author, pokemon, auction["auction_data"]["_id"])
        auction_info = ctx._(
            "auction-info-bidding", startingBid=new_start, increment=auction["auction_data"]["bid_increment"]
        )
        embed.add_field(name=ctx._("auction-details"), value="\n".join(auction_info))
        embed.set_footer(
            ctx._(
                "auction-bid-cta",
                command=f"auction bid {auction['auction_data']['_id']}",
                delta=converters.strfdelta(auction["auction_data"]["ends"] - datetime.utcnow()),
            )
        )
        embed.timestamp = auction["auction_data"]["ends"]

        auction_channel = ctx.guild.get_channel(guild.auction_channel)
        if auction_channel is not None:
            self.bot.loop.create_task(auction_channel.send(embed=embed))

        await self.bot.mongo.db.pokemon.update_one(
            {"owned_by": "auction", "auction_data._id": auction["auction_data"]["_id"]},
            {"$set": {"auction_data.current_bid": new_start - auction["auction_data"]["bid_increment"]}},
        )
        await ctx.send(ctx._("lowerstart-completed", newStart=f"{new_start:,}"))

    @checks.has_started()
    @checks.is_not_in_trade()
    @commands.max_concurrency(1, per=commands.BucketType.user)
    @auction.command(aliases=("b",))
    async def bid(self, ctx, auction: AuctionConverter, bid: int):
        """Bid on an auction."""

        if ctx.author.id == auction["owner_id"]:
            return await ctx.send(ctx._("cannot-self-bid"))
        if ctx.author.id == auction["auction_data"]["bidder_id"]:
            return await ctx.send(ctx._("already-highest-bidder"))
        if bid < auction["auction_data"]["current_bid"] + auction["auction_data"]["bid_increment"]:
            return await ctx.send(
                ctx._(
                    "bid-minimum",
                    minimum=auction["auction_data"]["current_bid"] + auction["auction_data"]["bid_increment"],
                )
            )

        guild = await self.bot.mongo.fetch_guild(ctx.guild)
        member = await self.bot.mongo.fetch_member_info(ctx.author)
        if member.balance < bid:
            return await ctx.send(ctx._("not-enough-coins"))
        pokemon = self.bot.mongo.Pokemon.build_from_mongo(auction)

        # confirm

        result = await ctx.confirm(ctx._("bid-confirmation", pokemon=f"{pokemon:pl}", bid=bid))
        if result is None:
            return await ctx.send(ctx._("times-up"))
        if result is False:
            return await ctx.send(ctx._("aborted"))

        # go!

        auction = await self.bot.mongo.db.pokemon.find_one(
            {"owned_by": "auction", "auction_data._id": auction["auction_data"]["_id"]}
        )

        if auction is None:
            return await ctx.send(ctx._("unknown-auction"))

        if bid < auction["auction_data"]["current_bid"] + auction["auction_data"]["bid_increment"]:
            return await ctx.send(
                ctx._(
                    "bid-minimum",
                    minimum=auction["auction_data"]["current_bid"] + auction["auction_data"]["bid_increment"],
                )
            )

        if auction["auction_data"]["ends"] < datetime.utcnow():
            return await ctx.send(ctx._("auction-ended"))

        member = await self.bot.mongo.fetch_member_info(ctx.author)
        if member.balance < bid:
            return await ctx.send(ctx._("not-enough-coins"))

        # ok, bid

        res = await self.bot.mongo.db.member.find_one_and_update({"_id": ctx.author.id}, {"$inc": {"balance": -bid}})
        await self.bot.redis.hdel("db:member", ctx.author.id)
        if res["balance"] < bid:
            await self.bot.mongo.update_member(ctx.author, {"$inc": {"balance": bid}})
            return await ctx.send(ctx._("not-enough-coins"))

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
            return await ctx.send(ctx._("auction-ended-already"))

        if auction["auction_data"]["bidder_id"] is not None:
            await self.bot.mongo.update_member(
                auction["auction_data"]["bidder_id"], {"$inc": {"balance": auction["auction_data"]["current_bid"]}}
            )
            self.bot.loop.create_task(
                self.bot.send_dm(
                    auction["auction_data"]["bidder_id"],
                    ctx._(
                        "you-have-been-outbid",
                        pokemon=f"{pokemon:pl}",
                        auctionId=auction["auction_data"]["_id"],
                        bid=bid,
                    ),
                )
            )

        await ctx.send(
            ctx._("bid-completed", bid=f"{bid:,}", pokemon=f"{pokemon:pl}", auctionId=auction["auction_data"]["_id"])
        )

        # send embed

        host = await self.try_get_member(ctx.guild, auction["owner_id"])

        embed = self.make_base_embed(host, pokemon, auction["auction_data"]["_id"])

        embed.set_field(
            name=ctx._("auction-details"),
            value=ctx._(
                "auction-info-bidding-in-progress",
                bid=bid,
                bidder=ctx.author.mention,
                increment=auction["auction_data"]["bid_increment"],
            ),
        )
        embed.add_field(name=ctx._("auction-details"), value="\n".join(auction_info))
        embed.set_footer(
            text=ctx._(
                "auction-bid-cta",
                command=f"auction bid {auction['auction_data']['_id']} <bid>",
                delta=converters.strfdelta(auction["auction_data"]["ends"] - datetime.utcnow()),
            )
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
            return await ctx.send(ctx._("page-must-be-positive"))

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
            return ctx._(
                "auction-search-line-in-progress"
                if auction["auction_data"]["bidder_id"] is not None
                else "auction-search-line",
                paddedId=padn(auction["auction_data"]["_id"], menu.maxn),
                pokemon=f"{pokemon:Li}",
                ivTotal=pokemon.iv_total / 186,
                currentBid=auction["auction_data"]["current_bid"],
                bidIncrement=auction["auction_data"]["bid_increment"],
                startingBid=auction["auction_data"]["current_bid"] + auction["auction_data"]["bid_increment"],
                delta=converters.strfdelta(auction["auction_data"]["ends"] - now, max_len=1),
            )

        count = await self.bot.mongo.fetch_auction_count(ctx.guild, aggregations)
        pokemon = self.bot.mongo.fetch_auction_list(ctx.guild, aggregations)

        pages = pagination.ContinuablePages(
            pagination.AsyncListPageSource(
                pokemon,
                title=ctx._("auctions-in", guild=ctx.guild.name),
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
            await ctx.send(ctx._("no-auctions-found"))

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
            auction_info = ctx._(
                "auction-info-bidding",
                startingBid=auction["auction_data"]["current_bid"] + auction["auction_data"]["bid_increment"],
                increment=auction["auction_data"]["bid_increment"],
            )
        else:
            bidder = await self.try_get_member(ctx.guild, auction["auction_data"]["bidder_id"])
            auction_info = ctx._(
                "auction-info-bidding-in-progress",
                startingBid=auction["auction_data"]["current_bid"],
                bidder=bidder.mention,
                increment=auction["auction_data"]["bid_increment"],
            )

        embed.add_field(name=ctx._("auction-details"), value="\n".join(auction_info))
        embed.set_footer(
            text=ctx._(
                "auction-bid-cta",
                command=f"auction bid {auction['auction_data']['_id']} <bid>",
                delta=converters.strfdelta(auction["auction_data"]["ends"] - datetime.utcnow()),
            )
        )
        embed.timestamp = auction["auction_data"]["ends"]

        await ctx.send(embed=embed)

    def cog_unload(self):
        self.check_auctions.cancel()


async def setup(bot: commands.Bot):
    await bot.add_cog(Auctions(bot))
