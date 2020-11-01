import math
import random
from collections import defaultdict

from discord.ext import commands
from discord.ext.commands.core import command
from discord.utils import cached_property
from helpers import checks, converters

from . import mongo

QUESTS = [
    {
        "event": "catch",
        "count": 20,
        "condition": {"type": "Ghost"},
        "description": "Catch 20 Ghost-type pokémon",
        "reward": 80,
    },
    {
        "event": "catch",
        "count": 20,
        "condition": {"type": "Dark"},
        "description": "Catch 20 Dark-type pokémon",
        "reward": 80,
    },
    {
        "event": "trade",
        "count": 5,
        "condition": {"type": "Ghost"},
        "description": "Trade 5 Ghost-type pokémon",
        "reward": 20,
    },
    {
        "event": "battle_start",
        "count": 1,
        "condition": {"type": "Dark"},
        "description": "Battle using a Dark-type pokémon",
        "reward": 20,
    },
    {
        "event": "market_buy",
        "count": 5,
        "condition": {"type": "Ghost"},
        "description": "Buy 5 Ghost-type pokémon on the market",
        "reward": 20,
    },
    {
        "event": "catch",
        "count": 5,
        "condition": {"id": 92},
        "description": "Catch 5 Gastly",
        "reward": 50,
    },
    {
        "event": "catch",
        "count": 5,
        "condition": {"id": 607},
        "description": "Catch 5 Litwick",
        "reward": 50,
    },
    {
        "event": "catch",
        "count": 5,
        "condition": {"id": 679},
        "description": "Catch 5 Honedge",
        "reward": 50,
    },
    {
        "event": "catch",
        "count": 5,
        "condition": {"id": 355},
        "description": "Catch 5 Duskull",
        "reward": 50,
    },
    {
        "event": "catch",
        "count": 1,
        "condition": {"id": 93},
        "description": "Catch a Haunter",
        "reward": 40,
    },
    {
        "event": "evolve",
        "count": 1,
        "condition": {"id": 93, "to": 94},
        "description": "Evolve Haunter to Gengar",
        "reward": 20,
    },
    {
        "event": "evolve",
        "count": 1,
        "condition": {"id": 94, "to": 10038},
        "description": "Evolve Gengar to Mega Gengar",
        "reward": 20,
    },
]

SHOP = [
    {
        "name": "Embed Color",
        "description": "Allows you to customize the embed color for one pokémon.\n`{}event buy Embed Color <pokemon #>`",
        "price": 10,
        "action": "embed_color",
    },
    {
        "name": "Halloween Crate",
        "description": "A crate containing a random reward.\n`{}event buy Halloween Crate`",
        "price": 30,
        "action": "crate",
    },
    {
        "name": "Shadow Lugia",
        "description": "Didn't catch one, or want another one? You can buy one here.\n`{}event buy Shadow Lugia`",
        "price": 750,
        "action": "shadow_lugia",
    },
    {
        "name": "Halloween Badge",
        "description": "If you didn't complete the quests, you can still buy the badge here.\n`{}event buy Halloween Badge`",
        "price": 300,
        "action": "badge",
    },
]


CRATE_REWARDS = {
    "shards": 20,
    "special": 30,
    "rare": 10,
    "shadow_lugia": 1.5,
    "spooky": 28.5,
    "redeem": 10,
}

CRATE_REWARDS = list(CRATE_REWARDS.keys()), list(CRATE_REWARDS.values())


