import asyncio
import math
import random
from functools import cached_property

import discord
from discord.ext import commands, flags

from .database import Database
from helpers import checks, constants, converters, models, mongo, pagination


def setup(bot: commands.Bot):
    bot.add_cog(Administration(bot))


class Administration(commands.Cog):
    """Commands for bot administration."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @property
    def db(self) -> Database:
        return self.bot.get_cog("Database")

    @commands.is_owner()
    @commands.command()
    async def suspend(self, ctx: commands.Context, user: discord.User):
        """Suspend a user."""

        await self.db.update_member(
            user, {"$set": {"suspended": True}},
        )

        await ctx.send(f"Suspended {user.mention}.")

    @commands.is_owner()
    @commands.command()
    async def unsuspend(self, ctx: commands.Context, user: discord.User):
        """Suspend a user."""

        await self.db.update_member(
            user, {"$set": {"suspended": False}},
        )

        await ctx.send(f"Unsuspended {user.mention}.")

    @commands.is_owner()
    @commands.command()
    async def giveredeem(
        self, ctx: commands.Context, user: discord.Member, *, num: int = 1
    ):
        """Give a redeem."""

        await self.db.update_member(
            user, {"$inc": {"redeems": num}},
        )

        await ctx.send(f"Gave {user.mention} {num} redeems.")

    @commands.is_owner()
    @commands.command()
    async def give(self, ctx: commands.Context, user: discord.Member, *, species: str):
        """Give a pokémon."""

        member = await self.db.fetch_member_info(user)

        species = models.GameData.species_by_name(species)

        if species is None:
            return await ctx.send(f"Could not find a pokemon matching `{species}`.")

        await self.db.update_member(
            user,
            {
                "$push": {
                    "pokemon": {
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
                    }
                },
            },
        )

        await ctx.send(f"Gave {user.mention} a {species}.")

    @commands.is_owner()
    @commands.command()
    async def setup(self, ctx: commands.Context, user: discord.Member, num: int = 100):
        """Test setup pokémon."""

        # This is for development purposes.

        member = await self.db.fetch_member_info(user)

        pokemon = []
        pokedex = {}

        for i in range(num):
            spid = random.randint(1, 809)
            pokemon.append(
                {
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
                    "shiny": random.randint(1, 4096) == 1,
                }
            )
            pokedex["pokedex." + str(spid)] = pokedex.get("pokedex." + str(spid), 0) + 1

        await self.db.update_member(
            user, {"$push": {"pokemon": {"$each": pokemon}}, "$inc": pokedex},
        )

        await ctx.send(f"Gave {user.mention} {num} pokémon.")
