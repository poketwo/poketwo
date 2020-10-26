import math
from collections import defaultdict

from discord.ext import commands
from discord.ext.commands.cooldowns import BucketType
from helpers import checks

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


class Halloween(commands.Cog):
    """Halloween event commands."""

    def __init__(self, bot):
        self.bot = bot

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
    @commands.max_concurrency(1, BucketType.user)
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
