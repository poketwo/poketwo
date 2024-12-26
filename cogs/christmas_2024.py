from __future__ import annotations

import contextlib
from dataclasses import dataclass
from enum import Enum
import itertools
import random
import re
import string
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple
from collections import defaultdict
from textwrap import dedent
import random
from urllib.parse import urlencode, urljoin

import discord
from discord.ext import commands

from .sprites import other
from data.models import Species
from helpers import checks, constants
from helpers.context import PoketwoContext
from helpers.utils import FlavorString, make_slider, unwind, write_fp
from lib.box_rewards import Reward, RewardItem, give_rewards, simulate_rewards

if TYPE_CHECKING:
    from bot import ClusterBot

# region CONSTANTS
EVENT_PREFIX = "christmas_2024"

EMBED_COLOR = 0x7385F7


class FlavorStrings:
    """Holds various flavor strings."""

    pokecoins = FlavorString("Pokécoin", None, default_plural=True)
    box = FlavorString("Present", "<:present_blue:1186054091617619968>", "Presents")
    blueprint = FlavorString("Blueprint", "<:blueprint:1320156844014047323>", "Blueprints")
    santa = FlavorString("Santa Snorlax")


class EventSpecies(Enum):
    """Enum for all event pokemon for this event"""

    AUDINO = 50206  # TODO, make catchable on 28th
    WIGLETT = 50208

    SNORLAX = 50202, "special"
    # GRIMMSNARL = 50207, "special"  # TODO, make boxable on 3rd
    GLACEON = 50205, "box"
    BELLOSSOM = 50203, "box"
    LOPUNNY = 50204, "box"
    GIMMIGHOUL = 50209, "box"

    def __init__(self, id: int, tag: Optional[str] = None) -> None:
        self.id = id
        self.tag = tag

    def get_species(self, bot: ClusterBot) -> Species:
        return bot.data.species_by_number(self.id)

    def text(self, bot: ClusterBot, *, amount: Optional[int] = None) -> str:
        species = self.get_species(bot)
        return f"""{bot.sprites.get(species)} {f"{amount}x " if amount is not None else ""}{species.name}"""

    @classmethod
    def ids(cls, *, tag: Optional[str] = None) -> List[int]:
        return [species.id for species in cls if (tag and species.tag == tag)]


EVENT_SHINY_BOOST = 5

# TODO
BOX_REWARDS = [
    Reward(item=RewardItem.POKECOINS, chance=26, amounts=range(1500, 2501)),
    Reward(item=RewardItem.SHARDS, chance=18, amounts=range(8, 16)),
    Reward(
        item=RewardItem.EVENT_POKEMON,
        chance=28,
        amounts=[1],
        species_ids=EventSpecies.ids(tag="box"),
        shiny_boost=EVENT_SHINY_BOOST,
    ),
    Reward(
        item=RewardItem.EVENT_POKEMON,
        chance=8,
        amounts=[1],
        species_ids=EventSpecies.ids(tag="special"),
        shiny_boost=EVENT_SHINY_BOOST,
    ),
    Reward(item=RewardItem.RARE_POKEMON, chance=10, amounts=[1]),
    Reward(item=RewardItem.POKEMON, chance=8, amounts=[1], shiny_boost=300, min_iv_percent=75),
    Reward(item=RewardItem.POKEMON, chance=0.05, amounts=[1], shiny_boost=4096),
    Reward(item=RewardItem.REDEEM, chance=1.95, amounts=[1]),
]
# QUESTS

MAX_QUESTS = 25
GOOD_QUEST_BOXES = 1
BAD_QUEST_PC = 1000

REGION_RANGES = unwind(
    {
        ("paldea",): range(20, 30),
        ("kanto", "johto", "hoenn", "unova"): range(14, 18),
        ("sinnoh", "alola", "kalos", "galar"): range(12, 16),
    }
)
REGIONS = tuple(REGION_RANGES)

