import random
import typing
from datetime import datetime
from typing import Optional

from discord.ext import commands

from helpers import flags
from helpers.constants import FILTER_BY_NUMERICAL
from helpers.context import PoketwoContext
from helpers.converters import FetchUserConverter, TimeDelta, strfdelta


class PokemonFlagConverter(commands.FlagConverter, case_insensitive=True):
    species: str = commands.flag(max_args=1, positional=True)
    shiny: Optional[bool] = False
    level: Optional[int] = None
    xp: Optional[int] = 0
    nature: Optional[str] = None
    gender: Optional[str] = None
    has_color: Optional[bool] = commands.flag(aliases=("embedcolor",), default=False)

    iv_total: Optional[int] = commands.flag(aliases=("iv",))
    iv_hp: Optional[int] = commands.flag(aliases=("hpiv", "hp"))
    iv_atk: Optional[int] = commands.flag(aliases=("atkiv", "atk"))
    iv_defn: Optional[int] = commands.flag(aliases=("iv_def", "defiv", "def"))
    iv_satk: Optional[int] = commands.flag(aliases=("satkiv", "satk"))
    iv_sdef: Optional[int] = commands.flag(aliases=("sdefiv", "sdef"))
    iv_spd: Optional[int] = commands.flag(aliases=("spdiv", "spd"))

    @classmethod
    def signature(self) -> str:
        return " ".join(
            ("<{}>" if flag.required else "[{}]").format(
                f"{name}: {name.upper()}"
                + (f"={flag.default if flag.default is not None else 'random'}" if not flag.required else "")
            )
            for name, flag in PokemonFlagConverter.get_flags().items()
        )


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
            {"$set": {"suspended": True, "suspension_reason": reason}, "$unset": {"suspended_until": 1}},
        )
        await self.bot.redis.hdel("db:member", *[int(x.id) for x in users])
        users_msg = ", ".join(f"**{x}**" for x in users)

        if ctx.message.reference:
            await ctx.message.reference.resolved.add_reaction("✅")
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
            {
                "$set": {"suspended_until": datetime.utcnow() + duration, "suspension_reason": reason},
                "$unset": {"suspended": 1},
            },
        )
        await self.bot.redis.hdel("db:member", *[int(x.id) for x in users])
        users_msg = ", ".join(f"**{x}**" for x in users)

        if ctx.message.reference:
            await ctx.message.reference.resolved.add_reaction("✅")
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
        await ctx.send(f"Gave **{user}** {num:,} redeems.")

    @commands.is_owner()
    @admin.command(aliases=("givecoins", "ac", "gc"))
    async def addcoins(self, ctx, user: FetchUserConverter, amt: int):
        """Add to a user's balance."""

        await self.bot.mongo.update_member(user, {"$inc": {"balance": amt}})
        await ctx.send(f"Gave **{user}** {amt:,} Pokécoins.")

    @commands.is_owner()
    @admin.command(aliases=("giveshard", "as", "gs"))
    async def addshard(self, ctx, user: FetchUserConverter, amt: int):
        """Add to a user's shard balance."""

        await self.bot.mongo.update_member(user, {"$inc": {"premium_balance": amt}})
        await ctx.send(f"Gave **{user}** {amt:,} shards.")

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

        await ctx.send(f"Increased vote streak by {amt:,} for **{user}**.")

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
            await ctx.send(f"Gave **{user}** {amt:,} {box_type} boxes.")

    @commands.is_owner()
    @admin.command(aliases=("g",), usage=f"[user=<you>] {PokemonFlagConverter.signature()}")
    async def give(self, ctx, user: Optional[FetchUserConverter] = commands.Author, *, flags: PokemonFlagConverter):
        """Give a pokémon."""

        species = self.bot.data.species_by_name(flags.species)
        if species is None:
            return await ctx.send(f"Could not find a pokemon matching `{flags.species}`.")

        details = {flag: value for flag, value in flags if flag != "species" and value}

        pokemon = await self.bot.mongo.make_pokemon(
            user,
            species,
            **details,
        )
        pokemon_obj = self.bot.mongo.Pokemon.build_from_mongo(pokemon)
        await self.bot.mongo.db.pokemon.insert_one(pokemon)

        await ctx.send(f"Gave **{user}** a **{pokemon_obj:Di}**.")

    @commands.is_owner()
    @admin.command()
    async def setup(self, ctx: PoketwoContext, user: FetchUserConverter, num: int = 100):
        """Test setup pokémon for development purposes."""

        member = await self.bot.mongo.fetch_member_info(user)
        pokemon = []
        idx = await self.bot.mongo.fetch_next_idx(user, reserve=num)

        species = random.choices(tuple(self.bot.data.all_pokemon()), k=num)
        for i, sp in enumerate(species):
            pokemon.append(await self.bot.mongo.make_pokemon(member, sp, idx=idx + i))

        await self.bot.mongo.db.pokemon.insert_many(pokemon)
        await ctx.send(f"Gave **{user}** {num:,} pokémon.")


async def setup(bot: commands.Bot):
    await bot.add_cog(Administration(bot))
