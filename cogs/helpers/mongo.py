import random

from mongoengine.connection import get_db
from mongoengine.document import *
from mongoengine.fields import *
from pymongo import ReturnDocument

from .constants import NATURES
from .models import GameData

random_iv = lambda: random.randint(0, 31)
random_nature = lambda: random.choice(NATURES)


class Pokemon(EmbeddedDocument):
    number = IntField(required=True)
    species_id = IntField(min_value=1, max_value=807, required=True)
    owner_id = LongField(required=True)

    level = IntField(min_value=1, max_value=100, required=True)
    xp = IntField(min_value=0, default=0, required=True)

    nature = StringField(default=random_nature, required=True)

    iv_hp = IntField(min_value=0, max_value=31, default=random_iv, required=True)
    iv_atk = IntField(min_value=0, max_value=31, default=random_iv, required=True)
    iv_defn = IntField(min_value=0, max_value=31, default=random_iv, required=True)
    iv_satk = IntField(min_value=0, max_value=31, default=random_iv, required=True)
    iv_sdef = IntField(min_value=0, max_value=31, default=random_iv, required=True)
    iv_spd = IntField(min_value=0, max_value=31, default=random_iv, required=True)

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


class Member(Document):
    id = LongField(primary_key=True)
    pokemon = EmbeddedDocumentListField(Pokemon, required=True)
    next_id = IntField(default=1, required=True)
    selected = IntField(default=1, required=True)

    @property
    def selected_pokemon(self):
        return self.pokemon.get(number=self.selected)


class Guild(Document):
    id = LongField(primary_key=True)
    counter = IntField(default=0, required=True)
    channel = LongField()
