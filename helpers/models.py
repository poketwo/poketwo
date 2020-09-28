import typing
import random
import unicodedata
from abc import ABC
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from typing import ClassVar, List, Union, overload

from . import constants


def deaccent(text):
    norm = unicodedata.normalize("NFD", text)
    result = "".join(ch for ch in norm if unicodedata.category(ch) != "Mn")
    return unicodedata.normalize("NFC", result)


#


class UnregisteredError(Exception):
    pass


class UnregisteredDataManager:
    pass


# Moves


@dataclass
class MoveEffect:
    id: int
    description: str

    instance: typing.Any = UnregisteredDataManager()


@dataclass
class StatChange:
    stat_id: int
    change: int

    @cached_property
    def stat(self):
        return ("hp", "atk", "defn", "satk", "sdef", "spd", "evasion", "accuracy")[
            self.stat_id - 1
        ]


@dataclass
class StatStages:
    atk: int = 0
    defn: int = 0
    satk: int = 0
    sdef: int = 0
    spd: int = 0
    evasion: int = 0
    accuracy: int = 0
    crit: int = 0

    def update(self, stages):
        self.atk += stages.atk
        self.defn += stages.defn
        self.satk += stages.satk
        self.sdef += stages.sdef
        self.spd += stages.spd
        self.evasion += stages.evasion
        self.accuracy += stages.accuracy
        self.crit += stages.crit


@dataclass
class MoveResult:
    success: bool
    damage: int
    healing: int
    ailment: str
    messages: typing.List[str]
    stat_changes: typing.List[StatChange]


@dataclass
class MoveMeta:
    meta_category_id: int
    meta_ailment_id: int
    drain: int
    healing: int
    crit_rate: int
    ailment_chance: int
    flinch_chance: int
    stat_chance: int
    min_hits: typing.Optional[int] = None
    max_hits: typing.Optional[int] = None
    min_turns: typing.Optional[int] = None
    max_turns: typing.Optional[int] = None
    stat_changes: typing.List[StatChange] = None

    def __post_init__(self):
        if self.stat_changes is None:
            self.stat_changes = []

    @cached_property
    def meta_category(self):
        return constants.MOVE_META_CATEGORIES[self.meta_category_id]

    @cached_property
    def meta_ailment(self):
        return constants.MOVE_AILMENTS[self.meta_ailment_id]


