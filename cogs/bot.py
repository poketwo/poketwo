from functools import cached_property

import discord
from discord.ext import commands, flags

from .database import Database
from .helpers import checks, mongo
from .helpers.models import *
from .helpers.constants import HELP


class Bot(commands.Cog):
    """For basic bot operation."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.prefixes = {}

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

            if page_or_cmd not in HELP:
                return await ctx.send("Could not find that page or command.")

            page = HELP[page_or_cmd]

            embed.title = page.get("title", "Help")
            embed.description = page.get("description", None)

            for key, field in page.get("fields", {}).items():
                embed.add_field(name=key, value=field, inline=False)

        else:
            embed.title = f"p!{cmd.qualified_name}"

            print(type(cmd.description))

            if cmd.help:
                embed.description = cmd.help

            embed.set_footer(text=f"p!{cmd.qualified_name} {cmd.signature}",)

        if isinstance(ctx.channel, discord.TextChannel):
            await ctx.message.add_reaction("📬")

        await ctx.author.send(embed=embed)

    async def determine_prefix(self, message):
        if message.guild:
            if message.guild.id not in self.prefixes:
                guild = await mongo.Guild.find_one({"id": message.guild.id})
                if guild is None:
                    guild = mongo.Guild(id=message.guild.id)
                    await guild.commit()

                self.prefixes[message.guild.id] = guild.prefix

            return self.prefixes[message.guild.id] or ["p!", "P!"]

        return ["p!", "P!"]

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.MissingRequiredArgument):
            return await ctx.send_help(ctx.command)

        if isinstance(error, checks.MustHaveStarted):
            return await ctx.send(
                "Please pick a starter pokémon by typing `p!start` before using this command!"
            )

        if isinstance(error, flags.ArgumentParsingError):
            return await ctx.send(error)

        if isinstance(error, commands.CheckFailure):
            return await ctx.send(f"Check failed: {error}")

        if isinstance(error, commands.BadArgument):
            return await ctx.send(f"Bad argument: {error}")

        if isinstance(error, commands.CommandNotFound):
            return

        raise error

    @commands.command()
    async def invite(self, ctx: commands.Context):
        """Get the invite link for the bot."""

        await ctx.send(
            "Want to add me to your server? Use the link below!\n\n"
            "Invite Bot: https://invite.poketwo.net/"
            "Join Server: https://discord.gg/QyEWy4C\n\n"
            "This bot is still in development and has limited functionality. Please report bugs to the server."
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
            self.prefixes[ctx.guild.id] = None

            return await ctx.send("Reset prefix to `p!` for this server.")

        if len(prefix) > 100:
            return await ctx.send("Prefix must not be longer than 100 characters.")

        await self.db.update_guild(ctx.guild, {"$set": {"prefix": prefix}})
        self.prefixes[ctx.guild.id] = prefix

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
    async def admingiveredeem(
        self, ctx: commands.Context, user: discord.Member, *, num: int = 1
    ):
        """Redeem a pokémon."""

        await self.db.update_member(
            user, {"$inc": {"redeems": num},},
        )

        await ctx.send(f"Gave {user.mention} {num} redeems.")

    @commands.is_owner()
    @commands.command()
    async def admingive(
        self, ctx: commands.Context, user: discord.Member, *, species: str
    ):
        """Redeem a pokémon."""

        member = await self.db.fetch_member_info(user)

        try:
            species = GameData.species_by_name(species)
        except SpeciesNotFoundError:
            return await ctx.send(f"Could not find a pokemon matching `{species}`.")

        await self.db.update_member(
            user,
            {
                "$inc": {"next_id": 1},
                "$push": {
                    "pokemon": {
                        "number": member.next_id,
                        "species_id": species.id,
                        "level": 1,
                        "xp": 0,
                        "owner_id": ctx.author.id,
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
