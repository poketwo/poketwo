import random
from functools import cached_property

from discord.ext import commands

from cogs import mongo
from helpers import checks, converters

BOXES = {
    "random": "random",
    "pokemon": "pokemon",
    "currency": "currency",
    "event": "event",
    "r": "random",
    "p": "pokemon",
    "c": "currency",
    "e": "event",
}

NAMES = {
    "random": "Random Box",
    "pokemon": "Pokémon Box",
    "currency": "Currency Box",
    "event": "Event Box",
}

COSTS = {"random": 1, "pokemon": 4, "currency": 4, "event": 8}

CRATE_REWARDS = {
    "random": {
        "event": 10,
        "non-event": 40,
        "shards": 20,
        "pokecoins": 30,
    },
    "pokemon": {
        "event": 40,
        "shiny": 1,
        "rare": 9,
        "non-event": 50,
    },
    "currency": {
        "shards": 40,
        "pokecoins": 50,
        "redeem": 10,
    },
    "event": {
        "event": 100,
    },
}

CRATE_REWARDS = {k: (list(v.keys()), list(v.values())) for k, v in CRATE_REWARDS.items()}


class Christmas(commands.Cog):
    """Christmas event commands."""

    def __init__(self, bot):
        self.bot = bot

    @cached_property
    def pools(self):
        p = {
            "event": [50079, 50080, 50081, 50082, 50083, 50084, 50085, 50086],
            "non-event": self.bot.data.pokemon.keys(),
            "shiny": self.bot.data.pokemon.keys(),
            "rare": [
                *self.bot.data.list_legendary,
                *self.bot.data.list_mythical,
                *self.bot.data.list_ub,
            ],
        }
        return {k: [self.bot.data.species_by_number(i) for i in v] for k, v in p.items()}

    @commands.Cog.listener()
    async def on_catch(self, ctx, species):
        if random.random() < 0.05:
            await self.bot.mongo.update_member(ctx.author, {"$inc": {"christmas_coins_2022": 1}})
            await ctx.send(
                f"The Pokémon dropped a **🪙 Christmas Coin**! Use `{ctx.clean_prefix}christmas` to view more info."
            )

    @checks.has_started()
    @commands.group(aliases=("event",), invoke_without_command=True, case_insensitive=True)
    async def christmas(self, ctx):
        """View Christmas event information."""

        member = await self.bot.mongo.fetch_member_info(ctx.author)
        count = await self.bot.mongo.db.counter.find_one({"_id": "christmas_2022"})
        count = count.get("next", 0) if count is not None else 0

        embed = self.bot.Embed(
            color=0xE67D23,
            title=f"Christmas 2022 — 🪙 {member.christmas_coins_2022}",
            description="It's Christmas Eve, but unfortunately, somebody has hacked into Santa's workshop and stolen all his presents! Santa needs your help to raise enough money to recover his gifts and spread his holiday cheer.",
        )
        embed.add_field(
            name=f"Obtaining and Spending Coins",
            value=f"Look out for **🪙 Christmas Coins** dropped while catching Pokémon. Donate these coins to Santa by spending them at Santa's Shop. If the community donates a total of **200,000 coins**, then Santa will be able to get everyone presents!",
            inline=False,
        )
        embed.add_field(
            name="Santa's Shop",
            value="\n".join(
                (
                    "You can donate coins to Santa to receive different boxes:",
                    f"**Random Box** (1 coin) — `{ctx.clean_prefix}christmas buy random` — {member.christmas_boxes_2022_random}",
                    f"**Pokémon Box** (4 coins) — `{ctx.clean_prefix}christmas buy pokemon` — {member.christmas_boxes_2022_pokemon}",
                    f"**Currency Box** (4 coins) — `{ctx.clean_prefix}christmas buy currency` — {member.christmas_boxes_2022_currency}",
                    f"**Event Box** (8 coins) — `{ctx.clean_prefix}christmas buy event` — {member.christmas_boxes_2022_event}",
                )
            ),
            inline=False,
        )
        embed.add_field(name="Community Quest Progress", value=f"Current Progress: **🪙 {count:,}** / 200,000 ")

        await ctx.send(embed=embed)

    @commands.check_any(
        commands.is_owner(), commands.has_role(718006431231508481), commands.has_role(930346842586218607)
    )
    @christmas.command(aliases=("givecoin", "gc", "ac"))
    async def addcoin(self, ctx, user: converters.FetchUserConverter, num: int = 1):
        """Give a coin."""

        await self.bot.mongo.update_member(user, {"$inc": {"christmas_coins_2022": num}})
        await ctx.send(f"Gave **{user}** {num} Christmas Coins.")

    @checks.has_started()
    @checks.is_not_in_trade()
    @commands.max_concurrency(1, commands.BucketType.user)
    @christmas.command()
    async def buy(self, ctx, type, qty: int = 1):
        """Donate coins to receive boxes!"""

        if qty < 1:
            return await ctx.send("Nice try...")

        if type.lower() not in BOXES:
            return await ctx.send("Please type `random`, `pokemon`, `currency`, or `event`!")

        type = BOXES[type.lower()]
        member = await self.bot.mongo.fetch_member_info(ctx.author)

        if member.christmas_coins_2022 < COSTS[type] * qty:
            return await ctx.send("You don't have enough Christmas Coins for that!")

        if await self.bot.get_cog("Trading").is_in_trade(ctx.author):
            return await ctx.send("You can't do that in a trade!")

        # confirmed, offer

        await self.bot.mongo.update_member(
            ctx.author,
            {
                "$inc": {
                    "christmas_coins_2022": -COSTS[type] * qty,
                    f"christmas_boxes_2022_{type}": qty,
                }
            },
        )
        await self.bot.mongo.db.counter.find_one_and_update(
            {"_id": "christmas_2022"}, {"$inc": {"next": COSTS[type] * qty}}, upsert=True
        )
        await ctx.send(f"You purchased {qty}x **{NAMES[type]}** for 🪙 {COSTS[type] * qty}!")

    @checks.has_started()
    @commands.cooldown(1, 2, commands.BucketType.user)
    @commands.max_concurrency(1, commands.BucketType.user)
    @christmas.command()
    async def open(self, ctx, type, amount: int = 1):
        """Open a box."""

        if type.lower() not in BOXES:
            return await ctx.send("Please type `random`, `pokemon`, `currency`, or `event`!")

        type = BOXES[type.lower()]
        member = await self.bot.mongo.fetch_member_info(ctx.author)

        if not 1 <= amount <= 15:
            return await ctx.send("You can only open 15 boxes at once!")

        if getattr(member, f"christmas_boxes_2022_{type}") < amount:
            return await ctx.send("You don't have enough boxes to do that!")

        await self.bot.mongo.update_member(
            ctx.author,
            {"$inc": {f"christmas_boxes_2022_{type}_opened": amount, f"christmas_boxes_2022_{type}": -amount}},
        )

        # Go

        update = {"$inc": {"premium_balance": 0, "balance": 0, "redeems": 0}}
        inserts = []
        text = []

        for reward in random.choices(*CRATE_REWARDS[type], k=amount):
            if reward == "shards":
                shards = 35 + round(abs(random.normalvariate(0, 10)))
                if type == "random":
                    shards //= 2
                update["$inc"]["premium_balance"] += shards
                text.append(f"{shards} Shards")

            if reward == "pokecoins":
                shards = 3000 + round(abs(random.normalvariate(0, 2000)))
                update["$inc"]["balance"] += shards
                text.append(f"{shards} Pokécoins")

            elif reward == "redeem":
                update["$inc"]["redeems"] += 1
                text.append("1 redeem")

            elif reward in ("event", "non-event", "rare", "shiny"):
                pool = [x for x in self.pools[reward] if x.catchable or reward == "event"]
                species = random.choices(pool, weights=[x.abundance for x in pool], k=1)[0]
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

                text.append(f"{self.bot.mongo.Pokemon.build_from_mongo(pokemon):lni} ({sum(ivs) / 186:.2%} IV)")
                inserts.append(pokemon)

        await self.bot.mongo.update_member(ctx.author, update)
        if len(inserts) > 0:
            await self.bot.mongo.db.pokemon.insert_many(inserts)

        embed = self.bot.Embed(title=f"Opened {amount}x {NAMES[type]}...", description="\n".join(text))
        embed.set_author(icon_url=ctx.author.display_avatar.url, name=str(ctx.author))

        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Christmas(bot))
