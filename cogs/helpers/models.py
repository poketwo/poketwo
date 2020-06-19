import csv
import random
import unicodedata
from abc import ABC, abstractmethod
from enum import Enum
from functools import cached_property
from pathlib import Path
from typing import ClassVar, List, Union, overload

from PIL import Image


def deaccent(text):
    norm = unicodedata.normalize("NFD", text)
    result = "".join(ch for ch in norm if unicodedata.category(ch) != "Mn")
    return unicodedata.normalize("NFC", result)


class _Data:
    pokemon = {}
    items = {}


# Items


class Item:
    id: int
    name: str
    description: str
    cost: int
    page: int
    action: str
    inline: bool
    emote: str

    def __init__(
        self,
        id: int,
        name: str,
        description: str,
        cost: int,
        page: int,
        action: str,
        inline: bool,
        emote: str = None,
    ):
        self.id = id
        self.name = name
        self.description = description
        self.cost = cost
        self.page = page
        self.action = action
        self.inline = inline
        self.emote = emote

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
        return f"using a {self.item}"


class TradeTrigger(EvolutionTrigger):
    def __init__(self, item: int = None):
        self.item_id = item

    @cached_property
    def item(self):
        if self.item_id is None:
            return None
        return _Data.items[self.item_id]

    @cached_property
    def text(self):
        if self.item_id is None:
            return "when traded"
        return f"when traded while holding a {self.item}"


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
        return _Data.pokemon[self.target_id]

    @cached_property
    def text(self):
        if (pevo := getattr(self.target, f"evolution_{self.dir}")) is not None:
            return f"evolves {self.dir} {self.target} {self.trigger.text}, which {pevo.text}"

        return f"evolves {self.dir} {self.target} {self.trigger.text}"


class EvolutionList:
    items: list

    def __init__(self, evolutions: Union[list, Evolution]):
        if type(evolutions) == Evolution:
            evolutions = [evolutions]
        self.items = evolutions

    @cached_property
    def text(self):
        txt = " and ".join(e.text for e in self.items)
        txt = txt.replace(" and ", ", ", txt.count(" and ") - 1)
        return txt


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
    evolution_from: EvolutionList
    evolution_to: EvolutionList
    mythical: bool
    legendary: bool
    ultra_beast: bool
    dex_number: int
    height: int
    weight: int
    catchable: bool
    is_form: bool
    types: List[str]
    form_item: int
    abundance: int

    mega_id: int
    mega_x_id: int
    mega_y_id: int

    def __init__(
        self,
        id: int,
        names: list,
        slug: str,
        base_stats: Stats,
        height: int,
        weight: int,
        dex_number: int,
        catchable: bool,
        types: List[str],
        abundance: int,
        mega_id: int = None,
        mega_x_id: int = None,
        mega_y_id: int = None,
        evolution_from: List[Evolution] = None,
        evolution_to: List[Evolution] = None,
        mythical: bool = False,
        legendary: bool = False,
        ultra_beast: bool = False,
        is_form: bool = False,
        form_item: int = None,
    ):
        self.id = id
        self.names = names
        self.slug = slug
        self.name = next(filter(lambda x: x[0] == "🇬🇧", names))[1]
        self.base_stats = base_stats
        self.dex_number = dex_number
        self.catchable = catchable
        self.is_form = is_form
        self.form_item = form_item
        self.abundance = abundance

        self.height = height
        self.weight = weight

        self.mega_id = mega_id
        self.mega_x_id = mega_x_id
        self.mega_y_id = mega_y_id

        self.types = types

        if evolution_from is not None:
            self.evolution_from = EvolutionList(evolution_from)
        else:
            self.evolution_from = None

        if evolution_to is not None:
            self.evolution_to = EvolutionList(evolution_to)
        else:
            self.evolution_to = None

        self.mythical = mythical
        self.legendary = legendary
        self.ultra_beast = ultra_beast

    def __str__(self):
        return self.name

    @cached_property
    def mega(self):
        if self.mega_id is None:
            return None

        return _Data.pokemon[self.mega_id]

    @cached_property
    def mega_x(self):
        if self.mega_x_id is None:
            return None

        return _Data.pokemon[self.mega_x_id]

    @cached_property
    def mega_y(self):
        if self.mega_y_id is None:
            return None

        return _Data.pokemon[self.mega_y_id]

    @cached_property
    def image_url(self):
        return f"https://assets.poketwo.net/images/{self.id}.png"

    @cached_property
    def shiny_image_url(self):
        return f"https://assets.poketwo.net/shiny/{self.id}.png"

    @cached_property
    def correct_guesses(self):
        extra = []
        if self.is_form:
            extra.extend(_Data.pokemon[self.dex_number].correct_guesses)
        if "nidoran" in self.slug:
            extra.append("nidoran")
        return extra + [deaccent(x.lower()) for _, x in self.names] + [self.slug]

    @cached_property
    def level_evolution(self):
        if self.evolution_to is None:
            return None

        for e in self.evolution_to.items:
            if isinstance(e.trigger, LevelTrigger):
                return e

        return None

    @cached_property
    def trade_evolution(self):
        if self.evolution_to is None:
            return None

        for e in self.evolution_to.items:
            if isinstance(e.trigger, TradeTrigger):
                return e

        return None

    @cached_property
    def evolution_text(self):
        if self.is_form and self.form_item is not None:
            species = _Data.pokemon[self.dex_number]
            item = _Data.items[self.form_item]
            return f"{self.name} transforms from {species} when given a {item.name}."

        if self.evolution_from is not None and self.evolution_to is not None:
            return (
                f"{self.name} {self.evolution_from.text} and {self.evolution_to.text}."
            )
        elif self.evolution_from is not None:
            return f"{self.name} {self.evolution_from.text}."
        elif self.evolution_to is not None:
            return f"{self.name} {self.evolution_to.text}."
        else:
            return None


