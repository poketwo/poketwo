from __future__ import annotations

import abc
import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import random
import string
from textwrap import dedent
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Tuple

import discord
from discord.ext import commands
from discord.utils import get
import humanfriendly

from .sprites import other
from data.models import Species
from data.utils import comma_formatted
from helpers import checks
from helpers.context import ConfirmationYesNoView, PoketwoContext
from helpers.utils import FlavorString, unwind
from discord.ext.commands import check

from lib.box_rewards import Reward, RewardItem, give_rewards, simulate_rewards

if TYPE_CHECKING:
    from bot import ClusterBot


# TODO: Event End TODOs
# TODO: - Show results on main menu
# TODO:   - Custom result banner
# TODO: - Command to claim rewards (Top 3 teams: moltres and boxes. Everyone: team badge)
# TODO:   - Enable moltres


# region CONSTANTS
SUMMER_PREFIX = "summer_2024"
STANDING_ID = f"{SUMMER_PREFIX}_points_{{minisport}}_{{team}}"

EMBED_COLOR = 0x0085C7
REQUIRED_CATCHES = 10
EVENT_SHINY_BOOST = 5

POINTS_PC_RANGE = range(300, 501)


class FlavorStrings:
    """Holds various flavor strings."""

    olympics = FlavorString("The Summer Olympics")
    ticket = FlavorString("Olympic Ticket", "🎟️")
    minisport = FlavorString("Minisport")

    pokecoins = FlavorString("Pokécoins", "<:pokecoins:1185296751012356126>")
    box = FlavorString("Box", plural="Boxes")


# region BASE CLASSES
@dataclass
class BaseTeam:
    name: str
    emoji: str


@dataclass
class BaseBox:
    name: str
    emoji: str
    rewards: List[Reward]


# region MINISPORT BASE CLASSES
@dataclass
class Progress:
    """Progress of a minisport game"""

    count: int
    goal: int
    points: int

    @property
    def remaining(self) -> int:
        return self.goal - self.count

    @property
    def percent(self) -> float:
        return self.count / self.goal

    @property
    def completed(self) -> bool:
        return self.remaining <= 0

    def __format__(self, format_spec: str) -> str:
        return f"{self.percent:.2%}"

    def __str__(self) -> str:
        return format(self)


@dataclass
class BaseMinisport(abc.ABC):
    name: str = field(init=False)
    emoji: str = field(init=False)
    description: str = field(init=False)
    help_msg: str = field(init=False)
    input_required: str = field(init=False, default=False)

    started_at: datetime
    data: dict

    @property
    def enum(self) -> Minisport:
        return Minisport.from_name(self.name)

    @property
    def id(self) -> Minisport:
        return self.enum.name

    def __format__(self, format_spec: str) -> str:
        val = self.enum.__format__(format_spec)

        if "p" in format_spec:
            val += f" ({self.progress})"

        return val

    def __str__(self) -> str:
        return f"{self}"

    def to_dict(self) -> dict:
        return dict(
            id=self.id,
            started_at=self.started_at,
            data=self.data,
        )

    @classmethod
    def from_dict(cls, data: dict) -> BaseMinisport | None:
        if not data:
            return None

        _id = data.pop("id")
        minisport_cls = Minisport[_id].value
        return minisport_cls(**data)

    @classmethod
    def new(cls):
        return cls(
            started_at=datetime.utcnow(),
            data=cls.new_data(),
        )

    async def start_hook(self, ctx: PoketwoContext):
        pass

    async def start(self, ctx: PoketwoContext):
        await self.start_hook(ctx)
        await ctx.bot.mongo.update_member(
            ctx.author,
            {
                "$set": {f"{SUMMER_PREFIX}_current_minisport": self.to_dict()},
                "$inc": {f"{SUMMER_PREFIX}_minisports_played": 1, f"{SUMMER_PREFIX}_tickets": -1},
            },
        )

    def determine_pc(self) -> int:
        points = self.progress.points

        pc = 0
        for _ in range(points):
            pc += random.choice(POINTS_PC_RANGE)

        return pc

    def determine_boxes(self) -> Dict[Box, int]:
        points = self.progress.points

        if points <= 0:
            return {}

        if 1 <= points <= 2:
            return {Box.BRONZE: 1}

        if 3 <= points <= 4:
            return {Box.SILVER: 1}

        if 5 <= points:
            return {Box.GOLD: 1}

    async def update(self, bot: ClusterBot, ctx_or_user: PoketwoContext | discord.User):
        if isinstance(ctx_or_user, PoketwoContext):
            user = ctx_or_user.author
            send_method = ctx_or_user.reply
        else:
            user = ctx_or_user
            send_method = user.send

        if not self.progress.completed:
            return await bot.mongo.update_member(
                user,
                {"$set": {f"{SUMMER_PREFIX}_current_minisport": self.to_dict()}},
            )

        user = user
        member = await bot.mongo.fetch_member_info(user)
        team = Team[member[f"{SUMMER_PREFIX}_team"]]

        inc = {}
        rewards = []

        points = self.progress.points
        if points:
            inc[f"{SUMMER_PREFIX}_points.{self.id}"] = points

        boxes = self.determine_boxes()
        for box, qty in boxes.items():
            inc[f"{SUMMER_PREFIX}_boxes.{box.name}"] = qty
            rewards.append(f"- **{box.emoji} {qty} {box:!e} Box**")

        pc = self.determine_pc()
        if pc:
            inc["balance"] = pc
            rewards.append(f"- {FlavorStrings.pokecoins.emoji} {pc:,} {FlavorStrings.pokecoins:!e}")

        await bot.mongo.update_member(user, {"$inc": inc, "$set": {f"{SUMMER_PREFIX}_current_minisport": None}})

        if points:
            await bot.mongo.db.counter.find_one_and_update(
                {"_id": STANDING_ID.format(minisport=self.id, team=team.name)},
                {"$inc": {"next": points}},
                upsert=True,
            )

        embed = bot.Embed(
            title=f"{self} game completed, {'good game' if points else 'better luck next time'}!",
            description=f"**Total points earned for your team**: {self.progress.points}",
        )
        embed.set_author(name=str(user), icon_url=user.display_avatar.url)

        if rewards:
            embed.add_field(
                name="Rewards",
                value="\n".join(rewards),
            )

        await send_method(embed=embed, mention_author=False)

    @classmethod
    @abc.abstractmethod
    def new_data(cls) -> dict:
        pass

    @abc.abstractmethod
    async def check(self, bot: ClusterBot, ctx: PoketwoContext, input):
        pass

    @property
    @abc.abstractmethod
    def progress(self) -> Progress:
        pass

    @abc.abstractmethod
    def progress_text(self) -> str:
        pass


