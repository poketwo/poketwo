import random
from functools import cached_property

from discord.ext import commands, flags

from cogs import mongo
from helpers import checks, converters

CRATE_REWARDS = {
    "event": 50,
    "event2": 13,
    "redeem": 6.3,
    "shiny": 0.7,
    "shards": 15,
    "spooky": 0,
    "rare": 15,
}

CRATE_REWARDS = list(CRATE_REWARDS.keys()), list(CRATE_REWARDS.values())


class Halloween(commands.Cog):
    """Halloween event commands."""

    def __init__(self, bot):
        self.bot = bot

    @cached_property
    def pools(self):
        p = {
            "event": [50076, 50077, 50078],
            "event2": [50071, 50072, 50073, 50074, 50075],
            "spooky": [*set(self.bot.data.list_type("Ghost")) | set(self.bot.data.list_type("Dark"))],
            "rare": [
                *self.bot.data.list_legendary,
                *self.bot.data.list_mythical,
                *self.bot.data.list_ub,
            ],
            "shiny": self.bot.data.pokemon.keys(),
        }
        return {k: [self.bot.data.species_by_number(i) for i in v] for k, v in p.items()}

    @checks.has_started()
    @commands.group(aliases=("event",), invoke_without_command=True, case_insensitive=True)
    async def halloween(self, ctx):
        """View halloween event information."""

        member = await self.bot.mongo.fetch_member_info(ctx.author)
        count = await self.bot.mongo.db.counter.find_one({"_id": "halloween_2022"})
        count = count.get("next", 0) if count is not None else 0

        embed = self.bot.Embed(
            color=0xE67D23,
            title=f"Autumn & Halloween 2022 — 🎫 {member.halloween_tickets_2022}",
            description="These two weeks, some new Pokémon wearing new Autumn outfits have been spotted in the Pokétwo wilderness. What's more, there have been reports of spooky Halloween Pokémon roaming around as well. Join us in the Autumn & Halloween event for chances to obtain these new limited-time Event Pokémon!",
        )
        embed.add_field(
            name=f"Obtaining Trick-or-Treat Tickets",
            value=f"Some *spooky* entities have been searching for some Autumn Pokémon.... Offer any Autumn 2022 Pokémon you have with the `@Pokétwo halloween offer` command to receive trick-or-treat tickets!",
            inline=False,
        )
        embed.add_field(
            name="Using Trick-or-Treat Tickets",
            value=f"Use these tickets with the `@Pokétwo halloween trickortreat` command for a chance to receive limited-time Halloween Pokémon!",
            inline=False,
        )
        embed.add_field(
            name="Community Quest",
            value="If the community trick-or-treats 666,666 times, drop rates will be increased!\n"
            f"Current progress: {count}",
            inline=False,
        )

        await ctx.send(embed=embed)

    @commands.is_owner()
    @halloween.command(aliases=("giveticket", "at", "gt"))
    async def addticket(self, ctx, user: converters.FetchUserConverter, num: int = 1):
        """Give a ticket."""

        await self.bot.mongo.update_member(user, {"$inc": {"halloween_tickets_2022": num}})
        await ctx.send(f"Gave **{user}** {num} Trick-or-Treat tickets.")

    @checks.has_started()
    @checks.is_not_in_trade()
    @commands.max_concurrency(1, commands.BucketType.user)
    @halloween.command()
    async def offer(self, ctx, pokemon: commands.Greedy[converters.PokemonConverter]):
        """Offer pokémon to receive Trick-or-Treat Tickets!"""

        member = await self.bot.mongo.fetch_member_info(ctx.author)

        ids = set()
        mons = list()

        for pk in pokemon:
            if pk is not None:
                if pk.id in ids:
                    continue
                if pk.species.id not in (50071, 50072, 50073, 50074, 50075):
                    await ctx.send(
                        f"{pk.idx}: You can only offer Autumn 2022 pokémon! (Autumn Chikorita, Autumn Rapidash, Autumn Snivy, Autumn Pansage, Autumn Skiddo)"
                    )
                    continue
                if member.selected_id == pk.id:
                    await ctx.send(f"{pk.idx}: You can't offer your selected pokémon!")
                    continue
                if pk.favorite:
                    await ctx.send(f"{pk.idx}: You can't offer favorited pokémon!")
                    continue
                if pk.shiny:
                    await ctx.send(f"{pk.idx}: You can't offer shiny pokémon!")
                    continue
                ids.add(pk.id)
                mons.append(pk)

        if len(pokemon) != len(mons):
            await ctx.send(f"Couldn't find/offer {len(pokemon)-len(mons)} pokémon in this selection!")

        # Confirmation msg

        if len(mons) == 0:
            return await ctx.send_help(ctx.command)

        if len(mons) == 1:
            message = f"Are you sure you want to offer your {mons[0]:spl} No. {mons[0].idx}?"
        else:
            message = f"Are you sure you want to offer the following pokémon?\n\n" + "\n".join(
                f"{x:spl} ({x.idx})" for x in mons
            )

        result = await ctx.confirm(message)
        if result is None:
            return await ctx.send("Time's up. Aborted.")
        if result is False:
            return await ctx.send("Aborted.")

        if await self.bot.get_cog("Trading").is_in_trade(ctx.author):
            return await ctx.send("You can't do that in a trade!")

        # confirmed, offer

        result = await self.bot.mongo.db.pokemon.update_many(
            {"owner_id": ctx.author.id, "_id": {"$in": list(ids)}},
            {"$set": {"owned_by": "offered"}},
        )
        await self.bot.mongo.update_member(ctx.author, {"$inc": {"halloween_tickets_2022": result.modified_count}})
        await ctx.send(
            f"You offered {result.modified_count} pokémon. You received {result.modified_count:,} **🎫 Trick-or-Treat Tickets**!"
        )
        self.bot.dispatch("release", ctx.author, result.modified_count)

    # Filter
    @flags.add_flag("page", nargs="?", type=int, default=1)
    @flags.add_flag("--shiny", action="store_true")
    @flags.add_flag("--alolan", action="store_true")
    @flags.add_flag("--galarian", action="store_true")
    @flags.add_flag("--hisuian", action="store_true")
    @flags.add_flag("--paradox", action="store_true")
    @flags.add_flag("--mythical", action="store_true")
    @flags.add_flag("--legendary", action="store_true")
    @flags.add_flag("--ub", action="store_true")
    @flags.add_flag("--event", action="store_true")
    @flags.add_flag("--mega", action="store_true")
    @flags.add_flag("--embedcolor", "--ec", action="store_true")
    @flags.add_flag("--name", "--n", nargs="+", action="append")
    @flags.add_flag("--nickname", nargs="*", action="append")
    @flags.add_flag("--type", "--t", type=str, action="append")
    @flags.add_flag("--region", "--r", type=str, action="append")

    # IV
    @flags.add_flag("--level", nargs="+", action="append")
    @flags.add_flag("--hpiv", nargs="+", action="append")
    @flags.add_flag("--atkiv", nargs="+", action="append")
    @flags.add_flag("--defiv", nargs="+", action="append")
    @flags.add_flag("--spatkiv", nargs="+", action="append")
    @flags.add_flag("--spdefiv", nargs="+", action="append")
    @flags.add_flag("--spdiv", nargs="+", action="append")
    @flags.add_flag("--iv", nargs="+", action="append")

    # Duplicate IV's
    @flags.add_flag("--triple", "--three", type=int)
    @flags.add_flag("--quadruple", "--four", "--quadra", "--quad", "--tetra", type=int)
    @flags.add_flag("--pentuple", "--quintuple", "--penta", "--pent", "--five", type=int)
    @flags.add_flag("--hextuple", "--sextuple", "--hexa", "--hex", "--six", type=int)

    # Skip/limit
    @flags.add_flag("--skip", type=int)
    @flags.add_flag("--limit", type=int)

    # Offer all
    @checks.has_started()
    @checks.is_not_in_trade()
    @commands.max_concurrency(1, commands.BucketType.user)
    @commands.cooldown(1, 5, commands.BucketType.user)
    @halloween.command(cls=flags.FlagCommand)
    async def offerall(self, ctx, **flags):
        """Mass offer pokémon to receive Trick-or-treat tickets!"""

        member = await self.bot.mongo.fetch_member_info(ctx.author)
        aggregations = await self.bot.get_cog("Pokemon").create_filter(flags, ctx, order_by=member.order_by)

        if aggregations is None:
            return

        member = await self.bot.mongo.fetch_member_info(ctx.author)

        aggregations.extend(
            [
                {"$match": {"_id": {"$not": {"$eq": member.selected_id}}}},
                {"$match": {"species_id": {"$in": (50071, 50072, 50073, 50074, 50075)}}},
                {"$match": {"shiny": {"$not": {"$eq": True}}}},
                {"$match": {"favorite": {"$not": {"$eq": True}}}},
            ]
        )

        num = await self.bot.mongo.fetch_pokemon_count(ctx.author, aggregations=aggregations)

        if num == 0:
            return await ctx.send(
                "Found no Autumn 2022 pokémon matching this search (excluding favorited, selected, and shiny pokémon)."
            )

        # confirm

        result = await ctx.confirm(
            f"Are you sure you want to offer **{num} pokémon**? Favorited, selected, and shiny pokémon won't be offered."
        )
        if result is None:
            return await ctx.send("Time's up. Aborted.")
        if result is False:
            return await ctx.send("Aborted.")

        if await self.bot.get_cog("Trading").is_in_trade(ctx.author):
            return await ctx.send("You can't do that in a trade!")

        # confirmed, offer all

        num = await self.bot.mongo.fetch_pokemon_count(ctx.author, aggregations=aggregations)

        await ctx.send(f"Offering {num} pokémon, this might take a while...")

        pokemon = self.bot.mongo.fetch_pokemon_list(ctx.author, aggregations)

        result = await self.bot.mongo.db.pokemon.update_many(
            {"owner_id": ctx.author.id, "_id": {"$in": [x.id async for x in pokemon]}},
            {"$set": {"owned_by": "offered"}},
        )

        await self.bot.mongo.update_member(ctx.author, {"$inc": {"halloween_tickets_2022": result.modified_count}})

        await ctx.send(
            f"You have offered {result.modified_count} pokémon. You received {result.modified_count:,} **🎫 Trick-or-Treat Tickets**!"
        )
        self.bot.dispatch("release", ctx.author, result.modified_count)

    @checks.has_started()
    @commands.cooldown(1, 2, commands.BucketType.user)
    @commands.max_concurrency(1, commands.BucketType.user)
    @halloween.command(aliases=("tot", "tt", "open"))
    async def trickortreat(self, ctx, amount: int = 1):
        """Use a ticket to trick or treat."""

        member = await self.bot.mongo.fetch_member_info(ctx.author)

        if not 1 <= amount <= 15:
            return await ctx.send("You can only trick-or-treat 15 times at once!")

        if member.halloween_tickets_2022 < amount:
            return await ctx.send("You don't have enough tickets to do that!")

        await self.bot.mongo.update_member(
            ctx.author, {"$inc": {"halloween_trick_or_treats_2022": amount, "halloween_tickets_2022": -amount}}
        )
        await self.bot.mongo.db.counter.find_one_and_update(
            {"_id": "halloween_2022"}, {"$inc": {"next": amount}}, upsert=True
        )

        # Go

        update = {"$inc": {"premium_balance": 0, "balance": 0, "redeems": 0}}
        inserts = []
        text = []

        for reward in random.choices(*CRATE_REWARDS, k=amount):
            title = {
                "event": "**🍬 Treat!**",
                "event2": "**🍬 Treat!**",
                "redeem": "**🍬 Treat!**",
                "shiny": "**🍬 Treat!**",
                "shards": "**👻 Trick!**",
                "spooky": "**👻 Trick!**",
                "rare": "**👻 Trick!**",
            }[reward]

            if reward == "shards":
                shards = round(random.normalvariate(25, 10))
                update["$inc"]["premium_balance"] += shards
                text.append([title, f"{shards} Shards"])

            elif reward == "redeem":
                update["$inc"]["redeems"] += 1
                text.append([title, "1 redeem"])

            elif reward in ("event", "event2", "spooky", "rare", "shiny"):
                pool = [x for x in self.pools[reward] if x.catchable or reward in ("event", "event2")]
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

                text.append(
                    [title, f"{self.bot.mongo.Pokemon.build_from_mongo(pokemon):lni} ({sum(ivs) / 186:.2%} IV)"]
                )
                inserts.append(pokemon)

        await self.bot.mongo.update_member(ctx.author, update)
        if len(inserts) > 0:
            await self.bot.mongo.db.pokemon.insert_many(inserts)

        if len(text) == 1:
            embed = self.bot.Embed(title=text[0][0], description=text[0][1])
        else:
            embed = self.bot.Embed(
                title=f"Trick-or-Treated {amount} times...", description="\n".join("　".join(x) for x in text)
            )
        embed.set_author(icon_url=ctx.author.display_avatar.url, name=str(ctx.author))

        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Halloween(bot))
