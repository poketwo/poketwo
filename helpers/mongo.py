import math
import os
import random
from datetime import datetime, timedelta, timezone

from motor.motor_asyncio import AsyncIOMotorClient
from suntime import Sun
from umongo import Document, EmbeddedDocument, Instance, MixinDocument, fields

from . import constants, models

random_iv = lambda: random.randint(0, 31)
random_nature = lambda: random.choice(constants.NATURES)

# Instance


class PokemonBase(MixinDocument):
    class Meta:
        strict = False
        abstract = True

    id = fields.ObjectIdField(attribute="_id")
    timestamp = fields.DateTimeField(default=datetime.utcnow)
    owner_id = fields.IntegerField(required=True)

    species_id = fields.IntegerField(required=True)
    level = fields.IntegerField(required=True)
    xp = fields.IntegerField(required=True)
    nature = fields.StringField(required=True)

    iv_hp = fields.IntegerField(required=True)
    iv_atk = fields.IntegerField(required=True)
    iv_defn = fields.IntegerField(required=True)
    iv_satk = fields.IntegerField(required=True)
    iv_sdef = fields.IntegerField(required=True)
    iv_spd = fields.IntegerField(required=True)

    nickname = fields.StringField(default=None)
    favorite = fields.BooleanField(default=False)

    shiny = fields.BooleanField(required=True)
    held_item = fields.IntegerField(default=None)

    moves = fields.ListField(fields.IntegerField, default=list)

    idx = None
    _hp = None
    ailments = None
    stages = None

    @classmethod
    def random(cls, **kwargs):
        return cls(
            iv_hp=random_iv(),
            iv_atk=random_iv(),
            iv_defn=random_iv(),
            iv_satk=random_iv(),
            iv_sdef=random_iv(),
            iv_spd=random_iv(),
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
            (2 * self.species.base_stats.hp + self.iv_hp + 5) * self.level // 100
            + self.level
            + 10
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
        return math.floor(
            (
                (2 * self.species.base_stats.atk + self.iv_atk + 5) * self.level // 100
                + 5
            )
            * constants.NATURE_MULTIPLIERS[self.nature]["atk"]
        )

    @property
    def defn(self):
        return math.floor(
            (
                (2 * self.species.base_stats.defn + self.iv_defn + 5)
                * self.level
                // 100
                + 5
            )
            * constants.NATURE_MULTIPLIERS[self.nature]["defn"]
        )

    @property
    def satk(self):
        return math.floor(
            (
                (2 * self.species.base_stats.satk + self.iv_satk + 5)
                * self.level
                // 100
                + 5
            )
            * constants.NATURE_MULTIPLIERS[self.nature]["satk"]
        )

    @property
    def sdef(self):
        return math.floor(
            (
                (2 * self.species.base_stats.sdef + self.iv_sdef + 5)
                * self.level
                // 100
                + 5
            )
            * constants.NATURE_MULTIPLIERS[self.nature]["sdef"]
        )

    @property
    def spd(self):
        return math.floor(
            (
                (2 * self.species.base_stats.spd + self.iv_spd + 5) * self.level // 100
                + 5
            )
            * constants.NATURE_MULTIPLIERS[self.nature]["spd"]
        )

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
            if (
                evo.trigger.time == "day"
                and not is_day
                or evo.trigger.time == "night"
                and is_day
            ):
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

    pass


class EmbeddedPokemon(PokemonBase, EmbeddedDocument):
    class Meta:
        strict = False

    pass


class Member(Document):
    class Meta:
        strict = False

    id = fields.IntegerField(attribute="_id")

    selected = fields.IntegerField(required=True)

    order_by = fields.StringField(default="number")
    pokedex = fields.DictField(
        fields.StringField(), fields.IntegerField(), default=dict
    )
    shinies_caught = fields.IntegerField(default=0)
    balance = fields.IntegerField(default=0)
    redeems = fields.IntegerField(default=0)

    shiny_hunt = fields.IntegerField(default=None)
    shiny_streak = fields.IntegerField(default=0)

    boost_expires = fields.DateTimeField(default=datetime.min)
    shiny_charm_expires = fields.DateTimeField(default=datetime.min)

    last_voted = fields.DateTimeField(default=datetime.min)
    vote_total = fields.IntegerField(default=0)
    vote_streak = fields.IntegerField(default=0)
    gifts_normal = fields.IntegerField(default=0)
    gifts_great = fields.IntegerField(default=0)
    gifts_ultra = fields.IntegerField(default=0)
    gifts_master = fields.IntegerField(default=0)

    silence = fields.BooleanField(default=False)
    joined_at = fields.DateTimeField(default=None)
    invites = fields.IntegerField(default=0)

    suspended = fields.BooleanField(default=False)
    premium_balance = fields.IntegerField(default=0)

    redeems_purchased = fields.DictField(
        fields.IntegerField(), fields.IntegerField(), default=dict
    )

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
    id = fields.IntegerField(attribute="_id")
    pokemon = fields.EmbeddedField(EmbeddedPokemon, required=True)
    user_id = fields.IntegerField(required=True)
    price = fields.IntegerField(required=True)


class Guild(Document):
    id = fields.IntegerField(attribute="_id")
    channel = fields.IntegerField(default=None)
    channels = fields.ListField(fields.IntegerField, default=list)
    prefix = fields.StringField(default=None)
    silence = fields.BooleanField(default=False)
    display_images = fields.BooleanField(default=True)

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
    id = fields.IntegerField(attribute="_id")
    incense_expires = fields.DateTimeField(default=datetime.min)

    @property
    def incense_active(self):
        return datetime.utcnow() < self.incense_expires


class Counter(Document):
    id = fields.StringField(attribute="_id")
    next = fields.IntegerField(default=0)


class Blacklist(Document):
    id = fields.IntegerField(attribute="_id")


class Database:
    def __init__(self, bot, host, dbname):
        self.db = AsyncIOMotorClient(host, io_loop=bot.loop)[dbname]
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
        ):
            setattr(self, x, instance.register(g[x]))
            getattr(self, x).bot = bot
