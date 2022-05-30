import random
from collections import defaultdict

from discord.ext import commands
from helpers import constants

TYPES = [
    "Normal",
    "Fighting",
    "Flying",
    "Poison",
    "Ground",
    "Rock",
    "Bug",
    "Ghost",
    "Steel",
    "Fire",
    "Water",
    "Grass",
    "Electric",
    "Psychic",
    "Ice",
    "Dragon",
    "Dark",
    "Fairy",
]

REGIONS = ("kanto", "johto", "hoenn", "sinnoh", "unova", "kalos", "alola", "galar")


def make_catch_type_quest(type):
    return lambda: {
        "event": "catch",
        "count": (count := random.randint(10, 20)),
        "condition": {"type": type},
        "description": f"Catch {count} {type}-type pokémon",
    }


def make_catch_region_quest(region):
    return lambda: {
        "event": "catch",
        "count": (count := random.randint(30, 50)),
        "condition": {"region": region},
        "description": f"Catch {count} pokémon from the {region.title()} region",
    }


GUARANTEED_QUESTS = [
    lambda: {
        "event": "open_box",
        "count": (count := random.randint(5, 8)),
        "description": f"Open {count} voting boxes",
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
        "event": "battle_start",
        "count": (count := random.randint(1, 3)),
        "description": f"Battle another player {count} times",
    },
    lambda: {
        "event": "market_buy",
        "count": (count := random.randint(10, 20)),
        "description": f"Purchase {count} pokémon on the market",
    },
]

POSSIBLE_QUESTS = [
    *[make_catch_type_quest(type) for type in TYPES],
    *[make_catch_region_quest(type) for type in REGIONS],
]


