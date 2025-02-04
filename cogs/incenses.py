from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
import math
import textwrap
from typing import TYPE_CHECKING, Dict, Iterable, List, Optional

import discord
from discord.ext import commands, tasks
import humanfriendly
from pymongo import IndexModel, ASCENDING
from bson.objectid import ObjectId

from helpers import checks, converters, pagination
from helpers import flags
from helpers.context import PoketwoContext
from lib.multi_field_paginator import MultiFieldPageSource, PaginatedField
from .sprites import other as other_sprites

if TYPE_CHECKING:
    from cogs.mongo import Channel, Member


# CONSTANTS

DURATIONS = [1800, 3600, 10800, 86400]  # 30m, 1h, 3h, 24h
DURATIONS = {seconds: humanfriendly.format_timespan(seconds) for seconds in DURATIONS}
DEFAULT_DURATION = 3600

INTERVALS = [10, 20, 30]  # 10s, 20s, 30s
INTERVALS = {seconds: humanfriendly.format_timespan(seconds) for seconds in INTERVALS}
DEFAULT_INTERVAL = 20

DEFAULT_TOTAL_SPAWNS = round(DEFAULT_DURATION / DEFAULT_INTERVAL)
YELLOW_STATUS_THRESHOLD = 20

SHARDS_PER_SPAWN = 50 / 180

# Discount on price of incenses
DISCOUNT = 0  # No discount at the moment, but leaving potential for it in the future
DISCOUNT_SPAWN_THRESHOLD = DEFAULT_TOTAL_SPAWNS


class IncenseStatus(Enum):
    RESUME = 0
    PAUSE = 1


# CONVERTERS


def join_words(string: str) -> str:
    """Remove whitespace between words in a string. E.g. '1 hour' -> '1hour'"""

    return "".join(string.split())


def format_timespans(timespans: Iterable[str]) -> str:
    formatted_timespans = list(map(join_words, timespans))

    if len(formatted_timespans) == 0:
        return ""
    elif len(formatted_timespans) == 1:
        return str(formatted_timespans[0])

    return f"{', '.join(formatted_timespans[:-1])} or {formatted_timespans[-1]}"


class DurationConverter(commands.Converter):
    async def convert(self, ctx: discord.Context, arg: str) -> int:
        duration = await converters.TimeDelta().convert(ctx, arg)
        duration_seconds = duration.total_seconds()

        if duration_seconds not in DURATIONS:
            raise ValueError(
                f"Unsupported duration provided. It must be one of: {format_timespans(DURATIONS.values())}"
            )

        return int(duration_seconds)


class IntervalConverter(commands.Converter):
    async def convert(self, ctx: discord.Context, arg: str) -> int:
        if arg.isdigit():
            interval_seconds = int(arg)
        else:
            interval = await converters.TimeDelta().convert(ctx, arg)
            interval_seconds = interval.total_seconds()

        if interval_seconds not in INTERVALS:
            raise ValueError(
                f"Unsupported interval provided. It must be one of: {format_timespans(INTERVALS.values())}"
            )

        return int(interval_seconds)


# CLASSES


