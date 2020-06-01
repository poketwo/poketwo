import csv
from abc import ABC, abstractmethod
from enum import Enum
from pathlib import Path
from typing import ClassVar, List, overload

from PIL import Image


class _Data:
    pokemon = []


# Evolution


class EvolutionTrigger(ABC):
    pass


class LevelTrigger(EvolutionTrigger):
    def __init__(self, level: int):
        self.level = level

    @property
    def text(self):
        return f"starting from level {self.level}"


class OtherTrigger(EvolutionTrigger):
    @property
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

    @property
    def dir(self) -> str:
        return "to" if self.type == True else "from" if self.type == False else "??"

    @property
    def target(self):
        return _Data.pokemon[self.target_id - 1]

    @property
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
    def __init__(
        self,
        id_: int,
        name: str,
        base_stats: Stats,
        evolution_from: Evolution = None,
        evolution_to: Evolution = None,
    ):
        self.id = id_
        self.name = name
        self.base_stats = base_stats

        if evolution_from is not None and evolution_from.type != False:
            raise ValueError(Evolution)
        if evolution_to is not None and evolution_to.type != True:
            raise ValueError(Evolution)

        self.evolution_from = evolution_from
        self.evolution_to = evolution_to

    def __str__(self):
        return self.name

    @property
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


def load_pokemon(pokemon):
    _Data.pokemon = pokemon


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
            return next(filter(lambda x: x.name.lower() == name.lower(), _Data.pokemon))
        except StopIteration:
            raise SpeciesNotFoundError

    @classmethod
    def get_image_url(cls, number: int) -> str:
        return (
            f"https://assets.pokemon.com/assets/cms2/img/pokedex/full/{number:03}.png"
        )