class Halloween(commands.Cog):
    """Halloween event commands."""

    def __init__(self, bot):
        self.bot = bot

    @cached_property
    def pools(self):
        return {
            "special": (10027, 10028, 10029, 10030, 10031, 10032, 10143),
            "rare": [
                x
                for x in (
                    self.bot.data.list_legendary * 2
                    + self.bot.data.list_mythical * 2
                    + self.bot.data.list_ub
                )
                if x != 50001
            ],
            "spooky": (
                self.bot.data.list_type("Ghost") + self.bot.data.list_type("Dark")
            ),
            "shadow_lugia": (50001,),
        }

    async def get_quests(self, user):
        member = await self.bot.mongo.fetch_member_info(user)
        ret = []
        for idx, quest in enumerate(QUESTS):
            if not member.hquests.get(str(idx), False):
                q = quest.copy()
                q["id"] = idx
                q["progress"] = member.hquest_progress.get(str(idx), 0)
                q["slider"] = q["progress"] / q["count"]
                ret.append(q)
                if len(ret) >= 3:
                    return ret
        return ret

    def make_slider(self, progress):
        func = math.ceil if progress < 0.5 else math.floor
        bars = min(func(progress * 10), 10)
        first, last = bars > 0, bars == 10
        mid = bars - (1 if last else 0) - (1 if first else 0)

        ret = (
            self.bot.sprites.slider_start_full
            if first
            else self.bot.sprites.slider_start_empty
        )
        ret += mid * self.bot.sprites.slider_mid_full
        ret += (8 - mid) * self.bot.sprites.slider_mid_empty
        ret += (
            self.bot.sprites.slider_end_full
            if last
            else self.bot.sprites.slider_end_empty
        )

        return ret

    @checks.has_started()
    @commands.group(aliases=["event"], invoke_without_command=True)
    async def halloween(self, ctx: commands.Context):
        """View halloween event information."""

        member = await self.bot.mongo.fetch_member_info(ctx.author)

        embed = self.bot.Embed(color=0xE67D23)
        embed.title = f"Spooktober Event"
        embed.description = "It's spooky season! Join us this month to earn special rewards, including exclusive event pokémon!"
        # embed.set_thumbnail(url="https://i.imgur.com/3YB6ldP.png")
        embed.add_field(
            name=f"{self.bot.sprites.candy_halloween} Candies — {member.halloween_tickets}",
            value=(
                # f"**Your Candies:** {member.halloween_tickets}\n"
                "Earn candy by voting and completing tasks, and exchange them for rewards on Halloween!\n"
            ),
            inline=False,
        )

        quests = await self.get_quests(ctx.author)

        embed.add_field(
            name=f"{self.bot.sprites.quest_trophy} Quests",
            value="You have completed all currently available quests!"
            if len(quests) == 0
            else "Complete the following quests in order to earn more candy!",
            inline=False,
        )

        for q in quests:
            text = (
                f"{self.make_slider(q['slider'])} `{q['progress']}/{q['count']}`",
                f"**Reward:** {self.bot.sprites.candy_halloween} {q['reward']} candies",
            )
            if q["progress"] >= q["count"]:
                text += (
                    f"**Use `{ctx.prefix}halloween claim {q['id'] + 1}` to claim your reward.**",
                )
            embed.add_field(
                name=q["description"],
                value="\n".join(text),
                inline=False,
            )

        await ctx.send(embed=embed)

    @checks.has_started()
    @commands.max_concurrency(1, commands.BucketType.user)
    @halloween.command(aliases=["c"])
    async def claim(self, ctx: commands.Context, *, quest: int):
        quests = await self.get_quests(ctx.author)
        for q in quests:
            if q["id"] == quest - 1:
                if q["progress"] >= q["count"]:
                    await self.bot.mongo.update_member(
                        ctx.author,
                        {
                            "$set": {f"hquests.{q['id']}": True},
                            "$inc": {"halloween_tickets": q["reward"]},
                        },
                    )
                    return await ctx.send(
                        f"You have claimed **{q['reward']} Halloween Candies**."
                    )

        await ctx.send(f"You can't claim that reward!")

    @checks.has_started()
    @halloween.command()
    async def shop(self, ctx: commands.Context):
        """View the Halloween item shop."""

        member = await self.bot.mongo.fetch_member_info(ctx.author)

        embed = self.bot.Embed(color=0xE67D23)
        embed.title = f"Event Shop"

        embed.title += (
            f" — {self.bot.sprites.candy_halloween} {member.halloween_tickets} Candies"
        )

        embed.description = (
            "Use the candies you earned this month to buy some special items!"
        )

        for item in SHOP:
            embed.add_field(
                name=f"{item['name']} – {item['price']} candies",
                value=item["description"].format(ctx.prefix),
                inline=False,
            )

        await ctx.send(embed=embed)

    @checks.has_started()
    @commands.max_concurrency(1, commands.BucketType.user)
    @halloween.command()
    async def buy(self, ctx: commands.Context, *args):
        """Buy items from the Halloween shop."""

        member = await self.bot.mongo.fetch_member_info(ctx.author)

        arg2 = None
        if args[-1].isdigit():
            *args, arg2 = args
        item = " ".join(args).lower()

        try:
            item = next(x for x in SHOP if x["name"].lower() == item)
        except StopIteration:
            return await ctx.send("Couldn't find that item!")

        pokemon = None
        if item["action"] == "embed_color":
            if arg2 is None:
                return await ctx.send(
                    "Please specify a pokémon to buy embed colors for."
                )
            pokemon = await converters.Pokemon().convert(ctx, arg2)
            if pokemon is None:
                return await ctx.send("Couldn't find that pokémon!")
            if pokemon.has_color:
                return await ctx.send("That pokémon can already use embed colors!")
        elif item["action"] == "badge":
            quests = await self.get_quests(ctx.author)
            if member.halloween_badge or len(quests) == 0:
                return await ctx.send("You already have the halloween badge!")

        if member.halloween_tickets < item["price"]:
            return await ctx.send("You don't have enough candies to buy that!")

        await self.bot.mongo.update_member(
            ctx.author, {"$inc": {"halloween_tickets": -item["price"]}}
        )

        message = f"You bought a **{item['name']}** for **{item['price']} candies**."

        if item["action"] == "embed_color":
            await self.bot.mongo.update_pokemon(pokemon, {"$set": {"has_color": True}})
            message = f"You bought custom embed colors for your **{pokemon:ls}** for **{item['price']} candies**."

        elif item["action"] == "shadow_lugia":
            await self.bot.mongo.db.pokemon.insert_one(
                {
                    "owner_id": ctx.author.id,
                    "species_id": 50001,
                    "level": min(max(int(random.normalvariate(20, 10)), 1), 100),
                    "xp": 0,
                    "nature": mongo.random_nature(),
                    "iv_hp": mongo.random_iv(),
                    "iv_atk": mongo.random_iv(),
                    "iv_defn": mongo.random_iv(),
                    "iv_satk": mongo.random_iv(),
                    "iv_sdef": mongo.random_iv(),
                    "iv_spd": mongo.random_iv(),
                    "shiny": member.determine_shiny(
                        self.bot.data.species_by_number(50001)
                    ),
                    "idx": await self.bot.mongo.fetch_next_idx(ctx.author),
                }
            )
            message += f" Use `{ctx.prefix}info latest` to view it!"

        elif item["action"] == "badge":
            await self.bot.mongo.update_member(
                ctx.author, {"$set": {"halloween_badge": True}}
            )

        elif item["action"] == "crate":
            reward = random.choices(*CRATE_REWARDS, k=1)[0]
            shards = round(random.normalvariate(15, 5))
            text = [f"{shards} Shards"]

            print(reward)

            if reward == "shards":
                shards = round(random.normalvariate(50, 10))
                text = [f"{shards} Shards"]

            elif reward == "redeem":
                await self.bot.mongo.update_member(ctx.author, {"$inc": {"redeems": 1}})
                text.append("1 redeem")

            elif reward in ("special", "rare", "spooky", "shadow_lugia"):
                pool = self.pools[reward]

                species = random.choice(pool)
                species = self.bot.data.species_by_number(species)

                level = min(max(int(random.normalvariate(70, 10)), 1), 100)
                shiny = member.determine_shiny(species)

                if reward == "spooky":
                    total = 145 + int(abs(random.normalvariate(0, 10)))
                    pts = [random.choice(range(6)) for i in range(total)]
                    ivs = [pts.count(i) for i in range(6)]
                else:
                    ivs = [mongo.random_iv() for _ in range(6)]

                pokemon = {
                    "owner_id": ctx.author.id,
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
                    "shiny": shiny,
                    "idx": await self.bot.mongo.fetch_next_idx(ctx.author),
                }

                text.append(
                    f"{self.bot.mongo.Pokemon.build_from_mongo(pokemon):lni} ({sum(ivs) / 186:.2%} IV)"
                )

                await self.bot.mongo.db.pokemon.insert_one(pokemon)

            await self.bot.mongo.update_member(
                ctx.author, {"$inc": {"premium_balance": shards}}
            )

            embed = self.bot.Embed(color=0xE67D23)
            embed.title = "Opening Halloween Crate..."
            embed.add_field(name="Rewards Received", value="\n".join(text))

            return await ctx.send(embed=embed)

        await ctx.send(message)

    def verify_condition(self, condition, species, to=None):
        for k, v in condition.items():
            if k == "id" and species.id != v:
                return False
            elif k == "type" and v not in species.types:
                return False
            elif k == "to" and to.id != v:
                return False
        return True

    @commands.Cog.listener()
    async def on_catch(self, user, species):
        quests = await self.get_quests(user)
        incs = defaultdict(lambda: 0)
        for q in quests:
            if q["event"] != "catch":
                continue

            if self.verify_condition(q["condition"], species):
                incs[f"hquest_progress.{q['id']}"] += 1

        if len(incs) > 0:
            await self.bot.mongo.update_member(user, {"$inc": incs})

    @commands.Cog.listener()
    async def on_market_buy(self, user, listing):
        quests = await self.get_quests(user)
        incs = defaultdict(lambda: 0)
        for q in quests:
            if q["event"] != "market_buy":
                continue

            if self.verify_condition(
                q["condition"],
                self.bot.data.species_by_number(listing["pokemon"]["species_id"]),
            ):
                incs[f"hquest_progress.{q['id']}"] += 1

        if len(incs) > 0:
            await self.bot.mongo.update_member(user, {"$inc": incs})

    @commands.Cog.listener()
    async def on_trade(self, trade):
        a, b = trade["items"].keys()
        a = self.bot.get_user(a) or await self.bot.fetch_user(a)
        b = self.bot.get_user(b) or await self.bot.fetch_user(b)

        for user in (a, b):
            quests = await self.get_quests(user)
            incs = defaultdict(lambda: 0)
            for q in quests:
                if q["event"] != "trade":
                    continue

                for side in trade["items"].values():
                    for item in side:
                        if type(item) == int:
                            continue

                        if self.verify_condition(q["condition"], item.species):
                            incs[f"hquest_progress.{q['id']}"] += 1

            if len(incs) > 0:
                await self.bot.mongo.update_member(user, {"$inc": incs})

    @commands.Cog.listener()
    async def on_battle_start(self, battle):
        for trainer in battle.trainers:
            quests = await self.get_quests(trainer.user)
            incs = defaultdict(lambda: 0)
            for q in quests:
                if q["event"] != "battle_start":
                    continue

                for pokemon in trainer.pokemon:
                    if self.verify_condition(q["condition"], pokemon.species):
                        incs[f"hquest_progress.{q['id']}"] += 1

            if len(incs) > 0:
                await self.bot.mongo.update_member(trainer.user, {"$inc": incs})

    @commands.Cog.listener()
    async def on_evolve(self, user, pokemon, evo):
        quests = await self.get_quests(user)
        incs = defaultdict(lambda: 0)
        for q in quests:
            if q["event"] != "evolve":
                continue

            if self.verify_condition(q["condition"], pokemon.species, to=evo):
                incs[f"hquest_progress.{q['id']}"] += 1

        if len(incs) > 0:
            await self.bot.mongo.update_member(user, {"$inc": incs})


def setup(bot):
    bot.add_cog(Halloween(bot))