@dataclass
class Incense:
    channel_id: int
    spawns_remaining: Optional[int] = 0
    interval: Optional[int] = DEFAULT_INTERVAL
    paused: Optional[bool] = False
    old_system: Optional[bool] = False
    failing: Optional[bool] = False
    _id: Optional[ObjectId] = None

    @property
    def infinite(self) -> bool:
        return self.spawns_remaining == float("inf")

    @property
    def discount(self) -> float:
        discount = DISCOUNT if self.spawns_remaining > DISCOUNT_SPAWN_THRESHOLD else 0
        return discount

    @property
    def discount_percent(self) -> int:
        return round(self.discount * 100)

    def calculate_price(self) -> int | None:
        if self.infinite:
            return None

        base_price = math.floor(self.spawns_remaining * SHARDS_PER_SPAWN)

        price = int(base_price * (1 - self.discount))
        return price

    @property
    def ends_in(self) -> timedelta | None:
        if self.infinite:
            return None

        seconds = self.spawns_remaining * self.interval
        return timedelta(seconds=seconds)

    @property
    def ends_at(self) -> datetime | None:
        if self.infinite:
            return None

        return datetime.now() + self.ends_in

    def item_text(self) -> str:

        if self.infinite:
            emoji_id = other_sprites["blue"]
            duration_text = "Infinite"
        else:
            emoji_id = (
                other_sprites["green"] if self.spawns_remaining > YELLOW_STATUS_THRESHOLD else other_sprites["yellow"]
            )
            duration_text = f"Ends {discord.utils.format_dt(self.ends_at, 'R')}"

        if self.failing:
            emoji_id = other_sprites["red"]
            duration_text = "Failing to spawn"

        if self.paused:
            emoji_id = other_sprites["invisible"]
            duration_text = "Paused"

        if self.old_system:
            emoji_id = other_sprites["red"]
            duration_text = "Migrating, please wait..."

        emoji = f"<:_:{emoji_id}>"
        return f"{emoji} <#{self.channel_id}>　•　{self.spawns_remaining} remaining　•　{duration_text}"

    def to_dict(self) -> dict:
        return {
            "_id": self._id,
            "spawns_remaining": self.spawns_remaining,
            "interval": self.interval,
            "paused": self.paused,
        }

    def new(self) -> Incense:
        _dict = self.to_dict()
        _dict["_id"] = ObjectId()
        return Incense(channel_id=self.channel_id, **_dict)


class IncenseConfirmationView(discord.ui.View):
    def __init__(self, ctx: PoketwoContext, member: Member, *, initial_duration: int, initial_interval: int) -> None:
        self.ctx = ctx
        self.member = member
        super().__init__(timeout=60)

        self.result: bool | None = None
        self.message: discord.Message | None = None

        self.duration = initial_duration
        self.interval = initial_interval

    @property
    def total_spawns(self) -> int:
        return int(self.duration / self.interval)

    @property
    def incense(self) -> Incense:
        return Incense(channel_id=self.ctx.channel.id, spawns_remaining=self.total_spawns, interval=self.interval)

    def confirmation_message(self) -> str:
        discount_msg = f"({self.incense.discount_percent}% Discount)" if self.incense.discount else ""
        return textwrap.dedent(
            f"""
            ### Please choose the Duration and Interval of your Incense
            **Total Spawns**: {self.total_spawns}
            **Duration**: {DURATIONS[self.duration]}
            **Interval**: {INTERVALS[self.interval]}
            **Price**: {self.incense.calculate_price()} Shards {discount_msg}

            **The incense will instantly be activated in this channel. Are you sure?**
            -# You can skip this confirmation using the `--confirm/-y` flag (be careful!)
            """
        )

    def update_default(self, select_menu: discord.ui.Select, default_value: str) -> None:
        for option in select_menu.options:
            option.default = option.value == str(default_value)

    async def update_message(self) -> None:
        content = self.confirmation_message()

        self.update_default(self.duration_select, self.duration)
        self.update_default(self.interval_select, self.interval)

        allowed_mentions = (
            discord.AllowedMentions(replied_user=True)
            if self.member.confirm_mention
            else discord.AllowedMentions.none()
        )
        if self.message:
            await self.message.edit(content=content, view=self, allowed_mentions=allowed_mentions)
        else:
            self.message = await self.ctx.reply(
                self.confirmation_message(), view=self, allowed_mentions=allowed_mentions
            )

    async def start(self, *, skip: Optional[bool] = False) -> None:
        if skip:
            self.result = True
            return

        await self.update_message()
        await self.wait()

    async def end(self):
        if self.message:
            await self.message.edit(view=None)
        self.stop()

    @discord.ui.select(
        options=[
            discord.SelectOption(
                label=timespan,
                description=f"The Incense will last for {timespan}",
                value=str(duration_seconds),
            )
            for duration_seconds, timespan in DURATIONS.items()
        ],
        placeholder="Select the duration of the Incense",
    )
    async def duration_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        await interaction.response.defer()
        self.duration = int(select.values[0])
        await self.update_message()

    @discord.ui.select(
        options=[
            discord.SelectOption(
                label=timespan,
                description=f"The Incense will spawn a pokémon every {timespan}",
                value=str(interval),
            )
            for interval, timespan in INTERVALS.items()
        ],
        placeholder="Select the interval between spawns",
    )
    async def interval_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        await interaction.response.defer()
        self.interval = int(select.values[0])
        await self.update_message()

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.green)
    async def confirm(self, interaction: discord.Interaction, button: discord.Button) -> None:
        await interaction.response.defer()

        self.result = True
        await self.end()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.red)
    async def cancel(self, interaction: discord.Interaction, button: discord.Button) -> None:
        await interaction.response.defer()

        self.result = False
        await self.end()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id not in {
            self.ctx.bot.owner_id,
            self.ctx.author.id,
            *self.ctx.bot.owner_ids,
        }:
            await interaction.response.send_message("You can't use this!", ephemeral=True)
            return False
        return True

    async def on_timeout(self) -> None:
        await self.end()