TYPE_RANGES = unwind(
    {
        ("Normal", "Water", "Grass", "Flying", "Bug"): range(16, 20),
        ("Poison", "Ground", "Psychic", "Rock", "Electric", "Ghost"): range(14, 18),
        ("Dragon", "Fire", "Fairy", "Dark", "Fighting", "Steel", "Ice"): range(12, 16),
    }
)
TYPES = tuple(TYPE_RANGES)

GENDER_RANGES = unwind(
    {("male", "female"): range(24, 36), ("unknown",): range(6, 12)},
)
GENDERS = tuple(GENDER_RANGES)


def make_catch_type_quest(type):
    return lambda: {
        "event": "catch",
        "count": (count := random.choice(TYPE_RANGES[type])),
        "condition": {"type": type},
        "description": f"Catch {count} <:{type.title()}:{other[f'type_{type.lower()}']}> {type}-type pokémon",
    }


def make_catch_region_quest(region):
    return lambda: {
        "event": "catch",
        "count": (count := random.choice(REGION_RANGES[region])),
        "condition": {"region": region},
        "description": f"Catch {count} pokémon from the {region.title()} region",
    }


def make_catch_gender_quest(gender):
    return lambda: {
        "event": "catch",
        "count": (count := random.choice(GENDER_RANGES[gender])),
        "condition": {"gender": gender},
        "description": f"Catch {count} {constants.GENDER_EMOTES[gender.lower()]} {gender.title()} gender pokémon",
        "good_guaranteed": True,
    }


GUARANTEED_QUESTS = [
    lambda: {
        "event": "catch",
        "count": (count := random.randint(40, 60)),
        "description": f"Catch {count} pokémon",
        "good_guaranteed": True,
    },
    lambda: {
        "event": "trade",
        "count": (count := random.randint(1, 3)),
        "description": f"Trade with {count} {'person' if count == 1 else 'people'}",
    },
    lambda: {
        "event": "evolve",
        "count": (count := random.randint(4, 8)),
        "description": f"Evolve {count} pokémon",
    },
    lambda: {
        "event": "release",
        "count": (count := random.randint(5, 10)),
        "description": f"Release {count} pokémon",
    },
    lambda: {
        "event": "market_buy",
        "count": (count := random.randint(200, 600)),
        "description": f"Spend {count} Pokécoins on the market",
    },
    lambda: {
        "event": "market_sell",
        "count": (count := random.randint(200, 400)),
        "description": f"Earn {count} Pokécoins from the market",
    },
]

POSSIBLE_QUESTS = [
    *[make_catch_type_quest(type) for type in TYPES],
    *[make_catch_region_quest(region) for region in REGIONS],
    *[make_catch_gender_quest(gender) for gender in GENDERS],
]

# region Boards
EMPTY_BOARD = [[0, 0, 0, 0, 0], [0, 0, 0, 0, 0], [0, 0, 0, 0, 0], [0, 0, 0, 0, 0], [0, 0, 0, 0, 0]]

BLUEPRINTS = {
    0: [[0, 0, 1, 0, 0], [0, 1, 1, 1, 0], [0, 1, 1, 1, 0], [1, 1, 1, 1, 1], [1, 1, 1, 1, 1]],
    1: [[0, 0, 1, 0, 0], [0, 1, 1, 1, 0], [0, 1, 1, 1, 0], [1, 1, 1, 1, 1], [0, 1, 1, 1, 0]],
    2: [[0, 1, 1, 1, 0], [1, 1, 1, 1, 1], [1, 1, 1, 1, 1], [0, 1, 1, 1, 0], [1, 1, 1, 1, 1]],
    3: [[0, 0, 1, 1, 0], [0, 0, 1, 1, 1], [0, 1, 1, 1, 1], [1, 1, 1, 0, 0], [1, 1, 0, 0, 0]],
    4: [[0, 1, 1, 1, 0], [0, 1, 1, 1, 0], [0, 1, 1, 1, 0], [0, 1, 1, 1, 0], [0, 1, 0, 1, 0]],
    5: [[0, 1, 1, 1, 0], [1, 1, 1, 1, 1], [1, 1, 1, 1, 1], [0, 1, 1, 1, 0], [1, 1, 1, 1, 1]],
    6: [[0, 1, 1, 1, 0], [0, 1, 1, 1, 0], [1, 1, 1, 1, 1], [1, 1, 1, 1, 1], [1, 1, 1, 1, 1]],
    7: [[0, 0, 0, 0, 0], [0, 1, 1, 1, 1], [0, 1, 1, 1, 1], [1, 1, 1, 1, 1], [1, 1, 1, 1, 1]],
}

