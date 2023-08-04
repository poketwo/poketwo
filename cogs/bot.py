import pickle
import random
import sys
import traceback
from datetime import datetime, timedelta
from typing import Counter

import aiohttp
import discord
import humanfriendly
from discord.channel import TextChannel
from discord.ext import commands, flags, tasks

from helpers import checks, constants, converters
from helpers.views import ConfirmTermsOfServiceView

GENERAL_CHANNEL_NAMES = {"welcome", "general", "lounge", "chat", "talk", "main"}

VOTING_PROVIDERS = {
    "topgg": {"name": "Top.gg", "url": "https://top.gg/bot/716390085896962058/vote"},
    "dbl": {"name": "Discord Bot List", "url": "https://discordbotlist.com/bots/poketwo/upvote"},
}


class Blacklisted(commands.CheckFailure):
    pass


class Bot(commands.Cog):
    """For basic bot operation."""

    def __init__(self, bot):
        self.bot = bot
        headers = {"Authorization": self.bot.config.DBL_TOKEN}
        self.dbl_session = aiohttp.ClientSession(headers=headers)

        self.post_count.start()

        if self.bot.cluster_idx == 0 and self.bot.config.DBL_TOKEN is not None:
            self.post_dbl.start()
            self.remind_votes.start()

        self.cd = commands.CooldownMapping.from_cooldown(5, 3, commands.BucketType.user)
        self.bot.loop.create_task(self.process_dms())

    async def bot_check(self, ctx):
        if ctx.invoked_with.lower() == "help":
            return True

        bucket = self.cd.get_bucket(ctx.message)
        if retry_after := bucket.update_rate_limit():
            raise commands.CommandOnCooldown(bucket, retry_after)

        return True

    async def process_dms(self):
        await self.bot.wait_until_ready()
        with await self.bot.redis as r:
            while True:
                req = await r.blpop("send_dm")
                uid, content = pickle.loads(req[1])
                self.bot.loop.create_task(self.bot.send_dm(uid, content))

    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
        if after.content != before.content:
            after.content = after.content.replace("—", "--").replace("'", "′").replace("‘", "′").replace("’", "′")
            await self.bot.process_commands(after)

    @commands.Cog.listener()
    async def on_command(self, ctx):
        ctx.log.info("command")

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.CommandOnCooldown):
            ctx.log.info("command.error.ComamndOnCooldown", retry_after=error.retry_after)
            await ctx.message.add_reaction("\N{HOURGLASS}")
        elif isinstance(error, commands.MaxConcurrencyReached):
            ctx.log.info("command.error.MaxConcurrencyReached")
            bucket_name = error.per.name

            if bucket_name == "default":
                msg = ctx._("error-command-concurrency-global", rate=error.number)
            else:
                msg = ctx._("error-command-concurrency-bucketed", bucket=bucket_name, rate=error.number)

            await ctx.send(msg)
        elif isinstance(error, commands.NoPrivateMessage):
            await ctx.send(ctx._("error-command-no-private-messages"))
        elif isinstance(error, commands.DisabledCommand):
            ctx.log.info("command.error.DisabledCommand")
            await ctx.send(ctx._("error-command-disabled"))
        elif isinstance(error, commands.BotMissingPermissions):
            ctx.log.info("command.error.BotMissingPermissions")
            missing = [
                f"`{perm.replace('_', ' ').replace('guild', 'server').title()}`" for perm in error.missing_permissions
            ]
            fmt = "\n".join(missing)
            message = ctx._("error-bot-missing-permissions", fmt=fmt)
            botmember = self.bot.user if ctx.guild is None else ctx.guild.get_member(self.bot.user.id)
            if ctx.channel.permissions_for(botmember).send_messages:
                await ctx.send(message)
        elif isinstance(error, commands.ConversionError):
            await ctx.send(error.original)
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send_help(ctx.command)
        elif isinstance(error, checks.Suspended):
            ctx.log.info("command.error.Suspended", reason=error.reason)
            embed = ctx.localized_embed(
                "error-account-suspended-embed",
                field_values={
                    "expires": error.until and converters.strfdelta(error.until - datetime.utcnow(), long=True),
                    "reason": error.reason or ctx._("error-no-reason-provided"),
                },
                droppable_fields=["expires"],
                block_fields=["expires", "reason"],
            )
            await ctx.send(embed=embed)
        elif isinstance(error, checks.AcceptTermsOfService):
            ctx.log.info("command.error.AcceptTermsOfService")
        elif isinstance(error, (commands.CheckFailure, commands.UserInputError, flags.ArgumentParsingError)):
            await ctx.send(error)
        elif isinstance(error, commands.CommandNotFound):
            return
        else:
            print(error)
            ctx.log.exception("command.error")

    @commands.Cog.listener()
    async def on_error(self, event, *args, **kwargs):
        self.bot.log.info("error", event=event, event_args=args, event_kwargs=kwargs)

    def sendable_channel(self, channel):
        if channel.permissions_for(channel.guild.me).send_messages:
            return channel
        return None

    @commands.Cog.listener()
    async def on_guild_join(self, guild):
        priority_channels = []
        channels = []
        for channel in guild.channels:
            if channel == guild.system_channel or any(x in channel.name for x in GENERAL_CHANNEL_NAMES):
                priority_channels.append(channel)
            else:
                channels.append(channel)
        channels = priority_channels + channels
        try:
            channel = next(
                x for x in channels if isinstance(x, TextChannel) and x.permissions_for(guild.me).send_messages
            )
        except StopIteration:
            return

        embed = self.bot.localized_embed("joined-guild-embed", block_fields=["configs", "support"])
        await channel.send(embed=embed)

    @commands.command()
    async def invite(self, ctx):
        """View the invite link for the bot."""

        embed = self.bot.localized_embed("invite-embed", block_fields=["invite", "join"])
        embed.set_thumbnail(url=self.bot.user.display_avatar.url)
        await ctx.send(embed=embed)

    async def get_stats(self):
        result = await self.bot.mongo.db.stats.aggregate(
            [
                {
                    "$group": {
                        "_id": None,
                        "servers": {"$sum": "$servers"},
                        "shards": {"$sum": "$shards"},
                        "latency": {"$sum": "$latency"},
                    }
                }
            ]
        ).to_list(None)
        result = result[0]

        return result

    @tasks.loop(minutes=5)
    async def post_dbl(self):
        result = await self.get_stats()
        data = {"server_count": result["servers"], "shard_count": result["shards"]}
        await self.dbl_session.post(f"https://top.gg/api/bots/{self.bot.user.id}/stats", data=data)

    @post_dbl.before_loop
    async def before_post_dbl(self):
        await self.bot.wait_until_ready()

    async def send_voting_reminder(self, uid, provider):
        message = self.bot._("vote-timer-refreshed", name=provider["name"])
        view = discord.ui.View(timeout=0)
        view.add_item(
            discord.ui.Button(label=self.bot._("vote-timer-visit", name=provider["name"]), url=provider["url"])
        )
        await self.bot.send_dm(uid, message, view=view)

    @tasks.loop(seconds=15)
    async def remind_votes(self):
        for pid, provider in VOTING_PROVIDERS.items():
            query = {
                f"need_vote_reminder_on.{pid}": True,
                f"last_voted_on.{pid}": {"$lt": datetime.utcnow() - timedelta(hours=12)},
            }

            ids = [int(x["_id"]) async for x in self.bot.mongo.db.member.find(query, {"_id": 1})]
            if len(ids) == 0:
                continue

            for uid in ids:
                self.bot.loop.create_task(self.send_voting_reminder(uid, provider))

            await self.bot.mongo.db.member.update_many(
                {"_id": {"$in": ids}}, {"$set": {f"need_vote_reminder_on.{pid}": False}}
            )
            await self.bot.redis.hdel("db:member", *ids)

    @remind_votes.before_loop
    async def before_remind_votes(self):
        await self.bot.wait_until_ready()

    @tasks.loop(minutes=1)
    async def post_count(self):
        await self.bot.mongo.db.stats.update_one(
            {"_id": self.bot.cluster_name},
            {
                "$max": {"servers": len(self.bot.guilds)},
                "$set": {
                    "shards": len(self.bot.shards),
                    "latency": min(sum(x[1] for x in self.bot.latencies), 1),
                },
            },
            upsert=True,
        )

    @post_count.before_loop
    async def before_post_count(self):
        await self.bot.wait_until_ready()

    @checks.has_started()
    @commands.command(aliases=("v", "daily", "boxes"))
    async def vote(self, ctx):
        """View information on voting rewards."""

        member = await self.bot.mongo.fetch_member_info(ctx.author)
        embed = self.bot.Embed(title=f"Voting Rewards")
        view = discord.ui.View(timeout=0)

        embed = ctx.localized_embed(
            "vote-embed",
            providers=ctx._("vote-provider-joiner").join(
                f"**[{provider['name']}]({provider['url']})**" for provider in VOTING_PROVIDERS.values()
            ),
            ignored_fields=["voting"] if ctx.guild and ctx.guild.id == 716390832034414685 else [],
        )

        for pid, provider in VOTING_PROVIDERS.items():
            next_vote = member.last_voted_on.get(pid, datetime.min) + timedelta(hours=12)

            if next_vote < datetime.utcnow():
                message = ctx._("vote-can-vote-now", url=provider["url"])
            else:
                timespan = next_vote - datetime.utcnow()
                formatted = humanfriendly.format_timespan(timespan.total_seconds())
                message = ctx._("vote-can-vote-again-in", time=formatted)

            embed.add_field(name=ctx._("vote-field-timer-name", name=provider["name"]), value=message, inline=True)
            view.add_item(
                discord.ui.Button(label=ctx._("vote-visit-button", provider=provider["name"]), url=provider["url"])
            )

        embed.add_field(
            name=ctx._("vote-field-streak-name"),
            value=str(self.bot.sprites.check) * min(member.vote_streak, 14)
            + str(self.bot.sprites.gray) * (14 - min(member.vote_streak, 14))
            + "\n"
            + ctx._("vote-current-streak", votes=member.vote_streak),
            inline=False,
        )

        GIFT_TYPES = ("normal", "great", "ultra", "master")

        embed.add_field(
            name=ctx._("vote-field-rewards-name"),
            value=(
                "\n".join(
                    f"{getattr(self.bot.sprites, f'gift_{gift_type}')} "
                    + ctx._(f"vote-{gift_type}-mystery-box", gifts=getattr(member, f"gifts_{gift_type}"))
                    for gift_type in GIFT_TYPES
                )
            ),
            inline=False,
        )

        await ctx.send(embed=embed, view=view)

    @commands.command(aliases=("botinfo",))
    async def stats(self, ctx):
        """View bot info."""

        result = await self.get_stats()

        embed = ctx.localized_embed(
            "botinfo-embed",
            block_fields=["servers", "shards", "trainers", "latency"],
            servers=result["servers"],
            shards=result["shards"],
            trainers=await self.bot.mongo.db.member.estimated_document_count(),
            average=int(result["latency"] * 1000 / result["shards"]),
        )
        embed.color = constants.PINK
        embed.set_thumbnail(url=self.bot.user.display_avatar.url)
        print(repr(embed.fields))

        await ctx.send(embed=embed)

    @commands.command()
    async def ping(self, ctx):
        """View the bot's latency."""

        message = await ctx.send("Pong!")
        ms = int((message.created_at - ctx.message.created_at).total_seconds() * 1000)

        if ms > 300 and random.random() < 0.3:
            await message.edit(content=ctx._("pong-donate", ms=ms))
        else:
            await message.edit(content=ctx._("pong", ms=ms))

    @commands.command()
    async def start(self, ctx):
        """View the starter pokémon."""

        embed = ctx.localized_embed("start-embed")

        for gen, pokemon in constants.STARTER_GENERATION.items():
            embed.add_field(name=gen, value=" · ".join(pokemon), inline=False)

        await ctx.send(embed=embed)

    @commands.command()
    async def pick(self, ctx, *, name: str):
        """Pick a starter pokémon to get started."""

        member = await self.bot.mongo.fetch_member_info(ctx.author)

        if member is not None:
            return await ctx.send(ctx._("pick-already-chosen"))

        species = self.bot.data.species_by_name(name)

        if species is None or species.name.lower() not in constants.STARTER_POKEMON:
            return await ctx.send(ctx._("pick-invalid-choice"))

        # ToS

        embed = ctx.localized_embed("tos-embed")
        embed.color = constants.PINK
        embed.set_author(name=str(ctx.author), icon_url=ctx.author.display_avatar.url)

        result = await ctx.confirm(embed=embed, cls=ConfirmTermsOfServiceView)
        if result is None:
            return await ctx.send(ctx._("times-up"))
        if result is False:
            return await ctx.send(ctx._("tos-disagreed"))

        # Go

        starter = self.bot.mongo.Pokemon.random(
            owner_id=ctx.author.id,
            owned_by="user",
            species_id=species.id,
            level=1,
            xp=0,
            idx=1,
        )

        result = await self.bot.mongo.db.pokemon.insert_one(starter.to_mongo())
        await self.bot.mongo.db.member.insert_one(
            {
                "_id": ctx.author.id,
                "selected_id": result.inserted_id,
                "joined_at": datetime.utcnow(),
                "tos": datetime.utcnow(),
                "next_idx": 2,
            }
        )
        await self.bot.redis.hdel("db:member", ctx.author.id)

        await ctx.send(ctx._("pick-congrats", species=str(species)))

    @checks.has_started()
    @commands.command()
    async def profile(self, ctx):
        """View your profile."""

        member = await self.bot.mongo.fetch_member_info(ctx.author)

        pokemon_caught = []
        pokemon_caught.append(
            ctx._("profile-caught-category-total", amount=await self.bot.mongo.fetch_pokedex_sum(ctx.author))
        )

        for name, filt in (
            ("mythical", self.bot.data.list_mythical),
            ("legendary", self.bot.data.list_legendary),
            ("ultra-beast", self.bot.data.list_ub),
        ):
            pokemon_caught.append(
                ctx._(
                    f"profile-caught-category-{name}",
                    amount=await self.bot.mongo.fetch_pokedex_sum(
                        ctx.author,
                        [{"$match": {"k": {"$in": [str(x) for x in filt]}}}],
                    ),
                )
            )

        pokemon_caught.append(ctx._("profile-caught-category-shiny", amount=member.shinies_caught))

        badges = [k for k, v in member.badges.items() if v]
        if member.halloween_badge:
            badges.append("halloween")

        embed = ctx.localized_embed(
            "profile-embed",
            field_values={
                "caught": "\n".join(pokemon_caught),
                "badges": " ".join(getattr(self.bot.sprites, f"badge_{x}") for x in badges)
                or ctx._("profile-no-badges"),
            },
            field_ordering=["caught", "badges"],
        )
        embed.set_author(name=str(ctx.author), icon_url=ctx.author.display_avatar.url)
        embed.color = constants.PINK

        await ctx.send(embed=embed)

    def cog_unload(self):
        self.post_count.cancel()

        if self.bot.cluster_idx == 0 and self.bot.config.DBL_TOKEN is not None:
            self.post_dbl.cancel()
            self.remind_votes.cancel()

    @commands.command()
    @commands.has_permissions(manage_messages=True)
    async def cleanup(self, ctx, search=100):
        """Cleans up the bot's messages from the channel."""

        def check(m):
            return m.author == ctx.me or m.content.startswith(ctx.clean_prefix)

        deleted = await ctx.channel.purge(limit=search, check=check, before=ctx.message)
        spammers = Counter(m.author.display_name for m in deleted)
        count = len(deleted)

        messages = [ctx._("cleanup", count=count)]
        if len(deleted) > 0:
            messages.append("")
            spammers = sorted(spammers.items(), key=lambda t: t[1], reverse=True)
            messages.extend(f"– **{author}**: {count}" for author, count in spammers)

        await ctx.send("\n".join(messages), delete_after=5)


async def setup(bot: commands.Bot):
    await bot.add_cog(Bot(bot))
