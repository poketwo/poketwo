import math
from collections import defaultdict

from discord.ext import commands
from helpers import checks
from pymongo import ReturnDocument

name = lambda r: lambda c: f"Catch {c} pokémon originally found in the {r.title()} region."

CATCHING_TRACKS = {
    f"catch_region_{region}": {
        "event": "catch",
        "counts": [20, 50, 100, 200, 500],
        "condition": {"region": region},
        "description": name(region),
        "rewards": [2000, 5000, 10000, 20000, 50000],
        "final_reward": region,
    }
    for region in ("kanto", "johto", "hoenn", "sinnoh", "unova", "kalos", "alola", "galar")
}


class Quests(commands.Cog):
    """Quest commands."""

    def __init__(self, bot):
        self.bot = bot

    async def get_quests(self, user):
        member = await self.bot.mongo.fetch_member_info(user)
        quests = []
        for id, quest in CATCHING_TRACKS.items():
            prog = member.quest_progress.get(id, 0)
            try:
                idx = next(i for i, x in enumerate(quest["counts"]) if prog < x)
            except StopIteration:
                continue
            quests.append(
                {
                    **quest,
                    "_id": id,
                    "description": quest["description"](c := quest["counts"][idx]),
                    "progress": prog,
                    "slider": prog / c,
                    "next_count": c,
                    "next_reward": quest["rewards"][idx],
                    "next_is_last": idx == len(quest["rewards"]) - 1,
                }
            )
        return quests

    def make_slider(self, progress):
        func = math.ceil if progress < 0.5 else math.floor
        bars = min(func(progress * 10), 10)
        first, last = bars > 0, bars == 10
        mid = bars - (1 if last else 0) - (1 if first else 0)

        ret = self.bot.sprites.slider_start_full if first else self.bot.sprites.slider_start_empty
        ret += mid * self.bot.sprites.slider_mid_full
        ret += (8 - mid) * self.bot.sprites.slider_mid_empty
        ret += self.bot.sprites.slider_end_full if last else self.bot.sprites.slider_end_empty

        return ret

    @checks.has_started()
    @commands.group(aliases=["q"], invoke_without_command=True)
    async def quests(self, ctx: commands.Context):
        """View quests."""

        embed = self.bot.Embed(color=0xFE9AC9)
        embed.title = f"Quests"
        embed.description = "Complete these quests to earn special rewards!"

        quests = await self.get_quests(ctx.author)

        for q in quests:
            text = (
                f"{self.make_slider(q['slider'])} `{q['progress']}/{q['next_count']}`",
                f"**Reward:** {q['next_reward']:,} Pokécoins",
                # "**Duration:** Permanent",
            )
            embed.add_field(
                name=q["description"],
                value="\n".join(text),
                inline=False,
            )

        await ctx.send(embed=embed)

    def verify_condition(self, condition, species, to=None):
        for k, v in condition.items():
            if k == "id" and species.id != v:
                return False
            elif k == "type" and v not in species.types:
                return False
            elif k == "region" and species.region != v:
                return False
            elif k == "to" and to.id != v:
                return False
        return True

    @commands.Cog.listener()
    async def on_catch(self, ctx, species):
        quests = await self.get_quests(ctx.author)
        incs = defaultdict(lambda: 0)

        for q in quests:
            if q["event"] != "catch":
                continue
            if self.verify_condition(q["condition"], species):
                incs[f"quest_progress.{q['_id']}"] += 1

        if len(incs) == 0:
            return

        m = await self.bot.mongo.db.member.find_one_and_update(
            {"_id": ctx.author.id}, {"$inc": incs}, return_document=ReturnDocument.AFTER
        )
        await self.bot.redis.hdel(f"db:member", ctx.author.id)

        for q in quests:
            if "quest_progress." + q["_id"] not in incs:
                continue
            if m["quest_progress"][q["_id"]] == q["next_count"]:
                await self.bot.mongo.update_member(
                    ctx.author, {"$inc": {"balance": q["next_reward"]}}
                )
                await ctx.send(
                    f"You have completed the quest **{q['description']}** and received **{q['next_reward']:,}** Pokécoins!"
                )
                if q["next_is_last"]:
                    await self.bot.mongo.update_member(
                        ctx.author, {"$set": {f"badges.{q['final_reward']}": True}}
                    )
                    await ctx.send(
                        f"You have completed this quest track and received the **{q['final_reward'].title()}** badge!"
                    )


def setup(bot):
    bot.add_cog(Quests(bot))
