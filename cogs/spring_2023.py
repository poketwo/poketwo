import contextlib
import random
import typing
import uuid
from collections import Counter, defaultdict
from itertools import accumulate, zip_longest

import discord
from discord.ext import commands

from cogs import mongo

FLOWER_NAMES = {
    "flower_venusaur": "Venusaur Leaf",
    "flower_shaymin": "Shaymin Gracidea",
    "flower_lilligant": "Lilligant Lily",
    "flower_gossifleur": "Gossifleur Cotton Blossom",
    "flower_eldegoss": "Eldegoss Cotton Ball",
}

FLOWER_MAP = {
    "venusaur": "flower_venusaur",
    "leaf": "flower_venusaur",
    "venusaur leaf": "flower_venusaur",
    "shaymin": "flower_shaymin",
    "gracidea": "flower_shaymin",
    "shaymin gracidea": "flower_shaymin",
    "lilligant": "flower_lilligant",
    "lily": "flower_lilligant",
    "lilligant lily": "flower_lilligant",
    "gossifleur": "flower_gossifleur",
    "cotton blossom": "flower_gossifleur",
    "blossom": "flower_gossifleur",
    "gossifleur cotton blossom": "flower_gossifleur",
    "gossifleur blossom": "flower_gossifleur",
    "eldegoss": "flower_eldegoss",
    "cotton ball": "flower_eldegoss",
    "ball": "flower_eldegoss",
    "eldegoss cotton ball": "flower_eldegoss",
    "eldegoss ball": "flower_eldegoss",
}

DROP_CHANCES = {
    ("flower", "flower_venusaur"): 0.08,
    ("flower", "flower_eldegoss"): 0.04,
    ("flower", "flower_lilligant"): 0.03,
    ("flower", "flower_shaymin"): 0.03,
    ("flower", "flower_gossifleur"): 0.015,
    ("egg", 50096): 0.011,
    ("egg", 50098): 0.011,
    ("egg", 50092): 0.007,
    ("egg", 50093): 0.003,
}

DROPS = [*DROP_CHANCES.keys(), None]
DROP_WEIGHTS = [*accumulate(DROP_CHANCES.values()), 1]

BOUQUETS = {
    ("flower_eldegoss", "flower_gossifleur", "flower_lilligant"): 50099,
    ("flower_eldegoss", "flower_lilligant", "flower_venusaur"): 50091,
    ("flower_venusaur", "flower_venusaur", "flower_venusaur"): 50090,
    ("flower_gossifleur", "flower_gossifleur", "flower_gossifleur"): 50097,
    ("flower_eldegoss", "flower_lilligant", "flower_shaymin"): 50094,
    ("flower_eldegoss", "flower_venusaur", "flower_venusaur"): 50095,
}


def make_catch_type_quest(type):
    return lambda: {
        "event": "catch",
        "count": (count := random.randint(10, 20)),
        "condition": {"type": type},
        "description": f"Catch {count} {type}-type pokémon",
    }


SPECIALIZED_QUESTS = {
    50096: [
        lambda: {
            "event": "make_bouquet",
            "count": 1,
            "description": "Make a flower bouquet",
        },
        lambda: {
            "event": "market_buy",
            "condition": {"id": [184, 427, 50096, 428, 10088, 659, 660, 813, 814, 815, 10201]},
            "count": (count := random.randint(5, 10)),
            "description": f"Purchase {count} rabbit-like pokémon from the market",
        },
        lambda: {
            "event": "market_add",
            "condition": {"id": [184, 427, 50096, 428, 10088, 659, 660, 813, 814, 815, 10201]},
            "count": 1,
            "description": "List a rabbit-like pokémon on the market",
        },
        (
            BABY_POKEMON := lambda: {
                "event": "catch",
                "condition": {
                    # fmt: off
                "id": [172, 50067, 173, 174, 50012, 175, 50026, 236, 238, 239, 240, 298, 360, 406, 433, 438, 439, 440, 446, 447, 458, 848]
                    # fmt: on
                },
                "count": (count := random.randint(5, 10)),
                "description": f"Catch {count} baby pokémon",
            }
        ),
    ],
    50098: [
        lambda: {
            "event": "market_buy",
            "count": (count := random.randint(10, 20)),
            "description": f"Purchase {count} pokémon on the market",
        },
        lambda: {
            "event": "battle_start",
            "count": 1,
            "condition": {"type": "Grass"},
            "description": f"Battle using a Grass-type pokémon",
        },
        lambda: {
            "event": "release",
            "count": (count := random.randint(10, 20)),
            "description": f"Release {count} pokémon",
        },
        make_catch_type_quest("Grass"),
    ],
    50092: [
        lambda: {
            "event": "catch",
            "count": (count := random.randint(5, 10)),
            "condition": {"id": [81]},
            "description": f"Catch {count} magnemite",
        },
        lambda: {
            "event": "battle_win",
            "count": (count := random.randint(1, 3)),
            "description": f"Win a battle {count} times",
        },
    ],
    50093: [
        BABY_POKEMON,
        make_catch_type_quest("Normal"),
        lambda: {
            "event": "battle_start",
            "count": 1,
            "condition": {"type": "Normal"},
            "description": f"Battle using a Normal-type pokémon",
        },
    ],
}


