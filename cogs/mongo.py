import pickle
import math
import random
from datetime import datetime, timedelta, timezone

import discord
import pymongo
from bson.objectid import ObjectId
from data import models
from discord.ext import commands
from motor.motor_asyncio import AsyncIOMotorClient
from suntime import Sun
from umongo import Document, EmbeddedDocument, Instance, MixinDocument, fields

from helpers import constants

random_iv = lambda: random.randint(0, 31)
random_nature = lambda: random.choice(constants.NATURES)

# Instance


def calc_stat(pokemon, stat):
    base = getattr(pokemon.species.base_stats, stat)
    iv = getattr(pokemon, f"iv_{stat}")
    return math.floor(
        ((2 * base + iv + 5) * pokemon.level // 100 + 5)
        * constants.NATURE_MULTIPLIERS[pokemon.nature][stat]
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
        if self.shiny:
            name = "✨ "
        else:
            name = ""

        if "l" in spec:
            name += f"Level {self.level} "

        elif "L" in spec:
            name += f"L{self.level} "

        if "p" in spec:
            name += f"{self.iv_percentage:.2%} "

        if self.bot.sprites.status and "i" in spec:
            sprite = self.bot.sprites.get(self.species.dex_number, shiny=self.shiny)
            name = sprite + " " + name

        name += str(self.species)

        if self.nickname is not None and "n" in spec:
            name += ' "' + self.nickname + '"'

        if self.favorite and "f" in spec:
            name += " ❤️"

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
    def max_xp(self):
        return 250 + 25 * self.level

    @property
    def max_hp(self):
        if self.species_id == 292:
            return 1
        return (
            (2 * self.species.base_stats.hp + self.iv_hp + 5) * self.level // 100 + self.level + 10
        )

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

    def get_next_evolution(self, is_day):
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
                [
                    self.bot.data.move_by_number(x).type_id == evo.trigger.move_type_id
                    for x in self.moves
                ]
            ):
                can = False
            if evo.trigger.time == "day" and not is_day or evo.trigger.time == "night" and is_day:
                can = False

            if evo.trigger.relative_stats == 1 and self.atk <= self.defn:
                can = False
            if evo.trigger.relative_stats == -1 and self.defn <= self.atk:
                can = False
            if evo.trigger.relative_stats == 0 and self.atk != self.defn:
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


class EmbeddedPokemon(PokemonBase, EmbeddedDocument):
    class Meta:
        strict = False


class Member(Document):
    class Meta:
        strict = False

    # General
    id = fields.IntegerField(attribute="_id")
    joined_at = fields.DateTimeField(default=None)
    suspended = fields.BooleanField(default=False)

    # Pokémon
    next_idx = fields.IntegerField(default=1)
    selected_id = fields.ObjectIdField(required=True)
    order_by = fields.StringField(default="number")

    # Pokédex
    pokedex = fields.DictField(fields.StringField(), fields.IntegerField(), default=dict)
    shinies_caught = fields.IntegerField(default=0)

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
    last_voted = fields.DateTimeField(default=datetime.min)
    need_vote_reminder = fields.BooleanField(default=False)
    vote_total = fields.IntegerField(default=0)
    vote_streak = fields.IntegerField(default=0)
    gifts_normal = fields.IntegerField(default=0)
    gifts_great = fields.IntegerField(default=0)
    gifts_ultra = fields.IntegerField(default=0)
    gifts_master = fields.IntegerField(default=0)

    # Settings
    show_balance = fields.BooleanField(default=True)
    silence = fields.BooleanField(default=False)

    # Events
    halloween_tickets = fields.IntegerField(default=0)
    hquests = fields.DictField(fields.StringField(), fields.BooleanField(), default=dict)
    hquest_progress = fields.DictField(fields.StringField(), fields.IntegerField(), default=dict)
    halloween_badge = fields.BooleanField(default=False)

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
        # NOTE math.log is the natural log (log base e)
        return 1 + math.log(1 + self.shiny_streak / 30)

    def determine_shiny(self, species):
        chance = 1 / 4096
        if self.shiny_charm_active:
            chance *= 1.2
        if self.shiny_hunt == species.dex_number:
            chance *= self.shiny_hunt_multiplier

        return random.random() < chance


class Listing(Document):
    class Meta:
        strict = False

    id = fields.IntegerField(attribute="_id")
    pokemon = fields.EmbeddedField(EmbeddedPokemon, required=True)
    user_id = fields.IntegerField(required=True)
    price = fields.IntegerField(required=True)


class Auction(Document):
    class Meta:
        strict = False

    id = fields.IntegerField(attribute="_id")
    guild_id = fields.IntegerField(required=True)
    message_id = fields.IntegerField(required=True)
    pokemon = fields.EmbeddedField(EmbeddedPokemon, required=True)
    user_id = fields.IntegerField(required=True)
    current_bid = fields.IntegerField(required=True)
    bid_increment = fields.IntegerField(required=True)
    bidder_id = fields.IntegerField(default=None)
    ends = fields.DateTimeField(required=True)


class Guild(Document):
    class Meta:
        strict = False

    id = fields.IntegerField(attribute="_id")
    channel = fields.IntegerField(default=None)
    channels = fields.ListField(fields.IntegerField, default=list)
    prefix = fields.StringField(default=None)
    silence = fields.BooleanField(default=False)
    display_images = fields.BooleanField(default=True)
    auction_channel = fields.IntegerField(default=None)

    lat = fields.FloatField(default=37.7790262)
    lng = fields.FloatField(default=-122.4199061)
    loc = fields.StringField(
        default="San Francisco, San Francisco City and County, California, United States of America"
    )

    @property
    def is_day(self):
        sun = Sun(self.lat, self.lng)
        sunrise, sunset = sun.get_sunrise_time(), sun.get_sunset_time()
        if sunset < sunrise:
            sunset += timedelta(days=1)

        now = datetime.now(timezone.utc)
        return (
            sunrise < now < sunset
            or sunrise < now + timedelta(days=1) < sunset
            or sunrise < now + timedelta(days=-1) < sunset
        )


class Channel(Document):
    class Meta:
        strict = False

    id = fields.IntegerField(attribute="_id")
    spawns_remaining = fields.IntegerField(default=0)

    @property
    def incense_active(self):
        return self.spawns_remaining > 0

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
        self.db = AsyncIOMotorClient(bot.config.DATABASE_URI, io_loop=bot.loop)[
            bot.config.DATABASE_NAME
        ]
        instance = Instance(self.db)

        g = globals()

        for x in (
            "PokemonBase",
            "Pokemon",
            "EmbeddedPokemon",
            "Member",
            "Listing",
            "Guild",
            "Channel",
            "Counter",
            "Blacklist",
            "Sponsor",
            "Auction",
        ):
            setattr(self, x, instance.register(g[x]))
            getattr(self, x).bot = bot

    async def fetch_member_info(self, member: discord.Member):
        val = await self.bot.redis.hget(f"db:member", member.id)
        if val is None:
            val = await self.Member.find_one({"id": member.id}, {"pokemon": 0, "pokedex": 0})
            v = "" if val is None else pickle.dumps(val.to_mongo())
            await self.bot.redis.hset(f"db:member", member.id, v)
        elif len(val) == 0:
            return None
        else:
            val = self.Member.build_from_mongo(pickle.loads(val))
        return val

    async def fetch_next_idx(self, member: discord.Member, reserve=1):
        result = await self.db.member.find_one_and_update(
            {"_id": member.id},
            {"$inc": {"next_idx": reserve}},
            projection={"next_idx": 1},
        )
        await self.bot.redis.hdel(f"db:member", member.id)
        return result["next_idx"]

    async def reset_idx(self, member: discord.Member, value):
        result = await self.db.member.find_one_and_update(
            {"_id": member.id},
            {"$set": {"next_idx": value}},
            projection={"next_idx": 1},
        )
        await self.bot.redis.hdel(f"db:member", member.id)
        return result["next_idx"]

    async def fetch_pokedex(self, member: discord.Member, start: int, end: int):

        filter_obj = {}

        for i in range(start, end):
            filter_obj[f"pokedex.{i}"] = 1

        return await self.Member.find_one({"id": member.id}, filter_obj)

    async def fetch_market_list(self, aggregations=[]):
        async for x in self.db.listing.aggregate(aggregations, allowDiskUse=True):
            yield self.bot.mongo.Listing.build_from_mongo(x)

    async def fetch_auction_list(self, guild, aggregations=[]):
        async for x in self.db.auction.aggregate(
            [
                {"$match": {"guild_id": guild.id}},
                *aggregations,
            ],
            allowDiskUse=True,
        ):
            yield self.bot.mongo.Auction.build_from_mongo(x)

    async def fetch_auction_count(self, guild, aggregations=[]):

        result = await self.db.auction.aggregate(
            [
                {"$match": {"guild_id": guild.id}},
                *aggregations,
                {"$count": "num_matches"},
            ],
            allowDiskUse=True,
        ).to_list(None)

        if len(result) == 0:
            return 0

        return result[0]["num_matches"]

    async def fetch_pokemon_list(self, member: discord.Member, aggregations=[]):
        async for x in self.db.pokemon.aggregate(
            [
                {"$match": {"owner_id": member.id}},
                {"$sort": {"idx": 1}},
                {"$project": {"pokemon": "$$ROOT", "idx": "$idx"}},
                *aggregations,
                {"$replaceRoot": {"newRoot": "$pokemon"}},
            ],
            allowDiskUse=True,
        ):
            yield self.bot.mongo.Pokemon.build_from_mongo(x)

    async def fetch_pokemon_count(self, member: discord.Member, aggregations=[]):

        result = await self.db.pokemon.aggregate(
            [
                {"$match": {"owner_id": member.id}},
                {"$project": {"pokemon": "$$ROOT"}},
                *aggregations,
                {"$count": "num_matches"},
            ],
            allowDiskUse=True,
        ).to_list(None)

        if len(result) == 0:
            return 0

        return result[0]["num_matches"]

    async def fetch_pokedex_count(self, member: discord.Member, aggregations=[]):

        result = await self.db.member.aggregate(
            [
                {"$match": {"_id": member.id}},
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

    async def fetch_pokedex_sum(self, member: discord.Member, aggregations=[]):

        result = await self.db.member.aggregate(
            [
                {"$match": {"_id": member.id}},
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

    async def update_member(self, member, update):
        if hasattr(member, "id"):
            member = member.id
        result = await self.db.member.update_one({"_id": member}, update)
        await self.bot.redis.hdel(f"db:member", int(member))
        return result

    async def update_pokemon(self, pokemon, update):
        if hasattr(pokemon, "id"):
            pokemon = pokemon.id
        if hasattr(pokemon, "_id"):
            pokemon = pokemon._id
        if isinstance(pokemon, dict) and "_id" in pokemon:
            pokemon = pokemon["_id"]
        return await self.db.pokemon.update_one({"_id": pokemon}, update)

    async def fetch_pokemon(self, member: discord.Member, idx: int):
        if isinstance(idx, ObjectId):
            result = await self.db.pokemon.find_one({"_id": idx})
        elif idx == -1:
            result = await self.db.pokemon.aggregate(
                [
                    {"$match": {"owner_id": member.id}},
                    {"$sort": {"idx": -1}},
                    {"$project": {"pokemon": "$$ROOT", "idx": "$idx"}},
                    {"$limit": 1},
                ],
                allowDiskUse=True,
            ).to_list(None)

            if len(result) == 0 or "pokemon" not in result[0]:
                result = None
            else:
                result = result[0]["pokemon"]
        else:
            result = await self.db.pokemon.find_one({"owner_id": member.id, "idx": idx})

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


def setup(bot: commands.Bot):
    bot.add_cog(Mongo(bot))
