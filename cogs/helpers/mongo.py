import os
import random
from datetime import datetime

from motor.motor_asyncio import AsyncIOMotorClient
from umongo import Document, EmbeddedDocument, Instance, fields

from .constants import NATURES
from .models import GameData

random_iv = lambda: random.randint(0, 31)
random_nature = lambda: random.choice(NATURES)

# Instance

database_uri = os.getenv("DATABASE_URI")
database_name = os.getenv("DATABASE_NAME")

db = AsyncIOMotorClient(database_uri)[database_name]
instance = Instance(db)


@instance.register
class Pokemon(EmbeddedDocument):
    number = fields.IntegerField(required=True)
    species_id = fields.IntegerField(required=True)
    owner_id = fields.IntegerField(required=True)

    level = fields.IntegerField(required=True)
    xp = fields.IntegerField(required=True)

    nature = fields.StringField(required=True)

    iv_hp = fields.IntegerField(required=True)
    iv_atk = fields.IntegerField(required=True)
    iv_defn = fields.IntegerField(required=True)
    iv_satk = fields.IntegerField(required=True)
    iv_sdef = fields.IntegerField(required=True)
    iv_spd = fields.IntegerField(required=True)

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
            **kwargs
        )

    @property
    def species(self):
        return GameData.species_by_number(self.species_id)

    @property
    def max_xp(self):
        return 250 + 25 * self.level

    @property
    def hp(self):
        return (
            (2 * self.species.base_stats.hp + self.iv_hp + 5) * self.level // 100
            + self.level
            + 10
        )

    @property
    def atk(self):
        return (
            2 * self.species.base_stats.atk + self.iv_atk + 5
        ) * self.level // 100 + 5

    @property
    def defn(self):
        return (
            2 * self.species.base_stats.defn + self.iv_defn + 5
        ) * self.level // 100 + 5

    @property
    def satk(self):
        return (
            2 * self.species.base_stats.satk + self.iv_satk + 5
        ) * self.level // 100 + 5

    @property
    def sdef(self):
        return (
            2 * self.species.base_stats.sdef + self.iv_sdef + 5
        ) * self.level // 100 + 5

    @property
    def spd(self):
        return (
            2 * self.species.base_stats.spd + self.iv_spd + 5
        ) * self.level // 100 + 5

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


@instance.register
class Member(Document):
    id = fields.IntegerField(attribute="_id")
    pokemon = fields.ListField(fields.EmbeddedField(Pokemon), required=True)
    next_id = fields.IntegerField(required=True)
    selected = fields.IntegerField(required=True)
    order_by = fields.StringField(default="number")
    pokedex = fields.DictField(
        fields.StringField(), fields.IntegerField(), default=dict
    )
    balance = fields.IntegerField(default=0)
    redeems = fields.IntegerField(default=0)

    boost_expires = fields.DateTimeField(default=datetime.min)

    @property
    def selected_pokemon(self):
        return next(filter(lambda x: x.number == int(self.selected), self.pokemon))

    @property
    def boost_active(self):
        return datetime.now() < self.boost_expires


@instance.register
class Guild(Document):
    id = fields.IntegerField(attribute="_id")
    channel = fields.IntegerField(default=None)
    prefix = fields.StringField(default=None)
