import asyncio
import random
import sys
import traceback
from datetime import datetime, timedelta

import aiohttp
import discord
import humanfriendly
import pymongo
from discord.ext import commands, flags, tasks
from helpers import checks, constants, converters

from .database import Database


class Auctions(commands.Cog):
    """For auctions."""

    def __init__(self, bot):
        self.bot = bot
        self.check_auctions.start()
        self.sem = asyncio.Semaphore(1)

    @property
    def db(self) -> Database:
        return self.bot.get_cog("Database")

    @tasks.loop(minutes=1)
    async def check_auctions(self):
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

        guild = await self.db.fetch_guild(auction_guild)

        auction_channel = auction_guild.get_channel(guild.auction_channel)
        try:
            prev = await auction_channel.fetch_message(auction.message_id)
            await prev.delete()
        except:
            pass

        if auction.bidder_id is None:
            auction.bidder_id = auction.user_id
            auction.current_bid = 0

        host = self.bot.get_user(auction.user_id) or await self.bot.fetch_user(
            auction.user_id
        )
        bidder = self.bot.get_user(auction.bidder_id) or await self.bot.fetch_user(
            auction.bidder_id
        )

        embed = self.make_base_embed(host, auction.pokemon, auction.id)
        embed.title = "[SOLD] " + embed.title
        auction_info = (
            f"**Winning Bid:** {auction.current_bid:,} Pokécoins",
            f"**Bidder:** {bidder.mention}",
        )
        embed.add_field(name="Auction Details", value="\n".join(auction_info))
        embed.set_footer(text=f"The auction has ended.")

        message = await auction_channel.send(embed=embed)

        # ok, bid

        try:
            await self.bot.mongo.db.pokemon.insert_one(
                {
                    **auction.pokemon.to_mongo(),
                    "owner_id": auction.bidder_id,
                    "idx": await self.db.fetch_next_idx(bidder),
                }
            )
        except pymongo.errors.DuplicateKeyError:
            return
        await self.db.update_member(host, {"$inc": {"balance": auction.current_bid}})
        await self.bot.mongo.db.auction.delete_one({"_id": auction.id})

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

    def make_base_embed(self, author, pokemon, auction_id):
        embed = discord.Embed(color=0xE67D23)
        embed.set_author(name=str(author), icon_url=author.avatar_url)
        embed.title = f"Auction #{auction_id} • Level {pokemon.level} {pokemon.species}"
        if pokemon.nickname is not None:
            embed.title += f' "{pokemon.nickname}"'

        if pokemon.shiny:
            embed.title += " ✨"
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

    @commands.group(aliases=["auctions", "a"], invoke_without_command=True)
    async def auction(self, ctx: commands.Context, **flags):
        """Auction pokémon."""

        await ctx.send_help(ctx.command)

    @commands.has_permissions(administrator=True)
    @auction.command()
    async def channel(self, ctx: commands.Context, channel: discord.TextChannel):
        """Change the auctions channel."""

        await self.db.update_guild(ctx.guild, {"$set": {"auction_channel": channel.id}})
        await ctx.send(f"Setup auctions in {channel}.")

    @checks.has_started()
    @auction.command()
    async def start(
        self,
        ctx: commands.Context,
        pokemon: converters.Pokemon,
        duration: converters.TimeDelta,
        starting_bid: int,
        bid_increment: int,
    ):
        """Start an auction."""

        if ctx.author.id in self.bot.trades:
            return await ctx.send("You can't do that in a trade!")

        if pokemon is None:
            return await ctx.send("Couldn't find that pokémon!")

        if starting_bid < 1 or starting_bid > 1000000000:
            return await ctx.send("The starting bid is not valid.")

        if bid_increment < 1 or bid_increment > 1000000000:
            return await ctx.send("The bid increment is not valid.")

        guild = await self.db.fetch_guild(ctx.guild)
        if (
            guild.auction_channel is None
            or (auction_channel := ctx.guild.get_channel(guild.auction_channel)) is None
        ):
            return await ctx.send("Auctions have not been set up in this server.")

        member = await self.db.fetch_member_info(ctx.author)

        # confirm

        await ctx.send(
            f"You are auctioning your **{pokemon.iv_percentage:.2%} {pokemon.species} No. {pokemon.idx}**:\n"
            f"**Starting Bid:** {starting_bid:,} Pokécoins\n"
            f"**Bid Increment:** {bid_increment:,} Pokécoins\n"
            f"**Duration:** {humanfriendly.format_timespan(duration.total_seconds())}\n"
            "Auctions are server-specific and cannot be canceled. Are you sure? [y/N]"
        )

        def check(m):
            return m.channel.id == ctx.channel.id and m.author.id == ctx.author.id

        try:
            msg = await self.bot.wait_for("message", timeout=30, check=check)
        except asyncio.TimeoutError:
            return await ctx.send("Time's up. Aborted.")

        if msg.content.lower() != "y":
            return await ctx.send("Aborted.")

        # create auction

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
            text=f"Bid with `{ctx.prefix}auction bid {counter['next']} <bid>`\nEnds at"
        )
        embed.timestamp = ends

        message = await auction_channel.send(embed=embed)

        await self.bot.mongo.db.auction.insert_one(
            {
                "_id": counter["next"],
                "guild_id": ctx.guild.id,
                "message_id": message.id,
                "pokemon": pokemon.to_mongo(),
                "user_id": ctx.author.id,
                "current_bid": starting_bid - bid_increment,
                "bid_increment": bid_increment,
                "bidder_id": None,
                "ends": ends,
            }
        )

        await self.bot.mongo.db.pokemon.delete_one({"_id": pokemon.id})

        await ctx.send(
            f"Auctioning your **{pokemon.iv_percentage:.2%} {pokemon.species} No. {pokemon.idx}**."
        )

    @checks.has_started()
    @commands.max_concurrency(1, per=commands.BucketType.member, wait=True)
    @auction.command()
    async def lowerstart(self, ctx: commands.Context, auction_id: int, new_start: int):
        """Lower the starting bid for your auction."""

        auction = await self.bot.mongo.Auction.find_one(
            {"guild_id": ctx.guild.id, "_id": auction_id}
        )

        if auction is None:
            return await ctx.send("Couldn't find that auction!")

        if ctx.author.id != auction.user_id:
            return await ctx.send(
                "You can only lower the starting bid on your own auction."
            )

        if auction.bidder_id is not None:
            return await ctx.send("Someone has already bid on this auction.")

        if auction.current_bid + auction.bid_increment < new_start:
            return await ctx.send(
                "You can only lower the starting bid, not increase it."
            )

        guild = await self.db.fetch_guild(ctx.guild)

        embed = self.make_base_embed(ctx.author, auction.pokemon, auction.id)
        auction_info = (
            f"**Starting Bid:** {new_start:,} Pokécoins",
            f"**Bid Increment:** {auction.bid_increment:,} Pokécoins",
        )
        embed.add_field(name="Auction Details", value="\n".join(auction_info))
        embed.set_footer(
            text=f"Bid with `{ctx.prefix}auction bid {auction.id} <bid>`\nEnds at"
        )
        embed.timestamp = auction.ends

        auction_channel = ctx.guild.get_channel(guild.auction_channel)
        try:
            prev = await auction_channel.fetch_message(auction.message_id)
            await prev.delete()
        except Exception as e:
            print(e)
        message = await auction_channel.send(embed=embed)

        await self.bot.mongo.db.auction.update_one(
            {"_id": auction.id},
            {
                "$set": {
                    "current_bid": new_start - auction.bid_increment,
                    "message_id": message.id,
                }
            },
        )

        await ctx.send(
            f"Lowered the starting bid on your auction to **{new_start:,} Pokécoins**."
        )

    @checks.has_started()
    @commands.max_concurrency(1, per=commands.BucketType.member, wait=True)
    @auction.command()
    async def bid(self, ctx: commands.Context, auction_id: int, bid: int):
        """Bid on an auction."""

        auction = await self.bot.mongo.Auction.find_one(
            {"guild_id": ctx.guild.id, "_id": auction_id}
        )
        guild = await self.db.fetch_guild(ctx.guild)

        if auction is None:
            return await ctx.send("Couldn't find that auction!")

        if bid < auction.current_bid + auction.bid_increment:
            return await ctx.send(
                f"Your bid must be at least {auction.current_bid + auction.bid_increment:,} Pokécoins."
            )

        member = await self.db.fetch_member_info(ctx.author)
        if member.balance < bid:
            return await ctx.send("You don't have enough Pokécoins for that!")

        if ctx.author.id == auction.user_id:
            return await ctx.send("You can't bid on your own auction.")

        if ctx.author.id == auction.bidder_id:
            return await ctx.send("You are already the highest bidder.")

        # confirm

        await ctx.send(
            f"Do you want to bid **{bid:,} Pokécoins** on the **{auction.pokemon.iv_percentage:.2%} {auction.pokemon.species}**? [y/N]"
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
                {"guild_id": ctx.guild.id, "_id": auction_id}
            )

            if auction is None:
                return await ctx.send("Couldn't find that auction!")

            if bid < auction.current_bid + auction.bid_increment:
                return await ctx.send(
                    f"Your bid must be at least {auction.current_bid + auction.bid_increment:,} Pokécoins."
                )

            member = await self.db.fetch_member_info(ctx.author)
            if member.balance < bid:
                return await ctx.send("You don't have enough Pokécoins for that!")

            # send embed

            host = self.bot.get_user(auction.user_id) or await self.bot.fetch_user(
                auction.user_id
            )

            embed = self.make_base_embed(host, auction.pokemon, auction.id)

            auction_info = (
                f"**Current Bid:** {bid:,} Pokécoins",
                f"**Bidder:** {ctx.author.mention}",
                f"**Bid Increment:** {auction.bid_increment:,} Pokécoins",
            )
            embed.add_field(name="Auction Details", value="\n".join(auction_info))
            embed.set_footer(
                text=f"Bid with `{ctx.prefix}auction bid {auction.id} <bid>`\nEnds at"
            )
            embed.timestamp = auction.ends

            auction_channel = ctx.guild.get_channel(guild.auction_channel)
            try:
                prev = await auction_channel.fetch_message(auction.message_id)
                await prev.delete()
            except Exception as e:
                print(e)
            message = await auction_channel.send(embed=embed)

            if auction.bidder_id is not None:
                old_bidder = self.bot.get_user(
                    auction.bidder_id
                ) or await self.bot.fetch_user(auction.bidder_id)

            update = {
                "$set": {
                    "current_bid": bid,
                    "bidder_id": ctx.author.id,
                    "message_id": message.id,
                }
            }

            if datetime.utcnow() + timedelta(minutes=5) > auction.ends:
                update["$set"]["ends"] = datetime.utcnow() + timedelta(minutes=5)

            # ok, bid

            if auction.bidder_id is not None:
                await self.db.update_member(
                    old_bidder, {"$inc": {"balance": auction.current_bid}}
                )
            await self.bot.mongo.db.auction.update_one({"_id": auction.id}, update)
            await self.db.update_member(ctx.author, {"$inc": {"balance": -bid}})

            if auction.bidder_id is not None:
                self.bot.loop.create_task(
                    old_bidder.send(
                        f"You have been outbid on the **{auction.pokemon.iv_percentage:.2%} {auction.pokemon.species}** (Auction #{auction.id})."
                    )
                )
            self.bot.loop.create_task(
                ctx.send(
                    f"You bid **{bid:,} Pokécoins** on the **{auction.pokemon.iv_percentage:.2%} {auction.pokemon.species}** (Auction #{auction.id})."
                )
            )

    def cog_unload(self):
        self.check_auctions.cancel()


def setup(bot):
    bot.add_cog(Auctions(bot))
