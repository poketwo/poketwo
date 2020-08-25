import random
from datetime import datetime
import typing
from pymongo.errors import DuplicateKeyError
import discord
from discord.ext import commands

from helpers import mongo

from .database import Database


class Administration(commands.Cog):
    """Commands for bot administration."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @property
    def db(self) -> Database:
        return self.bot.get_cog("Database")

    @commands.is_owner()
    @commands.command()
    async def blacklist(self, ctx: commands.Context, user: discord.User):
        """Blacklist a user."""

        try:
            await self.bot.mongo.db.blacklist.insert_one({"_id": user.id})
            await ctx.send(f"Blacklisted {user.mention}.")
        except DuplicateKeyError:
            await ctx.send("That user is already blacklisted!")

    @commands.is_owner()
    @commands.command()
    async def unblacklist(self, ctx: commands.Context, user: discord.User):
        """Unblacklist a user."""

        result = await self.bot.mongo.db.blacklist.delete_one({"_id": user.id})
        if result.deleted_count == 0:
            await ctx.send("That user is not blacklisted!")
        else:
            await ctx.send(f"Unblacklisted {user.mention}.")

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
    async def randomspawn(self, ctx: commands.Context):
        await self.bot.get_cog("Spawning").spawn_pokemon(ctx.channel)

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
    async def addbal(
        self, ctx: commands.Context, user: discord.Member, amt: int,
    ):
        """Add to a user's balance."""

        await self.db.update_member(user, {"$inc": {"balance": amt}})
        await ctx.send(f"Gave {user.mention} {amt} Pokécoins.")

    @commands.is_owner()
    @commands.command()
    async def addvote(
        self, ctx: commands.Context, user: discord.Member, box_type: str,
    ):
        """Give a user a vote."""

        if box_type not in ("normal", "great", "ultra"):
            return await ctx.send("That's not a valid box type!")

        await self.db.update_member(
            user,
            {
                "$set": {"last_voted": datetime.utcnow()},
                "$inc": {"vote_total": 1, "vote_streak": 1, f"gifts_{box_type}": 1},
            },
        )

        await ctx.send(f"Gave {user.mention} an {box_type} box.")

    @commands.is_owner()
    @commands.command()
    async def give(self, ctx: commands.Context, user: discord.Member, *, species: str):
        """Give a pokémon."""

        member = await self.db.fetch_member_info(user)

        shiny = False

        if species.lower().startswith("shiny"):
            shiny = True
            species = species.lower().replace("shiny", "").strip()

        species = self.bot.data.species_by_name(species)

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
                        "shiny": shiny,
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
                    "shiny": False,
                }
            )
            pokedex["pokedex." + str(spid)] = pokedex.get("pokedex." + str(spid), 0) + 1

        await self.db.update_member(
            user, {"$push": {"pokemon": {"$each": pokemon}}, "$inc": pokedex},
        )

        await ctx.send(f"Gave {user.mention} {num} pokémon.")


def setup(bot: commands.Bot):
    bot.add_cog(Administration(bot))
