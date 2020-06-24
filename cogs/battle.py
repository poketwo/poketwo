import asyncio
import math
from functools import cached_property

import discord
from discord.ext import commands, flags

from .database import Database
from .helpers import checks, converters, models, mongo, pagination


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

        embed.add_field(
            name="Available Moves",
            value="\n".join(
                x.move.name
                for x in pokemon.species.moves
                if pokemon.level >= x.method.level
            ),
        )

        await ctx.send(embed=embed)

    @commands.command(aliases=["ms"])
    async def moveset(self, ctx: commands.Context, *, search: str):

        if search[0] in "N#" and search[1:].isdigit():
            species = models.GameData.species_by_number(int(search[1:]))
        else:
            species = models.GameData.species_by_name(search)

        if species is None:
            return await ctx.send("Couldn't find that pokémon!")

        async def get_page(pidx, clear):
            pgstart = (pidx) * 20
            pgend = min(pgstart + 20, len(species.moves))

            # Send embed

            embed = discord.Embed()
            embed.color = 0xF44336
            embed.title = f"{species} — Moveset"

            embed.set_footer(
                text=f"Showing {pgstart + 1}–{pgend} out of {len(species.moves)}."
            )

            for move in species.moves[pgstart:pgend]:
                embed.add_field(name=move.move.name, value=move.text)

            for i in range(-pgend % 3):
                embed.add_field(name="‎", value="‎")

            return embed

        paginator = pagination.Paginator(
            get_page, num_pages=math.ceil(len(species.moves) / 20)
        )
        await paginator.send(self.bot, ctx, 0)

    @commands.command(aliases=["mi"])
    async def moveinfo(self, ctx: commands.Context, *, search: str):
        """Get information about a certain move."""

        move = models.GameData.move_by_name(search)

        if move is None:
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