@dataclass
class Move:
    id: int
    slug: str
    name: str
    power: int
    pp: int
    accuracy: int
    priority: int
    target_id: int
    type_id: int
    damage_class_id: int
    effect_id: int
    effect_chance: int
    meta: MoveMeta

    instance: typing.Any = UnregisteredDataManager()

    @cached_property
    def type(self):
        return constants.TYPES[self.type_id]

    @cached_property
    def target_text(self):
        return constants.MOVE_TARGETS[self.target_id]

    @cached_property
    def damage_class(self):
        return constants.DAMAGE_CLASSES[self.damage_class_id]

    @cached_property
    def effect(self):
        return self.instance.effects[self.effect_id]

    @cached_property
    def description(self):
        return self.effect.description.format(effect_chance=self.effect_chance)

    def __str__(self):
        return self.name

    def calculate_turn(self, pokemon, opponent):
        if self.damage_class_id == 1 or self.power is None:
            success = True
            damage = 0
            hits = 0
        else:
            success = random.randrange(100) < self.accuracy * (
                constants.STAT_STAGE_MULTIPLIERS[pokemon.stages.accuracy] * 2 + 1
            ) / (constants.STAT_STAGE_MULTIPLIERS[opponent.stages.evasion] * 2 + 1)

            hits = random.randint(self.meta.min_hits or 1, self.meta.max_hits or 1)

            if self.damage_class_id == 2:
                atk = pokemon.atk * constants.STAT_STAGE_MULTIPLIERS[pokemon.stages.atk]
                defn = (
                    opponent.defn
                    * constants.STAT_STAGE_MULTIPLIERS[opponent.stages.defn]
                )
            else:
                atk = (
                    pokemon.satk * constants.STAT_STAGE_MULTIPLIERS[pokemon.stages.satk]
                )
                defn = (
                    opponent.sdef
                    * constants.STAT_STAGE_MULTIPLIERS[opponent.stages.sdef]
                )

            damage = int((2 * pokemon.level / 5 + 2) * self.power * atk / defn / 50 + 2)

        healing = damage * self.meta.drain / 100
        healing += pokemon.max_hp * self.meta.healing / 100

        for ailment in pokemon.ailments:
            if ailment == "Paralysis":
                if random.random() < 0.25:
                    success = False
            elif ailment == "Sleep":
                if self.id not in (173, 214):
                    success = False
            elif ailment == "Freeze":
                if self.id not in (588, 172, 221, 293, 503, 592):
                    success = False
            elif ailment == "Burn":
                if self.damage_class_id == 2:
                    damage /= 2

            # elif ailment == "Confusion":
            #     pass
            # elif ailment == "Infatuation":
            #     pass
            # elif ailment == "Trap":
            #     pass
            # elif ailment == "Nightmare":
            #     pass
            # elif ailment == "Torment":
            #     pass
            # elif ailment == "Disable":
            #     pass
            # elif ailment == "Yawn":
            #     pass
            # elif ailment == "Heal Block":
            #     pass
            # elif ailment == "No type immunity":
            #     pass
            # elif ailment == "Leech Seed":
            #     pass
            # elif ailment == "Embargo":
            #     pass
            # elif ailment == "Perish Song":
            #     pass
            # elif ailment == "Ingrain":
            #     pass
            # elif ailment == "Silence":
            #     pass

        ailment = (
            self.meta.meta_ailment
            if random.randrange(100) < self.meta.ailment_chance
            else None
        )

        typ_mult = 1
        for typ in opponent.species.types:
            typ_mult *= constants.TYPE_EFFICACY[self.type_id][
                constants.TYPES.index(typ)
            ]

        damage *= typ_mult
        messages = []

        if typ_mult == 0:
            messages.append("It's not effective...")
        elif typ_mult > 1:
            messages.append("It's super effective!")
        elif typ_mult < 1:
            messages.append("It's not very effective...")

        if hits > 1:
            messages.append(f"It hit {hits} times!")

        changes = []

        for change in self.meta.stat_changes:
            if random.randrange(100) < self.meta.stat_chance:
                changes.append(change)

        return MoveResult(
            success=success,
            damage=damage,
            healing=healing,
            ailment=ailment,
            messages=messages,
            stat_changes=changes,
        )


# Items


@dataclass
class Item:
    id: int
    name: str
    description: str
    cost: int
    page: int
    action: str
    inline: bool
    emote: str = None
    shard: bool = False

    instance: typing.Any = UnregisteredDataManager()

    def __str__(self):
        return self.name


class MoveMethod(ABC):
    pass


@dataclass
class LevelMethod(MoveMethod):
    level: int

    instance: typing.Any = UnregisteredDataManager()

    @cached_property
    def text(self):
        return f"Level {self.level}"


@dataclass
class PokemonMove:
    move_id: int
    method: MoveMethod

    instance: typing.Any = UnregisteredDataManager()

    @cached_property
    def move(self):
        return self.instance.moves[self.move_id]

    @cached_property
    def text(self):
        return self.method.text


# Evolution


@dataclass
class EvolutionTrigger(ABC):
    pass


@dataclass
class LevelTrigger(EvolutionTrigger):
    level: int
    item_id: int
    move_id: int
    move_type_id: int
    time: str
    relative_stats: int

    instance: typing.Any = UnregisteredDataManager()

    @cached_property
    def item(self):
        if self.item_id is None:
            return None
        return self.instance.items[self.item_id]

    @cached_property
    def move(self):
        if self.move_id is None:
            return None
        return self.instance.moves[self.move_id]

    @cached_property
    def move_type(self):
        if self.move_type_id is None:
            return None
        return constants.TYPES[self.move_type_id]

    @cached_property
    def text(self):
        if self.level is None:
            text = f"when leveled up"
        else:
            text = f"starting from level {self.level}"

        if self.item is not None:
            text += f" while holding a {self.item}"

        if self.move is not None:
            text += f" while knowing {self.move}"

        if self.move_type is not None:
            text += f" while knowing a {self.move_type}-type move"

        if self.relative_stats == 1:
            text += f" when its Attack is higher than its Defense"
        elif self.relative_stats == -1:
            text += f" when its Defense is higher than its Attack"
        elif self.relative_stats == 0:
            text += f" when its Attack is equal to its Defense"

        if self.time is not None:
            text += " in the " + self.time + "time"

        return text