QUESTS = [
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
    make_catch_type_quest("Fairy"),
    make_catch_type_quest("Psychic"),
    make_catch_type_quest("Normal"),
]


class BouquetButton(discord.ui.Button):
    def __init__(self, bot, flower):
        super().__init__(emoji=bot.sprites[flower])
        self.flower = flower

    async def callback(self, interaction):
        self.view.result.append(self.flower)
        if len(self.view.result) == 3:
            await interaction.response.edit_message(view=None, embed=self.view.build_embed())
            self.view.stop()
        else:
            await interaction.response.edit_message(embed=self.view.build_embed())


class BouquetView(discord.ui.View):
    def __init__(self, ctx, qty):
        super().__init__()
        self.ctx = ctx
        self.qty = qty
        self.result = []
        for flower in FLOWER_NAMES:
            self.add_item(BouquetButton(ctx.bot, flower))

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.red, row=1)
    async def cancel(self, interaction, button):
        self.result = []
        await interaction.response.edit_message(view=None)
        self.stop()

    def build_embed(self):
        return self.ctx.bot.Embed(
            title=f"Making {self.qty}× Flower Bouquet",
            description="\n".join(
                f"Flower {i}: Pick one!" if flower is None else f"Flower {i}: {self.ctx.bot.sprites[flower]}"
                for i, flower in zip_longest(range(1, 4), self.result)
            ),
        )

    async def interaction_check(self, interaction):
        if interaction.user.id not in {
            self.ctx.bot.owner_id,
            self.ctx.author.id,
            *self.ctx.bot.owner_ids,
        }:
            await interaction.response.send_message("You can't use this!", ephemeral=True)
            return False
        return True


