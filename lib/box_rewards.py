from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import random
from typing import TYPE_CHECKING, Dict, Iterable, List, Optional
from enum import Enum, Flag, auto

import discord

from data.models import Species
from helpers.utils import FlavorString

if TYPE_CHECKING:
    from bot import ClusterBot


class Rarity(Flag):
    MYTHICAL = auto()
    LEGENDARY = auto()
    UB = auto()

    ANY = MYTHICAL | LEGENDARY | UB


class RewardItem(Enum):
    POKECOINS = "pokecoins", FlavorString("Pokécoin", "<:pokecoins:1185296751012356126>", default_plural=True)
    SHARDS = "shards", FlavorString("Shard", "<:shards:1185296789918728263>", default_plural=True)
    REDEEM = "redeem", FlavorString("Redeem")

    # Pokemon
    POKEMON = "pokemon", FlavorString("Pokémon")
    RARE_POKEMON = "rare_pokemon", FlavorString("Rare Pokémon")
    EVENT_POKEMON = "event_pokemon", FlavorString("Event Pokémon")

    def __init__(self, value: str, flavor_string: Optional[FlavorString] = None) -> None:
        self.id = value
        self.flavor_string = flavor_string

    @property
    def qualified_name(self) -> str | None:
        if self.flavor_string:
            return self.flavor_string.string
        else:
            return None

    @property
    def emoji(self) -> str | None:
        if self.flavor_string:
            return self.flavor_string.emoji
        else:
            return None

    def __format__(self, format_spec: str) -> str:
        if self.flavor_string:
            return format(self.flavor_string, format_spec)
        else:
            return super().__format__(format_spec)

    def __str__(self) -> str:
        if self.flavor_string:
            return f"{self.flavor_string!s}"
        else:
            return super().__str__()

    def __repr__(self) -> str:
        if self.flavor_string:
            return f"{self.flavor_string!r}"
        else:
            return super().__repr__()


@dataclass
class Reward:
    """Function for giving box rewards.

    Parameters
    ----------
    item : RewardItem
        The reward item enum that represents the reward to be given and is parsed by the code
    chance : float
        The chance (0-1 or 0-100) of this reward to be chosen
    amounts : Iterable[int]
        The amounts of this reward to choose randomly from. For a non-random amount, a list containing that single amount
        should be passed in.

    ### Pokemon reward only parameters
    species_ids : Optional[List[int]] = None
        The list of species IDs to choose from when this reward item is chosen. Default is all catchable pokemon. Only for
        POKEMON reward item.
    shiny_boost : Optional[int | float] = 1
        The boost to multiply the shiny chance by. No boost by default.
    min_iv_percent : Optional[int] = 0
        The minimum total IV percent (0-100) of the pokemon. 0 by default.
    rarity : Optional[Rarity] = Rarity.ANY
        The rarity of the pokemon to choose from. Only for RARE_POKEMON reward item. Chooses pokemon that are either mythical,
        legendary or ub by default.
    """

    item: RewardItem
    chance: float
    amounts: Iterable[int]

    # Pokemon reward only parameters
    species_ids: Optional[List[int] | Dict[int, int | float]] = None
    shiny_boost: Optional[int | float] = 1
    min_iv_percent: Optional[int] = 0
    rarity: Optional[Rarity] = Rarity.ANY