class Archery(BaseMinisport):
    name = "Archery"
    emoji = "🎯"
    description = "Remember and shoot targets"
    input_required = True

    TARGET_COUNT = 5
    MAX_TRIES = TARGET_COUNT
    HINT_SECONDS = 3

    HEIGHT = 5
    WIDTH = 5

    help_msg = dedent(
        f"""
        In Archery, you are briefly shown {TARGET_COUNT} targets on a square board only once, **whose locations you have to remember and type in to shoot**.

        Each location on the board is denoted by coordinates such as A1, A5, B4, etc. You have to shoot the coordinates of the targets from memory in order to shoot with your bow! **You have 1 try for each target**.
        - Use `@Pokétwo olympics minisport/m shoot <locations>` to shoot coordinates of targets
          - E.g. `@Pokétwo olympics m shoot a4 b4 a1 e5 d4`

        The more targets you hit, the more points, pokécoins and better rewards you will receive!
        """
    )

    # Need to add the rest if HEIGHT or WIDTH is increased
    COLUMN_ICONS = [
        "<:aa:1263911221133050028>",
        "<:bb:1263911253894631594>",
        "<:cc:1263911280897560647>",
        "<:dd:1263911308055810088>",
        "<:ee:1263911345489973319>",
    ]
    ROW_ICONS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]
    CELL_ICON_1 = "<:1:1263910096409329685>"
    CELL_ICON_2 = "<:2:1263898987694653560>"

    async def start_hook(self, ctx: PoketwoContext):
        result = await ctx.confirm(
            f"{self.help_msg}\nAs soon as you confirm, the targets will be shown for **{self.HINT_SECONDS} seconds**. Are you ready?",
            timeout=60,
            delete_after_timeout=False,
            cls=ConfirmationYesNoView,
        )
        if result is None:
            raise commands.UserInputError("Time's up. Aborted. Please start another game once you are ready.")
        if result is False:
            raise commands.UserInputError("Aborted. You can try again when you are ready.")

        embed = ctx.bot.Embed(
            title=f"Your {self} Game Targets",
            description=dedent(
                f"""
                {self.generate_board(show_targets=True)}
                """
            ),
        )
        dt_fmt = discord.utils.format_dt(datetime.utcnow() + timedelta(seconds=self.HINT_SECONDS), "R")
        message = await ctx.reply(
            f"Deleting {dt_fmt}, try your best to remember the coordinates (a1, b1, etc) of the targets!",
            embed=embed,
        )
        await asyncio.sleep(self.HINT_SECONDS)

        input_cmd = ctx.bot.get_cog("Summer").input
        await message.edit(
            content=f"Time's up, good luck! Use `{ctx.clean_prefix}{input_cmd.qualified_name} a1 b1 ...` with the correct target locations from memory!",
            embed=None,
        )

    @classmethod
    def new_data(cls) -> dict:
        cells = [[x, y] for y in range(cls.HEIGHT) for x in range(cls.WIDTH)]
        targets = random.sample(cells, cls.TARGET_COUNT)

        return dict(targets=targets, tries=[])

    async def check(self, bot: ClusterBot, ctx: PoketwoContext, cells_text: str):
        if not (isinstance(ctx, PoketwoContext) and isinstance(cells_text, str)):
            return

        tries = self.data["tries"]
        targets = self.data["targets"]

        points = 0

        texts = {}
        cells = cells_text.split()
        for cell in cells:
            if len(tries) >= self.MAX_TRIES:
                texts[cell.upper()] = "Out of tries"
                break

            # Input validation

            row = cell[0]
            col = cell[1:]

            if row not in string.ascii_letters or not all((d in string.digits for d in col)):
                texts[cell] = "Invalid location. Example: `a1`"
                continue

            cell = cell.upper()
            x = string.ascii_lowercase.index(row.lower())
            y = int(col) - 1

            if (x < 0 or x > self.WIDTH) or (y < 0 or y > self.HEIGHT):
                texts[cell] = "Out of bounds"
                continue

            # Valid, now check if correct

            coords = [x, y]

            if cell in texts:
                continue

            if coords in tries:
                texts[cell] = "Already hit"
                continue

            if coords in targets:
                texts[cell] = "🎯 Bullseye! +1 Point"
                points += 1
            else:
                texts[cell] = "❌"

            tries.append(coords)

        embed = ctx.bot.Embed(
            title="You take aim and shoot with your bow...",
            description="\n".join([f"{i}. `{cell}` — {text}" for i, (cell, text) in enumerate(texts.items(), 1)]),
        )
        embed.set_author(name=str(ctx.author), icon_url=ctx.author.display_avatar.url)
        embed.add_field(name=f"Progress — {self.progress}", value=self.progress_text(), inline=False)

        await ctx.reply(embed=embed, mention_author=False)
        return await self.update(bot, ctx)

    @property
    def hits(self) -> int:
        tries = self.data["tries"]
        targets = self.data["targets"]

        return len([t for t in tries if t in targets])

    @property
    def progress(self) -> Progress:
        tries = self.data["tries"]
        return Progress(len(tries), self.MAX_TRIES, self.hits)

    def generate_board(self, *, show_targets: Optional[bool] = False) -> str:
        tries = self.data["tries"]
        targets = self.data["targets"]

        board = [[self.CELL_ICON_1, *self.COLUMN_ICONS[: self.WIDTH]]]
        for y in range(self.HEIGHT):
            row = [self.ROW_ICONS[y]]
            for x in range(self.WIDTH):
                cell_coords = [x, y]

                empty_cell_icon = self.CELL_ICON_1 if (x + y) % 2 == 0 else self.CELL_ICON_2
                if show_targets:
                    if cell_coords in targets:
                        cell = "🎯"
                    else:
                        cell = empty_cell_icon
                else:
                    if cell_coords in tries:
                        if cell_coords in targets:
                            cell = f"<:check:{other['check']}>"
                        else:
                            cell = f"<:check:{other['cross']}>"
                    elif self.progress.completed and cell_coords in targets:
                        cell = "🎯"
                    else:
                        cell = empty_cell_icon

                row.append(cell)
            board.append(row)

        return "\n".join(["\u200c".join(row) for row in board])

    def progress_text(self) -> str:
        board = self.generate_board()

        return "\n".join(
            [
                "**Your Target Board**",
                board,
                f"\n**Tries left**: {self.progress.remaining}/{self.MAX_TRIES}",
                f"**Targets hit**: {self.hits}/{self.TARGET_COUNT}",
                f"**Points earned**: {self.progress.points}",
            ]
        )


