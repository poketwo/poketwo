import random
from collections import defaultdict
from functools import cached_property

from discord.ext import commands
from helpers import checks, constants
from helpers.converters import FetchUserConverter
from helpers.utils import FakeUser

from cogs import mongo

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
        "count": (count := random.randint(20, 40)),
        "condition": {"region": region},
        "description": f"Catch {count} pokémon from the {region.title()} region",
    }


GUARANTEED_QUESTS = [
    lambda: {
        "event": "open_box",
        "count": 1,
        "description": "Open a voting box",
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

BOX_REWARDS = {
    "shards": 32,
    "event": 25,
    "pokecoins": 10,
    "rare": 10,
    "sunflora": 2,
    "shiny": 1,
    "redeem": 20,
}


class Anniversary(commands.Cog):
    """Anniversary event commands."""

    def __init__(self, bot):
        self.bot = bot

    @cached_property
    def pools(self):
        p = {
            "event": tuple(range(50059, 50064)),
            "sunflora": (50064,),
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
        quests = member.get("anniversary_quests")
        if quests is None:
            return quests
        for q in quests:
            if q["event"] == "open_box" and q["count"] > 1:
                q["count"] = 1
                q["description"] = "Open a voting box"
                break
        else:
            return quests
        await self.bot.mongo.update_member(user, {"$set": {"anniversary_quests": quests}})
        return quests

    async def make_quests(self, user):
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

    @checks.has_started()
    @commands.group(aliases=("event",), invoke_without_command=True, case_insensitive=True)
    async def anniversary(self, ctx: commands.Context):
        """View Anniversary event information."""

        await self.check_quests(ctx.author)

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

        embed = self.bot.Embed(
            title="Anniversary Bingo",
            description=f"Happy birthday, Pokétwo! \N{PARTY POPPER}\N{PARTY POPPER}\n\nTo celebrate, let's play bingo! Complete the following quests to earn **Anniversary Boxes**. Create Bingos to get even more rewards!\n\n{quests_text}",
        )
        embed.add_field(
            name=f"Anniversary Boxes — {member.get('anniversary_boxes', 0)}",
            value=f"You will receive an **Anniversary Box** for each quest you complete. Use `{ctx.prefix}anniversary open` to open boxes for rewards!",
            inline=False,
        )
        embed.add_field(
            name="Bingo Rewards",
            value=(
                "Create Bingos to receive extra rewards! A Bingo is a full row, column, or diagonal of quests completed (there are 12 Bingos per board).\n"
                "**Each Bingo:** On every Bingo, you will receive a box and **10,000 pokécoins**!\n"
                "**Third Bingo:** On your third Bingo, you will receive **Anniversary Sunflora**."
            ),
            inline=False,
        )
        reset_text = ""
        if member.get("bingos_awarded", 0) == 12:
            reset_text = f"\nYou have completed the whole board! If you would like to restart, type `{ctx.prefix}!anniversary reset` to get a fresh board and new quests."
        embed.add_field(
            name=f"Your Bingo Board (#{member.get('boards_completed', 0) + 1})",
            value=f"**# Bingos:** {member.get('bingos_awarded', 0)}{reset_text}\n\n" + self.generate_bingo_board(board),
            inline=False,
        )

        await ctx.send(embed=embed)

    @checks.has_started()
    @commands.max_concurrency(1, commands.BucketType.user)
    @anniversary.command()
    async def reset(self, ctx):
        """Reset your bingo board"""

        member = await self.bot.mongo.fetch_member_info(ctx.author)
        if member.bingos_awarded < 12:
            return await ctx.send("You must have a full board to do this!")

        result = await ctx.confirm("Are you sure you would like to reset your board? This cannot be undone.")
        if result is None:
            return await ctx.send("Time's up. Aborted.")
        if result is False:
            return await ctx.send("Aborted.")

        member = await self.bot.mongo.fetch_member_info(ctx.author)
        if member.bingos_awarded < 12:
            return await ctx.send("You must have a full board to do this!")

        quests = [{**x, "progress": 0} for x in self.generate_quests()]
        await self.bot.mongo.update_member(
            ctx.author, {"$set": {"anniversary_quests": quests, "bingos_awarded": 0}, "$inc": {"boards_completed": 1}}
        )

        await ctx.send("Your board has been reset.")

    @checks.has_started()
    @commands.max_concurrency(1, commands.BucketType.user)
    @anniversary.command(aliases=("o",))
    async def open(self, ctx, amt: int = 1):
        """Open a box"""

        if amt <= 0:
            return await ctx.send("Nice try...")

        if amt > 15:
            return await ctx.send("You can only open up to 15 anniversary boxes at once!")

        member = await self.bot.mongo.fetch_member_info(ctx.author)

        if member.anniversary_boxes < amt:
            return await ctx.send("You don't have enough boxes to do that!")

        await self.bot.mongo.update_member(
            ctx.author, {"$inc": {"anniversary_boxes": -amt, "anniversary_boxes_opened": amt}}
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
                shards = max(round(random.normalvariate(35, 10)), 2)
                update["$inc"]["premium_balance"] += shards
                text.append(f"{shards} Shards")

            elif reward == "pokecoins":
                pokecoins = max(round(random.normalvariate(3000, 500)), 800)
                update["$inc"]["balance"] += pokecoins
                text.append(f"{pokecoins} Pokécoins")

            elif reward == "redeem":
                update["$inc"]["redeems"] += 1
                text.append("1 redeem")

            elif reward in ("event", "sunflora", "rare", "shiny"):
                pool = [x for x in self.pools[reward] if x.catchable or reward == "sunflora"]
                species = random.choices(pool, weights=[x.abundance + 1 for x in pool], k=1)[0]
                level = min(max(int(random.normalvariate(30, 10)), 1), 100)
                shiny = reward == "shiny" or member.determine_shiny(species)
                ivs = [mongo.random_iv() for i in range(6)]

                pokemon = {
                    "owner_id": ctx.author.id,
                    "owned_by": "user",
                    "species_id": species.id,
                    "level": level,
                    "xp": 0,
                    "nature": mongo.random_nature(),
                    "iv_hp": ivs[0],
                    "iv_atk": ivs[1],
                    "iv_defn": ivs[2],
                    "iv_satk": ivs[3],
                    "iv_sdef": ivs[4],
                    "iv_spd": ivs[5],
                    "iv_total": sum(ivs),
                    "shiny": shiny,
                    "idx": await self.bot.mongo.fetch_next_idx(ctx.author),
                }
                added_pokemon.append(pokemon)
                text.append(f"{self.bot.mongo.Pokemon.build_from_mongo(pokemon):lni} ({sum(ivs) / 186:.2%} IV)")

        embed = self.bot.Embed(
            title=f"Opening {amt} Anniversary Box{'' if amt == 1 else 'es'}...",
        )
        embed.set_author(icon_url=ctx.author.display_avatar.url, name=str(ctx.author))
        embed.add_field(name="Rewards Received", value="\n".join(text))

        await self.bot.mongo.update_member(ctx.author, update)
        if len(added_pokemon) > 0:
            await self.bot.mongo.db.pokemon.insert_many(added_pokemon)
        await ctx.send(embed=embed)

    @commands.check_any(
        commands.is_owner(), commands.has_role(718006431231508481), commands.has_role(930346842586218607)
    )
    @anniversary.command(aliases=("givebox", "ab", "gb"))
    async def addbox(self, ctx, user: FetchUserConverter, num: int = 1):
        """Give a box."""

        await self.bot.mongo.update_member(user, {"$inc": {"anniversary_boxes": num}})
        await ctx.send(f"Gave **{user}** {num} Anniversary Boxes.")

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
        if quests is None:
            return
        incs = defaultdict(lambda: 0)
        for i, q in enumerate(quests):
            if q["event"] != "catch":
                continue

            if self.verify_condition(q.get("condition"), species):
                incs[f"anniversary_quests.{i}.progress"] += 1

        if len(incs) > 0:
            await self.bot.mongo.update_member(ctx.author, {"$inc": incs})

        await self.check_quests(ctx.author)

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
                incs[f"anniversary_quests.{i}.progress"] += 1

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
                incs[f"anniversary_quests.{i}.progress"] += 1

            if len(incs) > 0:
                await self.bot.mongo.update_member(user, {"$inc": incs})

            await self.check_quests(user)

    @commands.Cog.listener()
    async def on_battle_start(self, battle):
        for trainer in battle.trainers:
            quests = await self.get_quests(trainer.user)
            if quests is None:
                continue
            incs = defaultdict(lambda: 0)
            for i, q in enumerate(quests):
                if q["event"] != "battle_start":
                    continue

                for pokemon in trainer.pokemon:
                    if self.verify_condition(q.get("condition"), pokemon.species):
                        incs[f"anniversary_quests.{i}.progress"] += 1

            if len(incs) > 0:
                await self.bot.mongo.update_member(trainer.user, {"$inc": incs})

            await self.check_quests(trainer.user)

    @commands.Cog.listener()
    async def on_evolve(self, user, pokemon, evo):
        quests = await self.get_quests(user)
        if quests is None:
            return

        incs = defaultdict(lambda: 0)
        for i, q in enumerate(quests):
            if q["event"] != "evolve":
                continue
            incs[f"anniversary_quests.{i}.progress"] += 1

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

            incs[f"anniversary_quests.{i}.progress"] += count

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

            incs[f"anniversary_quests.{i}.progress"] += count

        if len(incs) > 0:
            await self.bot.mongo.update_member(user, {"$inc": incs})

        await self.check_quests(user)

    async def check_quests(self, user):
        quests = await self.get_quests(user)
        if quests is None:
            return

        for i, q in enumerate(quests):
            if q["progress"] >= q["count"] and not q.get("complete"):
                member = await self.bot.mongo.db.member.find_one_and_update(
                    {"_id": user.id, f"anniversary_quests.{i}.complete": {"$ne": True}},
                    {"$set": {f"anniversary_quests.{i}.complete": True}, "$inc": {"anniversary_boxes": 1}},
                )
                await self.bot.redis.hdel("db:member", user.id)
                if member is not None:
                    try:
                        await user.send(
                            f"You have completed Anniversary Quest {'ABCDE'[i % 5]}{i // 5 + 1} ({q['description']}) and received an **Anniversary Box**!"
                        )
                    except:
                        pass

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
            {"_id": user.id}, {"$set": {"bingos_awarded": bingos}}
        )
        await self.bot.redis.hdel("db:member", user.id)
        member_t = self.bot.mongo.Member.build_from_mongo(member)
        awarded = member.get("bingos_awarded", 0)

        incs = defaultdict(int)

        for i in range(awarded, bingos):
            incs["anniversary_boxes"] += 1
            incs["balance"] += 10000
            try:
                await user.send(
                    "You have completed a Bingo and received an **Anniversary Box** and **10,000 pokécoins**!"
                )
            except:
                pass
            if i == 2:
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
                try:
                    await user.send("Since this is your third Bingo, you have received an **Anniversary Sunflora**!")
                except:
                    pass

        if len(incs) > 0:
            await self.bot.mongo.update_member(user, {"$inc": incs})


async def setup(bot: commands.Bot):
    await bot.add_cog(Anniversary(bot))