class Spring(commands.Cog):
    """Spring 2023 commands."""

    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_catch(self, ctx, species):
        await self.on_quest_event(ctx.author, "catch", [species])

        match random.choices(DROPS, cum_weights=DROP_WEIGHTS, k=1)[0]:
            case None:
                return

            case "flower", flower:
                await self.bot.mongo.update_member(ctx.author, {"$inc": {f"spring_2023_{flower}": 1}})
                emoji = self.bot.sprites[flower]
                msg = f"The Pokémon dropped a **{emoji} {FLOWER_NAMES[flower]}**! Use `{ctx.clean_prefix}spring` to view more info."
                await ctx.send(msg)

            case "egg", species_id:
                possible_quests = [*QUESTS, *SPECIALIZED_QUESTS[species_id]]
                egg = {
                    **random.choice(possible_quests)(),
                    "_id": str(uuid.uuid4()),
                    "color": random.choice(["all", "blue", "green", "red", "yellow"]),
                    "species_id": species_id,
                    "progress": 0,
                }

                m = await self.bot.mongo.db.member.find_one_and_update(
                    {"_id": ctx.author.id, "spring_2023_eggs.4": {"$exists": False}},
                    {"$push": {f"spring_2023_eggs": egg}},
                )
                await self.bot.redis.hdel("db:member", ctx.author.id)
                if m is None:
                    return

                msg = f"The Pokémon dropped an **{self.egg_emoji(egg)} Easter Egg**! {egg['description']} to hatch it. Use `{ctx.clean_prefix}spring` to view more info."
                await ctx.send(msg)

    def egg_emoji(self, egg):
        idx = min(int(egg["progress"] / egg["count"] * 2) + 1, 3)
        return self.bot.sprites[f"egg_{egg['color']}_{idx}"]

    @commands.group(invoke_without_command=True, case_insensitive=True, aliases=("event",))
    async def spring(self, ctx):
        member = await self.bot.mongo.fetch_member_info(ctx.author)

        embed = self.bot.Embed(
            title="Spring & Easter 2023 🌱",
            description="It's Spring Time! Flowers are blooming, creating a perfect opportunity to create some beautiful bouquets. Maybe flower-arranging isn't your thing and you prefer finding hidden eggs within the vast landscape for a special gift! No matter what choice you prefer, there is always something for everyone.",
        )

        embed.add_field(
            name="Obtaining and Arranging Flowers",
            value="Look out for an assortment of flowers dropped while catching Pokémon. Arrange these flowers into bouquets to entice Spring Pokemon to come to you. Different Pokemon will prefer different flowers, so don't forget to make different bouquets in order to entice a variety of Spring Pokemon!",
            inline=False,
        )
        embed.add_field(
            name="Your Flower Inventory",
            value="\n".join(
                f"{getattr(member, f'spring_2023_{k}')}× {self.bot.sprites[k]} {v}" for k, v in FLOWER_NAMES.items()
            )
            + f"\nUse `{ctx.clean_prefix}spring bouquet` to make a bouquet!`",
            inline=False,
        )

        embed.add_field(
            name="Obtaining Easter Eggs",
            value="You can obtain eggs from catching Pokemon. Complete quests in order to hatch the eggs you have obtain and obtain Easter Pokemon.",
            inline=False,
        )
        if len(member.spring_2023_eggs) > 0:
            text = [
                f"{self.egg_emoji(x)} {x['description']} ({x['progress']}/{x['count']})"
                for x in member.spring_2023_eggs
            ]
            embed.add_field(name="Your Eggs", value="\n".join(text), inline=False)

        await ctx.send(embed=embed)

    @spring.command(rest_is_raw=True)
    async def bouquet(self, ctx, qty: typing.Optional[int] = 1, *, flowers: str):
        if qty < 1 <= 15:
            return await ctx.send("You can't make less than 1 or more than 15 bouquets.")

        if len(flowers) == 0:
            view = BouquetView(ctx, qty)
            await ctx.send(embed=view.build_embed(), view=view)
            await view.wait()

            if len(view.result) < 3:
                return await ctx.send("Aborted.")
            return await self.process_bouquet(ctx, view.result, qty=qty)

        flowers = flowers.split(",")
        if len(flowers) != 3:
            return await ctx.send("You must specify 3 flowers, separated by commas.")
        for f in flowers:
            if f.strip().casefold() not in FLOWER_MAP:
                return await ctx.send(
                    f"Invalid flower: {f}.\nPlease select between {', '.join(FLOWER_NAMES.values())}."
                )

        flowers = [FLOWER_MAP[f.strip().casefold()] for f in flowers]
        await self.process_bouquet(ctx, flowers, qty=qty)

    async def process_bouquet(self, ctx, flowers, *, qty=1):
        member = await self.bot.mongo.fetch_member_info(ctx.author)
        for k, v in Counter(flowers).items():
            if getattr(member, f"spring_2023_{k}") < v * qty:
                return await ctx.send(f"You don't have enough {self.bot.sprites[k]} to do that!")

        bouquet = "".join(self.bot.sprites[f] for f in flowers)

        try:
            species = self.bot.data.species_by_number(BOUQUETS[tuple(sorted(flowers))])
        except KeyError:
            return await ctx.send(
                f"You place down your bouquet of {bouquet} and wait...\n\nUnfortunately, nothing happens. Try a different combination!"
            )

        pokemon = []
        text = []

        start_idx = await self.bot.mongo.fetch_next_idx(ctx.author, reserve=qty)

        for idx in range(start_idx, start_idx + qty):
            level = min(max(int(random.normalvariate(30, 10)), 1), 100)
            shiny = member.determine_shiny(species, boost=16)
            ivs = [mongo.random_iv() for i in range(6)]

            p = {
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
                "idx": idx,
            }
            pokemon.append(p)
            text.append(f"{self.bot.mongo.Pokemon.build_from_mongo(p):lni} ({sum(ivs) / 186:.2%} IV)")

        await self.bot.mongo.db.pokemon.insert_many(pokemon)
        await self.bot.mongo.update_member(
            ctx.author, {"$inc": {f"spring_2023_{k}": -v * qty for k, v in Counter(flowers).items()}}
        )
        self.bot.dispatch("make_bouquet", ctx.author, flowers, qty)

        if qty == 1:
            msg = f"You place down your bouquet of {bouquet} and wait...\n\nYour bouquet attracts a **{text[0]}**!\n\nUse `@Pokétwo info latest` to view it."
        else:
            msg = (
                f"You place down {qty} bouquets of {bouquet} and wait...\n\nYour bouquet attracts some **{species}**! You have received:\n\n"
                + "\n".join(text)
            )

        await ctx.send(msg)

    def verify_condition(self, condition, species, to=None):
        if condition is not None:
            for k, v in condition.items():
                if k == "id" and species.id not in v:
                    return False
                elif k == "type" and v not in species.types:
                    return False
                elif k == "region" and v != species.region:
                    return False
                elif k == "to" and to.id != v:
                    return False
        return True

    async def on_quest_event(self, user, event, to_verify, *, count=1):
        member = await self.bot.mongo.fetch_member_info(user)
        if member is None:
            return

        for q in member.spring_2023_eggs:
            if "_id" not in q:
                await self.bot.mongo.update_member(user, {"$pull": {"spring_2023_eggs": {"_id": q["_id"]}}})
                continue

            if q["event"] != event:
                continue

            if len(to_verify) == 0 or any(self.verify_condition(q.get("condition"), x) for x in to_verify):
                self.bot.mongo.db.member.update_one(
                    {"_id": user.id, "spring_2023_eggs._id": q["_id"]},
                    {"$inc": {"spring_2023_eggs.$.progress": count}},
                )

        await self.bot.redis.hdel("db:member", user.id)
        await self.check_quests(user)

    async def check_quests(self, user):
        member = await self.bot.mongo.fetch_member_info(user)
        if member is None:
            return

        for q in member.spring_2023_eggs:
            if q["progress"] >= q["count"]:
                species = self.bot.data.species_by_number(q["species_id"])
                level = min(max(int(random.normalvariate(30, 10)), 1), 100)
                shiny = member.determine_shiny(species, boost=16)
                ivs = [mongo.random_iv() for i in range(6)]

                p = {
                    "owner_id": user.id,
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
                    "idx": await self.bot.mongo.fetch_next_idx(user),
                }

                await self.bot.mongo.update_member(user, {"$pull": {"spring_2023_eggs": {"_id": q["_id"]}}})
                await self.bot.mongo.db.pokemon.insert_one(p)

                with contextlib.suppress(discord.HTTPException):
                    msg = f"Your egg {self.egg_emoji(q)} has hatched! You haver received a **{self.bot.mongo.Pokemon.build_from_mongo(p):lni} ({sum(ivs) / 186:.2%} IV)**!"
                    await user.send(msg)

    @commands.Cog.listener()
    async def on_market_buy(self, user, pokemon):
        await self.on_quest_event(user, "market_buy", [self.bot.data.species_by_number(pokemon["species_id"])])

    @commands.Cog.listener()
    async def on_market_add(self, user, pokemon):
        await self.on_quest_event(user, "market_add", [self.bot.data.species_by_number(pokemon["species_id"])])

    @commands.Cog.listener()
    async def on_trade(self, trade):
        a, b = trade["users"]
        await self.on_quest_event(a, "trade", [])
        await self.on_quest_event(b, "trade", [])

    @commands.Cog.listener()
    async def on_battle_start(self, ba):
        await self.on_quest_event(ba.trainers[0].user, "battle_start", [x.species for x in ba.trainers[0].pokemon])
        await self.on_quest_event(ba.trainers[1].user, "battle_start", [x.species for x in ba.trainers[1].pokemon])

    @commands.Cog.listener()
    async def on_battle_win(self, _battle, winner):
        await self.on_quest_event(winner, "battle_win", [])

    @commands.Cog.listener()
    async def on_evolve(self, user, pokemon, evo):
        await self.on_quest_event(user, "evolve", [])

    @commands.Cog.listener()
    async def on_release(self, user, count):
        await self.on_quest_event(user, "release", [], count=count)

    @commands.Cog.listener()
    async def on_make_bouquet(self, user, flowers, qty):
        await self.on_quest_event(user, "make_bouquet", [], count=qty)


async def setup(bot: commands.Bot):
    await bot.add_cog(Spring(bot))