class RelayRace(BaseMinisport):
    name = "Relay Race"
    emoji = "🏃"
    description = "Complete words by catching pokémon"

    WORDS = [
        "olympics",
        "rings",
        "torch",
        "medal",
        "archery",
        "baton",
        "fencing",
        "swim",
        "running",
        "boxing",
    ]  #! IF WORDS ARE CHANGED, LETTER EMOJIS BELOW NEED TO BE UPDATED TOO

    HINT_THRESHOLD = 3.5
    LETTER_CHANCES = {
        "s": 13.8824,
        "t": 8.1699,
        "c": 7.402,
        "g": 6.9159,
        "p": 6.7421,
        "m": 5.8127,
        "b": 5.7905,
        "f": 5.4774,
        "d": 5.4026,
        "r": 4.8347,
        "l": 3.9906,
        "w": 3.8428,
        "h": 3.3632,
        "a": 3.223,
        "n": 3.095,
        "v": 2.897,
        "k": 2.4983,
        "o": 1.5393,
        "e": 1.4073,
        "z": 0.8634,
        "i": 0.8272,
        "j": 0.6391,
        "y": 0.5906,
        "q": 0.5328,
        "u": 0.2278,
        "x": 0.0307,
    }

    COMPLETE_LETTER_EMOJIS = {
        "a": "<:green_a:1265360925259726858>",
        "b": "<:green_b:1265360930653343846>",
        "c": "<:green_c:1265360935401426965>",
        "d": "<:green_d:1265360941323653273>",
        "e": "<:green_e:1265360947476697223>",
        "f": "<:green_f:1265360953474551829>",
        "g": "<:green_g:1265360959761940561>",
        "h": "<:green_h:1265360966196134069>",
        "i": "<:green_i:1265360972181409792>",
        "j": "",
        "k": "",
        "l": "<:green_l:1265360978007162912>",
        "m": "<:green_m:1265360984781094913>",
        "n": "<:green_n:1265360991517016146>",
        "o": "<:green_o:1265360997774790689>",
        "p": "<:green_p:1265361004053921825>",
        "q": "",
        "r": "<:green_r:1265361010194251890>",
        "s": "<:green_s:1265361016435507264>",
        "t": "<:green_t:1265361022823170280>",
        "u": "<:green_u:1265361029085270188>",
        "v": "",
        "w": "<:green_w:1265361035678842990>",
        "x": "<:green_x:1265361041794142208>",
        "y": "<:green_y:1265361047485939736>",
        "z": "",
    }
    INCOMPLETE_LETTER_EMOJIS = {
        "a": "<:gray_a:1265361053794173050>",
        "b": "<:gray_b:1265361058227552359>",
        "c": "<:gray_c:1265361063139086387>",
        "d": "<:gray_d:1265361068163731526>",
        "e": "<:gray_e:1265361072332738631>",
        "f": "<:gray_f:1265361076812255343>",
        "g": "<:gray_g:1265361082432753744>",
        "h": "<:gray_h:1265361090980610111>",
        "i": "<:gray_i:1265361095577567412>",
        "j": "",
        "k": "",
        "l": "<:gray_l:1265361099629396123>",
        "m": "<:gray_m:1265361104192671805>",
        "n": "<:gray_n:1265361109121241208>",
        "o": "<:gray_o:1265361113562742898>",
        "p": "<:gray_p:1265361118017097881>",
        "q": "",
        "r": "<:gray_r:1265361122392018974>",
        "s": "<:gray_s:1265401779902742672>",
        "t": "<:gray_t:1265401786425016462>",
        "u": "<:gray_u:1265401793517715598>",
        "v": "",
        "w": "<:gray_w:1265401800576602166>",
        "x": "<:gray_x:1265401807639937205>",
        "y": "<:gray_y:1265401814870917234>",
        "z": "",
    }

    RAW_CATCHES_TO_POINTS = {
        range(0, 31): 5,
        range(31, 46): 4,
        range(46, 61): 3,
        range(61, 76): 2,
    }
    CATCHES_TO_POINTS = unwind(RAW_CATCHES_TO_POINTS)
    DEFAULT_POINTS = 1

    help_msg = (
        dedent(
            f"""
        In Relay Race, you are given an olympic-themed word, **for each letter of which you have to catch a pokémon whose English name starts with that letter**.

        **Green** letters have already been completed. **Gray** letters need to be caught still. There is no sequence in which you have to catch these letters. **Harder letters are autocompleted for you.**

        The less number of catches you can complete your word in, the more points, pokécoins and better rewards you will receive!
        """
        )
        + "\n".join(
            [f"> **≤{r[-1]} catches**: {p} points" for r, p in RAW_CATCHES_TO_POINTS.items()]
            + [f"> **>{list(RAW_CATCHES_TO_POINTS.keys())[-1][-1]} catches**: {DEFAULT_POINTS} point\n"]
        )
    )

    @dataclass
    class Letter:
        idx: int
        letter: str
        done: bool

        @property
        def emoji(self) -> str:
            return (
                RelayRace.COMPLETE_LETTER_EMOJIS[self.letter]
                if self.done
                else RelayRace.INCOMPLETE_LETTER_EMOJIS[self.letter]
            )

    @classmethod
    def new_data(cls) -> dict:
        word = random.choice(cls.WORDS).lower()

        return dict(
            letters=[{"letter": letter, "done": cls.LETTER_CHANCES[letter] < cls.HINT_THRESHOLD} for letter in word],
            catches=0,
        )

    async def check(self, bot: ClusterBot, ctx: PoketwoContext, species: Species):
        if not (isinstance(ctx, PoketwoContext) and isinstance(species, Species)):
            return

        letter = get(self.letters, letter=species.name[0].lower(), done=False)
        if letter:
            letter.done = True
            self.data["letters"][letter.idx]["done"] = True

            await ctx.reply(
                f"You caught a pokémon starting with {letter.emoji} for your {self:b} game! Use `{ctx.clean_prefix}{ctx.bot.get_cog('Summer').minisport}` to view your progress.",
                mention_author=False,
            )

        self.data["catches"] += 1
        return await self.update(bot, ctx)

    @property
    def letters(self) -> List[Letter]:
        return [self.Letter(idx, data["letter"], data["done"]) for idx, data in enumerate(self.data["letters"])]

    def calculate_points(self) -> int:
        catches = self.data["catches"]
        return self.CATCHES_TO_POINTS.get(catches, self.DEFAULT_POINTS)

    @property
    def progress(self) -> Progress:
        letters = self.letters
        done = len([letter for letter in letters if letter.done])

        return Progress(done, len(letters), self.calculate_points())

    def generate_word_hint(self) -> str:
        return "\u200b".join([letter.emoji for letter in self.letters])

    def progress_text(self) -> str:
        word_emojis = self.generate_word_hint()

        return "\n".join(
            [
                "**Your Word**",
                word_emojis,
                f"\n**Letters done**: {self.progress.count}/{self.progress.goal}",
                f"**Total catches**: {self.data['catches']}",
                f"**Potential earnable points**: {self.progress.points}",
            ]
        )


def seconds_to_hours(seconds: float) -> float:
    return round(seconds / 60 / 60, 2)


