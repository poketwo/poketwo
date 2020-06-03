from functools import cached_property

import discord
from discord.ext import commands
from mongoengine import DoesNotExist

from .database import Database
from .helpers import checks, mongo
from .helpers.models import GameData, SpeciesNotFoundError

STARTER_GENERATION = {
    "Generation I (Kanto)": ("Bulbasaur", "Charmander", "Squirtle"),
    "Generation II (Johto)": ("Chikorita", "Cyndaquil", "Totodile"),
    "Generation III (Hoenn)": ("Treecko", "Torchic", "Mudkip"),
    "Generation IV (Sinnoh)": ("Turtwig", "Chimchar", "Piplup"),
    "Generation V (Unova)": ("Snivy", "Tepig", "Oshawott"),
    "Generation VI (Kalos)": ("Chespin", "Fennekin", "Froakie"),
    "Generation VII (Alola)": ("Rowlet", "Litten", "Popplio"),
}

STARTER_POKEMON = [item.lower() for l in STARTER_GENERATION.values() for item in l]

SORTING_FUNCTIONS = {
    "number": lambda p: p.number,
    "iv": lambda p: -p.iv_percentage,
    "level": lambda p: -p.level,
    "abc": lambda p: p.species.name,
}


class Pokemon(commands.Cog):
    """Pokémon-related commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @cached_property
    def db(self) -> Database:
        return self.bot.get_cog("Database")

    @commands.command()
    async def start(self, ctx: commands.Context):
        embed = discord.Embed()
        embed.color = 0xF44336
        embed.title = "Welcome to the world of Pokémon!"
        embed.description = "To start, choose one of the starter pokémon using the `p!pick <pokemon>` command. "

        for gen, pokemon in STARTER_GENERATION.items():
            embed.add_field(name=gen, value=" · ".join(pokemon), inline=False)

        await ctx.send(embed=embed)

    @commands.command()
    async def pick(self, ctx: commands.Context, *, name: str):
        try:
            self.db.fetch_member(ctx.author)

            return await ctx.send(
                "You have already chosen a starter pokémon! View your pokémon with `p!pokemon`."
            )

        except DoesNotExist:
            pass

        if name.lower() not in STARTER_POKEMON:
            return await ctx.send(
                "Please select one of the starter pokémon. To view them, type `p!start`."
            )

        species = GameData.species_by_name(name)

        member = mongo.Member.objects.create(
            id=ctx.author.id,
            pokemon=[
                mongo.Pokemon(
                    number=1,
                    species_id=species.id,
                    level=1,
                    xp=0,
                    owner_id=ctx.author.id,
                )
            ],
        )

        member.update(inc__next_id=1)

        await ctx.send(
            f"Congratulations on entering the world of pokémon! {species} is your first pokémon. Type `p!info` to view it!"
        )

    @checks.has_started()
    @commands.command()
    async def info(self, ctx: commands.Context, *, number: str = None):
        member = self.db.fetch_member(ctx.author)

        if number is None:
            pokemon = member.selected_pokemon
        elif number.isdigit():
            try:
                pokemon = member.pokemon.get(number=int(number))
            except DoesNotExist:
                return await ctx.send("Could not find a pokemon with that number.")
        elif number == "latest":
            pokemon = member.pokemon[member.pokemon.count() - 1]
        else:
            return await ctx.send(
                "Please use `p!info` to view your selected pokémon, "
                "`p!info <number>` to view another pokémon, "
                "or `p!info latest` to view your latest pokémon."
            )

        embed = discord.Embed()
        embed.color = 0xF44336
        embed.title = f"Level {pokemon.level} {pokemon.species}"
        embed.set_image(url=GameData.get_image_url(pokemon.species_id))
        embed.set_thumbnail(url=ctx.author.avatar_url)

        info = (
            f"**XP:** {pokemon.xp}/{pokemon.max_xp}",
            f"**Nature:** {pokemon.nature}",
        )

        embed.add_field(name="Details", value="\n".join(info), inline=False)

        stats = (
            f"**HP:** {pokemon.hp} – IV: {pokemon.iv_hp}/31",
            f"**Attack:** {pokemon.atk} – IV: {pokemon.iv_atk}/31",
            f"**Defense:** {pokemon.defn} – IV: {pokemon.iv_defn}/31",
            f"**Sp. Atk:** {pokemon.satk} – IV: {pokemon.iv_satk}/31",
            f"**Sp. Def:** {pokemon.sdef} – IV: {pokemon.iv_sdef}/31",
            f"**Speed:** {pokemon.spd} – IV: {pokemon.iv_spd}/31",
            f"**Total IV:** {pokemon.iv_percentage * 100:.2f}%",
        )

        embed.add_field(name="Stats", value="\n".join(stats), inline=False)

        await ctx.send(embed=embed)

    @checks.has_started()
    @commands.command()
    async def select(self, ctx: commands.Context, *, number: int):
        member = self.db.fetch_member(ctx.author)

        try:
            pokemon = member.pokemon.get(number=number)
        except DoesNotExist:
            return await ctx.send("Could not find a pokemon with that number.")

        member.update(selected=number)
        await ctx.send(
            f"You selected your level {pokemon.level} {pokemon.species}. No. {pokemon.number}."
        )

    @checks.has_started()
    @commands.command()
    async def order(self, ctx: commands.Context, *, sort: str):
        if (s := sort.lower()) not in ("number", "iv", "level", "abc"):
            return await ctx.send(
                "Please specify either `number`, `IV`, `level`, or `abc`."
            )

        self.db.update_member(ctx.author, order_by=s)

        await ctx.send(f"Now ordering pokemon by {'IV' if s == 'iv' else s}.")

    @checks.has_started()
    @commands.command()
    async def pokemon(self, ctx: commands.Context, *, page: int = 1):
        member = self.db.fetch_member(ctx.author)

        pokemon = sorted(member.pokemon, key=SORTING_FUNCTIONS[member.order_by])

        pgstart = (page - 1) * 20

        if pgstart >= len(pokemon) or pgstart < 0:
            return await ctx.send("You don't have that many pages.")

        pgend = min(page * 20, len(pokemon))

        page = [
            f"**{p.species}** | Level: {p.level} | Number: {p.number} | IV: {p.iv_percentage * 100:.2f}%"
            for p in pokemon[pgstart:pgend]
        ]

        embed = discord.Embed()
        embed.color = 0xF44336
        embed.title = f"Your pokémon"
        embed.description = "\n".join(page)
        embed.set_footer(text=f"Showing {pgstart + 1}–{pgend} out of {len(pokemon)}.")

        await ctx.send(embed=embed)