@dataclass
class ItemTrigger(EvolutionTrigger):
    item_id: int

    instance: typing.Any = UnregisteredDataManager()

    @cached_property
    def item(self):
        return self.instance.items[self.item_id]

    @cached_property
    def text(self):
        return f"using a {self.item}"


@dataclass
class TradeTrigger(EvolutionTrigger):
    item_id: int = None

    instance: typing.Any = UnregisteredDataManager()

    @cached_property
    def item(self):
        if self.item_id is None:
            return None
        return self.instance.items[self.item_id]

    @cached_property
    def text(self):
        if self.item_id is None:
            return "when traded"
        return f"when traded while holding a {self.item}"


@dataclass
class OtherTrigger(EvolutionTrigger):
    instance: typing.Any = UnregisteredDataManager()

    @cached_property
    def text(self):
        return "somehow"


@dataclass
class Evolution:
    target_id: int
    trigger: EvolutionTrigger
    type: bool

    instance: typing.Any = UnregisteredDataManager()

    @classmethod
    def evolve_from(cls, target: int, trigger: EvolutionTrigger, instance=None):
        if instance is None:
            instance: typing.Any = UnregisteredDataManager()
        return cls(target, trigger, False, instance=instance)

    @classmethod
    def evolve_to(cls, target: int, trigger: EvolutionTrigger, instance=None):
        if instance is None:
            instance: typing.Any = UnregisteredDataManager()
        return cls(target, trigger, True, instance=instance)

    @cached_property
    def dir(self) -> str:
        return "to" if self.type == True else "from" if self.type == False else "??"

    @cached_property
    def target(self):
        return self.instance.pokemon[self.target_id]

    @cached_property
    def text(self):
        if getattr(self.target, f"evolution_{self.dir}") is not None:
            pevo = getattr(self.target, f"evolution_{self.dir}")
            return f"evolves {self.dir} {self.target} {self.trigger.text}, which {pevo.text}"

        return f"evolves {self.dir} {self.target} {self.trigger.text}"


@dataclass
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


@dataclass
class Stats:
    hp: int
    atk: int
    defn: int
    satk: int
    sdef: int
    spd: int


# Species


@dataclass
class Species:
    id: int
    names: typing.List[typing.Tuple[str, str]]
    slug: str
    base_stats: Stats
    height: int
    weight: int
    dex_number: int
    catchable: bool
    types: typing.List[str]
    abundance: int
    description: str = None
    mega_id: int = None
    mega_x_id: int = None
    mega_y_id: int = None
    evolution_from: EvolutionList = None
    evolution_to: EvolutionList = None
    mythical: bool = False
    legendary: bool = False
    ultra_beast: bool = False
    is_form: bool = False
    form_item: int = None
    moves: typing.List[PokemonMove] = None

    instance: typing.Any = UnregisteredDataManager()

    def __post_init__(self):
        self.name = next(filter(lambda x: x[0] == "🇬🇧", self.names))[1]
        if self.moves is None:
            self.moves = []

    def __str__(self):
        return self.name

    @cached_property
    def moveset(self):
        return [self.instance.moves[x] for x in self.moveset_ids]

    @cached_property
    def mega(self):
        if self.mega_id is None:
            return None

        return self.instance.pokemon[self.mega_id]

    @cached_property
    def mega_x(self):
        if self.mega_x_id is None:
            return None

        return self.instance.pokemon[self.mega_x_id]

    @cached_property
    def mega_y(self):
        if self.mega_y_id is None:
            return None

        return self.instance.pokemon[self.mega_y_id]

    @cached_property
    def image_url(self):
        return f"https://assets.poketwo.net/images/{self.id}.png?v=1600"

    @cached_property
    def shiny_image_url(self):
        return f"https://assets.poketwo.net/shiny/{self.id}.png?v=1600"

    @cached_property
    def correct_guesses(self):
        extra = []
        if self.is_form:
            extra.extend(self.instance.pokemon[self.dex_number].correct_guesses)
        if "nidoran" in self.slug:
            extra.append("nidoran")
        return extra + [deaccent(x.lower()) for _, x in self.names] + [self.slug]

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
            species = self.instance.pokemon[self.dex_number]
            item = self.instance.items[self.form_item]
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


