import random
from functools import cached_property

from discord.ext import commands
from helpers import checks, converters

from cogs import mongo

CRATE_REWARDS = {
    "event": 40,
    "event2": 20,
    "redeem": 4.5,
    "shiny": 0.5,
    "shards": 15,
    "spooky": 10,
    "rare": 5,
    "nothing": 5,
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

        embed = self.bot.Embed(color=0xE67D23)
        embed.title = f"Autumn & Halloween 2022 — 🎫 {member.halloween_tickets_2022}"
        embed.add_field(
            name=f"Obtaining Trick-or-Treat Tickets",
            value=f"Offer any Autumn 2022 Pokémon to the bot with the `@Pokétwo halloween offer` command to receive trick-or-treat tickets!",
            inline=False,
        )
        embed.add_field(
            name="Using Trick-or-treat Tickets",
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

    @commands.check_any(
        commands.is_owner(), commands.has_role(718006431231508481), commands.has_role(930346842586218607)
    )
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

        # confirmed, release

        result = await self.bot.mongo.db.pokemon.update_many(
            {"owner_id": ctx.author.id, "_id": {"$in": list(ids)}},
            {"$set": {"owned_by": "offered"}},
        )
        await self.bot.mongo.update_member(ctx.author, {"$inc": {"halloween_tickets_2022": result.modified_count}})
        await ctx.send(
            f"You offered {result.modified_count} pokémon. You received {result.modified_count:,} **🎫 Trick-or-Treat Tickets**!"
        )
        self.bot.dispatch("release", ctx.author, result.modified_count)

    @checks.has_started()
    @commands.max_concurrency(1, commands.BucketType.user)
    @halloween.command(aliases=("tot", "tt", "open"))
    async def trickortreat(self, ctx):
        """Use a ticket to trick or treat."""

        member = await self.bot.mongo.fetch_member_info(ctx.author)

        if member.halloween_tickets_2022 <= 0:
            return await ctx.send("You don't have enough tickets to do that!")

        await self.bot.mongo.update_member(
            ctx.author, {"$inc": {"halloween_trick_or_treats_2022": 1, "halloween_tickets_2022": -1}}
        )
        await self.bot.mongo.db.counter.find_one_and_update(
            {"_id": "halloween_2022"}, {"$inc": {"next": 1}}, upsert=True
        )

        # Go

        reward = random.choices(*CRATE_REWARDS, k=1)[0]

        if reward == "shards":
            shards = round(random.normalvariate(25, 10))
            await self.bot.mongo.update_member(ctx.author, {"$inc": {"premium_balance": shards}})
            text = f"{shards} Shards"

        elif reward == "redeem":
            await self.bot.mongo.update_member(ctx.author, {"$inc": {"redeems": 1}})
            text = "1 redeem"

        elif reward in ("event", "event2", "spooky", "rare", "shiny"):
            pool = [x for x in self.pools[reward] if x.catchable or reward in ("event", "event2")]
            print(reward, pool)
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

            text = f"{self.bot.mongo.Pokemon.build_from_mongo(pokemon):lni} ({sum(ivs) / 186:.2%} IV)"

            await self.bot.mongo.db.pokemon.insert_one(pokemon)

        else:
            text = "Nothing"

        embed = self.bot.Embed(
            title="🍬 Treat!" if reward in ("event", "event2", "shiny") else "👻 Trick!", description=text
        )
        embed.set_author(icon_url=ctx.author.display_avatar.url, name=str(ctx.author))

        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Halloween(bot))