BLUEPRINT_POKEMON = {
    3: EventSpecies.WIGLETT,
    4: EventSpecies.LOPUNNY,
    5: EventSpecies.GLACEON,
    6: EventSpecies.GIMMIGHOUL,
    7: EventSpecies.BELLOSSOM,
}

CELLS_PER_ROW = 5

# COMMUNITY GOALS
GIFT_COUNT_ID = f"{EVENT_PREFIX}_gifts_crafted"


def cell_to_coords(cell: str) -> Tuple[int, int]:
    return (int(cell[1:]) - 1, string.ascii_lowercase.index(cell[0].lower()))


def coords_to_cell(x: int, y: int) -> str:
    return f"{string.ascii_uppercase[y]}{x}"


class EventView(discord.ui.View):
    def __init__(self, ctx: PoketwoContext):
        self.ctx = ctx
        self.cog: Christmas = self.ctx.bot.get_cog("Christmas")
        super().__init__(timeout=120)

    @discord.ui.button(label="Inventory", style=discord.ButtonStyle.grey)
    async def inventory(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await self.ctx.invoke(self.cog.inventory)

    async def interaction_check(self, interaction):
        if interaction.user.id not in {
            self.ctx.bot.owner_id,
            self.ctx.author.id,
            *self.ctx.bot.owner_ids,
        }:
            await interaction.response.send_message("You can't use this!", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        if self.message:
            for child in self.children:
                child.disabled = True
            await self.message.edit(view=self)


# region MAIN COG
class Christmas(commands.Cog):
    """Christmas event commands."""

    def __init__(self, bot):
        self.bot: ClusterBot = bot

    async def cog_load(self):
        self.bot.Embed.CUSTOM_COLOR = EMBED_COLOR  # Set custom embed color for this event

    async def cog_unload(self):
        self.bot.Embed.CUSTOM_COLOR = None  # Unset custom embed color

    # region Functions
    # region board
    async def choose_blueprint(self, user):
        blueprint_id = random.choice(list(BLUEPRINTS.keys()))
        quests = await self.generate_quests(BLUEPRINTS[blueprint_id])
        updates = {
            f"{EVENT_PREFIX}_blueprint": blueprint_id,
            f"{EVENT_PREFIX}_board": EMPTY_BOARD,
            f"{EVENT_PREFIX}_quests": quests,
        }
        await self.bot.mongo.update_member(user, {"$set": updates})

    async def check_completion(self, user: discord.User, *, ctx: Optional[commands.Context] = None):
        member = await self.bot.mongo.fetch_member_info(user)
        board = member[f"{EVENT_PREFIX}_board"]
        blueprint_id = member[f"{EVENT_PREFIX}_blueprint"]
        blueprint = BLUEPRINTS[blueprint_id]

        if self.check_done(board, blueprint):
            await self.bot.mongo.update_member(
                user, {"$inc": {f"{EVENT_PREFIX}_blueprints_completed": 1}, "$set": {f"{EVENT_PREFIX}_streak": 0}}
            )
            await self.bot.mongo.db.counter.update_one(
                {"_id": GIFT_COUNT_ID},
                {"$inc": {"next": 1}},
                upsert=True,
            )

            species = BLUEPRINT_POKEMON.get(blueprint_id, random.choice(list(BLUEPRINT_POKEMON.values()))).get_species(
                self.bot
            )
            pokemon_data = await self.bot.mongo.make_pokemon(user, species, shiny_boost=EVENT_SHINY_BOOST)
            pokemon = self.bot.mongo.Pokemon.build_from_mongo(pokemon_data)
            await self.bot.mongo.db.pokemon.insert_one(pokemon_data)

            await (ctx or user).send(
                f"You completed crafting a christmas gift! You've earned **{GOOD_QUEST_BOXES} {FlavorStrings.box}** and a **{pokemon:i}**."
            )
            await self.choose_blueprint(user)

    def check_done(self, board, blueprint):
        return all(
            all(board[i][j] == 1 or blueprint[i][j] == 0 for j in range(len(blueprint[0])))
            for i in range(len(blueprint))
        )

    # region quests
    async def generate_quests(self, blueprint: List[List[int]]):
        cell_map = list(itertools.chain.from_iterable(blueprint))
        good_cell_indices = [i for i, v in enumerate(cell_map) if v]

        quests = [
            *[x() for x in GUARANTEED_QUESTS],
            *[x() for x in random.sample(POSSIBLE_QUESTS, k=MAX_QUESTS - len(GUARANTEED_QUESTS))],
        ]
        random.shuffle(quests)

        quest_indices = {i: None for i in range(len(quests))}

        # Put the good cell guaranteed quests in first
        for good_quest in filter(lambda q: q.get("good_guaranteed"), quests):
            empty_indices = [i for i, v in quest_indices.items() if v is None]

            idx = [i for i in empty_indices if i in good_cell_indices][0]
            quest_indices[idx] = good_quest
            quests.remove(good_quest)

        # Put the rest of the quests in
        for quest in quests:
            empty_indices = [i for i, v in quest_indices.items() if v is None]

            idx = empty_indices[0]
            quest_indices[idx] = quest

        return [{**x, "progress": 0, "complete": False} for x in quest_indices.values()]

    async def on_quest_event(
        self,
        user: discord.User,
        event: str,
        to_verify: Optional[list] = None,
        *,
        count: Optional[int] = 1,
        ctx: Optional[PoketwoContext] = None,
    ):
        member = await self.bot.mongo.fetch_member_info(user)
        if (
            not member[f"{EVENT_PREFIX}_quests"]
            or not member[f"{EVENT_PREFIX}_blueprint"]
            or not member[f"{EVENT_PREFIX}_board"]
        ):
            await self.choose_blueprint(user)
            member = await self.bot.mongo.fetch_member_info(user)

        incs = defaultdict(lambda: 0)

        quests = member[f"{EVENT_PREFIX}_quests"]
        for j, q in enumerate(quests):
            if q["event"] != event or q.get("complete"):
                continue

            if to_verify and not all((self.verify_condition(q.get("condition"), p) for p in to_verify)):
                continue

            inc = min((q["progress"] + count, q["count"])) - q["progress"]  # So that progress doesn't go over the goal
            incs[f"{EVENT_PREFIX}_quests.{j}.progress"] += inc

        if incs:
            await self.bot.mongo.update_member(user, {"$inc": incs})

        await self.check_quests(user, ctx=ctx)

    def is_good_quest(self, blueprint: List[List[int]], idx: int):
        x, y = divmod(idx, CELLS_PER_ROW)
        return bool(blueprint[x][y])

    async def send_chunked_lines(self, user: discord.Member, lines: List[str]):
        max_lines = 10
        for chunk in discord.utils.as_chunks(lines, max_lines):
            with contextlib.suppress(discord.HTTPException):
                await user.send("\n".join(chunk))

    def get_streak_rewards(self, streak: int):
        boxes = streak // 2
        pc = 2 * streak * 1000

        return boxes, pc

    async def check_quests(self, user, ctx=None):
        member = await self.bot.mongo.fetch_member_info(user)

        messages = []
        quests = member[f"{EVENT_PREFIX}_quests"]
        blueprint = BLUEPRINTS[member[f"{EVENT_PREFIX}_blueprint"]]

        incs = defaultdict(lambda: 0)
        for j, q in enumerate(
            quests
        ):  #! doing it in position order instead of completion order might cause issues with streaks
            if q["progress"] >= q["count"] and not q.get("complete"):
                member = await self.bot.mongo.db.member.find_one_and_update(
                    {
                        "_id": user.id,
                        f"{EVENT_PREFIX}_quests.{j}.progress": {"$gte": q["count"]},
                        f"{EVENT_PREFIX}_quests.{j}.complete": {"$ne": True},
                    },
                    {
                        "$set": {
                            f"{EVENT_PREFIX}_quests.{j}.complete": True,
                            f"{EVENT_PREFIX}_board.{j // CELLS_PER_ROW}.{j % CELLS_PER_ROW}": 1,
                        },
                    },
                )
                if member is not None:
                    member = self.bot.mongo.Member.build_from_mongo(member)
                    await self.bot.redis.hdel("db:member", user.id)

                    is_good_quest = self.is_good_quest(blueprint, j)
                    current_streak = member[f"{EVENT_PREFIX}_streak"] + incs[f"{EVENT_PREFIX}_streak"]

                    first_part = f"""You have completed the christmas task "{q['description']}"."""
                    if is_good_quest:
                        incs[f"{EVENT_PREFIX}_boxes"] += GOOD_QUEST_BOXES
                        incs[f"{EVENT_PREFIX}_streak"] += 1
                        current_streak = member[f"{EVENT_PREFIX}_streak"] + incs[f"{EVENT_PREFIX}_streak"]

                        first_part = f"Congratulations{f' {user.mention}' if ctx else ''}! {first_part}"
                        first_part += f"""!\n\nYou crafted a new part of the toy! You earned **{GOOD_QUEST_BOXES} {FlavorStrings.box}**. ***+1 Streak ({current_streak})***!"""

                        if current_streak % 2 == 0:
                            streak_boxes, streak_pc = self.get_streak_rewards(
                                member[f"{EVENT_PREFIX}_streak"] + incs[f"{EVENT_PREFIX}_streak"]
                            )
                            incs[f"{EVENT_PREFIX}_boxes"] += streak_boxes
                            incs[f"balance"] += streak_pc

                            first_part += dedent(
                                f"""
                                Streak rewards:
                                - **{streak_boxes:,} {FlavorStrings.box:{'' if streak_boxes == 1 else 's'}}**
                                - **{streak_pc:,} {FlavorStrings.pokecoins}**
                                """
                            ).rstrip("\n")

                    else:

                        first_part += f""".\n\nUnfortunately, it did not help craft a new part of the toy. You earned **{BAD_QUEST_PC:,} {FlavorStrings.pokecoins}**."""
                        incs[f"balance"] += BAD_QUEST_PC
                        if current_streak:
                            first_part += f" *Streak reset ({current_streak})*"

                        incs[f"{EVENT_PREFIX}_streak"] -= current_streak

                    messages.append(
                        f"{first_part}\n-# Use `@Pokétwo#8236 {self.christmas.qualified_name}` to see your blueprint and all your tasks."
                    )

        if incs:
            await self.bot.mongo.update_member(user, {"$inc": incs})

        if messages:
            if ctx:
                for message in messages:
                    await ctx.send(
                        message,
                        allowed_mentions=discord.AllowedMentions(users=True)
                        if member["catch_mention"]
                        else discord.AllowedMentions.none(),
                    )
            else:
                await self.send_chunked_lines(user, messages)

        await self.check_completion(user, ctx=ctx)

    def verify_condition(self, condition, pokemon, to=None):
        if condition is not None:
            species = pokemon.species
            for k, v in condition.items():
                if k == "id" and species.id != v:
                    return False
                elif k == "type" and v not in species.types:
                    return False
                elif k == "region" and v != species.region:
                    return False
                elif k == "to" and to.id != v:
                    return False
                elif k == "gender" and v != pokemon.gender.lower():
                    return False
        return True

    def get_image_url(self, blueprint_id: int, board: List[List[int]]):
        cells = [coords_to_cell(i, j) for i, row in enumerate(board) for j, col in enumerate(row) if col]
        return (
            urljoin(self.bot.config.EXT_SERVER_URL, f"christmas_2024/blueprint/{blueprint_id}")
            + "?"
            + urlencode({"cells": ",".join(cells)})
        )

    async def fetch_image(self, blueprint_id: int, board: List[List[int]]):
        async with self.bot.http_session.get(self.get_image_url(blueprint_id, board)) as resp:
            if resp.status == 200:
                arr = await self.bot.loop.run_in_executor(None, write_fp, await resp.read())
                return discord.File(arr, filename="blueprint.png")

    async def fetch_gift_count(self) -> int:
        counter = await self.bot.mongo.Counter.find_one({"_id": GIFT_COUNT_ID})
        return counter.next if counter else 0

    @checks.has_started()
    @commands.group(aliases=("event", "ev"), invoke_without_command=True, case_insensitive=True)
    async def christmas(self, ctx: PoketwoContext):
        """View christmas event main menu."""

        # Check if user doesnt have a starting blueprint
        member = await self.bot.mongo.fetch_member_info(ctx.author)
        if not member[f"{EVENT_PREFIX}_board"] or member[f"{EVENT_PREFIX}_blueprint"] is None:
            await self.choose_blueprint(ctx.author)

        # The embed

        member = await self.bot.mongo.fetch_member_info(ctx.author)
        quests = member[f"{EVENT_PREFIX}_quests"]
        streak = member[f"{EVENT_PREFIX}_streak"]

        board = member[f"{EVENT_PREFIX}_board"]
        blueprint_id = member[f"{EVENT_PREFIX}_blueprint"]
        blueprint = BLUEPRINTS[blueprint_id]

        quests_text = "\n".join(
            f"""**{coords_to_cell(i // CELLS_PER_ROW + 1, i % CELLS_PER_ROW)}.** {q['description']} `{q['progress']}/{q['count']}`"""
            for i, q in enumerate(quests)
            if not q.get("complete")
        )
        event_information = dedent(
            f"""
            It's Christmas, and it's time for {FlavorStrings.santa} to set out with presents. But alas, he finds his workshop completely empty! All the elves are nowhere to be found, and {FlavorStrings.santa} is in a pickle.

            Help {FlavorStrings.santa} make toys and gifts by completing various tasks, and earn {FlavorStrings.pokecoins}, shards, redeems, special event Pokémon and more along the way!
            """
        )
        embed = self.bot.Embed(
            title=f"Christmas 2024 — Workshop Mystery",
            description=f"{event_information}\n{quests_text}",
            color=EMBED_COLOR,
        )

        image = await self.fetch_image(blueprint_id, board)
        if image:
            embed.set_image(url="attachment://blueprint.png")

        gifts_crafted = await self.fetch_gift_count()
        embed.add_field(
            name="📜 Story",
            # TODO: Update as event progresses
            value=dedent(
                f"""
                {FlavorStrings.santa} and the community are hard at work to craft as many gifts as possible within the short time they have...
                **Total gifts crafted globally**: `{gifts_crafted:,}`

                As the community crafts gifts and the event progresses, new parts of the story will unlock at random. **Two more event Pokémon are yet to be unlocked.**
                """
            ),
            inline=False,
        )

        parts_left = sum((value for row in blueprint for value in row if value)) - sum(
            (value for i, row in enumerate(board) for j, value in enumerate(row) if value and blueprint[i][j])
        )
        embed.add_field(
            name=f"{FlavorStrings.blueprint.emoji} Your {FlavorStrings.blueprint.string} #{member[f'{EVENT_PREFIX}_blueprints_completed'] + 1}",
            value=dedent(
                f"""
                Complete tasks to craft toys part-by-part. Craft correct parts in a row to build up streaks and earn increasingly better streak rewards! Beware though, one wrong move and it goes down to zero!

                Parts Left: {parts_left}
                **Current Streak: {streak:,}**
                """
            ),
            inline=False,
        )

        view = EventView(ctx)
        view.message = await ctx.send(embed=embed, file=image, view=view)

    @checks.has_started()
    @christmas.group(name="inventory", aliases=("inv",), invoke_without_command=True)
    async def inventory(
        self,
        ctx: PoketwoContext,
    ):
        """See how many presents you have"""

        member = await self.bot.mongo.fetch_member_info(ctx.author)
        boxes = member[f"{EVENT_PREFIX}_boxes"]

        embed = self.bot.Embed(title=f"Christmas Inventory", description="", color=EMBED_COLOR)
        embed.add_field(
            name=f"{FlavorStrings.box:s} — {boxes:,}",
            value=f"Help {FlavorStrings.santa} craft toys and gifts by completing {FlavorStrings.blueprint:sb} through tasks, and earn {FlavorStrings.box:s!e} that contain various rewards and gifts for you!\n-# Use `{ctx.clean_prefix}{self.open.qualified_name} {self.open.signature}` to open them!",
            inline=False,
        )
        await ctx.send(embed=embed)

    # region on_catch
    @commands.Cog.listener(name="on_catch")
    async def on_catch(self, ctx: PoketwoContext, species: Species, idx: int):
        pokemon = await self.bot.mongo.fetch_pokemon(ctx.author, idx)
        await self.on_quest_event(ctx.author, "catch", [pokemon], ctx=ctx)

    # region on_evolve
    @commands.Cog.listener()
    async def on_mass_evolve(self, user, evolved):
        await self.on_quest_event(user, "evolve", count=len(evolved))

    # region on_release
    @commands.Cog.listener()
    async def on_release(self, user, count):
        await self.on_quest_event(user, "release", count=count)

    # region on_trade
    @commands.Cog.listener()
    async def on_trade(self, trade):
        a, b = trade["users"]

        for user in (a, b):
            await self.on_quest_event(user, "trade")

    # region on_market_buy
    @commands.Cog.listener()
    async def on_market_buy(self, buyer, pokemon):
        price = pokemon["market_data"]["price"]

        # For buyer
        await self.on_quest_event(buyer, "market_buy", count=price)

        # For seller
        seller = await self.bot.fetch_user(pokemon["owner_id"])
        await self.on_quest_event(seller, "market_sell", count=price)

    @checks.has_started()
    @christmas.command(name="open", aliases=("o",))
    async def open(
        self,
        ctx: PoketwoContext,
        qty: Optional[int] = 1,
    ):
        """Open boxes for rewards"""

        if qty <= 0:
            return await ctx.send(f"Nice try...")

        if qty > 15:
            return await ctx.send(f"You can only open up to 15 {FlavorStrings.box:s} at once!")

        member = await self.bot.mongo.fetch_member_info(ctx.author)
        boxes = member[f"{EVENT_PREFIX}_boxes"]

        if qty > boxes:
            return await ctx.send(f"You don't have enough {FlavorStrings.box:s}!")

        await self.bot.mongo.update_member(ctx.author, {"$inc": {f"{EVENT_PREFIX}_boxes": -qty}})

        embed = self.bot.Embed(
            title=f"You open {qty} {FlavorStrings.box:{'' if qty == 1 else 's'}}...",
            description=None,
        )
        embed.set_author(name=str(ctx.author), icon_url=ctx.author.display_avatar.url)

        rewards_text = await give_rewards(self.bot, ctx.author, qty, rewards=BOX_REWARDS)
        embed.description = rewards_text

        await ctx.reply(embed=embed, mention_author=False)

    # region Debug
    @checks.is_developer()
    @christmas.group(name="debug", aliases=("dev",), invoke_without_command=True)
    async def debug(
        self,
        ctx: PoketwoContext,
    ):
        """Dev-only command for debugging purposes"""

        return await ctx.send_help(self.debug)

    @checks.is_developer()
    @debug.command(name="reload")
    async def reload(self, ctx: PoketwoContext, *, additional_command: str = None):
        ctx.message.content = f"{self.bot.user.mention} jsk reload {__name__}"
        await self.bot.process_commands(ctx.message)

        if additional_command:
            ctx.message.content = f"{self.bot.user.mention} jsk exec {additional_command}"
            await self.bot.process_commands(ctx.message)

    @checks.is_developer()
    @debug.command(name="reset")
    async def set_blueprint(self, ctx: PoketwoContext):
        await self.choose_blueprint(ctx.author)
        await ctx.send("Reset blueprint.")

    @checks.is_developer()
    @debug.command(name="fill", aliases=("complete",))
    async def admin_fill_spot(
        self, ctx: commands.Context, user: Optional[discord.User] = commands.Author, *, cells: Optional[str] = None
    ):
        member = await self.bot.mongo.fetch_member_info(user)
        sets = {}

        for cell in re.split("\s+", cells):
            if not cell:
                await ctx.send(f"Invalid cell `{cell}` provided")
                continue

            row, column = cell_to_coords(cell)

            if row < 0 or row > 4 or column < 0 or column > 4:
                return await ctx.send(f"Invalid cell `{cell}` provided")

            i = row * CELLS_PER_ROW + column

            quests = member[f"{EVENT_PREFIX}_quests"]
            sets[f"{EVENT_PREFIX}_quests.{i}.progress"] = quests[i]["count"]

        await self.bot.mongo.update_member(
            user,
            {"$set": sets},
        )
        await self.check_quests(user, ctx=ctx)

    @checks.is_developer()
    @debug.command(name="simulate-boxes")
    async def simulate_boxes(
        self,
        ctx: PoketwoContext,
        qty: Optional[int] = 1,
    ):
        """Dev-only command to simulate box openings"""

        embeds = []
        embed = self.bot.Embed(
            title=f"Simulating {qty:,} {FlavorStrings.box:{'' if qty == 1 else 'es'}}...",
            description=None,
        )
        embed.set_author(name=str(ctx.author), icon_url=ctx.author.display_avatar.url)

        rewards_text = simulate_rewards(self.bot, qty, rewards=BOX_REWARDS)
        embed.description = rewards_text
        embeds.append(embed)

        await ctx.reply(embeds=embeds, mention_author=False)

    @checks.is_developer()
    @debug.group(name="give", invoke_without_command=True)
    async def give(
        self,
        ctx: PoketwoContext,
    ):
        """Dev-only command to give stuff for debugging purposes"""

        return await ctx.send_help(self.give)

    @checks.is_developer()
    @give.command(name="boxes", aliases=("box",))
    async def give_boxes(
        self,
        ctx: PoketwoContext,
        user: Optional[discord.Member] = commands.Author,
        qty: Optional[int] = 1,
    ):
        """Dev-only command to give boxes for debugging purposes"""

        await self.bot.mongo.update_member(user, {"$inc": {f"{EVENT_PREFIX}_boxes": qty}})
        await ctx.send(f"Gave {qty}x {FlavorStrings.box} to **{user}**.")


async def setup(bot: commands.Bot):
    await bot.add_cog(Christmas(bot))
