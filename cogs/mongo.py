from __future__ import annotations

from enum import Enum
import math
import pickle
import random
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import discord
import pymongo
from bson.objectid import ObjectId
from discord.ext import commands
from motor.motor_asyncio import AsyncIOMotorClient
from suntime import Sun
from umongo import Document, EmbeddedDocument, Instance, MixinDocument, fields

from cogs.incenses import DEFAULT_INTERVAL, Incense
from data import models
from helpers import constants
from helpers.genders import generate_gender
from lib.probability import random_iv_composition

random_iv = lambda: random.randint(0, 31)
random_nature = lambda: random.choice(constants.NATURES)

# Instance


def iv_percent_to_total(percent: float) -> int:
    return math.ceil(percent / 100 * 186)


def iv_total_to_percent(total_iv: int, *, round_to: Optional[int] = 2) -> float:
    return round(total_iv / 186 * 100, round_to)


def calc_stat(pokemon, stat):
    base = getattr(pokemon.species.base_stats, stat)
    iv = getattr(pokemon, f"iv_{stat}")
    return math.floor(
        ((2 * base + iv + 5) * pokemon.level // 100 + 5) * constants.NATURE_MULTIPLIERS[pokemon.nature][stat]
    )


class PokemonBase(MixinDocument):
    class Meta:
        strict = False
        abstract = True

    # General
    id = fields.ObjectIdField(attribute="_id")
    timestamp = fields.DateTimeField(default=datetime.utcnow)
    owner_id = fields.IntegerField(required=True)
    idx = fields.IntegerField(required=True)

    # Details
    species_id = fields.IntegerField(required=True)
    level = fields.IntegerField(required=True)
    xp = fields.IntegerField(required=True)
    nature = fields.StringField(required=True)
    shiny = fields.BooleanField(required=True)
    _gender = fields.StringField(attribute="gender", default=None)

    # Stats
    iv_hp = fields.IntegerField(required=True)
    iv_atk = fields.IntegerField(required=True)
    iv_defn = fields.IntegerField(required=True)
    iv_satk = fields.IntegerField(required=True)
    iv_sdef = fields.IntegerField(required=True)
    iv_spd = fields.IntegerField(required=True)

    iv_total = fields.IntegerField(required=False)

    # Customization
    nickname = fields.StringField(default=None)
    favorite = fields.BooleanField(default=False)
    held_item = fields.IntegerField(default=None)
    moves = fields.ListField(fields.IntegerField, default=list)
    has_color = fields.BooleanField(default=False)
    color = fields.IntegerField(default=None)

    _hp = None
    ailments = None
    stages = None

    def __format__(self, spec):

        # Default specification
        if "D" in spec or not spec:
            spec += "lPg"

        name = ""

        if "!s" not in spec and self.shiny:
            name += "✨ "

        if "l" in spec:
            name += f"Level {self.level} "

        elif "L" in spec:
            name += f"L{self.level} "

        if "p" in spec:
            name += f"{self.iv_percentage:.2%} "

        if "i" in spec and self.bot.sprites.status:
            sprite = self.bot.sprites.get(self.species, shiny=self.shiny)
            name = sprite + " " + name

        if "!G" not in spec and self.species.is_gmax:
            name += f"{self.bot.sprites['gmax']} "

        name += str(self.species)

        if "g" in spec:
            name += f"{self.gender_icon}"

        if "P" in spec:
            name += f" ({self.iv_percentage:.2%})"

        if "n" in spec and self.nickname is not None:
            name += f' "{self.nickname}"'

        if "f" in spec and self.favorite:
            name += " ❤️"

        if "x" in spec:
            name += f" No. {self.idx}"

        if "X" in spec:
            name += f" (#{self.idx})"

        return name

    def __str__(self):
        return f"{self}"

    @classmethod
    def random(cls, **kwargs):
        ivs = [random_iv() for i in range(6)]
        return cls(
            iv_hp=ivs[0],
            iv_atk=ivs[1],
            iv_defn=ivs[2],
            iv_satk=ivs[3],
            iv_sdef=ivs[4],
            iv_spd=ivs[5],
            iv_total=sum(ivs),
            nature=random_nature(),
            shiny=random.randint(1, 4096) == 1,
            **kwargs,
        )

    @property
    def species(self):
        return self.bot.data.species_by_number(self.species_id)

    @property
    def gender(self) -> str:
        if self._gender is None:
            return generate_gender(self.species, _id=self.id)
        return self._gender

    @property
    def gender_icon(self):
        return constants.GENDER_EMOTES[self.gender.lower()]

    @property
    def image_url(self) -> str:
        return self.species.get_image_url(self.shiny, self.gender)

    @property
    def max_xp(self):
        return 250 + 25 * self.level

    @property
    def max_hp(self):
        if self.species_id == 292:
            return 1
        return (2 * self.species.base_stats.hp + self.iv_hp + 5) * self.level // 100 + self.level + 10

    @property
    def hp(self):
        if self._hp is None:
            return self.max_hp
        return self._hp

    @hp.setter
    def hp(self, value):
        self._hp = value

    @property
    def atk(self):
        return calc_stat(self, "atk")

    @property
    def defn(self):
        return calc_stat(self, "defn")

    @property
    def satk(self):
        return calc_stat(self, "satk")

    @property
    def sdef(self):
        return calc_stat(self, "sdef")

    @property
    def spd(self):
        return calc_stat(self, "spd")

    @property
    def iv_percentage(self):
        return (
            self.iv_hp / 31
            + self.iv_atk / 31
            + self.iv_defn / 31
            + self.iv_satk / 31
            + self.iv_sdef / 31
            + self.iv_spd / 31
        ) / 6

    def get_next_evolution(self, time: Time):
        if self.species.evolution_to is None or self.held_item == 13001:
            return None

        possible = []

        for evo in self.species.evolution_to.items:
            if not isinstance(evo.trigger, models.LevelTrigger):
                continue

            can = True

            if evo.trigger.level and self.level < evo.trigger.level:
                can = False
            if evo.trigger.item and self.held_item != evo.trigger.item_id:
                can = False
            if evo.trigger.move_id and evo.trigger.move_id not in self.moves:
                can = False
            if evo.trigger.move_type_id and not any(
                [self.bot.data.move_by_number(x).type_id == evo.trigger.move_type_id for x in self.moves]
            ):
                can = False
            if evo.trigger.time and evo.trigger.time != time:
                can = False

            if evo.trigger.relative_stats == 1 and self.atk <= self.defn:
                can = False
            if evo.trigger.relative_stats == -1 and self.defn <= self.atk:
                can = False
            if evo.trigger.relative_stats == 0 and self.atk != self.defn:
                can = False
            if evo.trigger.gender and evo.trigger.gender != self.gender:
                can = False
            if evo.trigger.natures and self.nature not in evo.trigger.natures:
                can = False

            if can:
                possible.append(evo.target)

        if len(possible) == 0:
            return None

        return random.choice(possible)

    def can_evolve(self, ctx):
        return self.get_next_evolution() is not None


class Pokemon(PokemonBase, Document):
    class Meta:
        strict = False

    owned_by = fields.StringField(required=True)


class EmbeddedPokemon(PokemonBase, EmbeddedDocument):
    class Meta:
        strict = False


class Member(Document):
    class Meta:
        strict = False

    # General
    id = fields.IntegerField(attribute="_id")
    username = fields.StringField(attribute="username")
    joined_at = fields.DateTimeField(default=None)
    suspended = fields.BooleanField(default=False)
    suspended_until = fields.DateTimeField(default=datetime.min)
    suspension_reason = fields.StringField(default=None)
    private_message_id = fields.IntegerField(default=None)
    tos = fields.DateTimeField(default=None)

    # Pokémon
    next_idx = fields.IntegerField(default=1)
    selected_id = fields.ObjectIdField(required=True)
    order_by = fields.StringField(default="number")

    # Pokédex
    pokedex = fields.DictField(fields.StringField(), fields.IntegerField(), default=dict)
    claimed_pokedex_rewards = fields.DictField(fields.StringField(), fields.BooleanField(), default=dict)
    notified_milestones = fields.DictField(fields.StringField(), fields.BooleanField(), default=dict)
    shinies_caught = fields.IntegerField(default=0)
    gmax_caught = fields.IntegerField(default=0)

    # Shop
    balance = fields.IntegerField(default=0)
    premium_balance = fields.IntegerField(default=0)
    redeems = fields.IntegerField(default=0)
    redeems_purchased = fields.DictField(fields.IntegerField(), fields.IntegerField(), default=dict)
    embed_colors = fields.IntegerField(default=0)

    # Shiny Hunt
    shiny_hunt = fields.IntegerField(default=None)
    shiny_streak = fields.IntegerField(default=0)

    # Boosts
    boost_expires = fields.DateTimeField(default=datetime.min)
    shiny_charm_expires = fields.DateTimeField(default=datetime.min)

    # Voting
    last_voted_on = fields.DictField(fields.StringField(), fields.DateTimeField(), default=dict)
    need_vote_reminder_on = fields.DictField(fields.StringField(), fields.BooleanField())
    vote_total = fields.IntegerField(default=0)
    vote_streak = fields.IntegerField(default=0)
    gifts_normal = fields.IntegerField(default=0)
    gifts_great = fields.IntegerField(default=0)
    gifts_ultra = fields.IntegerField(default=0)
    gifts_master = fields.IntegerField(default=0)

    # Settings
    show_balance = fields.BooleanField(default=True)
    silence = fields.BooleanField(default=False)
    catch_mention = fields.BooleanField(default=True)
    confirm_mention = fields.BooleanField(default=True)
    catch_ivs = fields.BooleanField(default=True)

    # Quests
    badges = fields.DictField(fields.StringField(), fields.BooleanField(), default=dict)
    quest_progress = fields.DictField(fields.StringField(), fields.IntegerField(), default=dict)

    # Events
    halloween_tickets = fields.IntegerField(default=0)
    halloween_tickets_2021 = fields.IntegerField(default=0)
    hquests = fields.DictField(fields.StringField(), fields.BooleanField(), default=dict)
    hquest_progress = fields.DictField(fields.StringField(), fields.IntegerField(), default=dict)
    halloween_badge = fields.BooleanField(default=False)
    msf_notified = fields.BooleanField(default=False)
    msf_donated_amount = fields.IntegerField(default=0)
    christmas_boxes_nice = fields.IntegerField(default=0)
    christmas_boxes_naughty = fields.IntegerField(default=0)
    christmas_boxes_nice_opened = fields.IntegerField(default=0)
    christmas_boxes_naughty_opened = fields.IntegerField(default=0)
    valentines_purchased = fields.IntegerField(default=0)
    valentines_purchased_2023 = fields.IntegerField(default=0)
    anniversary_boxes = fields.IntegerField(default=0)
    bingos_awarded = fields.IntegerField(default=0)
    halloween_tickets_2022 = fields.IntegerField(default=0)

    christmas_coins_2022 = fields.IntegerField(default=0)
    christmas_boxes_2022_random = fields.IntegerField(default=0)
    christmas_boxes_2022_pokemon = fields.IntegerField(default=0)
    christmas_boxes_2022_currency = fields.IntegerField(default=0)
    christmas_boxes_2022_event = fields.IntegerField(default=0)
    christmas_boxes_2022_santa = fields.IntegerField(default=0)
    christmas_boxes_2022_random_opened = fields.IntegerField(default=0)
    christmas_boxes_2022_pokemon_opened = fields.IntegerField(default=0)
    christmas_boxes_2022_currency_opened = fields.IntegerField(default=0)
    christmas_boxes_2022_event_opened = fields.IntegerField(default=0)
    christmas_boxes_2022_santa_opened = fields.IntegerField(default=0)

    spring_2023_flower_venusaur = fields.IntegerField(default=0)
    spring_2023_flower_shaymin = fields.IntegerField(default=0)
    spring_2023_flower_lilligant = fields.IntegerField(default=0)
    spring_2023_flower_gossifleur = fields.IntegerField(default=0)
    spring_2023_flower_eldegoss = fields.IntegerField(default=0)
    spring_2023_eggs = fields.ListField(fields.DictField(), default=list)

    pride_2023_flag_pride = fields.IntegerField(default=0)
    pride_2023_flag_nonbinary = fields.IntegerField(default=0)
    pride_2023_flag_lesbian = fields.IntegerField(default=0)
    pride_2023_flag_bisexual = fields.IntegerField(default=0)
    pride_2023_flag_transgender = fields.IntegerField(default=0)
    pride_2023_flag_gay = fields.IntegerField(default=0)
    pride_2023_flag_pansexual = fields.IntegerField(default=0)
    pride_2023_buddy = fields.ObjectIdField(default=None)
    pride_2023_buddy_progress = fields.IntegerField(default=0)
    pride_2023_quests = fields.DictField(
        fields.StringField(), fields.ListField(fields.DictField(), default=list), default=dict
    )
    pride_2023_categories = fields.DictField(fields.StringField(), fields.BooleanField(), default=dict)

    summer_2023_fishing_bait = fields.IntegerField(default=0)
    summer_2023_tokens = fields.IntegerField(default=0)

    halloween_2023_satchel_flames = fields.IntegerField(default=0)
    halloween_2023_satchel_shadows = fields.IntegerField(default=0)
    halloween_2023_satchel_foliage = fields.IntegerField(default=0)
    halloween_2023_satchel_snaring = fields.IntegerField(default=0)

    halloween_2023_sigil_flames = fields.IntegerField(default=0)
    halloween_2023_sigil_shadows = fields.IntegerField(default=0)
    halloween_2023_sigil_foliage = fields.IntegerField(default=0)
    halloween_2023_sigil_snaring = fields.IntegerField(default=0)

    halloween_2023_milestone_contribution_searching_golurk = fields.FloatField(default=0.0)
    halloween_2023_milestone_contribution_helping_flames = fields.FloatField(default=0.0)
    halloween_2023_milestone_contribution_helping_shadows = fields.FloatField(default=0.0)
    halloween_2023_milestone_contribution_helping_foliage = fields.FloatField(default=0.0)
    halloween_2023_milestone_contribution_helping_snaring = fields.FloatField(default=0.0)
    halloween_2023_milestone_contribution_saving_golurk = fields.FloatField(default=0.0)

    christmas_2023_xp = fields.IntegerField(default=0)
    christmas_2023_presents = fields.IntegerField(default=0)
    christmas_2023_quests = fields.ListField(fields.DictField(), default=list)
    christmas_2023_quests_notify = fields.BooleanField(default=True)

    valentines_2024_catches = fields.IntegerField(default=0)
    valentines_2024_boxes = fields.IntegerField(default=0)

    easter_2024_quests = fields.ListField(fields.DictField(), default=list)
    easter_2024_boxes = fields.IntegerField(default=0)
    easter_2024_boxes_opened = fields.IntegerField(default=0)
    easter_2024_bingos_awarded = fields.IntegerField(default=0)
    easter_2024_boards_completed = fields.IntegerField(default=0)

    anniversary_2024_orders = fields.DictField(fields.StringField(), fields.DictField(), default=dict)
    anniversary_2024_order_periods = fields.DictField(fields.StringField(), fields.IntegerField(), default=dict)
    anniversary_2024_order_lists = fields.DictField(
        fields.StringField(), fields.ListField(fields.DictField()), default=dict
    )
    anniversary_2024_available_orders = fields.DictField(fields.StringField(), fields.IntegerField(), default=dict)
    anniversary_2024_completed_orders = fields.DictField(fields.StringField(), fields.IntegerField(), default=dict)
    anniversary_2024_donated = fields.IntegerField(default=0)
    anniversary_2024_ingredients = fields.DictField(default=dict)
    anniversary_2024_notify = fields.BooleanField(default=True)

    summer_2024_team = fields.StringField(default=None)
    summer_2024_tickets = fields.IntegerField(default=0)
    summer_2024_tickets_total = fields.IntegerField(default=0)
    summer_2024_current_minisport = fields.DictField(allow_none=True, default=dict)
    summer_2024_minisports_played = fields.IntegerField(default=0)
    summer_2024_points = fields.DictField(fields.StringField(), fields.IntegerField(), default=dict)
    summer_2024_end_points = fields.DictField(fields.StringField(), fields.IntegerField(), default=dict)
    summer_2024_boxes = fields.DictField(fields.StringField(), fields.IntegerField(), default=dict)
    summer_2024_prizes_claimed = fields.BooleanField(default=False)
    summer_2024_prizes_notified = fields.BooleanField(default=False)

    day_of_the_dead_2024_boxes = fields.IntegerField(default=0)
    day_of_the_dead_2024_quests_metadata = fields.DictField(fields.StringField(), fields.StringField(), default=dict)
    day_of_the_dead_2024_quests = fields.ListField(fields.DictField(), default=list)
    day_of_the_dead_2024_items = fields.DictField(fields.StringField(), fields.IntegerField(), default=dict)
    day_of_the_dead_2024_ofrenda_offerings = fields.ListField(fields.IntegerField(), default=list)
    day_of_the_dead_2024_ofrendas_completed = fields.IntField(default=0)

    @property
    def is_suspended(self) -> bool:
        return self.suspended or datetime.utcnow() < self.suspended_until

    @property
    def selected_pokemon(self):
        try:
            return next(filter(lambda x: x.number == int(self.selected), self.pokemon))
        except StopIteration:
            return None

    @property
    def boost_active(self):
        return datetime.utcnow() < self.boost_expires

    @property
    def shiny_charm_active(self):
        return datetime.utcnow() < self.shiny_charm_expires

    @property
    def shiny_hunt_multiplier(self):
        return 1 + math.sqrt(self.shiny_streak) / 7

    def determine_shiny(self, species, *, boost=1):
        chance = 1 / 4096 * boost
        if self.shiny_charm_active:
            chance *= 1.2
        if self.shiny_hunt == species.dex_number:
            chance *= self.shiny_hunt_multiplier
        return random.random() < chance


class Time(Enum):
    DAWN = "🌅", "dawn"
    DAY = "☀️", "day time"
    DUSK = "🌆", "dusk"
    NIGHT = "🌛", "night time"

    def __init__(self, emoji: str, text: str):
        self.emoji = emoji
        self.text = text

    def __format__(self, format_spec: str) -> str:
        name = self.qname

        if "!e" not in format_spec:
            name += f" {self.emoji}"

        return name

    def __eq__(self, other) -> bool:
        return self.name.casefold() == getattr(other, "name", str(other)).casefold()

    @property
    def qname(self) -> str:
        return self.name.capitalize()

    @classmethod
    def from_time(cls, dt: datetime, *, sunrise: datetime, sunset: datetime) -> Time:
        if sunset < sunrise:
            sunset += timedelta(days=1)

        offset = timedelta(hours=1.5)
        for add_days in range(-1, 2):  # This is necessary because sunrise/set can be previous/current/next day
            new_dt = dt + timedelta(days=add_days)
            if (sunrise - offset) < new_dt < (sunrise + offset):  # 1.5 hours around sunrise
                return cls.DAWN
            elif (sunset - offset) < new_dt < (sunset + offset):  # 1.5 hours around sunset
                return cls.DUSK
            elif sunrise < new_dt < sunset:  # After sunrise and before sunset
                return cls.DAY
        else:
            return cls.NIGHT


class Guild(Document):
    class Meta:
        strict = False

    id = fields.IntegerField(attribute="_id")
    channel = fields.IntegerField(default=None)
    channels = fields.ListField(fields.IntegerField, default=list)
    silence = fields.BooleanField(default=False)
    display_images = fields.BooleanField(default=True)
    auction_channel = fields.IntegerField(default=None)

    lat = fields.FloatField(default=37.7790262)
    lng = fields.FloatField(default=-122.4199061)
    loc = fields.StringField(
        default="San Francisco, San Francisco City and County, California, United States of America"
    )

    @property
    def time(self) -> Time:
        sun = Sun(self.lat, self.lng)
        sunrise, sunset = sun.get_sunrise_time(), sun.get_sunset_time()

        now = datetime.now(timezone.utc)
        return Time.from_time(now, sunrise=sunrise, sunset=sunset)

    @property
    def is_day(self):
        return self.time in (Time.DAY, Time.DAWN)


class Channel(Document):
    class Meta:
        strict = False

    id = fields.IntegerField(attribute="_id")
    guild_id = fields.IntegerField()
    spawns_remaining = fields.IntegerField(default=0)
    _incense = fields.DictField(attribute="incense", default=dict)

    @property
    def incense(self):
        if self.spawns_remaining > 0:
            return Incense(
                channel_id=int(self.id),
                spawns_remaining=self.spawns_remaining,
                interval=DEFAULT_INTERVAL,
                old_system=True,
            )
        return Incense(channel_id=int(self.id), **self._incense)

    @property
    def incense_active(self):
        return (self.spawns_remaining or self.incense.spawns_remaining) > 0


class Counter(Document):
    id = fields.StringField(attribute="_id")
    next = fields.IntegerField(default=0)


class Blacklist(Document):
    id = fields.IntegerField(attribute="_id")


class Sponsor(Document):
    id = fields.IntegerField(attribute="_id")
    discord_id = fields.IntegerField(default=None)
    reward_date = fields.DateTimeField()
    reward_tier = fields.IntegerField()


class Mongo(commands.Cog):
    """For database operations."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.client = AsyncIOMotorClient(bot.config.DATABASE_URI, io_loop=bot.loop)
        self.db = self.client[bot.config.DATABASE_NAME]
        instance = Instance(self.db)

        g = globals()

        for x in (
            "PokemonBase",
            "Pokemon",
            "EmbeddedPokemon",
            "Member",
            "Guild",
            "Channel",
            "Counter",
            "Blacklist",
            "Sponsor",
        ):
            setattr(self, x, instance.register(g[x]))
            getattr(self, x).bot = bot

    async def fetch_member_info(self, member: discord.Member | Member) -> Member:
        val = await self.bot.redis.hget(f"db:member", int(int(member.id)))
        if val is None:
            val = await self.Member.find_one({"id": int(member.id)}, {"pokemon": 0, "pokedex": 0})
            v = "" if val is None else pickle.dumps(val.to_mongo())
            await self.bot.redis.hset(f"db:member", int(member.id), v)
        elif len(val) == 0:
            return None
        else:
            val = self.Member.build_from_mongo(pickle.loads(val))

        # If username in the database doesn't match with current username, update
        if (val and isinstance(member, (discord.Member, discord.User))) and val.username != member.name:
            result = await self.update_member(member, {"$set": {"username": member.name}})
            # Set it for the Member object to be returned as well, if modified successfully.
            # This check is not really necessary since it wouldn't get this far anyway if it doesn't
            # find any records, but doesn't hurt to have it still as a measure against any edge cases.
            if result.modified_count > 0:
                val.username = member.name

        return val

    async def fetch_next_idx(self, member: discord.Member | Member, reserve=1):
        result = await self.db.member.find_one_and_update(
            {"_id": int(member.id)},
            {"$inc": {"next_idx": reserve}},
            projection={"next_idx": 1},
        )
        await self.bot.redis.hdel(f"db:member", int(member.id))
        return result["next_idx"]

    async def reset_idx(self, member: discord.Member | Member, value):
        result = await self.db.member.find_one_and_update(
            {"_id": int(member.id)},
            {"$set": {"next_idx": value}},
            projection={"next_idx": 1},
        )
        await self.bot.redis.hdel(f"db:member", int(member.id))
        return result["next_idx"]

    async def fetch_pokedex(self, member: discord.Member | Member, start: int, end: int):
        filter_obj = {"claimed_pokedex_rewards": 1, "notified_milestones": 1}

        for i in range(start, end):
            filter_obj[f"pokedex.{i}"] = 1

        return await self.Member.find_one({"id": int(member.id)}, filter_obj)

    def fetch_market_list(self, aggregations=[]):
        pipeline = [
            {"$match": {"owned_by": "market"}},
            *aggregations,
        ]
        return self.db.pokemon.aggregate(pipeline, allowDiskUse=True)

    def fetch_auction_list(self, guild, aggregations=[]):
        pipeline = [
            {"$match": {"owned_by": "auction", "auction_data.guild_id": guild.id}},
            *aggregations,
        ]
        return self.db.pokemon.aggregate(pipeline, allowDiskUse=True)

    async def fetch_auction_count(self, guild, aggregations=[]):
        pipeline = [
            {"$match": {"owned_by": "auction", "auction_data.guild_id": guild.id}},
            *aggregations,
            {"$count": "num_matches"},
        ]
        result = await self.db.pokemon.aggregate(pipeline, allowDiskUse=True).to_list(None)

        if len(result) == 0:
            return 0

        return result[0]["num_matches"]

    async def fetch_pokemon_list(self, member: discord.Member | Member, aggregations=[]):
        pipeline = [
            {"$match": {"owner_id": int(member.id), "owned_by": "user"}},
            *aggregations,
        ]
        async for x in self.db.pokemon.aggregate(pipeline, allowDiskUse=True):
            yield self.bot.mongo.Pokemon.build_from_mongo(x)

    async def fetch_pokemon_count(self, member: discord.Member | Member, aggregations=[], *, max_time_ms=None):
        kwargs = {"maxTimeMS": max_time_ms} if max_time_ms else {}
        result = await self.db.pokemon.aggregate(
            [
                {"$match": {"owner_id": int(member.id), "owned_by": "user"}},
                *aggregations,
                {"$count": "num_matches"},
            ],
            allowDiskUse=True,
            **kwargs,
        ).to_list(None)

        if len(result) == 0:
            return 0

        return result[0]["num_matches"]

    async def fetch_pokedex_count(self, member: discord.Member | Member, aggregations=[]):
        result = await self.db.member.aggregate(
            [
                {"$match": {"_id": int(member.id)}},
                {"$project": {"pokedex": {"$objectToArray": "$pokedex"}}},
                {"$unwind": {"path": "$pokedex"}},
                {"$replaceRoot": {"newRoot": "$pokedex"}},
                *aggregations,
                {"$group": {"_id": "count", "result": {"$sum": 1}}},
            ],
            allowDiskUse=True,
        ).to_list(None)

        if len(result) == 0:
            return 0

        return result[0]["result"]

    async def fetch_pokedex_sum(self, member: discord.Member | Member, aggregations=[]):
        result = await self.db.member.aggregate(
            [
                {"$match": {"_id": int(member.id)}},
                {"$project": {"pokedex": {"$objectToArray": "$pokedex"}}},
                {"$unwind": {"path": "$pokedex"}},
                {"$replaceRoot": {"newRoot": "$pokedex"}},
                *aggregations,
                {"$group": {"_id": "sum", "result": {"$sum": "$v"}}},
            ],
            allowDiskUse=True,
        ).to_list(None)

        if len(result) == 0:
            return 0

        return result[0]["result"]

    async def make_pokemon(
        self,
        member: discord.User | discord.Member | Member,
        species: models.Species,
        *,
        shiny_boost: Optional[int] = 1,
        min_iv_percent: Optional[float] = 0,  # Minimum IV percentage 0-100
        max_iv_percent: Optional[float] = 100,  # Maximum IV percentage 0-100,
        **kwargs,
    ) -> dict[str, Any]:
        """Function to build a pokémon.

        Parameters
        ----------
        member : cogs.mongo.Member
            The Member mongo Document object representing a member.
            Used to determine shiny and idx.
        species : data.models.Species
            The species that the pokémon shousld be.
        shiny_boost : int
            How much to boost the shiny chance by (default 1).
        min_iv_percent : float
            Minimum total IV the pokémon should have (default 0).
        max_iv_percent : float
            Maximum total IV the pokémon should have (default 100).
        **kwargs
            Any other attribute of the pokémon can be passed in.
            E.g. shiny=True to guarantee shiny.

            You can pass in `member` and `idx` to make it faster as that
            removes the need to fetch them. Especially important for mass
            calls.

        Returns
        -------
        dict[str, Any]
            The dict containing all the data of the new pokémon, which can
            then be inserted into the database using `collection.insert`.
        """

        # Not sure if this instance check is the best way to do this, but isinstance does not work
        is_member_document = getattr(getattr(member, "opts", None), "template", None) == Member
        if not is_member_document and hasattr(member, "id"):
            member = await self.fetch_member_info(member)

        ivs = [random_iv() for _ in range(6)]
        if min_iv_percent > 0 or max_iv_percent < 100:
            min_iv = iv_percent_to_total(min_iv_percent)
            max_iv = iv_percent_to_total(max_iv_percent)
            ivs = random_iv_composition(sum_lower_bound=min_iv, sum_upper_bound=max_iv)

        level = min(max(int(random.normalvariate(20, 10)), 1), 50)
        shiny = member.determine_shiny(species, boost=shiny_boost)
        gender = generate_gender(species)

        possible_moves = [x.move.id for x in species.moves if level >= x.method.level]
        moves = random.sample(possible_moves, k=min(len(possible_moves), 4))
        idx = kwargs.pop("idx", None) or await self.fetch_next_idx(member)

        return {
            "owner_id": int(member.id),
            "owned_by": "user",
            "species_id": species.id,
            "level": level,
            "xp": 0,
            "nature": random_nature(),
            "iv_hp": ivs[0],
            "iv_atk": ivs[1],
            "iv_defn": ivs[2],
            "iv_satk": ivs[3],
            "iv_sdef": ivs[4],
            "iv_spd": ivs[5],
            "iv_total": sum(ivs),
            "shiny": shiny,
            "gender": gender,
            "moves": moves,
            "idx": idx,
            **kwargs,
        }

    async def update_member(self, member, update):
        if hasattr(member, "id"):
            member = member.id
        result = await self.db.member.update_one({"_id": member}, update)
        await self.bot.redis.hdel(f"db:member", int(member))
        return result

    async def update_pokemon(self, pokemon: Pokemon | dict, update: dict):
        if isinstance(pokemon, dict) and "_id" in pokemon:
            pokemon = self.Pokemon.build_from_mongo(pokemon)
        if hasattr(pokemon, "id"):
            pokemon_id = pokemon.id
        if hasattr(pokemon, "_id"):
            pokemon_id = pokemon._id

        gender_assigned = pokemon._gender is not None
        if not gender_assigned and ("gender" not in update):
            _set = update.setdefault("$set", {})
            _set["gender"] = pokemon.gender

        return await self.db.pokemon.update_one({"_id": pokemon_id}, update)

    async def fetch_pokemon(self, member: discord.Member, idx: int):
        if isinstance(idx, ObjectId):
            result = await self.db.pokemon.find_one({"_id": idx, "owned_by": "user"})
            if result is not None and result["owner_id"] != member.id:
                result = None
        elif idx == -1:
            result = await self.db.pokemon.aggregate(
                [
                    {"$match": {"owner_id": member.id, "owned_by": "user"}},
                    {"$sort": {"idx": -1}},
                    {"$limit": 1},
                ],
                allowDiskUse=True,
            ).to_list(None)

            if len(result) == 0:
                result = None
            else:
                result = result[0]
        else:
            result = await self.db.pokemon.find_one({"owner_id": member.id, "idx": idx, "owned_by": "user"})

        if result is None:
            return None

        return self.Pokemon.build_from_mongo(result)

    async def fetch_guild(self, guild: discord.Guild):
        g = await self.Guild.find_one({"id": guild.id})
        if g is None:
            g = self.Guild(id=guild.id)
            try:
                await g.commit()
            except pymongo.errors.DuplicateKeyError:
                pass
        return g

    async def update_guild(self, guild: discord.Guild, update):
        return await self.db.guild.update_one({"_id": guild.id}, update, upsert=True)

    async def fetch_channel(self, channel: discord.TextChannel):
        c = await self.Channel.find_one({"id": channel.id})
        if c is None:
            c = self.Channel(id=channel.id)
            await c.commit()
        return c

    async def update_channel(self, channel: discord.TextChannel, update):
        return await self.db.channel.update_one({"_id": channel.id}, update, upsert=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Mongo(bot))
