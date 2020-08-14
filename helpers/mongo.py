import math
import os
import random
from datetime import datetime

from motor.motor_asyncio import AsyncIOMotorClient
from umongo import Document, EmbeddedDocument, Instance, fields

from . import constants, models

random_iv = lambda: random.randint(0, 31)
random_nature = lambda: random.choice(constants.NATURES)

# Instance

database_uri = os.getenv("DATABASE_URI")
database_name = os.getenv("DATABASE_NAME")

db = AsyncIOMotorClient(database_uri)[database_name]
instance = Instance(db)


@instance.register
class Pokemon(EmbeddedDocument):
    class Meta:
        strict = False

    id = fields.ObjectIdField(attribute="_id")
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
        return models.GameData.species_by_number(self.species_id)

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

    @property
    def next_evolution(self):
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
                    models.GameData.move_by_number(x).type_id
                    == evo.trigger.move_type_id
                    for x in self.moves
                ]
            ):
                can = False
            if evo.trigger.time:
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

    @property
    def can_evolve(self):
        return self.next_evolution is not None


@instance.register
class Member(Document):
    class Meta:
        strict = False

    id = fields.IntegerField(attribute="_id")
    pokemon = fields.ListField(fields.EmbeddedField(Pokemon), required=True)

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

    last_voted = fields.DateTimeField(default=datetime.min)
    vote_total = fields.IntegerField(default=0)
    vote_streak = fields.IntegerField(default=0)
    gifts_normal = fields.IntegerField(default=0)
    gifts_great = fields.IntegerField(default=0)
    gifts_ultra = fields.IntegerField(default=0)

    silence = fields.BooleanField(default=False)
    joined_at = fields.DateTimeField(default=None)
    invites = fields.IntegerField(default=0)

    suspended = fields.BooleanField(default=False)

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
    def shiny_hunt_chance(self):
        return (1 + math.tanh(self.shiny_streak / 50)) / 4096

    def determine_shiny(self, species):
        if self.shiny_hunt != species.dex_number:
            return random.randint(1, 4096) == 1
        else:
            return random.random() < self.shiny_hunt_chance


@instance.register
class Listing(Document):
    id = fields.IntegerField(attribute="_id")
    pokemon = fields.EmbeddedField(Pokemon, required=True)
    user_id = fields.IntegerField(required=True)
    price = fields.IntegerField(required=True)


@instance.register
class Guild(Document):
    id = fields.IntegerField(attribute="_id")
    channel = fields.IntegerField(default=None)
    channels = fields.ListField(fields.IntegerField, default=list)
    prefix = fields.StringField(default=None)
    silence = fields.BooleanField(default=False)


@instance.register
class Counter(Document):
    id = fields.StringField(attribute="_id")
    next = fields.IntegerField(default=0)


@instance.register
class Blacklist(Document):
    id = fields.IntegerField(attribute="_id")