@dataclass
class DataManager:
    pokemon: typing.Dict[int, Species] = None
    items: typing.Dict[int, Item] = None
    effects: typing.Dict[int, MoveEffect] = None
    moves: typing.Dict[int, Move] = None

    def all_pokemon(self):
        return self.pokemon.values()

    @cached_property
    def list_alolan(self):
        return [
            10091,
            10092,
            10093,
            10100,
            10101,
            10102,
            10103,
            10104,
            10105,
            10106,
            10107,
            10108,
            10109,
            10110,
            10111,
            10112,
            10113,
            10114,
            10115,
        ]

    @cached_property
    def list_mythical(self):
        return [v.id for v in self.pokemon.values() if v.mythical]

    @cached_property
    def list_legendary(self):
        return [v.id for v in self.pokemon.values() if v.legendary]

    @cached_property
    def list_ub(self):
        return [v.id for v in self.pokemon.values() if v.ultra_beast]

    @cached_property
    def list_mega(self):
        return (
            [v.mega_id for v in self.pokemon.values() if v.mega_id is not None]
            + [v.mega_x_id for v in self.pokemon.values() if v.mega_x_id is not None]
            + [v.mega_y_id for v in self.pokemon.values() if v.mega_y_id is not None]
        )

    def list_type(self, type: str):
        return [v.id for v in self.pokemon.values() if type.title() in v.types]

    def all_items(self):
        return self.items.values()

    def all_species_by_number(self, number: int) -> Species:
        return [x for x in self.pokemon.values() if x.dex_number == number]

    def all_species_by_name(self, name: str) -> Species:
        return [
            x
            for x in self.pokemon.values()
            if deaccent(name.lower().replace("′", "'")) in x.correct_guesses
        ]

    def find_all_matches(self, name: str) -> Species:
        return [
            y.id
            for x in self.all_species_by_name(name)
            for y in self.all_species_by_number(x.id)
        ]

    def species_by_number(self, number: int) -> Species:
        try:
            return self.pokemon[number]
        except KeyError:
            return None

    def species_by_name(self, name: str) -> Species:
        try:
            return next(
                filter(
                    lambda x: deaccent(name.lower().replace("′", "'"))
                    in x.correct_guesses,
                    self.pokemon.values(),
                )
            )
        except StopIteration:
            return None

    def item_by_number(self, number: int) -> Item:
        try:
            return self.items[number]
        except KeyError:
            return None

    def item_by_name(self, name: str) -> Item:
        try:
            return next(
                filter(
                    lambda x: deaccent(name.lower().replace("′", "'"))
                    == x.name.lower(),
                    self.items.values(),
                )
            )
        except StopIteration:
            return None

    def move_by_number(self, number: int) -> Move:
        try:
            return self.moves[number]
        except KeyError:
            return None

    def move_by_name(self, name: str) -> Move:
        try:
            return next(
                filter(
                    lambda x: deaccent(name.lower().replace("′", "'"))
                    == x.name.lower(),
                    self.moves.values(),
                )
            )
        except StopIteration:
            return None

    def random_spawn(self, rarity="normal"):

        if rarity == "mythical":
            pool = [x for x in self.all_pokemon() if x.catchable and x.mythical]
        elif rarity == "legendary":
            pool = [x for x in self.all_pokemon() if x.catchable and x.legendary]
        elif rarity == "ultra_beast":
            pool = [x for x in self.all_pokemon() if x.catchable and x.ultra_beast]
        else:
            pool = [x for x in self.all_pokemon() if x.catchable]

        x = random.choices(pool, weights=[x.abundance for x in pool], k=1)[0]

        return x

    @cached_property
    def spawn_weights(self):
        return [p.abundance for p in self.pokemon.values()]