def load_pokemon(pokemon):
    _Data.pokemon = pokemon


def load_items(items):
    _Data.items = items


class SpeciesNotFoundError(Exception):
    pass


class GameData:
    @classmethod
    def all_pokemon(cls):
        return _Data.pokemon.values()

    @classmethod
    def list_mythical(cls):
        if not hasattr(cls, "_mythical"):
            cls._mythical = [v.id for v in _Data.pokemon.values() if v.mythical]
        return cls._mythical

    @classmethod
    def list_legendary(cls):
        if not hasattr(cls, "_legendary"):
            cls._legendary = [v.id for v in _Data.pokemon.values() if v.legendary]
        return cls._legendary

    @classmethod
    def list_ub(cls):
        if not hasattr(cls, "_ultra_beast"):
            cls._ultra_beast = [v.id for v in _Data.pokemon.values() if v.ultra_beast]
        return cls._ultra_beast

    @classmethod
    def list_mega(cls):
        if not hasattr(cls, "_mega"):
            cls._mega = (
                [v.mega_id for v in _Data.pokemon.values() if v.mega_id is not None]
                + [
                    v.mega_x_id
                    for v in _Data.pokemon.values()
                    if v.mega_x_id is not None
                ]
                + [
                    v.mega_y_id
                    for v in _Data.pokemon.values()
                    if v.mega_y_id is not None
                ]
            )
        return cls._mega

    @classmethod
    def list_type(cls, typee: str):
        return [v.id for v in _Data.pokemon.values() if typee.title() in v.types]

    @classmethod
    def all_items(cls):
        return _Data.items.values()

    @classmethod
    def all_species_by_number(cls, number: int) -> Species:
        return [x for x in _Data.pokemon.values() if x.dex_number == number]

    @classmethod
    def all_species_by_name(cls, name: str) -> Species:
        return [
            x
            for x in _Data.pokemon.values()
            if deaccent(name.lower().replace("’", "'")) in x.correct_guesses
        ]

    @classmethod
    def find_all_matches(cls, name: str) -> Species:
        return [
            y.id
            for x in cls.all_species_by_name(name)
            for y in cls.all_species_by_number(x.id)
        ]

    @classmethod
    def species_by_number(cls, number: int) -> Species:
        try:
            return _Data.pokemon[number]
        except KeyError:
            raise SpeciesNotFoundError

    @classmethod
    def species_by_name(cls, name: str) -> Species:
        try:
            return next(
                filter(
                    lambda x: deaccent(name.lower().replace("’", "'"))
                    in x.correct_guesses,
                    _Data.pokemon.values(),
                )
            )
        except StopIteration:
            raise SpeciesNotFoundError

    @classmethod
    def item_by_number(cls, number: int) -> Item:
        try:
            return _Data.items[number]
        except KeyError:
            raise SpeciesNotFoundError

    @classmethod
    def item_by_name(cls, name: str) -> Item:
        try:
            return next(
                filter(lambda x: name.lower() == x.name.lower(), _Data.items.values())
            )
        except StopIteration:
            raise SpeciesNotFoundError

    @classmethod
    def random_spawn(cls, rarity="normal"):

        if rarity == "mythical":
            pool = [x for x in cls.all_pokemon() if x.catchable and x.mythical]
        elif rarity == "legendary":
            pool = [x for x in cls.all_pokemon() if x.catchable and x.legendary]
        elif rarity == "ultra_beast":
            pool = [x for x in cls.all_pokemon() if x.catchable and x.ultra_beast]
        else:
            pool = [x for x in cls.all_pokemon() if x.catchable]

        x = random.choices(pool, weights=[x.abundance for x in pool], k=1)[0]

        return x

    @classmethod
    def spawn_weights(cls):
        if not hasattr(cls, "_spawn_weights"):
            cls._spawn_weights = [p.abundance for p in _Data.pokemon.values()]
        return cls._spawn_weights
