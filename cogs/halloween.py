import random

from discord.ext import commands
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

    # fmt: off

    @cached_property
    def pools(self):
        return {
            "special": (10027, 10028, 10029, 10030, 10031, 10032, 10143),
            "rare": (144, 145, 146, 150, 243, 244, 245, 249, 250, 377, 378, 379, 380, 381, 382, 383, 384, 480, 481, 482, 483, 484, 485, 486, 487, 488, 638, 639, 640, 641, 642, 643, 644, 645, 646, 716, 717, 718, 772, 773, 785, 786, 787, 788, 789, 790, 791, 792, 800, 10118, 10120, 151, 251, 385, 386, 489, 490, 491, 492, 493, 494, 647, 648, 649, 719, 720, 721, 801, 802, 807, 808, 809, 10001, 10002, 10003, 144, 145, 146, 150, 243, 244, 245, 249, 250, 377, 378, 379, 380, 381, 382, 383, 384, 480, 481, 482, 483, 484, 485, 486, 487, 488, 638, 639, 640, 641, 642, 643, 644, 645, 646, 716, 717, 718, 772, 773, 785, 786, 787, 788, 789, 790, 791, 792, 800, 10118, 10120, 151, 251, 385, 386, 489, 490, 491, 492, 493, 494, 647, 648, 649, 719, 720, 721, 801, 802, 807, 808, 809, 10001, 10002, 10003, 793, 794, 795, 796, 797, 798, 799, 803, 804, 805, 806),
            "spooky": (92, 93, 94, 200, 292, 302, 353, 354, 355, 356, 425, 426, 429, 442, 477, 478, 479, 487, 562, 563, 592, 593, 607, 608, 609, 622, 623, 679, 680, 681, 708, 709, 710, 711, 720, 724, 769, 770, 778, 781, 792, 802, 806, 10115, 10125, 197, 198, 215, 228, 229, 248, 261, 262, 274, 275, 302, 318, 319, 332, 342, 359, 430, 434, 435, 442, 452, 461, 491, 509, 510, 551, 552, 553, 559, 560, 570, 571, 624, 625, 629, 630, 633, 634, 635, 658, 675, 686, 687, 717, 727, 799, 10091, 10092, 10107, 10108, 10112, 10113),
            "shadow_lugia": (50001,),
        }

    # fmt: on

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

    @checks.has_started()
    @commands.group(aliases=("event",), invoke_without_command=True, case_insensitive=True)
    async def halloween(self, ctx):
        """View halloween event information."""

        member = await self.bot.mongo.fetch_member_info(ctx.author)

        embed = self.bot.Embed(color=0x9CCFFF)
        embed.title = f"Spooktober Event Shop"
        embed.description = "The event has ended, and the shop will be available until November 7."
        embed.add_field(
            name=f"{self.bot.sprites.candy_halloween} Candies — {member.halloween_tickets}",
            value=f"Spend your candies in the event shop using below.",
            inline=False,
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
    async def buy(self, ctx, *args):
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
                return await ctx.send("Please specify a pokémon to buy embed colors for.")
            pokemon = await converters.PokemonConverter().convert(ctx, arg2)
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
            message = f"You bought custom embed colors for your **{pokemon:ls}** for **{item['price']} candies**. Use it with `{ctx.prefix}embedcolor <pokemon #> <hex color>`."

        elif item["action"] == "shadow_lugia":
            ivs = [mongo.random_iv() for i in range(6)]
            await self.bot.mongo.db.pokemon.insert_one(
                {
                    "owner_id": ctx.author.id,
                    "species_id": 50001,
                    "level": min(max(int(random.normalvariate(20, 10)), 1), 100),
                    "xp": 0,
                    "nature": mongo.random_nature(),
                    "iv_hp": ivs[0],
                    "iv_atk": ivs[1],
                    "iv_defn": ivs[2],
                    "iv_satk": ivs[3],
                    "iv_sdef": ivs[4],
                    "iv_spd": ivs[5],
                    "iv_total": sum(ivs),
                    "shiny": member.determine_shiny(self.bot.data.species_by_number(50001)),
                    "idx": await self.bot.mongo.fetch_next_idx(ctx.author),
                }
            )
            message += f" Use `{ctx.prefix}info latest` to view it!"

        elif item["action"] == "badge":
            await self.bot.mongo.update_member(ctx.author, {"$set": {"halloween_badge": True}})

        elif item["action"] == "crate":
            reward = random.choices(*CRATE_REWARDS, k=1)[0]
            shards = round(random.normalvariate(10, 3))
            text = [f"{shards} Shards"]

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

                if reward in ("spooky", "special"):
                    total = 142 + int(abs(random.normalvariate(0, 9)))
                    ivs = [0, 0, 0, 0, 0, 0]
                    for i in range(total):
                        idx = random.randrange(6)
                        while ivs[idx] >= 31:
                            idx = random.randrange(6)
                        ivs[idx] += 1
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

            await self.bot.mongo.update_member(ctx.author, {"$inc": {"premium_balance": shards}})

            embed = self.bot.Embed(color=0x9CCFFF)
            embed.title = "Opening Halloween Crate..."
            embed.add_field(name="Rewards Received", value="\n".join(text))

            return await ctx.send(embed=embed)

        await ctx.send(message)


def setup(bot):
    bot.add_cog(Halloween(bot))
