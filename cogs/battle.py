import asyncio
from functools import cached_property

import discord
from discord.ext import commands, flags

from .database import Database
from .helpers import checks, mongo, models, converters


def setup(bot: commands.Bot):
    bot.add_cog(Battling(bot))


def chunks(l, n):
    """Yield n number of striped chunks from l."""
    for i in range(0, n):
        yield l[i::n]


class Battling(commands.Cog):
    """For battling."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.bot.battles = {}

    @property
    def db(self) -> Database:
        return self.bot.get_cog("Database")

    @checks.has_started()
    @commands.command(rest_is_raw=True)
    async def moves(self, ctx: commands.Context, *, pokemon: converters.Pokemon):
        pokemon, idx = pokemon

        embed = discord.Embed()
        embed.color = 0xF44336
        embed.title = f"Level {pokemon.level} {pokemon.species} — Moves"
        embed.description = "Early preview of battle moves (you can't set moves yet). Battling will come soon! Join the official server for updates regarding battling."

        for idx, xlist in enumerate(chunks(pokemon.species.moveset, 3)):
            embed.add_field(
                name="Moveset" if idx == 0 else "‎",
                value="\n".join(x.name for x in xlist),
            )

        await ctx.send(embed=embed)

    @commands.command(aliases=["mi"])
    async def moveinfo(self, ctx: commands.Context, *, search: str):
        """Get information about a certain move."""

        try:
            move = models.GameData.move_by_name(search)
        except models.SpeciesNotFoundError:
            return await ctx.send("Couldn't find a move with that name!")

        embed = discord.Embed()
        embed.color = 0xF44336
        embed.title = move.name

        embed.description = move.description

        embed.add_field(name="Target", value=move.target_text, inline=False)

        for name, x in (
            ("Power", "power"),
            ("Accuracy", "accuracy"),
            ("PP", "pp"),
            ("Priority", "priority"),
            ("Type", "type"),
        ):
            if (v := getattr(move, x)) is not None:
                embed.add_field(name=name, value=v)
            else:
                embed.add_field(name=name, value="—")

        embed.add_field(name="Class", value=move.damage_class)

        await ctx.send(embed=embed)