class Anniversary(commands.Cog):
    """Anniversary event commands."""

    def __init__(self, bot):
        self.bot = bot

    async def get_quests(self, user):
        member = await self.bot.mongo.db.member.find_one({"_id": user.id})
        if member.get("anniversary_quests"):
            return member["anniversary_quests"]
        quests = [{**x, "progress": 0} for x in self.generate_quests()]
        await self.bot.mongo.update_member(user, {"$set": {"anniversary_quests": quests}})
        return quests

    def generate_quests(self):
        quests = [
            *[x() for x in GUARANTEED_QUESTS],
            *[x() for x in random.sample(POSSIBLE_QUESTS, k=24 - len(GUARANTEED_QUESTS))],
        ]
        random.shuffle(quests)
        quests.insert(12, {"event": "free", "count": 0, "description": "Free Space"})
        return quests

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

        for i, row in enumerate(state):
            for j, cell in enumerate(row):
                board[i + 1].append(
                    self.bot.sprites.bingo_filled
                    if cell
                    else self.bot.sprites.bingo_blank_white
                    if (i + j) % 2 == 0
                    else self.bot.sprites.bingo_blank_gray
                )

        return "\n".join("".join(x) for x in board)

    @commands.command(aliases=("event",))
    async def anniversary(self, ctx: commands.Context):
        """View Anniversary event information."""

        member = await self.bot.mongo.db.member.find_one({"_id": ctx.author.id})

        quests = await self.get_quests(ctx.author)
        quests_state = [x["progress"] >= x["count"] for x in quests]
        quests_text = "\n".join(
            f"**{'ABCDE'[i % 5]}{i // 5 + 1}.** {x['description']} ({x['progress']}/{x['count']})"
            for i, x in enumerate(quests)
            if not quests_state[i]
        )
        board = [quests_state[i * 5 : i * 5 + 5] for i in range(5)]

        embed = self.bot.Embed(
            title="Anniversary Bingo",
            description=f"Happy birthday, Pokétwo! \N{PARTY POPPER}\N{PARTY POPPER}\n\nTo celebrate, let's play bingo! Complete the following quests to make Bingos and earn limited-time rewards. The more Bingos you make, the better the reward!\n\n{quests_text}",
        )
        embed.add_field(
            name="Bingo Rewards",
            value=(
                "**First Bingo:** 1 redeem, and, when the event ends, the **Second Anniversary** badge\n"
                "**Second Bingo:** 20,000 pokécoins\n"
                "**Third Bingo:** limited-time event Pokémon **Anniversary Sunflora**\n"
                "**Further Bingos:** 10,000 pokécoins per Bingo"
            ),
            inline=False,
        )
        embed.add_field(
            name="Your Bingo Board",
            value=f"**# Bingos:** {member.get('bingos_awarded', 0)}\n\n" + self.generate_bingo_board(board),
            inline=False,
        )

        await ctx.send(embed=embed)

    def verify_condition(self, condition, species, to=None):
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
        return True

    @commands.Cog.listener()
    async def on_catch(self, ctx, species):
        quests = await self.get_quests(ctx.author)
        incs = defaultdict(lambda: 0)
        for i, q in enumerate(quests):
            if q["event"] != "catch":
                continue

            if self.verify_condition(q.get("condition"), species):
                incs[f"anniversary_quests.{i}.progress"] += 1

        if len(incs) > 0:
            await self.bot.mongo.update_member(ctx.author, {"$inc": incs})

        await self.check_bingos(ctx.author)

    @commands.Cog.listener()
    async def on_market_buy(self, user, listing):
        quests = await self.get_quests(user)
        incs = defaultdict(lambda: 0)
        for i, q in enumerate(quests):
            if q["event"] != "market_buy":
                continue

            if self.verify_condition(
                q.get("condition"),
                self.bot.data.species_by_number(listing["species_id"]),
            ):
                incs[f"anniversary_quests.{i}.progress"] += 1

        if len(incs) > 0:
            await self.bot.mongo.update_member(user, {"$inc": incs})

        await self.check_bingos(user)

    @commands.Cog.listener()
    async def on_trade(self, trade):
        a, b = trade["items"].keys()
        a = self.bot.get_user(a) or await self.bot.fetch_user(a)
        b = self.bot.get_user(b) or await self.bot.fetch_user(b)

        for user in (a, b):
            quests = await self.get_quests(user)
            incs = defaultdict(lambda: 0)
            for i, q in enumerate(quests):
                if q["event"] != "trade":
                    continue

                for side in trade["items"].values():
                    for item in side:
                        if type(item) == int:
                            continue

                        if self.verify_condition(q.get("condition"), item.species):
                            incs[f"anniversary_quests.{i}.progress"] += 1

            if len(incs) > 0:
                await self.bot.mongo.update_member(user, {"$inc": incs})

            await self.check_bingos(user)

    @commands.Cog.listener()
    async def on_battle_start(self, battle):
        for trainer in battle.trainers:
            quests = await self.get_quests(trainer.user)
            incs = defaultdict(lambda: 0)
            for i, q in enumerate(quests):
                if q["event"] != "battle_start":
                    continue

                for pokemon in trainer.pokemon:
                    if self.verify_condition(q.get("condition"), pokemon.species):
                        incs[f"anniversary_quests.{i}.progress"] += 1

            if len(incs) > 0:
                await self.bot.mongo.update_member(trainer.user, {"$inc": incs})

            await self.check_bingos(trainer.user)

    @commands.Cog.listener()
    async def on_evolve(self, user, pokemon, evo):
        quests = await self.get_quests(user)
        incs = defaultdict(lambda: 0)
        for i, q in enumerate(quests):
            if q["event"] != "evolve":
                continue

            if self.verify_condition(q.get("condition"), pokemon.species, to=evo):
                incs[f"anniversary_quests.{i}.progress"] += 1

        if len(incs) > 0:
            await self.bot.mongo.update_member(user, {"$inc": incs})

        await self.check_bingos(user)

    @commands.Cog.listener()
    async def on_release(self, user, count):
        quests = await self.get_quests(user)
        incs = defaultdict(lambda: 0)
        for i, q in enumerate(quests):
            if q["event"] != "release":
                continue

            incs[f"anniversary_quests.{i}.progress"] += count

        if len(incs) > 0:
            await self.bot.mongo.update_member(user, {"$inc": incs})

        await self.check_bingos(user)

    @commands.Cog.listener()
    async def on_open_box(self, user, count):
        quests = await self.get_quests(user)
        incs = defaultdict(lambda: 0)
        for i, q in enumerate(quests):
            if q["event"] != "open_box":
                continue

            incs[f"anniversary_quests.{i}.progress"] += count

        if len(incs) > 0:
            await self.bot.mongo.update_member(user, {"$inc": incs})

        await self.check_bingos(user)

    async def check_bingos(self, user):
        quests = await self.get_quests(user)
        quests_state = [x["progress"] >= x["count"] for x in quests]
        board = [quests_state[i * 5 : i * 5 + 5] for i in range(5)]

        bingos = 0
        for i in range(5):
            bingos += all(board[i])
            bingos += all(row[i] for row in board)
        bingos += all(board[i][i] for i in range(5))
        bingos += all(board[i][4 - i] for i in range(5))

        member = await self.bot.mongo.db.member.find_one({"_id": user.id})
        member_t = self.bot.mongo.Member.build_from_mongo(member)
        awarded = member.get("bingos_awarded", 0)

        incs = defaultdict(int)

        for i in range(awarded, bingos):
            if i == 0:
                incs["redeems"] += 1
                await user.send("You have completed a Bingo and received **1 redeem**!")
            elif i == 1:
                incs["balance"] += 20000
                await user.send("You have completed a Bingo and received **20,000 pokécoins**!")
            elif i == 2:
                ivs = [random.randint(0, 31) for i in range(6)]
                await self.bot.mongo.db.pokemon.insert_one(
                    {
                        "owner_id": user.id,
                        "owned_by": "user",
                        "species_id": 50064,
                        "level": max(1, min(int(random.normalvariate(20, 10)), 100)),
                        "xp": 0,
                        "nature": random.choice(constants.NATURES),
                        "iv_hp": ivs[0],
                        "iv_atk": ivs[1],
                        "iv_defn": ivs[2],
                        "iv_satk": ivs[3],
                        "iv_sdef": ivs[4],
                        "iv_spd": ivs[5],
                        "iv_total": sum(ivs),
                        "moves": [],
                        "shiny": member_t.determine_shiny(self.bot.data.species_by_number(50064)),
                        "idx": await self.bot.mongo.fetch_next_idx(user),
                    }
                )
                await user.send("You have completed a Bingo and received an **Anniversary Sunflora**!")
            else:
                incs["balance"] += 10000
                await user.send("You have completed a Bingo and received **10,000 pokécoins**!")

        if len(incs) > 0:
            await self.bot.mongo.update_member(user, {"$inc": incs, "$set": {"bingos_awarded": bingos}})


async def setup(bot: commands.Bot):
    await bot.add_cog(Anniversary(bot))
