import contextlib
import random
from functools import cached_property
from typing import List, Optional, Tuple

import discord
from discord.ext import commands
import random

from helpers import checks, constants
from helpers.converters import FetchUserConverter
from collections import defaultdict
from helpers.utils import unwind
from data.models import Species
from helpers.context import PoketwoContext

EASTER_PREFIX = "easter_2024_"

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
        "description": f"Catch {count} {type}-type pokémon",
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
        "description": f"Catch {count} {gender.title()} gender pokémon",
    }


GUARANTEED_QUESTS = [
    lambda: {
        "event": "catch",
        "count": (count := random.randint(40, 60)),
        "description": f"Catch {count} pokémon",
    },
    lambda: {
        "event": "trade",
        "count": (count := random.randint(3, 6)),
        "description": f"Trade with {count} people",
    },
    lambda: {
        "event": "evolve",
        "count": (count := random.randint(10, 15)),
        "description": f"Evolve {count} pokémon",
    },
    lambda: {
        "event": "release",
        "count": (count := random.randint(10, 20)),
        "description": f"Release {count} pokémon",
    },
    lambda: {
        "event": "market_buy",
        "count": (count := random.randint(250, 750)),
        "description": f"Spend {count} Pokécoins on the market",
    },
    lambda: {
        "event": "market_sell",
        "count": (count := random.randint(250, 500)),
        "description": f"Earn {count} Pokécoins from the market",
    },
]

POSSIBLE_QUESTS = [
    *[make_catch_type_quest(type) for type in TYPES],
    *[make_catch_region_quest(type) for type in REGIONS],
    *[make_catch_gender_quest(type) for type in GENDERS],
]

VOTE_BOX_QUEST_CHANCE = 0.5
VOTE_BOX_QUEST = [
    lambda: {
        "event": "open_box",
        "count": 1,
        "description": "Open a voting box",
    },
]

BOX_REWARDS = {
    "shards": 30,
    "event": 33,
    "pokecoins": 17,
    "rare": 10.8,
    "blackout-event": 2,
    "special-event": 4,
    "shiny": 0.2,
    "redeem": 3,
}

BINGOS_PER_BOARD = 12
BINGO_COMPLETION_PC = 5000