class Pentathlon(BaseMinisport):
    name = "Pentathlon"
    emoji = "🏅"
    description = "Complete a sequence of tasks"

    class TaskEvent(Enum):
        CATCH = "catch"
        TRADE = "trade", "Trade with {count} people"
        BATTLE = "battle", "Battle {count} times"
        EVOLVE = "evolve", "Evolve {count} pokémon"
        RELEASE = "release", "Release {count} pokémon"

        def __init__(self, id: str, description: Optional[str] = "") -> None:
            self.id = id
            self.description = description

        @classmethod
        def from_id(self, id: str) -> Pentathlon.TaskEvent:
            return get(self, id=id)

    @dataclass
    class Task:
        event: Pentathlon.TaskEvent
        count: int
        condition: Optional[Dict[str, str]] = None
        progress: Optional[int] = 0
        unlocked: Optional[bool] = False

        @property
        def completed(self) -> str:
            return self.progress >= self.count

        @property
        def description(self) -> str:
            event = self.event
            count = self.count
            condition = self.condition

            match event:
                case Pentathlon.TaskEvent.CATCH:
                    if condition:
                        if type := condition.get("type"):
                            description = f"Catch {count:,} {type}-type pokémon"
                        elif region := condition.get("region"):
                            description = f"Catch {count:,} pokémon from the {region.title()} region"
                        elif gender := condition.get("gender"):
                            description = f"Catch {count:,} {gender.title()} gender pokémon"
                    else:
                        description = f"Catch {count:,} pokémon"
                case _:
                    description = self.event.description.format(count=self.count)

            return description

        def progress_text(self) -> str:
            emoji = (other["check"] if self.completed else other["gray"]) if self.unlocked else other["locked"]
            progress = f"`{self.progress}/{self.count}`" if self.unlocked else "— Locked"
            return f"<:_:{emoji}> {self.description} {progress}"

        def to_dict(self) -> dict:
            return dict(
                event=self.event.id,
                count=self.count,
                condition=self.condition,
                progress=self.progress,
            )

    CATCHING_TASK_COUNT = 1
    OTHER_TASK_COUNT = 4

    TYPE_RANGES = unwind(
        {
            ("Normal", "Water", "Grass", "Flying", "Bug"): range(8, 11),
            ("Poison", "Ground", "Psychic", "Rock", "Electric", "Ghost"): range(7, 10),
            ("Dragon", "Fire", "Fairy", "Dark", "Fighting", "Steel", "Ice"): range(6, 9),
        }
    )
    REGION_RANGES = unwind(
        {
            ("paldea",): range(10, 16),
            ("kanto", "johto", "hoenn", "unova"): range(7, 10),
            ("sinnoh", "alola", "kalos", "galar"): range(6, 9),
        }
    )
    GENDER_RANGES = unwind(
        {("male", "female"): range(12, 19), ("unknown",): range(3, 7)},
    )

    CATCHING_TASKS = [
        lambda: Pentathlon.Task(
            event=Pentathlon.TaskEvent.CATCH,
            count=random.randint(40, 51),
        ),
        lambda: Pentathlon.Task(
            event=Pentathlon.TaskEvent.CATCH,
            condition={"type": (type := random.choice(list(Pentathlon.TYPE_RANGES)))},
            count=random.choice(Pentathlon.TYPE_RANGES[type]),
        ),
        lambda: Pentathlon.Task(
            event=Pentathlon.TaskEvent.CATCH,
            condition={"region": (region := random.choice(list(Pentathlon.REGION_RANGES)))},
            count=random.choice(Pentathlon.REGION_RANGES[region]),
        ),
        lambda: Pentathlon.Task(
            event=Pentathlon.TaskEvent.CATCH,
            condition={"gender": (gender := random.choice(list(Pentathlon.GENDER_RANGES)))},
            count=random.choice(Pentathlon.GENDER_RANGES[gender]),
        ),
    ]

    OTHER_TASKS = [
        lambda: Pentathlon.Task(
            event=Pentathlon.TaskEvent.TRADE,
            count=random.randint(3, 6),
        ),
        lambda: Pentathlon.Task(
            event=Pentathlon.TaskEvent.BATTLE,
            count=random.randint(3, 6),
        ),
        lambda: Pentathlon.Task(
            event=Pentathlon.TaskEvent.EVOLVE,
            count=random.randint(10, 15),
        ),
        lambda: Pentathlon.Task(
            event=Pentathlon.TaskEvent.RELEASE,
            count=random.randint(10, 15),
        ),
    ]

    RAW_SECONDS_TO_POINTS = {
        range(0, 1801): 5,
        range(1801, 2701): 4,
        range(2701, 3601): 3,
        range(3601, 4501): 2,
    }
    SECONDS_TO_POINTS = unwind(RAW_SECONDS_TO_POINTS)
    DEFAULT_POINTS = 1

    help_msg = (
        dedent(
            f"""
        In Pentathlon, you have to complete {CATCHING_TASK_COUNT + OTHER_TASK_COUNT} tasks of varying difficulties in sequence: **Catching, Trading, Battling, Evolving and Releasing**.

        **Check mark** means the task has been completed, **Gray** means the task is in progress and **Locked** means you must first complete the prior tasks before you can do that one. **Tasks must be completed in sequence**.

        The lower the time you can complete all your tasks in, the more points, pokécoins and better rewards you will receive! **You will receive extra boxes for {name} since it is a harder minisport.**
        """
        )
        + "\n".join(
            [
                f"> **≤{seconds_to_hours(r[-1])} hour{'' if seconds_to_hours(r[-1]) == 1 else 's'}**: {p} points"
                for r, p in RAW_SECONDS_TO_POINTS.items()
            ]
            + [f"> **>{seconds_to_hours(list(RAW_SECONDS_TO_POINTS.keys())[-1][-1])} hours**: {DEFAULT_POINTS} point\n"]
        )
    )

    def determine_boxes(self) -> Dict[Box, int]:
        points = self.progress.points

        if points <= 0:
            return {}

        if 1 <= points <= 2:
            return {Box.BRONZE: 2}

        if 3 <= points <= 4:
            return {Box.SILVER: 1, Box.BRONZE: 2}

        if 5 <= points:
            return {Box.GOLD: 1, Box.SILVER: 2}

    @classmethod
    def new_data(cls) -> dict:
        task_selections = [
            *random.sample(cls.CATCHING_TASKS, cls.CATCHING_TASK_COUNT),
            *sorted(random.sample(cls.OTHER_TASKS, cls.OTHER_TASK_COUNT), key=lambda x: cls.OTHER_TASKS.index(x)),
        ]
        tasks = [task() for task in task_selections]
        return dict(tasks=[task.to_dict() for task in tasks])

    def verify_condition(self, condition, species, pokemon):
        if condition is not None:
            for k, v in condition.items():
                if k == "type" and v not in species.types:
                    return False
                elif k == "region" and v != species.region:
                    return False
                elif k == "gender" and v != pokemon.gender.lower():
                    return False
        return True

    async def check(
        self,
        bot: ClusterBot,
        ctx_or_user: PoketwoContext | discord.User,
        input: Tuple[TaskEvent, Optional[tuple]] = None,
    ):
        if not (isinstance(input, tuple) and isinstance(input[0], self.TaskEvent)):
            return

        current_task = self.current_task
        task_idx = self.tasks.index(current_task)

        task_event = input[0]
        if current_task.event != task_event:
            return

        if task_event == self.TaskEvent.CATCH:
            species, _id = input[1]
            pokemon = await bot.mongo.fetch_pokemon(ctx_or_user.author, _id)
            if current_task.event != self.TaskEvent.CATCH:
                return
            if not self.verify_condition(current_task.condition, species, pokemon):
                return

        count = input[1][-1] if task_event in (self.TaskEvent.RELEASE, self.TaskEvent.EVOLVE) else 1
        inc = min(current_task.count, current_task.progress + count) - current_task.progress

        self.data["tasks"][task_idx]["progress"] += inc
        current_task.progress += inc
        if current_task.completed:
            send_method = ctx_or_user.reply if isinstance(ctx_or_user, PoketwoContext) else ctx_or_user.send
            await send_method(
                f"You completed the **{current_task.description}** task for your {self:b} game! Use `@Pokétwo {bot.get_cog('Summer').minisport}` to view your progress.",
                mention_author=False,
            )

        return await self.update(bot, ctx_or_user)

    @property
    def elapsed(self) -> timedelta:
        now = datetime.utcnow()
        started_at = self.started_at
        return now - started_at

    @property
    def tasks(self) -> List[Pentathlon.Task]:
        unlocked = True
        tasks = []
        for task_data in self.data["tasks"]:
            task_data = task_data.copy()
            event = Pentathlon.TaskEvent.from_id(task_data.pop("event"))
            task = Pentathlon.Task(event=event, **task_data, unlocked=unlocked)
            unlocked = task.completed
            tasks.append(task)

        return tasks

    @property
    def current_task(self) -> Pentathlon.Task | None:
        return get(self.tasks, completed=False)

    def calculate_points(self) -> int:
        elapsed_seconds = round(self.elapsed.total_seconds())
        return self.SECONDS_TO_POINTS.get(elapsed_seconds, self.DEFAULT_POINTS)

    @property
    def progress(self) -> Progress:
        total_count = sum([task.count for task in self.tasks])
        total_progress = sum([task.progress for task in self.tasks])
        return Progress(total_progress, total_count, self.calculate_points())

    def generate_task_progresses(self) -> str:
        return "\n".join(
            [
                f"{i}. {'-# ' if not task.unlocked else ''} {task.progress_text()}"
                for i, task in enumerate(self.tasks, 1)
            ]
        )

    def progress_text(self) -> str:
        task_progresses = self.generate_task_progresses()

        return "\n".join(
            [
                "**Your Tasks**",
                task_progresses,
                f"\n**Total progress**: {self.progress.count}/{self.progress.goal}",
                f"**Elapsed time**: {humanfriendly.format_timespan(self.elapsed.total_seconds())}",
                f"**Potential earnable points**: {self.progress.points}",
            ]
        )


# region ENUMS
class EventSpecies(Enum):
    """Enum for all event pokemon for this event"""

    MOLTRES = 50182
    SENTRET = 50183, 27
    DUCKLETT = 50184, 6.33
    RABOOT = 50185, 27
    INTELEON = 50186, 27
    TOXEL = 50187, 6.33
    ORICORIO = 50188, 6.34

    def __init__(self, id: int, weight: Optional[int | float] = None) -> None:
        self.id = id
        self.weight = weight

    def get_species(self, bot: ClusterBot) -> Species:
        return bot.data.species_by_number(self.value)

    @classmethod
    def all_ids(cls) -> List[int]:
        return [species.id for species in cls]

    @classmethod
    def to_weights(cls) -> Dict[int, int | float]:
        return {species.id: species.weight for species in cls if species.weight}


