import random
import typing
from datetime import datetime

import discord
from discord.ext import commands
from pymongo.errors import DuplicateKeyError

from . import mongo


class Administration(commands.Cog):
    """Commands for bot administration."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.is_owner()
    @commands.command()
    async def blacklist(self, ctx: commands.Context, id: int):
        """Blacklist a user."""

        try:
            await self.bot.mongo.db.blacklist.insert_one({"_id": id})
            await ctx.send(f"Blacklisted {id}.")
        except DuplicateKeyError:
            await ctx.send("That ID is already blacklisted!")

    @commands.is_owner()
    @commands.command()
    async def unblacklist(self, ctx: commands.Context, id: int):
        """Unblacklist a user."""

        result = await self.bot.mongo.db.blacklist.delete_one({"_id": id})
        if result.deleted_count == 0:
            await ctx.send("That ID is not blacklisted!")
        else:
            await ctx.send(f"Unblacklisted {id}.")

    @commands.is_owner()
    @commands.command()
    async def suspend(self, ctx: commands.Context, user: discord.User):
        """Suspend a user."""

        await self.bot.mongo.update_member(user, {"$set": {"suspended": True}})
        await ctx.send(f"Suspended {user.mention}.")

    @commands.is_owner()
    @commands.command()
    async def randomspawn(self, ctx: commands.Context):
        await self.bot.get_cog("Spawning").spawn_pokemon(ctx.channel)

    @commands.is_owner()
    @commands.command()
    async def unsuspend(self, ctx: commands.Context, user: discord.User):
        """Suspend a user."""

        await self.bot.mongo.update_member(user, {"$set": {"suspended": False}})
        await ctx.send(f"Unsuspended {user.mention}.")

    @commands.is_owner()
    @commands.command(aliases=["addredeem"])
    async def giveredeem(
        self, ctx: commands.Context, user: discord.Member, *, num: int = 1
    ):
        """Give a redeem."""

        await self.bot.mongo.update_member(user, {"$inc": {"redeems": num}})
        await ctx.send(f"Gave {user.mention} {num} redeems.")

    @commands.is_owner()
    @commands.command(aliases=["givebal"])
    async def addbal(
        self,
        ctx: commands.Context,
        user: discord.Member,
        amt: int,
    ):
        """Add to a user's balance."""

        await self.bot.mongo.update_member(user, {"$inc": {"balance": amt}})
        await ctx.send(f"Gave {user.mention} {amt} Pokécoins.")

    @commands.is_owner()
    @commands.command(aliases=["giveshard"])
    async def addshard(
        self,
        ctx: commands.Context,
        user: discord.Member,
        amt: int,
    ):
        """Add to a user's shard balance."""

        await self.bot.mongo.update_member(user, {"$inc": {"premium_balance": amt}})
        await ctx.send(f"Gave {user.mention} {amt} shards.")

    @commands.is_owner()
    @commands.command(aliases=["givevote"])
    async def addvote(
        self, ctx: commands.Context, user: discord.Member, box_type: str, amt: int = 1
    ):
        """Give a user a vote."""

        if box_type not in ("normal", "great", "ultra", "master"):
            return await ctx.send("That's not a valid box type!")

        await self.bot.mongo.update_member(
            user,
            {
                "$set": {"last_voted": datetime.utcnow()},
                "$inc": {
                    "vote_total": amt,
                    "vote_streak": amt,
                    f"gifts_{box_type}": amt,
                },
            },
        )

        if amt == 1:
            await ctx.send(f"Gave {user.mention} an {box_type} box.")
        else:
            await ctx.send(f"Gave {user.mention} {amt} {box_type} boxes.")

    @commands.is_owner()
    @commands.command()
    async def give(self, ctx: commands.Context, user: discord.Member, *, species: str):
        """Give a pokémon."""

        shiny = False

        if species.lower().startswith("shiny"):
            shiny = True
            species = species.lower().replace("shiny", "").strip()

        species = self.bot.data.species_by_name(species)

        if species is None:
            return await ctx.send(f"Could not find a pokemon matching `{species}`.")

        await self.bot.mongo.db.pokemon.insert_one(
            {
                "owner_id": user.id,
                "species_id": species.id,
                "level": 1,
                "xp": 0,
                "nature": mongo.random_nature(),
                "iv_hp": mongo.random_iv(),
                "iv_atk": mongo.random_iv(),
                "iv_defn": mongo.random_iv(),
                "iv_satk": mongo.random_iv(),
                "iv_sdef": mongo.random_iv(),
                "iv_spd": mongo.random_iv(),
                "shiny": shiny,
                "idx": await self.bot.mongo.fetch_next_idx(user),
            }
        )

        await ctx.send(f"Gave {user.mention} a {species}.")

    @commands.is_owner()
    @commands.command()
    async def setup(self, ctx: commands.Context, user: discord.Member, num: int = 100):
        """Test setup pokémon."""

        # This is for development purposes.

        pokemon = []
        idx = await self.bot.mongo.fetch_next_idx(user, reserve=num)

        for i in range(num):
            spid = random.randint(1, 809)
            pokemon.append(
                {
                    "owner_id": user.id,
                    "species_id": spid,
                    "level": 80,
                    "xp": 0,
                    "nature": mongo.random_nature(),
                    "iv_hp": mongo.random_iv(),
                    "iv_atk": mongo.random_iv(),
                    "iv_defn": mongo.random_iv(),
                    "iv_satk": mongo.random_iv(),
                    "iv_sdef": mongo.random_iv(),
                    "iv_spd": mongo.random_iv(),
                    "shiny": False,
                    "idx": idx + i,
                }
            )

        await self.bot.mongo.db.pokemon.insert_many(pokemon)
        await ctx.send(f"Gave {user.mention} {num} pokémon.")


def setup(bot: commands.Bot):
    bot.add_cog(Administration(bot))