class Easter(commands.Cog):
    """Easter event commands."""

    def __init__(self, bot):
        self.bot = bot

    @cached_property
    def pools(self):
        p = {
            "event": (50164, 50166, 50167),
            "special-event": (50163,),
            "blackout-event": (50165,),
            "rare": [
                *self.bot.data.list_legendary,
                *self.bot.data.list_mythical,
                *self.bot.data.list_ub,
            ],
            "shiny": self.bot.data.pokemon.keys(),
        }
        return {k: [self.bot.data.species_by_number(i) for i in v] for k, v in p.items()}

    async def get_quests(self, user):
        member = await self.bot.mongo.db.member.find_one({"_id": user.id})
        quests = member.get(f"{EASTER_PREFIX}quests")
        if quests is None:
            return quests
        for q in quests:
            if q["event"] == "open_box" and q["count"] > 1:
                q["count"] = 1
                q["description"] = "Open a voting box"
                break
        else:
            return quests
        await self.bot.mongo.update_member(user, {"$set": {f"{EASTER_PREFIX}quests": quests}})
        return quests

    async def make_quests(self, user):
        quests = [{**x, "progress": 0} for x in self.generate_quests()]
        await self.bot.mongo.update_member(user, {"$set": {f"{EASTER_PREFIX}quests": quests}})
        return quests

    def generate_quests(self):
        vote_box_quest = VOTE_BOX_QUEST.copy()
        if random.random() >= VOTE_BOX_QUEST_CHANCE:
            vote_box_quest.clear()

        quests = [
            *[x() for x in GUARANTEED_QUESTS],
            *[x() for x in vote_box_quest],
            *[x() for x in random.sample(POSSIBLE_QUESTS, k=24 - len(GUARANTEED_QUESTS) - len(vote_box_quest))],
        ]
        random.shuffle(quests)
        quests.insert(12, {"event": "free", "count": 0, "description": "Free Space"})
        return quests

    def random_egg(self) -> Tuple[str, str]:
        color = random.choice(["all", "blue", "green", "red", "yellow"])
        return self.bot.sprites[f"egg_{color}_white"], self.bot.sprites[f"egg_{color}_gray"]

    def generate_bingo_board(self, state):
        board = [
            [
                self.bot.sprites.bingo_blank_white,
                self.bot.sprites.bingo_a,
                self.bot.sprites.bingo_b,
                self.bot.sprites.bingo_c,
                self.bot.sprites.bingo_d,
                self.bot.sprites.bingo_e,
            ],
            [self.bot.sprites.bingo_1],
            [self.bot.sprites.bingo_2],
            [self.bot.sprites.bingo_3],
            [self.bot.sprites.bingo_4],
            [self.bot.sprites.bingo_5],
        ]

        egg_emoji_white, egg_emoji_gray = self.random_egg()
        for i, row in enumerate(state):
            for j, cell in enumerate(row):
                even = (i + j) % 2 == 0
                egg_emoji = egg_emoji_white if even else egg_emoji_gray
                blank_emoji = self.bot.sprites.bingo_blank_white if even else self.bot.sprites.bingo_blank_gray

                board[i + 1].append(egg_emoji if cell else blank_emoji)

        return "\n".join("".join(x) for x in board)

    @checks.has_started()
    @commands.group(aliases=("event", "ev"), invoke_without_command=True, case_insensitive=True)
    async def easter(self, ctx: commands.Context):
        """View easter event information."""

        await self.check_quests(ctx.author, context=ctx)

        member = await self.bot.mongo.db.member.find_one({"_id": ctx.author.id})

        quests = await self.get_quests(ctx.author)
        if quests is None:
            quests = await self.make_quests(ctx.author)

        quests_state = [x["progress"] >= x["count"] for x in quests]
        quests_text = "\n".join(
            f"**{'ABCDE'[i % 5]}{i // 5 + 1}.** {x['description']} ({x['progress']}/{x['count']})"
            for i, x in enumerate(quests)
            if not quests_state[i]
        )
        board = [quests_state[i * 5 : i * 5 + 5] for i in range(5)]

        # TODO: ADD EVENT DESCRIPTION
        embed = self.bot.Embed(
            title="Easter Bingo",
            description=f"**The event has now ended. You may finish your existing Bingo card and open your Easter Eggs, but you can no longer get new ones!**\n\nHappy Easter everyone {self.bot.sprites.egg_red_1}! Complete the following quests to collect eggs on the bingo card and crack them open to get rewards. Get bingo's to get more rewards 👀\n\n{quests_text}",
        )
        embed.add_field(
            name=f"Easter Eggs — {member.get(f'{EASTER_PREFIX}boxes', 0):,}",
            value=f"Use `{ctx.clean_prefix}easter open` to open boxes for rewards!",
            inline=False,
        )
        third_bingo_pokemon = self.pools["special-event"][0]
        blackout_bingo_pokemon = self.pools["blackout-event"][0]
        embed.add_field(
            name="Bingo Rewards",
            value=(
                f"Create Bingos to receive extra rewards! A Bingo is a full row, column, or diagonal of quests completed (there are {BINGOS_PER_BOARD} Bingos per card).\n"
                f"**Each Bingo:** On every Bingo, you will receive a box and **{BINGO_COMPLETION_PC:,} pokécoins**!\n"
                f"**Third Bingo:** On your third Bingo, you will receive a **{third_bingo_pokemon}**.\n"
                f"**Blackout:** On every full bingo card, you will receive a **{blackout_bingo_pokemon}**."
            ),
            inline=False,
        )
        embed.add_field(
            name=f"Your bingo card (#{member.get(f'{EASTER_PREFIX}boards_completed', 0) + 1})",
            value=f"**Bingos:** {member.get(f'{EASTER_PREFIX}bingos_awarded', 0)}\n\n"
            + self.generate_bingo_board(board),
            inline=False,
        )

        if member.get(f"{EASTER_PREFIX}bingos_awarded", 0) == BINGOS_PER_BOARD:
            embed.set_footer(
                text=f"You have completed the whole card! If you would like to restart, type `{ctx.clean_prefix}easter reset` to get a fresh card and new quests."
            )

        await ctx.send(embed=embed)

    @checks.has_started()
    @commands.max_concurrency(1, commands.BucketType.user)
    @easter.command()
    async def reset(self, ctx):
        """Reset your bingo card"""

        return await ctx.send("The event has now ended, and you can no longer get new Bingo cards!")

        member = await self.bot.mongo.fetch_member_info(ctx.author)

        if member.easter_2024_bingos_awarded < BINGOS_PER_BOARD:
            return await ctx.send("You must have a full card to do this!")

        quests = [{**x, "progress": 0} for x in self.generate_quests()]
        await self.bot.mongo.update_member(
            ctx.author,
            {
                "$set": {f"{EASTER_PREFIX}quests": quests, f"{EASTER_PREFIX}bingos_awarded": 0},
                "$inc": {f"{EASTER_PREFIX}boards_completed": 1},
            },
        )

        await ctx.send("Your card has been reset.")

    @checks.has_started()
    @commands.max_concurrency(1, commands.BucketType.user)
    @easter.command(aliases=("o",))
    async def open(self, ctx, amt: int = 1):
        """Open a box"""

        if amt <= 0:
            return await ctx.send("Nice try...")

        if amt > 15:
            return await ctx.send("You can only open up to 15 Easter Eggs at once!")

        member = await self.bot.mongo.fetch_member_info(ctx.author)

        if member.easter_2024_boxes < amt:
            return await ctx.send("You don't have enough boxes to do that!")

        await self.bot.mongo.update_member(
            ctx.author, {"$inc": {f"{EASTER_PREFIX}boxes": -amt, "{EASTER_PREFIX}boxes_opened": amt}}
        )

        # Go

        rewards = random.choices(list(BOX_REWARDS.keys()), list(BOX_REWARDS.values()), k=amt)

        update = {
            "$inc": {"premium_balance": 0, "balance": 0, "redeems": 0},
        }
        text = []
        added_pokemon = []
        for reward in rewards:
            if reward == "shards":
                shards = random.randint(15, 55)
                update["$inc"]["premium_balance"] += shards
                text.append(f"{shards} Shards")

            elif reward == "pokecoins":
                pokecoins = random.randint(2000, 4000)
                update["$inc"]["balance"] += pokecoins
                text.append(f"{pokecoins} Pokécoins")

            elif reward == "redeem":
                update["$inc"]["redeems"] += 1
                text.append("1 redeem")

            elif reward in ("event", "special-event", "blackout-event"):
                pool = self.pools[reward]
                species = random.choice(pool)

                pokemon = await self.bot.mongo.make_pokemon(member, species)
                added_pokemon.append(pokemon)
                text.append(f"- {self.bot.mongo.Pokemon.build_from_mongo(pokemon):lPi}")

            elif reward in ("rare", "shiny"):
                pool = [x for x in self.pools[reward] if x.catchable]
                species = random.choices(pool, weights=[x.abundance + 1 for x in pool], k=1)[0]
                shiny = reward == "shiny" or member.determine_shiny(species)

                pokemon = await self.bot.mongo.make_pokemon(member, species, shiny=shiny)
                added_pokemon.append(pokemon)
                text.append(f"- {self.bot.mongo.Pokemon.build_from_mongo(pokemon):lPi}")

        embed = self.bot.Embed(
            title=f"Opening {amt} Easter Egg{'' if amt == 1 else 's'}...",
        )
        embed.set_author(icon_url=ctx.author.display_avatar.url, name=str(ctx.author))
        embed.add_field(name="Rewards Received", value="\n".join(text))

        await self.bot.mongo.update_member(ctx.author, update)
        if len(added_pokemon) > 0:
            await self.bot.mongo.db.pokemon.insert_many(added_pokemon)
        await ctx.send(embed=embed)

    @commands.is_owner()
    @easter.command(aliases=("givebox", "ab", "gb"))
    async def addbox(self, ctx, user: FetchUserConverter, num: int = 1):
        """Give a box."""

        await self.bot.mongo.update_member(user, {"$inc": {f"{EASTER_PREFIX}boxes": num}})
        await ctx.send(f"Gave **{user}** {num} Easter Eggs.")

    @commands.is_owner()
    @easter.group(invoke_without_command=True)
    async def debug(self, ctx):
        """Debugging command group."""

        return await ctx.send_help(ctx.command)

    @commands.is_owner()
    @debug.command()
    async def board(self, ctx, user: Optional[FetchUserConverter] = commands.Author):
        """Debugging command to complete board."""

        await self.bot.mongo.update_member(user, {"$set": {f"{EASTER_PREFIX}quests.$[].progress": 100}})
        await ctx.send(f"Completed **{user}**'s board.")

    @commands.is_owner()
    @debug.command(aliases=("q",))
    async def quests(self, ctx, user: Optional[FetchUserConverter] = commands.Author, number: Optional[int] = None):
        """Debugging command to reset or complete quests."""

        if number is None:
            # Reset
            await self.bot.mongo.update_member(
                user, {"$set": {f"{EASTER_PREFIX}quests": [{**x, "progress": 0} for x in self.generate_quests()]}}
            )
            return await ctx.send(f"Reset **{user}**'s quests.")

        quests = await self.get_quests(user)
        if quests is None:
            return

        n = 0
        for i, q in enumerate(quests):
            if not q.get("complete"):
                if n == number:
                    break
                m = await self.bot.mongo.db.member.update_one(
                    {"_id": user.id, f"{EASTER_PREFIX}quests.{i}.complete": {"$ne": True}},
                    {"$set": {f"{EASTER_PREFIX}quests.{i}.progress": q["count"]}},
                )
                n += 1
        else:
            return await ctx.send(f"Failed.")

        if m.modified_count:
            await self.bot.redis.hdel(f"db:member", user.id)
            await ctx.send(f"Completed {number} quest(s) of **{user}**.")
        else:
            await ctx.send(f"Failed.")

    def verify_condition(self, condition, species, pokemon, to=None):
        if condition is not None:
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

    @commands.Cog.listener("on_catch")
    async def on_catch(self, ctx: PoketwoContext, species: Species, idx: int):
        quests = await self.get_quests(ctx.author)
        if quests is None:
            return
        incs = defaultdict(lambda: 0)
        for i, q in enumerate(quests):
            if q["event"] != "catch":
                continue

            pokemon = await self.bot.mongo.fetch_pokemon(ctx.author, idx)
            if self.verify_condition(q.get("condition"), species, pokemon):
                incs[f"{EASTER_PREFIX}quests.{i}.progress"] += 1

        if len(incs) > 0:
            await self.bot.mongo.update_member(ctx.author, {"$inc": incs})

        await self.check_quests(ctx.author, context=ctx)

    @commands.Cog.listener()
    async def on_market_buy(self, user, listing):
        quests = await self.get_quests(user)
        if quests is None:
            return
        incs = defaultdict(lambda: 0)
        for i, q in enumerate(quests):
            if q["event"] != "market_buy":
                continue

            if self.verify_condition(
                q.get("condition"),
                self.bot.data.species_by_number(listing["species_id"]),
            ):
                incs[f"{EASTER_PREFIX}quests.{i}.progress"] += 1

        if len(incs) > 0:
            await self.bot.mongo.update_member(user, {"$inc": incs})

        await self.check_quests(user)

    @commands.Cog.listener()
    async def on_trade(self, trade):
        a, b = trade["users"]

        for user in (a, b):
            quests = await self.get_quests(user)
            if quests is None:
                continue

            incs = defaultdict(lambda: 0)
            for i, q in enumerate(quests):
                if q["event"] != "trade":
                    continue
                incs[f"{EASTER_PREFIX}quests.{i}.progress"] += 1

            if len(incs) > 0:
                await self.bot.mongo.update_member(user, {"$inc": incs})

            await self.check_quests(user)

    @commands.Cog.listener()
    async def on_evolve(self, user, pokemon, evo):
        quests = await self.get_quests(user)
        if quests is None:
            return

        incs = defaultdict(lambda: 0)
        for i, q in enumerate(quests):
            if q["event"] != "evolve":
                continue
            incs[f"{EASTER_PREFIX}quests.{i}.progress"] += 1

        if len(incs) > 0:
            await self.bot.mongo.update_member(user, {"$inc": incs})

        await self.check_quests(user)

    @commands.Cog.listener()
    async def on_release(self, user, count):
        quests = await self.get_quests(user)
        if quests is None:
            return

        incs = defaultdict(lambda: 0)
        for i, q in enumerate(quests):
            if q["event"] != "release":
                continue

            incs[f"{EASTER_PREFIX}quests.{i}.progress"] += count

        if len(incs) > 0:
            await self.bot.mongo.update_member(user, {"$inc": incs})

        await self.check_quests(user)

    @commands.Cog.listener()
    async def on_open_box(self, user, count):
        quests = await self.get_quests(user)
        if quests is None:
            return

        incs = defaultdict(lambda: 0)
        for i, q in enumerate(quests):
            if q["event"] != "open_box":
                continue

            incs[f"{EASTER_PREFIX}quests.{i}.progress"] += count

        if len(incs) > 0:
            await self.bot.mongo.update_member(user, {"$inc": incs})

        await self.check_quests(user)

    @commands.Cog.listener()
    async def on_market_buy(self, buyer, pokemon):
        price = pokemon["market_data"]["price"]

        # For buyer
        buyer_quests = await self.get_quests(buyer)
        if buyer_quests is not None:
            buyer_incs = defaultdict(lambda: 0)
            for i, q in enumerate(buyer_quests):
                if q["event"] == "market_buy":
                    buyer_incs[f"{EASTER_PREFIX}quests.{i}.progress"] += min((price, q["count"]))

            if len(buyer_incs) > 0:
                await self.bot.mongo.update_member(buyer, {"$inc": buyer_incs})

        await self.check_quests(buyer)

        # For seller
        seller = await self.bot.fetch_user(pokemon["owner_id"])
        seller_quests = await self.get_quests(seller)
        if seller_quests is not None:
            seller_incs = defaultdict(lambda: 0)
            for i, q in enumerate(seller_quests):
                if q["event"] == "market_sell":
                    seller_incs[f"{EASTER_PREFIX}quests.{i}.progress"] += min((price, q["count"]))

            if len(seller_incs) > 0:
                await self.bot.mongo.update_member(seller, {"$inc": seller_incs})

        await self.check_quests(seller)

    async def send_chunked_lines(self, user: discord.Member, lines: List[str]):
        max_lines = 10
        for chunk in discord.utils.as_chunks(lines, max_lines):
            with contextlib.suppress(discord.HTTPException):
                await user.send("\n".join(chunk))

    async def check_quests(self, user, context=None):
        quests = await self.get_quests(user)
        if quests is None:
            return

        messages = []
        for i, q in enumerate(quests):
            if q["progress"] >= q["count"] and not q.get("complete"):
                member = await self.bot.mongo.db.member.find_one_and_update(
                    {"_id": user.id, f"{EASTER_PREFIX}quests.{i}.complete": {"$ne": True}},
                    {"$set": {f"{EASTER_PREFIX}quests.{i}.complete": True}, "$inc": {f"{EASTER_PREFIX}boxes": 1}},
                )
                await self.bot.redis.hdel("db:member", user.id)
                if member is not None:
                    messages.append(
                        f"You have completed Easter Quest {'ABCDE'[i % 5]}{i // 5 + 1} ({q['description']}) and received an **Easter Egg**!"
                    )

        if context:
            for message in messages:
                await context.send(f"Congratulations {user.mention}! {message}")
        else:
            await self.send_chunked_lines(user, messages)
        await self.check_bingos(user)

    async def check_bingos(self, user):
        quests = await self.get_quests(user)
        if quests is None:
            return
        quests_state = [x["progress"] >= x["count"] for x in quests]
        board = [quests_state[i * 5 : i * 5 + 5] for i in range(5)]

        bingos = 0
        for i in range(5):
            bingos += all(board[i])
            bingos += all(row[i] for row in board)
        bingos += all(board[i][i] for i in range(5))
        bingos += all(board[i][4 - i] for i in range(5))

        member = await self.bot.mongo.db.member.find_one_and_update(
            {"_id": user.id}, {"$set": {f"{EASTER_PREFIX}bingos_awarded": bingos}}
        )
        await self.bot.redis.hdel("db:member", user.id)
        member_t = self.bot.mongo.Member.build_from_mongo(member)
        awarded = member.get(f"{EASTER_PREFIX}bingos_awarded", 0)

        incs = defaultdict(int)
        inserts = []

        messages = []
        for i in range(awarded, bingos):
            incs[f"{EASTER_PREFIX}boxes"] += 1
            incs["balance"] += BINGO_COMPLETION_PC
            with contextlib.suppress(discord.HTTPException):
                messages.append(
                    f"You have completed a Bingo and received an **Easter Egg** and **{BINGO_COMPLETION_PC:,} pokécoins**!"
                )

            if i == 2:
                third_bingo_pokemon = await self.bot.mongo.make_pokemon(member_t, self.pools["special-event"][0])
                inserts.append(third_bingo_pokemon)
                messages.append(
                    f"Since this is your third Bingo, you have received a **{self.bot.mongo.Pokemon.build_from_mongo(third_bingo_pokemon):Dx}**!"
                )

        if bingos == BINGOS_PER_BOARD and bingos > awarded:
            blackout_pokemon = await self.bot.mongo.make_pokemon(member_t, self.pools["blackout-event"][0])
            inserts.append(blackout_pokemon)
            messages.append(
                f"Since you've completed all bingos on your card, you have received a **{self.bot.mongo.Pokemon.build_from_mongo(blackout_pokemon):Dx}**!"
            )

        await self.send_chunked_lines(user, messages)

        if len(incs) > 0:
            await self.bot.mongo.update_member(user, {"$inc": incs})
        if inserts:
            await self.bot.mongo.db.pokemon.insert_many(inserts)


async def setup(bot: commands.Bot):
    await bot.add_cog(Easter(bot))
