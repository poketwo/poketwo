import csv
import random
from abc import ABC, abstractmethod
from enum import Enum
from functools import cached_property
from pathlib import Path
from typing import ClassVar, List, overload
import unicodedata

from PIL import Image


def deaccent(text):
    norm = unicodedata.normalize("NFD", text)
    result = "".join(ch for ch in norm if unicodedata.category(ch) != "Mn")
    return unicodedata.normalize("NFC", result)


class _Data:
    pokemon = []
    items = {}


# Items


class Item:
    id: int
    name: str
    cost: int

    def __init__(self, id: int, name: str, cost: int):
        self.id = id
        self.name = name
        self.cost = cost

    def __str__(self):
        return self.name


# Evolution


class EvolutionTrigger(ABC):
    pass


class LevelTrigger(EvolutionTrigger):
    def __init__(self, level: int):
        self.level = level

    @cached_property
    def text(self):
        return f"starting from level {self.level}"


class ItemTrigger(EvolutionTrigger):
    def __init__(self, item: int):
        self.item_id = item

    @cached_property
    def item(self):
        return _Data.items[self.item_id]

    @cached_property
    def text(self):
        return "somehow"


class OtherTrigger(EvolutionTrigger):
    @cached_property
    def text(self):
        return "somehow"


class Evolution:
    def __init__(self, target: int, trigger: EvolutionTrigger, evotype: bool):
        self.target_id = target
        self.trigger = trigger
        self.type = evotype

    @classmethod
    def evolve_from(cls, target: int, trigger: EvolutionTrigger):
        return cls(target, trigger, False)

    @classmethod
    def evolve_to(cls, target: int, trigger: EvolutionTrigger):
        return cls(target, trigger, True)

    @cached_property
    def dir(self) -> str:
        return "to" if self.type == True else "from" if self.type == False else "??"

    @cached_property
    def target(self):
        return _Data.pokemon[self.target_id - 1]

    @cached_property
    def text(self):
        if (pevo := getattr(self.target, f"evolution_{self.dir}")) is not None:
            return f"evolves {self.dir} {self.target} {self.trigger.text}, which {pevo.text}"

        return f"evolves {self.dir} {self.target} {self.trigger.text}"


# Stats


class Stats:
    def __init__(self, hp: int, atk: int, defn: int, satk: int, sdef: int, spd: int):
        self.hp = hp
        self.atk = atk
        self.defn = defn
        self.satk = satk
        self.sdef = sdef
        self.spd = spd


# Species


class Species:
    id: int
    name: str
    slug: str
    names: dict
    base_stats: Stats
    evolution_from: Evolution
    evolution_to: Evolution
    mythical: bool
    legendary: bool
    ultra_beast: bool
    height: int
    weight: int

    def __init__(
        self,
        id: int,
        names: list,
        slug: str,
        base_stats: Stats,
        height: int,
        weight: int,
        evolution_from: Evolution = None,
        evolution_to: Evolution = None,
        mythical=False,
        legendary=False,
        ultra_beast=False,
    ):
        self.id = id
        self.names = names
        self.slug = slug
        self.name = next(filter(lambda x: x[0] == "🇬🇧", names))[1]
        self.base_stats = base_stats

        self.height = height
        self.weight = weight

        if evolution_from is not None and evolution_from.type != False:
            raise ValueError(Evolution)
        if evolution_to is not None and evolution_to.type != True:
            raise ValueError(Evolution)

        self.evolution_from = evolution_from
        self.evolution_to = evolution_to

        self.mythical = mythical
        self.legendary = legendary
        self.ultra_beast = ultra_beast

    def __str__(self):
        return self.name

    @cached_property
    def correct_guesses(self):
        return [deaccent(x.lower()) for _, x in self.names] + [self.slug]

    @cached_property
    def evolution_text(self):
        if self.evolution_from is not None and self.evolution_to is not None:
            return (
                f"{self.name} {self.evolution_from.text} and {self.evolution_to.text}."
            )
        elif self.evolution_from is not None:
            return f"{self.name} {self.evolution_from.text}."
        elif self.evolution_to is not None:
            return f"{self.name} {self.evolution_to.text}."
        else:
            return f"{self.name} is not know to evolve from or into any Pokémon."

    @cached_property
    def abundance(self):
        if self.ultra_beast:
            return 1
        if self.legendary:
            return 2
        if self.mythical:
            return 4
        if self.evolution_to is None:
            return 128

        return self.evolution_to.target.abundance * 4


def load_pokemon(pokemon):
    _Data.pokemon = pokemon


def load_items(items):
    _Data.items = items


class SpeciesNotFoundError(Exception):
    pass


class GameData:
    @classmethod
    def all_pokemon(cls) -> List[Species]:
        return _Data.pokemon

    @classmethod
    def species_by_number(cls, number: int) -> Species:
        if 0 <= number < len(_Data.pokemon):
            return _Data.pokemon[number - 1]
        else:
            raise SpeciesNotFoundError

    @classmethod
    def species_by_name(cls, name: str) -> Species:
        try:
            return next(
                filter(
                    lambda x: deaccent(name.lower()) in x.correct_guesses,
                    _Data.pokemon,
                )
            )
        except StopIteration:
            raise SpeciesNotFoundError

    @classmethod
    def get_image_url(cls, number: int) -> str:
        return (
            f"https://assets.pokemon.com/assets/cms2/img/pokedex/full/{number:03}.png"
        )

    @classmethod
    def random_spawn(cls):
        return random.choices(_Data.pokemon, weights=cls.spawn_weights(), k=1)[0]

    @classmethod
    def spawn_weights(cls):
        if not hasattr(cls, "_spawn_weights"):
            cls._spawn_weights = [p.abundance for p in _Data.pokemon]
        return cls._spawn_weights