# TODO: Separate this into two functions; one for generating the rewards and one for actually giving them to member
async def give_rewards(
    bot: ClusterBot, user: discord.Member | discord.User, k: Optional[int] = 1, *, rewards: List[Reward]
) -> str:
    """Function for giving box rewards.

    Parameters
    ----------
    bot : bot.ClusterBot
        The bot object
    user : discord.Member | discord.User
        The user to whom the rewards should be given
    k : Optional[int] = 1
        The number of times to get random rewards
    rewards: List[Reward]
        List of Reward objects to choose from

    Returns
    -------
    str
        The reward text
    """

    member = await bot.mongo.fetch_member_info(user)
    weights = [reward.chance for reward in rewards]

    if sum(weights) not in (1, 100):
        raise ValueError("Chances of rewards must add up to a total of 1 or 100 (100%)")

    update = {"$inc": {"balance": 0, "premium_balance": 0, "redeems": 0}}
    inserts = []
    text = []

    for reward in random.choices(rewards, weights=weights, k=k):
        count = random.choice(reward.amounts)

        item = reward.item
        match item:
            case RewardItem.POKECOINS:
                text.append(f"- {item.emoji} {count:,} {item:!e}")
                update["$inc"]["balance"] += count

            case RewardItem.SHARDS:
                text.append(f"- {item.emoji} {count:,} {item:!e}")
                update["$inc"]["premium_balance"] += count

            case RewardItem.REDEEM:
                text.append(f"- {count:,} {item:!e{'' if count == 1 else 's'}}")
                update["$inc"]["redeems"] += count

            case RewardItem.POKEMON | RewardItem.RARE_POKEMON | RewardItem.EVENT_POKEMON:
                pokemon_weights = None
                if item == RewardItem.RARE_POKEMON:
                    rarity = reward.rarity
                    if rarity == Rarity.ANY:
                        population = []
                        for r in (
                            Rarity.MYTHICAL,
                            Rarity.LEGENDARY,
                            Rarity.UB,
                        ):  # TODO: iterate through Rarity.ANY in python 3.11+
                            population.extend(
                                [
                                    bot.data.species_by_number(species_id)
                                    for species_id in getattr(bot.data, f"list_{r.name.lower()}")
                                ]
                            )
                    else:
                        population = [
                            bot.data.species_by_number(species_id)
                            for species_id in getattr(bot.data, f"list_{rarity.name.lower()}")
                        ]

                    population = [
                        s for s in population if s.catchable
                    ]  #! Important to filter out non-catchable pokemon
                    pokemon_weights = [s.abundance for s in population]

                elif reward.species_ids:
                    if isinstance(reward.species_ids, list):
                        population = [bot.data.species_by_number(species_id) for species_id in reward.species_ids]
                    elif isinstance(reward.species_ids, dict):
                        population = [bot.data.species_by_number(species_id) for species_id in reward.species_ids]
                        pokemon_weights = list(reward.species_ids.values())
                        if sum(pokemon_weights) not in (1, 100):
                            raise ValueError("Weights of species must add up to a total of 1 or 100 (100%)")
                    else:
                        raise ValueError(
                            "Invalid object passed into Reward.species_ids, must be list or ids or dict of id-weight pairs"
                        )

                else:
                    population = list(bot.data.all_pokemon())
                    population = [
                        s for s in population if s.catchable
                    ]  #! Important to filter out non-catchable pokemon
                    pokemon_weights = [s.abundance for s in population]

                shiny_boost = reward.shiny_boost or 1
                min_iv_percent = reward.min_iv_percent or 0

                species = random.choices(population, pokemon_weights, k=1)[0]
                pokemon = await bot.mongo.make_pokemon(
                    member,
                    species=species,
                    shiny_boost=shiny_boost,
                    min_iv_percent=min_iv_percent,
                )
                pokemon_obj = bot.mongo.Pokemon.build_from_mongo(pokemon)
                text.append(f"- **{pokemon_obj:liPg}**")
                inserts.append(pokemon)

    await bot.mongo.update_member(user, update)
    if len(inserts) > 0:
        await bot.mongo.db.pokemon.insert_many(inserts)

    return "\n".join(text)