class Team(Enum):
    TEAM_1 = BaseTeam(name="Kalos", emoji="<:kalos_olympics:1262073123407134790>")
    TEAM_2 = BaseTeam(name="Galar", emoji="<:galar_olympics:1262073115798802482>")
    TEAM_3 = BaseTeam(name="Unova", emoji="<:unova_olympics:1262073112837755042>")
    TEAM_4 = BaseTeam(name="Alola", emoji="<:alola_olympics:1262073110132297749>")
    TEAM_5 = BaseTeam(name="Paldea", emoji="<:paldea_olympics:1262073107313594438>")
    TEAM_6 = BaseTeam(name="Kanto", emoji="<:kanto_olympics:1262073104696479846>")

    @property
    def qname(self) -> str:
        return self.value.name

    @property
    def emoji(self) -> str:
        return self.value.emoji

    def __format__(self, format_spec: str) -> str:
        val = self.qname
        emoji = self.emoji

        # Whether to not show emoji
        if "!e" not in format_spec and emoji is not None:
            val = f"{emoji} {val}"

        # Whether to bold
        if "b" in format_spec:
            val = f"**{val}**"

        return val

    def __str__(self) -> str:
        return f"{self}"

    @classmethod
    def from_name(cls, name: str) -> Minisport:
        name = name.casefold().strip()
        for enum in cls:
            if name in (enum.name.casefold(), enum.qname.casefold()):
                return enum
        else:
            raise commands.UserInputError(
                f"Invalid {cls.__name__}. Valid {cls.__name__}s are: {comma_formatted([f'{e:b!e}' for e in cls])}"
            )


class Minisport(Enum):
    ARCHERY = Archery
    RELAY_RACE = RelayRace
    PENTATHLON = Pentathlon

    @property
    def qname(self) -> str:
        return self.value.name

    @property
    def emoji(self) -> str:
        return self.value.emoji

    @property
    def description(self) -> str:
        return self.value.description

    def __format__(self, format_spec: str) -> str:
        val = self.qname
        emoji = self.emoji

        # Whether to not show emoji
        if "!e" not in format_spec and emoji is not None:
            val = f"{emoji} {val}"

        # Whether to bold
        if "b" in format_spec:
            val = f"**{val}**"

        return val

    def __str__(self) -> str:
        return f"{self}"

    @classmethod
    def from_name(cls, name: str) -> Minisport:
        name = name.casefold().strip()
        for enum in cls:
            if name in (enum.name.casefold(), enum.qname.casefold()):
                return enum
        else:
            raise commands.UserInputError(
                f"Invalid {cls.__name__}. Valid {cls.__name__}s are: {comma_formatted([f'{e:b!e}' for e in cls])}"
            )


class Box(Enum):
    GOLD = BaseBox(
        name="Gold",
        emoji="<:gold_box:1265524100894560352>",
        rewards=[
            Reward(item=RewardItem.POKECOINS, chance=45, amounts=range(3000, 4001)),
            Reward(
                item=RewardItem.EVENT_POKEMON,
                chance=40,
                amounts=[1],
                species_ids=EventSpecies.to_weights(),
                shiny_boost=EVENT_SHINY_BOOST,
            ),
            Reward(item=RewardItem.SHARDS, chance=5, amounts=range(20, 41)),
            Reward(item=RewardItem.POKEMON, chance=7, amounts=[1], shiny_boost=800),
            Reward(item=RewardItem.REDEEM, chance=3, amounts=[1]),
        ],
    )
    SILVER = BaseBox(
        name="Silver",
        emoji="<:silver_box:1265524105956818966>",
        rewards=[
            Reward(item=RewardItem.POKECOINS, chance=45, amounts=range(1500, 3001)),
            Reward(
                item=RewardItem.EVENT_POKEMON,
                chance=35,
                amounts=[1],
                species_ids=EventSpecies.to_weights(),
                shiny_boost=EVENT_SHINY_BOOST,
            ),
            Reward(item=RewardItem.SHARDS, chance=10, amounts=range(10, 21)),
            Reward(item=RewardItem.POKEMON, chance=8, amounts=[1], shiny_boost=400),
            Reward(item=RewardItem.REDEEM, chance=2, amounts=[1]),
        ],
    )
    BRONZE = BaseBox(
        name="Bronze",
        emoji="<:bronze_box:1265524107886198815>",
        rewards=[
            Reward(item=RewardItem.POKECOINS, chance=45, amounts=range(500, 1501)),
            Reward(
                item=RewardItem.EVENT_POKEMON,
                chance=30,
                amounts=[1],
                species_ids=EventSpecies.to_weights(),
                shiny_boost=EVENT_SHINY_BOOST,
            ),
            Reward(item=RewardItem.POKEMON, chance=9, amounts=[1], shiny_boost=200),
            Reward(item=RewardItem.SHARDS, chance=15, amounts=range(5, 11)),
            Reward(item=RewardItem.REDEEM, chance=1, amounts=[1]),
        ],
    )

    @property
    def qname(self) -> str:
        return self.value.name

    @property
    def emoji(self) -> str:
        return self.value.emoji

    @property
    def rewards(self) -> str:
        return self.value.rewards

    def __format__(self, format_spec: str) -> str:
        val = self.qname
        emoji = self.emoji

        # Whether to not show emoji
        if "!e" not in format_spec and emoji is not None:
            val = f"{emoji} {val}"

        # Whether to bold
        if "b" in format_spec:
            val = f"**{val}**"

        return val

    def __str__(self) -> str:
        return f"{self}"

    @classmethod
    def from_name(cls, name: str) -> Minisport:
        name = name.casefold().strip()
        for enum in cls:
            if name in (enum.name.casefold(), enum.qname.casefold()):
                return enum
        else:
            raise commands.UserInputError(
                f"Invalid {cls.__name__}. Valid {cls.__name__}es are: {comma_formatted([f'{e:b!e}' for e in cls])}"
            )


# region CONVERTERS
class EnumConverter(commands.Converter):
    def __init__(self, enum_class):
        self.enum_class = enum_class

    async def convert(self, ctx: PoketwoContext, argument: str):
        return self.enum_class.from_name(argument)


# region VIEWS
class OlympicsJoinView(discord.ui.View):
    def __init__(self, ctx: PoketwoContext):
        self.ctx = ctx
        self.cog: Summer = self.ctx.bot.get_cog("Summer")
        super().__init__(timeout=120)

    @discord.ui.button(label="Start Event", style=discord.ButtonStyle.blurple, row=2)
    async def start(self, interaction: discord.Interaction, button: discord.Button):
        await interaction.response.defer()
        member = await self.ctx.bot.mongo.fetch_member_info(self.ctx.author)

        if member[f"{SUMMER_PREFIX}_team"]:
            return await self.ctx.reply(f"You've already joined a team!", mention_author=False)

        team = random.choice(list(Team))
        await self.cog.bot.mongo.update_member(self.ctx.author, {"$set": {f"{SUMMER_PREFIX}_team": team.name}})
        await self.ctx.reply(f"You've been assigned to team {team:b}, good luck and have fun!", mention_author=False)

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


