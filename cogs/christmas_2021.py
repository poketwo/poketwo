import random

import discord
from discord.ext import commands
from discord.utils import cached_property
from helpers import checks
from helpers.converters import FetchUserConverter

from cogs import mongo

NAUGHTY = {
    "pokemon": 65,
    "pokecoins": 10,
    "shards": 10,
    "rare": 10,
    "nothing": 5,
}

NICE = {
    "event": 89,
    "redeem": 10,
    "shiny": 1,
}

NAUGHTY = list(NAUGHTY.keys()), list(NAUGHTY.values())
NICE = list(NICE.keys()), list(NICE.values())


class Christmas(commands.Cog):
    """Christmas event commands."""

    def __init__(self, bot):
        self.bot = bot

    @cached_property
    def pools(self):
        p = {
            "event": tuple(range(50033, 50048)),
            "pokemon": [
                *set(self.bot.data.list_type("Ice"))
                | set(self.bot.data.list_type("Fairy"))
                | set(self.bot.data.list_type("Rock"))
            ],
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
    #     if "Ice" in species.types and random.random() < 0.5:
    #         await self.bot.mongo.update_member(ctx.author, {"$inc": {"christmas_boxes_nice": 1}})
    #         await ctx.send(f"The Pokémon dropped a 🎁 **Nice Box**! Use `{ctx.prefix}event` to view more info.")
    #     if "Rock" in species.types and random.random() < 0.35:
    #         await self.bot.mongo.update_member(ctx.author, {"$inc": {"christmas_boxes_naughty": 1}})
    #         await ctx.send(f"The Pokémon dropped a 🎁 **Naughty Box**! Use `{ctx.prefix}event` to view more info.")

    @checks.has_started()
    @commands.group(aliases=("event", "ev"), invoke_without_command=True, case_insensitive=True)
    async def christmas(self, ctx):
        """View Christmas event information."""

        member = await self.bot.mongo.fetch_member_info(ctx.author)

        embed = self.bot.Embed(color=random.choice([0x9ECFFC, 0xDE2E43, 0x79B15A]))
        embed.title = f"Christmas 2021"
        embed.add_field(
            name=f"🎁 Boxes — Nice: {member.christmas_boxes_nice}, Naughty: {member.christmas_boxes_naughty}",
            value=
            # f"Some **Ice** or **Rock** Pokémon are carrying certain gift boxes for Santa... "
            f"Use these boxes with the `{ctx.prefix}event open` command for the possibility of receiving an exclusive event Pokémon!",
            inline=False,
        )
        embed.add_field(
            name=f"Christmas Badge\n🎁 Boxes opened — Nice: {member.christmas_boxes_nice_opened}, Naughty: {member.christmas_boxes_naughty_opened}",
            value="Open 15 Naughty Boxes and 15 Nice Boxes to receive the <:_:924126408693907507> **Christmas 2021** badge when the event ends.",
            inline=False,        )

        await ctx.send(embed=embed)

    @commands.check_any(commands.is_owner(), commands.has_role(718006431231508481))
    @christmas.command(aliases=("givebox", "ab", "gb"))
    async def addbox(self, ctx, user: FetchUserConverter, box_type, num: int = 1):
        """Give a box."""

        if box_type.lower() == "nice":
            await self.bot.mongo.update_member(user, {"$inc": {"christmas_boxes_nice": num}})
            await ctx.send(f"Gave **{user}** {num} Nice Boxes.")
        elif box_type.lower() == "naughty":
            await self.bot.mongo.update_member(user, {"$inc": {"christmas_boxes_naughty": num}})
            await ctx.send(f"Gave **{user}** {num} Naughty Boxes.")
        else:
            await ctx.send("Need a valid box type!")

    @checks.has_started()
    @commands.max_concurrency(1, commands.BucketType.user)
    @christmas.command(aliases=("o",))
    async def open(self, ctx, box_type: str = "", amt: int = 1):
        """Open a box"""

        if amt <= 0:
            return await ctx.send("Nice try...")

        if amt > 15:
            return await ctx.send("You can only open up to 15 event boxes at once!")
        
        box_type = box_type.lower()
        if box_type not in {"nice", "naughty"}:
            return await ctx.send("Please type `nice` or `naughty`!")

        member = await self.bot.mongo.fetch_member_info(ctx.author)

        if box_type == "nice" and member.christmas_boxes_nice < amt:
            return await ctx.send("You don't have enough nice boxes to do that!")
        if box_type == "naughty" and member.christmas_boxes_naughty < amt:
            return await ctx.send("You don't have enough naughty boxes to do that!")

        await self.bot.mongo.update_member(
            ctx.author,
            {"$inc": {f"christmas_boxes_{box_type}": -amt, f"christmas_boxes_{box_type}_opened": amt}},
        )

        # Go

        if box_type == "nice":
            rewards = random.choices(*NICE, k=amt)
        else:
            rewards = random.choices(*NAUGHTY, k=amt)

        embed = self.bot.Embed(
            title=f"Opening {amt} 🎁 {box_type.title()} Box{'es' if amt > 1 else ''}...",
            color=random.choice([0x9ECFFC, 0xDE2E43, 0x79B15A])
        )
        
        update = {
            "$inc": {"premium_balance": 0, "balance": 0, "redeems": 0},
        }
        
        text = []
        added_pokemon = []
        for reward in rewards:
            if reward == "shards":
                shards = max(round(random.normalvariate(25, 10)), 2)
                update["$inc"]["premium_balance"] += shards
                text.append(f"{shards} Shards")

            elif reward == "pokecoins":
                pokecoins = max(round(random.normalvariate(1000, 500)), 800)
                update["$inc"]["balance"] += pokecoins
                text.append(f"{pokecoins} Pokécoins")

            elif reward == "redeem":
                update["$inc"]["redeems"] += 1
                text.append("1 redeem")

            elif reward in ("event", "pokemon", "rare", "shiny"):
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

                text.append(
                    f"{self.bot.mongo.Pokemon.build_from_mongo(pokemon):lni} ({sum(ivs) / 186:.2%} IV)"
                )
                
                added_pokemon.append(pokemon)

            else:
                text.append("Nothing")

        embed.add_field(name="Rewards Received", value="\n".join(text))
        embed.set_author(icon_url=ctx.author.display_avatar.url, name=str(ctx.author))
        
        await self.bot.mongo.update_member(ctx.author, update)
        if len(added_pokemon) > 0:
            await self.bot.mongo.db.pokemon.insert_many(added_pokemon)
        await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(Christmas(bot))
