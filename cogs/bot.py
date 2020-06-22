import os
import random
from functools import cached_property

import dbl
import discord
from discord.ext import commands, flags

from .database import Database
from .helpers import checks, constants, converters, models, mongo


def setup(bot: commands.Bot):
    bot.add_cog(Bot(bot))


class Bot(commands.Cog):
    """For basic bot operation."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.bot.prefixes = {}
        self.bot.dblpy = dbl.DBLClient(self.bot, os.getenv("DBL_TOKEN"), autopost=True)

    @property
    def db(self) -> Database:
        return self.bot.get_cog("Database")

    @commands.command()
    async def help(self, ctx: commands.Context, *, page_or_cmd: str = "0"):
        """View a list of commands for the bot."""

        embed = discord.Embed()
        embed.color = 0xF44336

        cmd = self.bot.all_commands.get(page_or_cmd, None)

        if cmd is None:

            if page_or_cmd not in constants.HELP:
                return await ctx.send("Could not find that page or command.")

            page = constants.HELP[page_or_cmd]

            embed.title = page.get("title", "Help")
            embed.description = page.get("description", None)

            for key, field in page.get("fields", {}).items():
                embed.add_field(name=key, value=field, inline=False)

        else:
            embed.title = f"p!{cmd.qualified_name}"

            if cmd.help:
                embed.description = cmd.help

            embed.set_footer(text=f"p!{cmd.qualified_name} {cmd.signature}",)

        if isinstance(ctx.channel, discord.TextChannel):
            await ctx.message.add_reaction("📬")

        await ctx.author.send(embed=embed)

    async def determine_prefix(self, message):
        if message.guild:
            if message.guild.id not in self.bot.prefixes:
                guild = await mongo.Guild.find_one({"id": message.guild.id})
                if guild is None:
                    guild = mongo.Guild(id=message.guild.id)
                    await guild.commit()

                self.bot.prefixes[message.guild.id] = guild.prefix

            return self.bot.prefixes[message.guild.id] or ["p!", "P!"]

        return ["p!", "P!"]

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
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
        """Get the invite link for the bot."""

        if ctx.guild.id == self.bot.guild.id:
            member = await self.db.fetch_member_info(ctx.author)
            return await ctx.send(
                f"You've invited **{member.invites}** people to this server! For more info on the invite event, check out <#724215559943880714>."
            )

        await ctx.send(
            "Want to add me to your server? Use the link below!\n\n"
            "Invite Bot: https://invite.poketwo.net/\n"
            "Join Server: https://discord.gg/QyEWy4C\n\n"
        )

    @commands.command()
    async def stats(self, ctx: commands.Context):
        """View some interesting statistics about the bot."""

        embed = discord.Embed()
        embed.color = 0xF44336
        embed.title = f"Pokétwo Statistics"
        embed.set_thumbnail(url=self.bot.user.avatar_url)

        total = await mongo.db.member.aggregate(
            [
                {"$project": {"pokemon_count": {"$size": "$pokemon"}},},
                {"$group": {"_id": None, "total_count": {"$sum": "$pokemon_count"},},},
            ]
        ).to_list(1)

        embed.add_field(
            name="Servers", value=await mongo.db.guild.count_documents({}), inline=False
        )
        embed.add_field(name="Users", value=len(self.bot.users))
        embed.add_field(
            name="Real Users",
            value=await mongo.db.member.count_documents({}),
            inline=False,
        )
        embed.add_field(
            name="Pokémon Caught", value=total[0]["total_count"], inline=False
        )
        embed.add_field(
            name="Discord Latency",
            value=f"{int(self.bot.latencies[0][1] * 1000)} ms",
            inline=False,
        )

        await ctx.send(embed=embed)

    @checks.is_admin()
    @commands.command()
    async def prefix(self, ctx: commands.Context, *, prefix: str):
        """Change the bot prefix. (Needs admin)"""

        if prefix == "reset":
            await self.db.update_guild(ctx.guild, {"$set": {"prefix": None}})
            self.bot.prefixes[ctx.guild.id] = None

            return await ctx.send("Reset prefix to `p!` for this server.")

        if len(prefix) > 100:
            return await ctx.send("Prefix must not be longer than 100 characters.")

        await self.db.update_guild(ctx.guild, {"$set": {"prefix": prefix}})
        self.bot.prefixes[ctx.guild.id] = prefix

        await ctx.send(f"Changed prefix to `{prefix}` for this server.")

    @commands.command()
    async def ping(self, ctx: commands.Context):
        message = await ctx.send("Pong!")
        ms = (message.created_at - ctx.message.created_at).total_seconds() * 1000
        await message.edit(content=f"Pong! **{int(ms)} ms**")

    @commands.is_owner()
    @commands.command()
    async def eval(self, ctx: commands.Context, *, code: str):
        result = eval(code)
        await ctx.send(result)

    @commands.is_owner()
    @commands.command()
    async def giveredeem(
        self, ctx: commands.Context, user: discord.Member, *, num: int = 1
    ):
        """Redeem a pokémon."""

        await self.db.update_member(
            user, {"$inc": {"redeems": num},},
        )

        await ctx.send(f"Gave {user.mention} {num} redeems.")

    @commands.is_owner()
    @commands.command()
    async def give(self, ctx: commands.Context, user: discord.Member, *, species: str):
        """Give a pokémon."""

        member = await self.db.fetch_member_info(user)

        try:
            species = models.GameData.species_by_name(species)
        except models.SpeciesNotFoundError:
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

        member = await self.db.fetch_member_info(user)

        pokemon = []

        for i in range(num):
            pokemon.append(
                {
                    "species_id": random.randint(1, 809),
                    "level": 1,
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

        await self.db.update_member(
            user, {"$push": {"pokemon": {"$each": pokemon}},},
        )

        await ctx.send(f"Gave {user.mention} {num} pokémon.")
