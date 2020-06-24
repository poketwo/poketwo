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
        embed.description = "Here are the moves your pokémon can learn right now. View all moves and how to get them using `p!moveset`!"

        embed.add_field(
            name="Available Moves",
            value="\n".join(
                x.move.name
                for x in pokemon.species.moves
                if pokemon.level >= x.method.level
            ),
        )

        embed.add_field(
            name="Current Moves",
            value="No Moves"
            if len(pokemon.moves) == 0
            else "\n".join(
                models.GameData.move_by_number(x).name for x in pokemon.moves
            ),
        )

        await ctx.send(embed=embed)

    @checks.has_started()
    @commands.command()
    async def learn(self, ctx: commands.Context, *, search: str):
        move = models.GameData.move_by_name(search)

        if move is None:
            return await ctx.send("Couldn't find that move!")

        member = await self.db.fetch_member_info(ctx.author)
        pokemon = await self.db.fetch_pokemon(ctx.author, member.selected)

        if move.id in pokemon.moves:
            return await ctx.send("Your pokémon has already learned that move!")

        try:
            pokemon_move = next(
                x for x in pokemon.species.moves if x.move_id == move.id
            )
        except StopIteration:
            pokemon_move = None

        if pokemon_move is None or pokemon_move.method.level > pokemon.level:
            return await ctx.send("Your pokémon can't learn that move!")

        update = {}

        if len(pokemon.moves) >= 4:

            await ctx.send(
                "Your pokémon already knows the max number of moves! Please enter the name of a move to replace, or anything else to abort:\n"
                + "\n".join(
                    models.GameData.move_by_number(x).name for x in pokemon.moves
                )
            )

            def check(m):
                return m.channel.id == ctx.channel.id and m.author.id == ctx.author.id

            try:
                msg = await self.bot.wait_for("message", timeout=60, check=check)
            except asyncio.TimeoutError:
                return await ctx.send("Time's up. Aborted.")

            rep_move = models.GameData.move_by_name(msg.content)

            if rep_move is None or rep_move.id not in pokemon.moves:
                return await ctx.send("Aborted.")

            idx = pokemon.moves.index(rep_move.id)

            update["$set"] = {f"pokemon.{member.selected}.moves.{idx}": move.id}

        else:
            update["$push"] = {f"pokemon.{member.selected}.moves": move.id}

        await self.db.update_member(ctx.author, update)

        return await ctx.send("Your pokémon has learned " + move.name + "!")

    @commands.command(aliases=["ms"], rest_is_raw=True)
    async def moveset(self, ctx: commands.Context, *, search: str):

        search = search.strip()

        if len(search) > 0 and search[0] in "Nn#" and search[1:].isdigit():
            species = models.GameData.species_by_number(int(search[1:]))
        else:
            species = models.GameData.species_by_name(search)

            if species is None:
                converter = converters.Pokemon(raise_errors=False)
                pokemon, idx = await converter.convert(ctx, search)
                if pokemon is not None:
                    species = pokemon.species

        if species is None:
            raise converters.PokemonConversionError(
                f"Please either enter the name of a pokémon species, nothing for your selected pokémon, a number for a specific pokémon, `latest` for your latest pokémon."
            )

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