class Incenses(commands.Cog):
    """For Incense related commands and functions."""

    def __init__(self, bot):
        self.bot = bot
        self.spawning_cog = self.bot.get_cog("Spawning")
        self.spawn_pokemon = self.spawning_cog.spawn_pokemon

        self.interval_loops: Dict[str, tasks.Loop] = {}
        self.register_intervals.start()

    async def cog_load(self):
        self.bot.log.info("creating indexes", cog="incenses")
        await self.bot.mongo.db.channel.create_indexes(
            [
                IndexModel(
                    [
                        ("incense.spawns_remaining", ASCENDING),
                        ("incense.interval", ASCENDING),
                        ("incense.paused", ASCENDING),
                    ]
                )
            ]
        )

    def make_loop(self, interval_seconds: int) -> tasks.Loop:
        @tasks.loop(seconds=interval_seconds, reconnect=True)
        async def spawn_incense():
            try:
                channels = self.bot.mongo.Channel.find(
                    {
                        "incense.spawns_remaining": {"$gt": 0},
                        "incense.interval": interval_seconds,
                        "incense.paused": {"$ne": True},
                    }
                )
                async for result in channels:
                    guild = self.bot.get_guild(result.guild_id)
                    channel = None if guild is None else guild.get_channel_or_thread(result.id)

                    if channel is not None:
                        # The incense spawns decrement is inside spawn_pokemon so that it doesn't decrement
                        # if the incense is paused after the wait or if it encounters an error
                        self.bot.loop.create_task(self.spawn_pokemon(channel, incense=result.incense))

            except Exception as error:
                print(error)
                self.bot.log.exception("spawn_incense.error")

        @spawn_incense.before_loop
        async def before_spawn_incense():
            await self.bot.wait_until_ready()

        return spawn_incense

    @tasks.loop(seconds=10, reconnect=True)
    async def register_intervals(self):
        new_intervals = await self.bot.mongo.db.channel.distinct(
            "incense.interval",
            {"incense.interval": {"$nin": list(self.interval_loops.keys())}, "incense.spawns_remaining": {"$gt": 0}},
        )
        for interval in new_intervals:
            if not isinstance(interval, int):
                continue

            if interval < 1:
                continue

            loop = self.make_loop(interval)

            self.interval_loops[interval] = loop
            loop.start()

    @register_intervals.before_loop
    async def before_register_intervals(self):
        await self.bot.wait_until_ready()

    def cog_unload(self):
        self.register_intervals.cancel()

        for interval, loop in self.interval_loops.items():
            loop.cancel()

    async def find_channels(self, guild: discord.Guild, filter: dict) -> List[Channel]:
        channels = []
        async for channel in self.bot.mongo.Channel.find(
            {
                "guild_id": guild.id,
                **filter,
            }
        ):
            if guild.get_channel_or_thread(channel.id):
                channels.append(channel)
            else:
                try:
                    await guild.fetch_channel(channel.id)
                except discord.HTTPException:
                    continue
                else:
                    channel["_incense"]["failing"] = True
                    channels.append(channel)

        return channels

    @commands.guild_only()
    @commands.group(aliases=("incenses", "inc"), invoke_without_command=True, case_insensitive=True)
    async def incense(self, ctx: PoketwoContext):
        """See the list of all active incenses in the server"""

        incense_channels = await self.find_channels(
            ctx.guild, {"$or": [{"incense.spawns_remaining": {"$gt": 0}}, {"spawns_remaining": {"$gt": 0}}]}
        )

        paginated_fields = [
            PaginatedField(
                name=f"Active Incenses ({len(incense_channels)})",
                entries=[channel.incense.item_text() for channel in incense_channels],
            ),
        ]

        def make_embed(source: MultiFieldPageSource, page_fields: List[PaginatedField]):
            embed = self.bot.Embed(title="Server Incenses")

            embed.set_footer(
                text=textwrap.dedent(
                    f"""
                    Use `{ctx.clean_prefix}incense pause/resume` to pause/resume a specific incense
                    Use `{ctx.clean_prefix}incense pause/resume all` to pause/resume all incenses"""
                )
            )

            if ctx.guild.icon is not None:
                embed.set_thumbnail(url=ctx.guild.icon.url)

            # Add the paginated fields
            per_page = source.per_page
            current_page = source.current_page
            for field in page_fields:
                entries = field.get_entries(current_page, per_page=per_page)
                total_pages = field.get_num_pages(per_page)

                embed.add_field(
                    name=field,
                    value="\n".join(entries)
                    + (
                        f"\n**Showing page {min(total_pages, current_page + 1)}/{total_pages}**"
                        if total_pages > 1
                        else ""
                    ),
                    inline=False,
                )

            return embed

        pages = pagination.ContinuablePages(MultiFieldPageSource(paginated_fields, make_embed, per_page=10))
        self.bot.menus[ctx.author.id] = pages
        await pages.start(ctx)

    async def log_incense(self, ctx: PoketwoContext, incense: Incense, *, admin: Optional[bool] = False):
        insert = {
            "_id": incense._id,
            "event": "incense",
            "user_id": ctx.author.id,
            "channel_id": ctx.channel.id,
            "guild_id": ctx.guild.id,
            "total_spawns": incense.spawns_remaining,
            "interval": incense.interval,
            "price": incense.calculate_price(),
        }
        if admin:
            insert["admin"] = admin

        try:
            return await self.bot.mongo.db.logs.insert_one(insert)
        except:
            pass

    @flags.add_flag("--confirm", "-y", action="store_true", default=False)
    @commands.guild_only()
    @checks.has_started()
    @checks.has_incense_role()
    @checks.incenses_not_disabled()
    @incense.command(usage="[duration=1hour] [interval=20seconds]", cls=flags.FlagCommand)
    async def buy(
        self,
        ctx: PoketwoContext,
        duration: Optional[DurationConverter] = DEFAULT_DURATION,
        interval: Optional[IntervalConverter] = DEFAULT_INTERVAL,
        **flags,
    ):
        """Buy an Incense that spawns Pokémon at given intervals for a given duration."""

        channel = await self.bot.mongo.fetch_channel(ctx.channel)
        if channel.incense_active:
            return await ctx.send(
                f"This channel already has an incense active{' (paused)' if channel.incense.paused else ''}! Please wait for it to end before purchasing another one."
            )

        member = await self.bot.mongo.fetch_member_info(ctx.author)
        view = IncenseConfirmationView(ctx, member, initial_duration=duration, initial_interval=interval)

        await view.start(skip=flags.get("confirm"))
        if view.result is None:
            return await ctx.send("Time's up. Aborted.")
        if view.result is False:
            return await ctx.send("Aborted.")

        incense = view.incense.new()
        price = incense.calculate_price()
        member = await self.bot.mongo.fetch_member_info(ctx.author)
        if member.premium_balance < price:
            return await ctx.send(f"You don't have enough shards for that!")

        await self.log_incense(ctx, incense)

        await self.bot.mongo.update_member(
            ctx.author,
            {
                "$inc": {
                    "premium_balance": -price,
                },
            },
        )

        await self.bot.mongo.update_channel(
            ctx.channel,
            {
                "$set": {"guild_id": ctx.guild.id, "incense": incense.to_dict()},
            },
        )

        await ctx.send(f"You purchased an Incense for {price:,} shards!")

    async def update_incense_status(
        self, to_status: IncenseStatus, channels: List[discord.TextChannel | discord.Thread | Channel]
    ):
        """Pauses or resumes incenses in given channels."""

        if not isinstance(to_status, IncenseStatus):
            raise ValueError("Invalid value for to_status")

        pause = to_status == IncenseStatus.PAUSE
        channel_ids = [channel.id for channel in channels]

        return await self.bot.mongo.db.channel.update_many(
            {"_id": {"$in": channel_ids}},
            {"$set": {"incense.paused": pause}},
        )

    @commands.guild_only()
    @checks.has_started()
    @checks.has_incense_role()
    @incense.group(aliases=("p",), invoke_without_command=True, case_insensitive=True)
    async def pause(
        self,
        ctx: commands.Context,
    ):
        """Pause active incense in the current channel"""

        channel = ctx.channel
        channel_data = await self.bot.mongo.fetch_channel(channel)
        if not channel_data.incense_active:
            return await ctx.send("There is no incense active in this channel!")
        elif channel_data.incense.old_system:
            return await ctx.send(
                "The incense in this channel still uses the old system and cannot be paused. Please wait for it to migrate."
            )
        elif channel_data.incense.paused:
            return await ctx.send(
                f"The incense in this channel is already paused. Use `{ctx.clean_prefix}incense resume` to resume it."
            )

        await self.update_incense_status(IncenseStatus.PAUSE, [channel])
        await ctx.send(f"Incense has been paused. Use `{ctx.clean_prefix}incense resume` to resume it again.")

    @flags.add_flag("--confirm", "-y", action="store_true", default=False)
    @commands.guild_only()
    @checks.has_started()
    @checks.is_admin()
    @pause.command(name="all", aliases=("a",), cls=flags.FlagCommand)
    async def pause_all(self, ctx: PoketwoContext, **flags):
        """Pause all active incenses in the server"""

        channels = await self.find_channels(
            ctx.guild, {"incense.spawns_remaining": {"$gt": 0}, "incense.paused": {"$ne": True}}
        )

        num_incenses = len(channels)
        if num_incenses == 0:
            return await ctx.send(f"There are no currently unpaused incenses in this server.")

        incense_text = f"incense{'' if num_incenses == 1 else 's'}"
        result = await ctx.confirm(
            f"Are you sure you want to pause the {num_incenses} running {incense_text} in this server?",
            skip=flags.get("confirm"),
        )
        if result is None:
            return await ctx.send("Time's up. Aborted.")
        if result is False:
            return await ctx.send("Aborted.")

        await self.update_incense_status(IncenseStatus.PAUSE, channels)
        await ctx.send(
            f"Paused {num_incenses} running {incense_text} in this server. Use `{ctx.clean_prefix}incense resume [all]` to resume them again."
        )

    @commands.guild_only()
    @checks.has_started()
    @checks.has_incense_role()
    @checks.incenses_not_disabled()
    @incense.group(aliases=("r",), invoke_without_command=True, case_insensitive=True)
    async def resume(
        self,
        ctx: commands.Context,
    ):
        """Resume paused incense in the current channel"""

        channel = ctx.channel
        channel_data = await self.bot.mongo.fetch_channel(channel)
        if not channel_data.incense_active:
            return await ctx.send("There is no incense active in this channel!")
        elif not channel_data.incense.paused:
            return await ctx.send(f"The incense in this channel is not paused.")

        await self.update_incense_status(IncenseStatus.RESUME, [channel])
        await ctx.send(f"Incense has been resumed.")

    @flags.add_flag("--confirm", "-y", action="store_true", default=False)
    @commands.guild_only()
    @checks.has_started()
    @checks.is_admin()
    @checks.incenses_not_disabled()
    @resume.command(name="all", aliases=("a",), cls=flags.FlagCommand)
    async def resume_all(self, ctx: PoketwoContext, **flags):
        """Resume all paused incenses in the server"""

        channels = await self.find_channels(ctx.guild, {"incense.spawns_remaining": {"$gt": 0}, "incense.paused": True})

        num_incenses = len(channels)
        if num_incenses == 0:
            return await ctx.send("There are no paused incenses in this server.")

        incense_text = f"incense{'' if num_incenses == 1 else 's'}"
        result = await ctx.confirm(
            f"Are you sure you want to resume the {num_incenses} paused {incense_text} in this server?",
            skip=flags.get("confirm"),
        )
        if result is None:
            return await ctx.send("Time's up. Aborted.")
        if result is False:
            return await ctx.send("Aborted.")

        await self.update_incense_status(IncenseStatus.RESUME, channels)
        await ctx.send(f"Resumed {num_incenses} paused {incense_text} in this server.")

    @commands.guild_only()
    @checks.has_started()
    @checks.is_admin()
    @incense.command()
    async def stop(self, ctx: PoketwoContext):
        """Permanently stop incense in current channel. Does not refund remaining spawns."""

        channel = await self.bot.mongo.fetch_channel(ctx.channel)
        if not channel.incense_active:
            return await ctx.send("There is no active incense in this channel!")

        if not channel.incense.old_system:
            message = (
                f"Are you sure you want to cancel the incense? You can't undo this, and won't receive a refund "
                f"for the remaining spawns! If you want to pause instead, use `{ctx.clean_prefix}{self.pause.qualified_name}`."
            )
        else:
            message = (
                f"The incense in this channel is currently in the process of migrating to the new system "
                "and will need some time before resuming. Are you sure you want to cancel it? You can't undo this, "
                "and won't receive a refund for the remaining spawns!"
            )

        result = await ctx.confirm(message)
        if result is None:
            return await ctx.send("Time's up. Aborted.")
        if result is False:
            return await ctx.send("Aborted.")

        channel = await self.bot.mongo.fetch_channel(ctx.channel)
        incense = channel.incense
        if not channel.incense_active:
            return await ctx.send("There is no active incense in this channel!")

        if incense._id:
            try:
                await self.bot.mongo.db.logs.update_one(
                    {"_id": incense._id}, {"$set": {"stopped_at": incense.spawns_remaining}}
                )
            except:
                pass

        await self.bot.mongo.update_channel(
            ctx.channel,
            {
                "$set": {"incense.spawns_remaining": 0, "spawns_remaining": 0},
            },
        )
        await ctx.send("Incense has been stopped.")

    @commands.guild_only()
    @checks.has_started()
    @checks.is_admin()
    @commands.command()
    async def stopincense(self, ctx: PoketwoContext):
        """Alias for `incense stop`."""

        await ctx.invoke(self.stop)

    @commands.guild_only()
    @commands.is_owner()
    @incense.command()
    async def adminbuy(self, ctx: PoketwoContext, spawns: int = DEFAULT_TOTAL_SPAWNS, interval: int = DEFAULT_INTERVAL):
        """Admin command to buy an incense with any spawns or intervals. -1 spawns will start an infinite incense."""

        if interval <= 0:
            return await ctx.send("Invalid interval, it can't be less than or equal to 0")

        if spawns == -1:
            spawns = float("inf")

        channel = await self.bot.mongo.fetch_channel(ctx.channel)
        if channel.incense_active:
            result = await ctx.confirm(
                f"This channel already has an incense active! Are you sure you want to override it?"
            )
            if result is None:
                return await ctx.send("Time's up. Aborted.")
            if result is False:
                return await ctx.send("Aborted.")

            if channel.incense._id:
                try:
                    await self.bot.mongo.db.logs.update_one(
                        {"_id": channel.incense._id}, {"$set": {"stopped_at": channel.incense.spawns_remaining}}
                    )
                except:
                    pass

        incense = Incense(channel_id=ctx.channel.id, spawns_remaining=spawns, interval=interval).new()
        await self.log_incense(ctx, incense)

        await self.bot.mongo.update_channel(
            ctx.channel,
            {
                "$set": {"guild_id": ctx.guild.id, "incense": incense.to_dict(), "spawns_remaining": 0},
            },
        )
        await ctx.send(f"You purchased an Incense!")

    @commands.guild_only()
    @checks.is_developer()
    @incense.command()
    async def disable(self, ctx: PoketwoContext, *, message: str):
        """Admin command to disable buying and resuming incenses globally in case of instability, maintenance or other issues."""

        disabled_msg = await ctx.bot.redis.get("incense_disabled")
        if disabled_msg is None:
            confirm = (
                f"Are you sure you want to disable incenses globally with the given message? This will disable purchasing "
                f"new incenses and resuming paused ones, but will NOT pause running incenses."
            )
        else:
            disabled_msg = disabled_msg.decode("utf-8")
            confirm = (
                f"Incenses are already disabled globally, which you can re-enable using `{ctx.clean_prefix}{self.enable.qualified_name}`. "
                f"Do you want to change the message?\n### Current message:\n>>> {disabled_msg}"
            )

        result = await ctx.confirm(confirm)
        if result is None:
            return await ctx.send("Time's up. Aborted.")
        if result is False:
            return await ctx.send("Aborted.")

        await self.bot.redis.set("incense_disabled", message)
        return await ctx.send(
            f"Disabled purchasing and resuming incenses globally. You can re-enable them using `{ctx.clean_prefix}{self.enable.qualified_name}`."
        )

    @commands.guild_only()
    @checks.is_developer()
    @incense.command(aliases=("reenable",))
    async def enable(self, ctx: PoketwoContext):
        """Admin command to re-enable purchasing and resuming incenses globally."""

        disabled_msg = await ctx.bot.redis.get("incense_disabled")
        if disabled_msg is None:
            return await ctx.send("Incenses are not currently disabled.")

        disabled_msg = disabled_msg.decode("utf-8")
        result = await ctx.confirm(
            f"Purchasing and resuming incenses are currently disabled for the following reason. "
            f"Are you sure you want to re-enable them globally?\n### Current message:\n>>> {disabled_msg}"
        )
        if result is None:
            return await ctx.send("Time's up. Aborted.")
        if result is False:
            return await ctx.send("Aborted.")

        await self.bot.redis.delete("incense_disabled")
        return await ctx.send(f"Re-enabled purchasing and resuming incenses globally.")

    @checks.is_developer()
    @incense.command(name="migrate-old")
    async def migrate_old(self, ctx: PoketwoContext):
        """Developer-only command to migrate old incenses to the new system"""

        old_incenses = await self.bot.mongo.db.channel.count_documents({"spawns_remaining": {"$gt": 0}})
        if old_incenses == 0:
            return await ctx.send("No incenses to migrate.")

        result = await ctx.confirm(
            f"Are you sure you want to migrate **{old_incenses}** old incenses to the new system?"
        )
        if result is None:
            return await ctx.send("Time's up. Aborted.")
        if result is False:
            return await ctx.send("Aborted.")

        m = await self.bot.mongo.db.channel.update_many(
            {"spawns_remaining": {"$gt": 0}},
            [
                {"$set": {"incense": {"spawns_remaining": "$spawns_remaining", "interval": DEFAULT_INTERVAL}}},
                {"$unset": "spawns_remaining"},
            ],
        )
        await ctx.send(f"Migrated {m.modified_count} old incenses to the new system.")


async def setup(bot: commands.Bot):
    await bot.add_cog(Incenses(bot))
