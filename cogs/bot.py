import os
import random
from datetime import datetime
from functools import cached_property

import dbl
import discord
from discord.ext import commands, flags

from helpers import checks, constants, converters, models, mongo

from .database import Database


def setup(bot: commands.Bot):
    bot.add_cog(Bot(bot))


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

    @property
    def db(self) -> Database:
        return self.bot.get_cog("Database")

    async def determine_prefix(self, message):
        if message.guild:
            if message.guild.id not in self.bot.prefixes:
                guild = await mongo.Guild.find_one({"id": message.guild.id})
                if guild is None:
                    guild = mongo.Guild(id=message.guild.id)
                    await guild.commit()

                self.bot.prefixes[message.guild.id] = guild.prefix

            if self.bot.prefixes[message.guild.id] is not None:
                return [
                    self.bot.prefixes[message.guild.id],
                    self.bot.user.mention + " ",
                    self.bot.user.mention[:2] + "!" + self.bot.user.mention[2:] + " ",
                ]

        return [
            "p!",
            "P!",
            self.bot.user.mention + " ",
            self.bot.user.mention[:2] + "!" + self.bot.user.mention[2:] + " ",
        ]

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        if isinstance(error, discord.Forbidden):
            return

        if isinstance(error, commands.MissingRequiredArgument):
            embed = discord.Embed()
            embed.color = 0xF44336
            embed.title = f"p!{ctx.command.qualified_name}"

            if ctx.command.help:
                embed.description = ctx.command.help

            embed.set_footer(
                text=f"p!{ctx.command.qualified_name} {ctx.command.signature}",
            )
            return await ctx.send(embed=embed)

        if isinstance(error, checks.MustHaveStarted):
            return await ctx.send(
                "Please pick a starter pokémon by typing `p!start` before using this command!"
            )

        if isinstance(error, flags.ArgumentParsingError):
            return await ctx.send(error)

        if isinstance(error, commands.BadArgument):
            return await ctx.send(f"Bad argument: {error}")

        if isinstance(error, converters.PokemonConversionError):
            return await ctx.send(error)

        if isinstance(error, commands.BotMissingPermissions):
            missing = [
                "`" + perm.replace("_", " ").replace("guild", "server").title() + "`"
                for perm in error.missing_perms
            ]

            if len(missing) > 2:
                fmt = "{}, and {}".format(", ".join(missing[:-1]), missing[-1])
            else:
                fmt = " and ".join(missing)

            message = f"💥 Err, I need the following permissions to run this command:\n{fmt}\nPlease fix this and try again."
            return await ctx.send(message)

        if isinstance(error, commands.CheckFailure):
            return await ctx.send(error)

        if isinstance(error, commands.CommandNotFound):
            return

        raise error

    @commands.command()
    async def invite(self, ctx: commands.Context):
        """View the invite link for the bot."""

        await ctx.send(
            "Want to add me to your server? Use the link below!\n\n"
            "Invite Bot: https://invite.poketwo.net/\n"
            "Join Server: https://discord.gg/QyEWy4C"
        )

    @commands.command()
    async def stats(self, ctx: commands.Context):
        """View interesting statistics about the bot."""

        embed = discord.Embed()
        embed.color = 0xF44336
        embed.title = f"Pokétwo Statistics"
        embed.set_thumbnail(url=self.bot.user.avatar_url)

        embed.add_field(name="Servers", value=len(self.bot.guilds), inline=False)
        embed.add_field(name="Users", value=len(self.bot.users))
        embed.add_field(
            name="Trainers",
            value=await mongo.db.member.count_documents({}),
            inline=False,
        )
        embed.add_field(
            name="Latency",
            value=f"{int(self.bot.latencies[0][1] * 1000)} ms",
            inline=False,
        )

        await ctx.send(embed=embed)

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
        embed.description = "To start, choose one of the starter pokémon using the `p!pick <pokemon>` command. "

        for gen, pokemon in constants.STARTER_GENERATION.items():
            embed.add_field(name=gen, value=" · ".join(pokemon), inline=False)

        await ctx.send(embed=embed)

    @commands.command()
    async def pick(self, ctx: commands.Context, *, name: str):
        """Pick a starter pokémon to get started."""

        member = await self.db.fetch_member_info(ctx.author)

        if member is not None:
            return await ctx.send(
                "You have already chosen a starter pokémon! View your pokémon with `p!pokemon`."
            )

        if name.lower() not in constants.STARTER_POKEMON:
            return await ctx.send(
                "Please select one of the starter pokémon. To view them, type `p!start`."
            )

        species = models.GameData.species_by_name(name)

        starter = mongo.Pokemon.random(species_id=species.id, level=1, xp=0)

        member = mongo.Member(
            id=ctx.author.id, pokemon=[starter], selected=0, joined_at=datetime.now()
        )

        await member.commit()

        await ctx.send(
            f"Congratulations on entering the world of pokémon! {species} is your first pokémon. Type `p!info` to view it!"
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
            ("Mythical", models.GameData.list_mythical()),
            ("Legendary", models.GameData.list_legendary()),
            ("Ultra Beast", models.GameData.list_ub()),
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
        await self.db.update_member(
            member or ctx.author,
            {"$pull": {f"pokemon": {"species_id": {"$exists": False}}}},
        )
        await self.db.update_member(member or ctx.author, {"$pull": {f"pokemon": None}})
        await ctx.send("Trying to heal schema...")
