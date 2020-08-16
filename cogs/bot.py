import logging
import os
import sys
import traceback
from datetime import datetime

import dbl
import discord
from discord.ext import commands, flags

from helpers import checks, constants, converters, models, mongo

from .database import Database


class Blacklisted(commands.CheckFailure):
    pass


class CommandOnCooldown(commands.CommandOnCooldown):
    pass


class Bot(commands.Cog):
    """For basic bot operation."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

        if not hasattr(self.bot, "prefixes"):
            self.bot.prefixes = {}

        if not hasattr(self.bot, "dblpy"):
            self.bot.dblpy = dbl.DBLClient(
                self.bot, os.getenv("DBL_TOKEN"), autopost=True
            )

    async def bot_check(self, ctx):
        if (
            await self.bot.mongo.db.blacklist.count_documents({"_id": ctx.author.id})
            > 0
        ):
            raise Blacklisted

        return True

    @property
    def db(self) -> Database:
        return self.bot.get_cog("Database")

    async def determine_prefix(self, guild):
        if guild:
            if guild.id not in self.bot.prefixes:
                data = await self.bot.mongo.Guild.find_one({"id": guild.id})
                if data is None:
                    data = self.bot.mongo.Guild(id=guild.id)
                    await data.commit()

                self.bot.prefixes[guild.id] = data.prefix

            if self.bot.prefixes[guild.id] is not None:
                return [
                    self.bot.prefixes[guild.id],
                    self.bot.user.mention + " ",
                    self.bot.user.mention[:2] + "!" + self.bot.user.mention[2:] + " ",
                ]

        return [
            "p!",
            "P!",
            self.bot.user.mention + " ",
            self.bot.user.mention[:2] + "!" + self.bot.user.mention[2:] + " ",
        ]

    @commands.command()
    async def invite(self, ctx: commands.Context):
        """View the invite link for the bot."""

        await ctx.send(
            "Want to add me to your server? Use the link below!\n\n"
            "Invite Bot: https://invite.poketwo.net/\n"
            "Join Server: https://discord.gg/QyEWy4C"
        )

    # @commands.command()
    # async def stats(self, ctx: commands.Context):
    #     """View interesting statistics about the bot."""

    #     embed = discord.Embed()
    #     embed.color = 0xF44336
    #     embed.title = f"Pokétwo Statistics"
    #     embed.set_thumbnail(url=self.bot.user.avatar_url)

    #     embed.add_field(name="Servers", value=len(self.bot.guilds), inline=False)
    #     embed.add_field(name="Users", value=len(self.bot.users))
    #     embed.add_field(
    #         name="Trainers",
    #         value=await self.bot.mongo.db.member.count_documents({}),
    #         inline=False,
    #     )
    #     embed.add_field(
    #         name="Latency",
    #         value=f"{int(self.bot.latencies[0][1] * 1000)} ms",
    #         inline=False,
    #     )

    #     await ctx.send(embed=embed)

    @commands.command()
    async def ping(self, ctx: commands.Context):
        """View the bot's latency."""

        message = await ctx.send("Pong!")
        ms = (message.created_at - ctx.message.created_at).total_seconds() * 1000
        await message.edit(content=f"Pong! **{int(ms)} ms**")

    @commands.command()
    async def start(self, ctx: commands.Context):
        """View the starter pokémon."""

        embed = discord.Embed()
        embed.color = 0xF44336
        embed.title = "Welcome to the world of Pokémon!"
        embed.description = f"To start, choose one of the starter pokémon using the `{ctx.prefix}pick <pokemon>` command. "

        for gen, pokemon in constants.STARTER_GENERATION.items():
            embed.add_field(name=gen, value=" · ".join(pokemon), inline=False)

        await ctx.send(embed=embed)

    @commands.command()
    async def pick(self, ctx: commands.Context, *, name: str):
        """Pick a starter pokémon to get started."""

        member = await self.db.fetch_member_info(ctx.author)

        if member is not None:
            return await ctx.send(
                f"You have already chosen a starter pokémon! View your pokémon with `{ctx.prefix}pokemon`."
            )

        species = self.bot.data.species_by_name(name)

        if species.name.lower() not in constants.STARTER_POKEMON:
            return await ctx.send(
                f"Please select one of the starter pokémon. To view them, type `{ctx.prefix}start`."
            )

        starter = self.bot.mongo.Pokemon.random(species_id=species.id, level=1, xp=0)

        member = self.bot.mongo.Member(
            id=ctx.author.id, pokemon=[starter], selected=0, joined_at=datetime.utcnow()
        )

        await member.commit()

        await ctx.send(
            f"Congratulations on entering the world of pokémon! {species} is your first pokémon. Type `{ctx.prefix}info` to view it!"
        )

    @checks.has_started()
    @commands.command()
    async def profile(self, ctx: commands.Context):
        """View your profile."""

        embed = discord.Embed()
        embed.color = 0xF44336
        embed.title = f"{ctx.author}"

        member = await self.db.fetch_member_info(ctx.author)

        pokemon_caught = []

        pokemon_caught.append(
            "**Total: **" + str(await self.db.fetch_pokedex_sum(ctx.author))
        )

        for name, filt in (
            ("Mythical", self.bot.data.list_mythical()),
            ("Legendary", self.bot.data.list_legendary()),
            ("Ultra Beast", self.bot.data.list_ub()),
        ):
            pokemon_caught.append(
                f"**{name}: **"
                + str(
                    await self.db.fetch_pokedex_sum(
                        ctx.author,
                        [{"$match": {"k": {"$in": [str(x) for x in filt]}}}],
                    )
                )
            )

        pokemon_caught.append("**Shiny: **" + str(member.shinies_caught))

        embed.add_field(name="Pokémon Caught", value="\n".join(pokemon_caught))

        await ctx.send(embed=embed)

    @checks.has_started()
    @commands.command()
    async def healschema(self, ctx: commands.Context, member: discord.User = None):
        """Fix database schema if broken."""

        await self.db.update_member(
            member or ctx.author,
            {"$pull": {f"pokemon": {"species_id": {"$exists": False}}}},
        )
        await self.db.update_member(member or ctx.author, {"$pull": {f"pokemon": None}})
        await ctx.send("Trying to heal schema...")


def setup(bot: commands.Bot):
    bot.add_cog(Bot(bot))