@dataclass
class BaseSimulatedReward:
    """Dataclass for holding data of simulated rewards.

    Parameters
    ----------
    shiny_possible : Optional[bool] = False
        If it is possible for this simulated reward to have shiny variants
    reward : Optional[Reward] = None
        The Reward object to use as base for generating

    Methods
    -------
    text
        The formatted simulation values
    pokemon_text
        The formatted simulation values of all pokemon if applicable
    increment
        Increment count by given count and times by 1
    """

    shiny_possible: Optional[bool] = False
    reward: Optional[Reward] = None

    def __post_init__(self):
        self.times = 0
        self.count = 0

        self.pokemon = (
            {species_id: BaseSimulatedReward(shiny_possible=True) for species_id in self.reward.species_ids}
            if self.reward and self.reward.species_ids
            else None
        )
        self.shiny = BaseSimulatedReward() if self.shiny_possible else None

    def text(self, k: int) -> str:
        return f"**{self.times / k:.2%}** ({self.times:,} times, {self.count:,} total)"

    def pokemon_text(self, bot: ClusterBot, k: int, parent_k: int, shiny: Optional[bool] = False) -> str:
        if not self.pokemon:
            return

        lines = []
        for species_id, pkm_sr in self.pokemon.items():
            if shiny and not pkm_sr.shiny.times:
                continue

            species = bot.data.species_by_number(species_id)

            sr = pkm_sr.shiny if shiny else pkm_sr
            shiny_emoji = "✨ " if shiny else ""
            sprite = bot.sprites.get(species, shiny)

            lines.append(f"  - {shiny_emoji}{sprite} {species.name} - **{sr.times / parent_k:.2%}**/{sr.text(k)}")

        return "\n".join(lines)

    def increment(self, count: int):
        self.times += 1
        self.count += count


def simulate_rewards(
    bot: ClusterBot, k: Optional[int] = 1, *, rewards: List[Reward], shiny_charm: Optional[bool] = False
) -> str:
    """Function for simulating box rewards, useful for debugging. Does not actually give rewards to the user.

    Parameters
    ----------
    bot : bot.ClusterBot
        The bot object
    k : Optional[int] = 1
        The number of times to simulate
    rewards : List[Reward]
        List of Reward objects to choose from

    Returns
    -------
    str
        The simulated rewards text
    """

    weights = [reward.chance for reward in rewards]

    if sum(weights) not in (1, 100):
        raise ValueError("Chances of rewards must add up to a total of 1 or 100 (100%)")

    simulated_rewards = defaultdict(lambda: BaseSimulatedReward()) | {
        reward.item: BaseSimulatedReward(shiny_possible="pokemon" in reward.item.id, reward=reward)
        for reward in rewards
    }
    for reward in random.choices(rewards, weights=weights, k=k):
        count = random.choice(reward.amounts)
        item = reward.item

        match item:
            case RewardItem.POKEMON | RewardItem.RARE_POKEMON | RewardItem.EVENT_POKEMON:
                shiny_chance = 1 / 4096 * (reward.shiny_boost if reward.shiny_boost is not None else 1)
                if shiny_charm:
                    shiny_chance *= 1.2

                shiny = random.random() < shiny_chance
                if shiny:
                    simulated_rewards[item].shiny.increment(count)

                if reward.species_ids:
                    if isinstance(reward.species_ids, list):
                        population = reward.species_ids
                        pokemon_weights = None
                    elif isinstance(reward.species_ids, dict):
                        population = list(reward.species_ids)
                        pokemon_weights = list(reward.species_ids.values())
                        if sum(pokemon_weights) not in (1, 100):
                            raise ValueError("Weights of species must add up to a total of 1 or 100 (100%)")
                    else:
                        raise ValueError(
                            "Invalid object passed into Reward.species_ids, must be list or ids or dict of id-weight pairs"
                        )
                    species_id = random.choices(population, pokemon_weights, k=1)[0]
                    simulated_rewards[item].pokemon[species_id].increment(count)
                    if shiny:
                        simulated_rewards[item].pokemon[species_id].shiny.increment(count)

        simulated_rewards[item].increment(count)

    lines = []
    for item, sr in simulated_rewards.items():
        lines.append(f"- **{item}** - {sr.text(k)}")

        if sr.pokemon:
            lines.append(sr.pokemon_text(bot, k, sr.times))

        if sr.shiny_possible:
            lines.append(f"- **✨ {item}** - {sr.shiny.text(k)}")
            if sr.pokemon and sr.shiny.times:
                lines.append(sr.pokemon_text(bot, k, sr.times, True))

    return "\n".join(lines)