class MinisportSelectMenu(discord.ui.Select):
    def __init__(self):
        super().__init__(
            placeholder=f"Play a {FlavorStrings.minisport}...",
            options=[
                discord.SelectOption(
                    label=minisport.qname,
                    value=minisport.name,
                    description=minisport.description,
                    emoji=minisport.emoji,
                )
                for minisport in Minisport
            ],
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()

        selected_sport = Minisport[self.values[0]]
        await self.view.ctx.invoke(self.view.cog.play, minisport=selected_sport)


class OlympicView(discord.ui.View):
    def __init__(self, ctx: PoketwoContext):
        self.ctx = ctx
        self.cog: Summer = self.ctx.bot.get_cog("Summer")
        super().__init__(timeout=120)

        children = self.children
        self.clear_items()
        self.play = MinisportSelectMenu()
        self.add_item(self.play)
        for child in children:
            self.add_item(child)

    @discord.ui.button(label="Current Minisport Game", style=discord.ButtonStyle.blurple)
    async def minisport(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await self.ctx.invoke(self.cog.minisport)

    @discord.ui.button(label="Inventory", style=discord.ButtonStyle.grey)
    async def inventory(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await self.ctx.invoke(self.cog.inventory)

    @discord.ui.button(label="Standings", style=discord.ButtonStyle.grey)
    async def standings(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await self.ctx.invoke(self.cog.standings)

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


class MinisportView(discord.ui.View):
    def __init__(self, ctx: PoketwoContext):
        self.ctx = ctx
        self.cog: Summer = self.ctx.bot.get_cog("Summer")
        super().__init__(timeout=120)

        children = self.children
        self.clear_items()
        self.play = MinisportSelectMenu()
        self.add_item(self.play)
        for child in children:
            self.add_item(child)

    @discord.ui.button(label="Cancel Game", style=discord.ButtonStyle.red)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await self.ctx.invoke(self.cog.cancel)

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


def has_joined_team():
    async def predicate(ctx):
        member = await ctx.bot.mongo.fetch_member_info(ctx.author)
        if member["summer_2024_team"]:
            return True
        else:
            await ctx.invoke(ctx.bot.get_cog("Summer").start)
            raise commands.CheckFailure(f"To play the event, please join a team first.")

    return check(predicate)


TOP_3_TEXT = f"The top 3 teams with the highest points in each {FlavorStrings.minisport} at the end will receive special rewards, including lots of boxes and a **surprise exclusive pokémon**!"
MAIN_MENU_TEXT = f"""{FlavorStrings.olympics} has kicked off, and the competition for 1st position has begun! Join a team, earn points by playing unique {FlavorStrings.minisport:s}, along with rewards and **an exclusive badge** at the end! ❤️‍🔥

As you catch pokémon, you will earn {FlavorStrings.ticket:sb}. Use these to play {FlavorStrings.minisport:s} to earn points for your team, along with {FlavorStrings.pokecoins:b!e} and {FlavorStrings.box:sb} containing various rewards and exclusive pokémon!

{TOP_3_TEXT} Good luck and have fun! 👀"""

# region MAIN COG
class Summer(commands.Cog):
    """Summer 2024 event commands."""

    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        self.bot.Embed.CUSTOM_COLOR = EMBED_COLOR  # Set custom embed color for this event

    async def cog_unload(self):
        self.bot.Embed.CUSTOM_COLOR = None  # Unset custom embed color

    def sorted_standings(self, dictionary: Dict[Any, int], *, top: Optional[int] = None):
        return dict(sorted(dictionary.items(), key=lambda s: -s[1])[: top or len(dictionary)])

    async def fetch_standings(self, *, top: Optional[int] = None) -> Dict[Minisport, Dict[Team, int]]:
        raw_standings = await self.bot.mongo.Counter.find({"_id": {"$regex": f"^{SUMMER_PREFIX}_points"}}).to_list(None)

        all_standings = {}
        for minisport in Minisport:
            standings = {}
            for team in Team:
                points = getattr(
                    get(raw_standings, id=STANDING_ID.format(minisport=minisport.name, team=team.name)), "next", 0
                )
                standings[team] = points

            standings = self.sorted_standings(standings, top=top)
            all_standings[minisport] = standings

        return all_standings

    def member_text(
        self,
        member,
        *,
        tickets: Optional[bool] = True,
        total_played: Optional[bool] = True,
        points_earned: Optional[bool] = False,
    ) -> str:
        member_team = Team[member[f"{SUMMER_PREFIX}_team"]]

        lines = [
            f"**Your Team**: {member_team}",
        ]
        if tickets:
            lines.append(f"{FlavorStrings.ticket:sb!e}: {member[f'{SUMMER_PREFIX}_tickets']:,}")
        if total_played:
            lines.append(f"**Total Minisport Games Played**: {member[f'{SUMMER_PREFIX}_minisports_played']}")
        if points_earned:
            lines.append(f"**Total Points Earned**: {sum(member[f'{SUMMER_PREFIX}_points'].values()):,}")

        return "\n".join(lines)

    # region main embed
    @has_joined_team()
    @checks.has_started()
    @commands.group(aliases=("event", "ev"), invoke_without_command=True, case_insensitive=True)
    async def olympics(self, ctx: PoketwoContext):
        """Open Summer 2024's Olympics menu"""

        member = await self.bot.mongo.fetch_member_info(ctx.author)
        member_team = Team[member[f"{SUMMER_PREFIX}_team"]]
        current_minisport = BaseMinisport.from_dict(member[f"{SUMMER_PREFIX}_current_minisport"])

        embed = self.bot.Embed(
            title=f"Welcome to {FlavorStrings.olympics}!",
            description=MAIN_MENU_TEXT + "\n\n" + self.member_text(member),
        )

        standings = await self.fetch_standings(top=3)
        for minisport in Minisport:
            value = "\n".join(
                f"{standing}. **{team} — {points:,}**" if team == member_team else f"{standing}. {team} — {points:,}"
                for standing, (team, points) in enumerate(standings[minisport].items(), 1)
            )
            embed.add_field(name=f"{minisport} Standings", value=value)

        embed.set_image(url=self.bot.data.asset("/assets/summer_2024/banner.png"))

        view = OlympicView(ctx)

        if current_minisport:
            view.play.placeholder = f"{current_minisport} game in progress ({current_minisport.progress})"
            view.play.disabled = True
            view.minisport.style = discord.ButtonStyle.green
        else:
            view.minisport.label = "Minisports"

        embed.set_footer(
            text=f"Use `{ctx.clean_prefix}{self.minisport}` or the select menu to view and play {FlavorStrings.minisport:s}!"
        )

        view.message = await ctx.send(embed=embed, view=view)

    # region Joining Team
    @checks.has_started()
    @olympics.command(name="start", aliases=("s", "join"))
    async def start(self, ctx: PoketwoContext):
        """Start the event and join a random team"""

        member = await self.bot.mongo.fetch_member_info(ctx.author)

        if member[f"{SUMMER_PREFIX}_team"]:
            await ctx.reply(f"You've already joined a team!", mention_author=False)
        else:
            view = OlympicsJoinView(ctx)
            embed = self.bot.Embed(
                title=f"Welcome to {FlavorStrings.olympics}!",
                description=MAIN_MENU_TEXT
                + dedent(
                    f"""

                    **Teams are assigned at random for an unbiased experience, and cannot be changed**. Compete alongside your teammates against the other teams to reach the top, earning various rewards along the way!

                    **All teams**: {comma_formatted([f"{team:b}" for team in Team])}
                    """
                ),
            )

            view.message = await ctx.reply(embed=embed, view=view, mention_author=False)

    @checks.has_started()
    @olympics.command(aliases=("points", "scores", "rankings", "ranks", "rank", "positions", "position"))
    async def standings(self, ctx: PoketwoContext):
        """View total earned points and team standings"""

        member = await self.bot.mongo.fetch_member_info(ctx.author)
        member_team = Team[member[f"{SUMMER_PREFIX}_team"]]

        embed = self.bot.Embed(
            title=f"Team Points & Standings",
            description=dedent(
                f"""
                Points you earn by playing {FlavorStrings.minisport:s} will directly affect your team's standings. The more points you earn in a {FlavorStrings.minisport:s} game, the more pokécoins and better rewards you will receive.

                {TOP_3_TEXT}

                May the best teams win!

                """
            )
            + self.member_text(member, tickets=False),
        )

        member_points = self.sorted_standings(
            {minisport: member[f"{SUMMER_PREFIX}_points"].get(minisport.name, 0) for minisport in Minisport}
        )
        embed.add_field(
            name="Your Earned Points",
            value=f"-# **Total Points: {sum(member_points.values()):,}**\n"
            + "\n".join(
                f"{i}. {minisport} — {points:,}" for i, (minisport, points) in enumerate(member_points.items(), 1)
            ),
            inline=False,
        )

        all_standings = await self.fetch_standings()

        # team_standings = self.sorted_standings(
        #     {team: sum([s.get(team) for s in all_standings.values()]) for team in Team}
        # )

        # embed.add_field(
        #     name="Total Standings",
        #     value=f"-# **Total Points: {sum(team_standings.values()):,}**\n"
        #     + "\n".join(
        #         f"{standing}. **{team} — {points:,}**" if team == member_team else f"{standing}. {team} — {points:,}"
        #         for standing, (team, points) in enumerate(team_standings.items(), 1)
        #     ),
        # )

        # embed.add_field(name="", value="")

        for minisport in Minisport:
            standings = all_standings[minisport]
            value = f"-# **Total Points: {sum(standings.values()):,}**\n" + "\n".join(
                f"{standing}. **{team} — {points:,}**" if team == member_team else f"{standing}. {team} — {points:,}"
                for standing, (team, points) in enumerate(standings.items(), 1)
            )
            embed.add_field(name=f"{minisport} Standings", value=value)

        await ctx.reply(embed=embed, mention_author=False)

    # region Start minisport
    @has_joined_team()
    @checks.has_started()
    @olympics.command(aliases=("p",))
    async def play(self, ctx: PoketwoContext, *, minisport: EnumConverter(Minisport)):
        """Play minisports for points and rewards"""

        member = await self.bot.mongo.fetch_member_info(ctx.author)
        current_minisport = BaseMinisport.from_dict(member[f"{SUMMER_PREFIX}_current_minisport"])

        if current_minisport:
            return await ctx.send(
                f"You already have a {current_minisport:bp} game in progress. You can cancel it using `{ctx.clean_prefix}{self.cancel.qualified_name}` if you want."
            )

        if member[f"{SUMMER_PREFIX}_tickets"] <= 0:
            await ctx.reply(f"You don't have enough tickets to play {minisport}!", mention_author=False)
            return

        await minisport.value.new().start(ctx)
        await ctx.invoke(self.minisport)

    @has_joined_team()
    @checks.has_started()
    @olympics.group(aliases=("m",), invoke_without_command=True)
    async def minisport(self, ctx: PoketwoContext):
        """See your current minisport game's progress"""

        member = await self.bot.mongo.fetch_member_info(ctx.author)
        current_minisport = BaseMinisport.from_dict(member[f"{SUMMER_PREFIX}_current_minisport"])

        view = MinisportView(ctx)

        if current_minisport:
            embed = self.bot.Embed(
                title=f"Your {current_minisport} Game",
                description=dedent(
                    f"""
                    ### How to play{current_minisport.help_msg}
                    """
                )
                + self.member_text(member, tickets=False, total_played=False),
            )

            embed.add_field(
                name=f"Progress — {current_minisport.progress}", value=current_minisport.progress_text(), inline=False
            )
            view.remove_item(view.play)
        else:
            embed = self.bot.Embed(
                title=f"Minisports",
                description=dedent(
                    f"""
                    As you catch pokémon in the wild, you will earn {FlavorStrings.ticket:sb}. You can use these tickets to play {FlavorStrings.minisport:s} and earn points for your team, {FlavorStrings.pokecoins:!e} and {FlavorStrings.box:s} containing various rewards!

                    The higher you score in a {FlavorStrings.minisport:s} game, the more points, {FlavorStrings.pokecoins:!e} and better {FlavorStrings.box:s} you will earn. You can see instructions on how to play a {FlavorStrings.minisport} and how to earn points once you start a game!

                    """
                )
                + self.member_text(member, points_earned=True),
            )

            for minisport in Minisport:
                embed.add_field(name=f"{minisport}", value=minisport.value.help_msg.split("\n\n")[0])

            view.remove_item(view.cancel)

        embed.set_author(name=str(ctx.author), icon_url=ctx.author.display_avatar.url)

        view.message = await ctx.reply(embed=embed, view=view, mention_author=False)

    # region MINISPORT PROGRESSION CHECKS
    @has_joined_team()
    @checks.has_started()
    @minisport.command(aliases=("i", "shoot"))
    async def input(self, ctx: PoketwoContext, *, input: str):
        """Give input to a minisport that needs it"""

        member = await self.bot.mongo.fetch_member_info(ctx.author)
        current_minisport = BaseMinisport.from_dict(member[f"{SUMMER_PREFIX}_current_minisport"])

        if not current_minisport:
            return await ctx.send(f"You don't have a minisport game in progress currently!")

        if not current_minisport.input_required:
            return await ctx.send(f"Your current minisport does not require input!")

        await current_minisport.check(self.bot, ctx, input)

    @commands.Cog.listener(name="on_catch")
    async def relay_race_on_catch(self, ctx: PoketwoContext, species: Species, _id: int):
        member = await self.bot.mongo.fetch_member_info(ctx.author)
        current_minisport = BaseMinisport.from_dict(member[f"{SUMMER_PREFIX}_current_minisport"])

        if not current_minisport:
            return

        await current_minisport.check(self.bot, ctx, species)

    @commands.Cog.listener(name="on_catch")
    async def pentathlon_on_catch(self, ctx: PoketwoContext, species: Species, _id: int):
        member = await self.bot.mongo.fetch_member_info(ctx.author)
        current_minisport = BaseMinisport.from_dict(member[f"{SUMMER_PREFIX}_current_minisport"])

        if not current_minisport:
            return

        await current_minisport.check(self.bot, ctx, (Pentathlon.TaskEvent.CATCH, (species, _id)))

    @commands.Cog.listener()
    async def on_trade(self, trade):
        a, b = trade["users"]

        for user in (a, b):
            member = await self.bot.mongo.fetch_member_info(user)
            current_minisport = BaseMinisport.from_dict(member[f"{SUMMER_PREFIX}_current_minisport"])

            if not current_minisport:
                continue

            await current_minisport.check(self.bot, user, (Pentathlon.TaskEvent.TRADE,))

    @commands.Cog.listener()
    async def on_battle_start(self, battle):
        a, b = battle.trainers[0].user, battle.trainers[1].user

        for user in (a, b):
            member = await self.bot.mongo.fetch_member_info(user)
            current_minisport = BaseMinisport.from_dict(member[f"{SUMMER_PREFIX}_current_minisport"])

            if not current_minisport:
                continue

            await current_minisport.check(self.bot, user, (Pentathlon.TaskEvent.BATTLE,))

    @commands.Cog.listener()
    async def on_mass_evolve(self, user, evolved):
        member = await self.bot.mongo.fetch_member_info(user)
        current_minisport = BaseMinisport.from_dict(member[f"{SUMMER_PREFIX}_current_minisport"])

        if not current_minisport:
            return

        await current_minisport.check(self.bot, user, (Pentathlon.TaskEvent.EVOLVE, (len(evolved),)))

    @commands.Cog.listener()
    async def on_release(self, user, count):
        member = await self.bot.mongo.fetch_member_info(user)
        current_minisport = BaseMinisport.from_dict(member[f"{SUMMER_PREFIX}_current_minisport"])

        if not current_minisport:
            return

        await current_minisport.check(self.bot, user, (Pentathlon.TaskEvent.RELEASE, (count,)))

    @has_joined_team()
    @checks.has_started()
    @olympics.command(aliases=("x",))
    async def cancel(self, ctx: PoketwoContext):
        """Cancel your minisport currently in progress."""

        member = await self.bot.mongo.fetch_member_info(ctx.author)
        current_minisport = BaseMinisport.from_dict(member[f"{SUMMER_PREFIX}_current_minisport"])

        if not current_minisport:
            return await ctx.send(f"You don't have a minisport game in progress currently!")

        result = await ctx.confirm(
            f"Are you sure you want to cancel your {current_minisport:bp} game? You will *not* be refunded your ticket."
        )
        if result is None:
            return await ctx.send("Time's up. Aborted.")
        if result is False:
            return await ctx.send("Aborted.")

        await self.bot.mongo.update_member(ctx.author, {"$set": {f"{SUMMER_PREFIX}_current_minisport": None}})

        await ctx.send(f"Cancelled your {current_minisport:b} game.")

    @checks.has_started()
    @olympics.command(name="inventory", aliases=("inv", "boxes"))
    async def inventory(self, ctx: PoketwoContext):
        """See how many tickets and boxes you have"""

        member = await self.bot.mongo.fetch_member_info(ctx.author)

        embed = self.bot.Embed(
            title=f"Your Inventory",
            description=dedent(
                f"""
                As you catch pokémon in the wild, you will earn {FlavorStrings.ticket:sb}. You can use these tickets to play {FlavorStrings.minisport:s} and earn points for your team, {FlavorStrings.pokecoins:!e} and {FlavorStrings.box:s} containing various rewards!

                The more points you earn in a {FlavorStrings.minisport} game, the more {FlavorStrings.pokecoins:!e} and higher tier boxes with better rewards you will earn!
                """
            ),
        )
        embed.set_author(name=str(ctx.author), icon_url=ctx.author.display_avatar.url)

        embed.add_field(
            name="Inventory",
            value="\n".join(
                [
                    f"{FlavorStrings.ticket:sb}: {member[f'{SUMMER_PREFIX}_tickets']:,}",
                    f"-# Use `{ctx.clean_prefix}{self.play.qualified_name} {self.play.signature}` to play {FlavorStrings.minisport:s} using tickets",
                    "",
                    *[f"**{box} Boxes**: {member[f'{SUMMER_PREFIX}_boxes'].get(box.name, 0):,}" for box in Box],
                    f"-# Use `{ctx.clean_prefix}{self.open.qualified_name} {self.open.signature}` to open your boxes",
                ]
            ),
        )

        await ctx.reply(embed=embed, mention_author=False)

    @checks.has_started()
    @olympics.command(name="open", aliases=("o",))
    async def open(
        self,
        ctx: PoketwoContext,
        box: EnumConverter(Box) = None,
        qty: Optional[int] = 1,
    ):
        """Open boxes for rewards"""

        if not box:
            return await ctx.invoke(self.inventory)

        if qty <= 0:
            return await ctx.send(f"Nice try...")

        if qty > 15:
            return await ctx.send(f"You can only open up to 15 boxes at once!")

        member = await self.bot.mongo.fetch_member_info(ctx.author)
        boxes = member.summer_2024_boxes

        if qty > boxes.get(box.name, 0):
            return await ctx.send(f"You don't have enough {box} boxes!")

        await self.bot.mongo.update_member(ctx.author, {"$inc": {f"{SUMMER_PREFIX}_boxes.{box.name}": -qty}})

        embed = self.bot.Embed(
            title=f"You open {qty} {box} Box{'' if qty == 1 else 'es'}...",
            description=None,
        )
        embed.set_author(name=str(ctx.author), icon_url=ctx.author.display_avatar.url)

        rewards_text = await give_rewards(self.bot, ctx.author, qty, rewards=box.rewards)
        embed.description = rewards_text

        await ctx.reply(embed=embed, mention_author=False)

    # region Gaining Olympic Tickets
    @commands.Cog.listener(name="on_catch")
    async def drop_ticket(self, ctx: PoketwoContext, species: Species, _id: int):
        count = await self.bot.redis.hincrby(f"{SUMMER_PREFIX}_catch_count", ctx.author.id, 1)
        if count >= REQUIRED_CATCHES:
            await self.bot.mongo.update_member(
                ctx.author, {"$inc": {f"{SUMMER_PREFIX}_tickets": 1, f"{SUMMER_PREFIX}_tickets_total": 1}}
            )
            await self.bot.redis.hdel(f"{SUMMER_PREFIX}_catch_count", ctx.author.id)

            await ctx.send(
                f"You've earned an {FlavorStrings.ticket:b}! Use `{ctx.clean_prefix}{self.play.qualified_name}` or the event menu to play a {FlavorStrings.minisport}."
            )

    # region Debug
    @checks.is_developer()
    @olympics.group(name="debug", aliases=("dev",), invoke_without_command=True)
    async def debug(
        self,
        ctx: PoketwoContext,
    ):
        """Dev-only command for debugging purposes"""

        return await ctx.send_help(self.debug)

    @checks.is_developer()
    @debug.command(name="simulate-boxes")
    async def simulate_boxes(
        self,
        ctx: PoketwoContext,
        qty: Optional[int] = 1,
    ):
        """Dev-only command to simulate box openings"""

        embeds = []
        for box in Box:
            embed = self.bot.Embed(
                title=f"Simulating {qty:,} {box} Box{'' if qty == 1 else 'es'}...",
                description=None,
            )
            embed.set_author(name=str(ctx.author), icon_url=ctx.author.display_avatar.url)

            rewards_text = simulate_rewards(self.bot, qty, rewards=box.rewards)
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
    @give.command(name="tickets", aliases=("ticket",))
    async def give_tickets(
        self,
        ctx: PoketwoContext,
        user: Optional[discord.Member] = commands.Author,
        qty: Optional[int] = 1,
    ):
        """Dev-only command to give tickets for debugging purposes"""

        await self.bot.mongo.update_member(user, {"$inc": {f"{SUMMER_PREFIX}_tickets": qty}})
        await ctx.send(f"Gave {qty}x {FlavorStrings.ticket:s} to **{user}**.")

    @checks.is_developer()
    @give.command(name="boxes", aliases=("box",))
    async def give_boxes(
        self,
        ctx: PoketwoContext,
        user: Optional[discord.Member] = commands.Author,
        qty: Optional[int] = 1,
    ):
        """Dev-only command to give boxes for debugging purposes"""

        await self.bot.mongo.update_member(user, {"$inc": {f"{SUMMER_PREFIX}_boxes.{box.name}": qty for box in Box}})
        await ctx.send(f"Gave {qty}x of all boxes to **{user}**.")

    @checks.is_developer()
    @give.command(name="points", aliases=("point",))
    async def give_points(
        self,
        ctx: PoketwoContext,
        user: Optional[discord.Member] = commands.Author,
        minisport: EnumConverter(Minisport) = Minisport.ARCHERY,
        team: Optional[str] = None,
        qty: Optional[int] = 1,
    ):
        """Dev-only command to give points for debugging purposes"""

        member = await self.bot.mongo.fetch_member_info(user)
        team = Team.from_name(team or member[f"{SUMMER_PREFIX}_team"])

        await ctx.bot.mongo.update_member(user, {"$inc": {f"{SUMMER_PREFIX}_points.{self.id}": qty}})
        await ctx.bot.mongo.db.counter.find_one_and_update(
            {"_id": STANDING_ID.format(minisport=self.id, team=team.name)},
            {"$inc": {"next": qty}},
            upsert=True,
        )

        await ctx.send(f"Added {qty} points for {minisport:b} to **{user}**'s team {team:b}.")


async def setup(bot: commands.Bot):
    await bot.add_cog(Summer(bot))
