import random

import discord
from discord.ext import commands
from discord.utils import cached_property

from cogs import mongo
from helpers import checks
from helpers.converters import FetchUserConverter

CRATE_REWARDS = {
    "event": 50,
    "redeem": 4.5,
    "shiny": 0.5,
    "shards": 15,
    "spooky": 15,
    "rare": 10,
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
            "event": (50022, 50023, 50024, 50025, 50026, 50027, 50028, 50029, 50030, 50031),
            "spooky": [*set(self.bot.data.list_type("Ghost")) | set(self.bot.data.list_type("Dark"))],
            "rare": [
                *self.bot.data.list_legendary,
                *self.bot.data.list_mythical,
                *self.bot.data.list_ub,
            ],
            "shiny": self.bot.data.pokemon.keys(),
        }
        return {k: [self.bot.data.species_by_number(i) for i in v] for k, v in p.items()}

    # @commands.Cog.listener()
    # async def on_catch(self, ctx, species):
    #     if "Ghost" in species.types or "Dark" in species.types:
    #         if random.random() < 0.5:
    #             return
    #         await self.bot.mongo.update_member(ctx.author, {"$inc": {"halloween_tickets_2021": 1}})
    #         await ctx.send(
    #             f"The Pokémon dropped a **🎫 Trick-or-Treat Ticket**! Use `{ctx.clean_prefix}halloween` to view more info."
    #         )

    @checks.has_started()
    @commands.group(aliases=("event",), invoke_without_command=True, case_insensitive=True)
    async def halloween(self, ctx):
        """View halloween event information."""

        member = await self.bot.mongo.fetch_member_info(ctx.author)

        embed = self.bot.Embed(color=0xE67D23)
        embed.title = f"Halloween 2021"
        embed.add_field(
            name=f"Trick-or-Treat Tickets — 🎫 {member.halloween_tickets_2021}",
            value=
            # f"Every **Dark** or **Ghost** type Pokémon caught has a 50% chance of dropping a ticket! "
            f"Use these tickets with the `{ctx.clean_prefix}halloween trickortreat` command for the possibility of receiving an exclusive event Pokémon!",
            inline=False,
        )
        # embed.add_field(
        #     name="Voting Rewards",
        #     value="You can also receive up to two tickets per day by simply voting for us on Top.gg! Click the link below to learn more.",
        #     inline=False,
        # )
        embed.add_field(
            name="Halloween Badge",
            value="Trick-or-Treat 30 times to receive the <:_:903483536865103912> Halloween 2021 badge when the event ends.",
            inline=False,
        )

        view = discord.ui.View()
        view.add_item(discord.ui.Button(label="Visit Top.gg", url="https://top.gg/bot/716390085896962058/vote"))

        await ctx.send(embed=embed, view=view)

    @commands.is_owner()
    @halloween.command(aliases=("giveticket", "at", "gt"))
    async def addticket(self, ctx, user: FetchUserConverter, num: int = 1):
        """Give a ticket."""

        await self.bot.mongo.update_member(user, {"$inc": {"halloween_tickets_2021": num}})
        await ctx.send(f"Gave **{user}** {num} Trick-or-Treat tickets.")

    @checks.has_started()
    @commands.max_concurrency(1, commands.BucketType.user)
    @halloween.command(aliases=("tot", "tt", "open"))
    async def trickortreat(self, ctx):
        """Use a ticket to trick or treat."""

        member = await self.bot.mongo.fetch_member_info(ctx.author)

        if member.halloween_tickets_2021 <= 0:
            return await ctx.send("You don't have enough tickets to do that!")

        await self.bot.mongo.update_member(
            ctx.author, {"$inc": {"halloween_trick_or_treats": 1, "halloween_tickets_2021": -1}}
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

        elif reward in ("event", "spooky", "rare", "shiny"):
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

            text = f"{self.bot.mongo.Pokemon.build_from_mongo(pokemon):lni} ({sum(ivs) / 186:.2%} IV)"

            await self.bot.mongo.db.pokemon.insert_one(pokemon)

        else:
            text = "Nothing"

        embed = self.bot.Embed(title="🍬 Treat!" if reward == "event" else "👻 Trick!", description=text)
        embed.set_author(icon_url=ctx.author.display_avatar.url, name=str(ctx.author))

        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Halloween(bot))
