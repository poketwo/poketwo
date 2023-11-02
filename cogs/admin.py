import random
import typing
from datetime import datetime

from discord.ext import commands

from helpers.converters import FetchUserConverter, TimeDelta, strfdelta

from . import mongo


class Administration(commands.Cog):
    """Commands for bot administration."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.is_owner()
    @commands.group(aliases=("am",), invoke_without_command=True, case_insensitive=True)
    async def admin(self, ctx):
        pass

    @commands.is_owner()
    @admin.command(aliases=("sp",))
    async def suspend(self, ctx, users: commands.Greedy[FetchUserConverter], *, reason: str = None):
        """Suspend one or more users."""

        await self.bot.mongo.db.member.update_many(
            {"_id": {"$in": [x.id for x in users]}},
            {"$set": {"suspended": True, "suspension_reason": reason}},
        )
        await self.bot.redis.hdel("db:member", *[int(x.id) for x in users])
        users_msg = ", ".join(f"**{x}**" for x in users)
        await ctx.send(f"Suspended {users_msg}.")

    @commands.is_owner()
    @admin.command(aliases=("tsp",))
    async def tempsuspend(
        self,
        ctx,
        duration: TimeDelta,
        users: commands.Greedy[FetchUserConverter],
        *,
        reason: str = None,
    ):
        """Temporarily suspend one or more users."""

        await self.bot.mongo.db.member.update_many(
            {"_id": {"$in": [x.id for x in users]}},
            {"$set": {"suspended_until": datetime.utcnow() + duration, "suspension_reason": reason}},
        )
        await self.bot.redis.hdel("db:member", *[int(x.id) for x in users])
        users_msg = ", ".join(f"**{x}**" for x in users)
        await ctx.send(f"Suspended {users_msg} for {strfdelta(duration)}.")

    @commands.is_owner()
    @admin.command(aliases=("usp",))
    async def unsuspend(self, ctx, users: commands.Greedy[FetchUserConverter]):
        """Unuspend one or more users."""

        await self.bot.mongo.db.member.update_many(
            {"_id": {"$in": [x.id for x in users]}},
            {"$unset": {"suspended": 1, "suspended_until": 1, "suspension_reason": 1}},
        )
        await self.bot.redis.hdel("db:member", *[int(x.id) for x in users])
        users_msg = ", ".join(f"**{x}**" for x in users)
        await ctx.send(f"Unsuspended {users_msg}.")

    @commands.is_owner()
    @admin.command(aliases=("spawn",))
    async def randomspawn(self, ctx):
        await self.bot.get_cog("Spawning").spawn_pokemon(ctx.channel)

    @commands.is_owner()
    @admin.command(aliases=("giveredeem", "ar", "gr"))
    async def addredeem(self, ctx, user: FetchUserConverter, num: int = 1):
        """Give a redeem."""

        await self.bot.mongo.update_member(user, {"$inc": {"redeems": num}})
        await ctx.send(f"Gave **{user}** {num} redeems.")

    @commands.is_owner()
    @admin.command(aliases=("givecoins", "ac", "gc"))
    async def addcoins(self, ctx, user: FetchUserConverter, amt: int):
        """Add to a user's balance."""

        await self.bot.mongo.update_member(user, {"$inc": {"balance": amt}})
        await ctx.send(f"Gave **{user}** {amt} Pokécoins.")

    @commands.is_owner()
    @admin.command(aliases=("giveshard", "as", "gs"))
    async def addshard(self, ctx, user: FetchUserConverter, amt: int):
        """Add to a user's shard balance."""

        await self.bot.mongo.update_member(user, {"$inc": {"premium_balance": amt}})
        await ctx.send(f"Gave **{user}** {amt} shards.")

    @commands.is_owner()
    @admin.command(aliases=("givevote", "av", "gv"))
    async def addvote(self, ctx, user: FetchUserConverter, amt: int = 1):
        """Add to a user's vote streak."""

        await self.bot.mongo.update_member(
            user,
            {
                "$set": {"last_voted": datetime.utcnow()},
                "$inc": {"vote_total": amt, "vote_streak": amt},
            },
        )

        await ctx.send(f"Increased vote streak by {amt} for **{user}**.")

    @commands.is_owner()
    @admin.command(aliases=("givebox", "ab", "gb"))
    async def addbox(self, ctx, user: FetchUserConverter, box_type, amt: int = 1):
        """Give a user boxes."""

        if box_type not in ("normal", "great", "ultra", "master"):
            return await ctx.send("That's not a valid box type!")

        await self.bot.mongo.update_member(
            user,
            {
                "$set": {"last_voted": datetime.utcnow()},
                "$inc": {f"gifts_{box_type}": amt},
            },
        )

        if amt == 1:
            await ctx.send(f"Gave **{user}** 1 {box_type} box.")
        else:
            await ctx.send(f"Gave **{user}** {amt} {box_type} boxes.")

    @commands.is_owner()
    @admin.command(aliases=("g",))
    async def give(self, ctx, user: FetchUserConverter, *, arg: str):
        """Give a pokémon."""

        shiny = False

        if arg.lower().startswith("shiny"):
            shiny = True
            arg = arg.lower().replace("shiny", "").strip()

        species = self.bot.data.species_by_name(arg)

        if species is None:
            return await ctx.send(f"Could not find a pokemon matching `{arg}`.")

        ivs = [mongo.random_iv() for i in range(6)]

        await self.bot.mongo.db.pokemon.insert_one(
            {
                "owner_id": user.id,
                "owned_by": "user",
                "species_id": species.id,
                "level": 1,
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
        )

        await ctx.send(f"Gave **{user}** a {species}.")

    @commands.is_owner()
    @admin.command()
    async def setup(self, ctx, user: FetchUserConverter, num: int = 100):
        """Test setup pokémon."""

        # This is for development purposes.

        pokemon = []
        idx = await self.bot.mongo.fetch_next_idx(user, reserve=num)

        for i in range(num):
            spid = random.randint(1, 905)
            ivs = [mongo.random_iv() for i in range(6)]
            pokemon.append(
                {
                    "owner_id": user.id,
                    "owned_by": "user",
                    "species_id": spid,
                    "level": 80,
                    "xp": 0,
                    "nature": mongo.random_nature(),
                    "iv_hp": ivs[0],
                    "iv_atk": ivs[1],
                    "iv_defn": ivs[2],
                    "iv_satk": ivs[3],
                    "iv_sdef": ivs[4],
                    "iv_spd": ivs[5],
                    "iv_total": sum(ivs),
                    "shiny": False,
                    "idx": idx + i,
                }
            )

        await self.bot.mongo.db.pokemon.insert_many(pokemon)
        await ctx.send(f"Gave **{user}** {num} pokémon.")


async def setup(bot: commands.Bot):
    await bot.add_cog(Administration(bot))
