from functools import cached_property

import discord
from discord.ext import commands, flags

from .database import Database
from .helpers import checks, mongo
from .helpers.models import GameData, SpeciesNotFoundError
from .helpers.constants import *


class Pokemon(commands.Cog):
    """Pokémon-related commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @property
    def db(self) -> Database:
        return self.bot.get_cog("Database")

    @checks.has_started()
    @commands.command()
    async def redeem(self, ctx: commands.Context, *, species: str = None):
        """Redeem a pokémon."""

        member = await self.db.fetch_member(ctx.author)

        if species is None:
            embed = discord.Embed()
            embed.color = 0xF44336
            embed.title = f"Your Redeems: {member.redeems}"
            embed.description = "You can use redeems to receive any pokémon of your choice. Currently, you can only receive redeems from giveaways."

            embed.add_field(
                name="p!redeem <pokémon>",
                value="Use a redeem to receive a pokémon of your choice.",
            )

            return await ctx.send(embed=embed)

        if member.redeems == 0:
            return await ctx.send("You don't have any redeems!")

        try:
            species = GameData.species_by_name(species)
        except SpeciesNotFoundError:
            return await ctx.send(f"Could not find a pokemon matching `{species}`.")

        if not species.catchable:
            return await ctx.send("You can't redeem this pokémon!")

        await self.db.update_member(
            ctx.author,
            {
                "$inc": {"next_id": 1, "redeems": -1},
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

        await ctx.send(
            f"You used a redeem and received a {species}! View it with `p!info latest`."
        )

    @commands.command(aliases=["nick"])
    async def nickname(self, ctx: commands.Context, *, nickname: str):
        if nickname == "reset":
            nickname = None

        if len(nickname) > 100:
            return await ctx.send("That nickname is too long.")

        member = await self.db.fetch_member(ctx.author)
        await self.db.update_pokemon(
            ctx.author, member.selected, {"$set": {"pokemon.$.nickname": nickname}},
        )

        if nickname == None:
            await ctx.send(
                f"Removed nickname for your level {member.selected_pokemon.level} {member.selected_pokemon.species}."
            )
        else:
            await ctx.send(
                f"Changed nickname to `{nickname}` for your level {member.selected_pokemon.level} {member.selected_pokemon.species}."
            )

    @commands.command(aliases=["fav"])
    async def favorite(self, ctx: commands.Context, number: str = None):

        member = await self.db.fetch_member(ctx.author)

        if number is None:
            pokemon = member.selected_pokemon

        elif number.isdigit():
            try:
                pokemon = next(
                    filter(lambda x: x.number == int(number), member.pokemon)
                )
            except StopIteration:
                return await ctx.send("Could not find a pokemon with that number.")

        elif number == "latest":
            pokemon = member.pokemon[-1]

        else:
            return await ctx.send(
                "Please use `p!favorite` to favorite your selected pokémon, "
                "`p!favorite <number>` to favorite another pokémon, "
                "or `p!favorite latest` to favorite your latest pokémon."
            )

        member = await self.db.fetch_member(ctx.author)
        await self.db.update_pokemon(
            ctx.author, pokemon.number, {"$set": {"pokemon.$.favorite": True}},
        )

        name = str(pokemon.species)

        if pokemon.nickname is not None:
            name += f' "{pokemon.nickname}"'

        await ctx.send(f"Favorited your level {pokemon.level} {name}.")

    @commands.command(aliases=["unfav"])
    async def unfavorite(self, ctx: commands.Context, number: str = None):

        member = await self.db.fetch_member(ctx.author)

        if number is None:
            pokemon = member.selected_pokemon

        elif number.isdigit():
            try:
                pokemon = next(
                    filter(lambda x: x.number == int(number), member.pokemon)
                )
            except StopIteration:
                return await ctx.send("Could not find a pokemon with that number.")

        elif number == "latest":
            pokemon = member.pokemon[-1]

        else:
            return await ctx.send(
                "Please use `p!unfavorite` to unfavorite your selected pokémon, "
                "`p!unfavorite <number>` to unfavorite another pokémon, "
                "or `p!unfavorite latest` to unfavorite your latest pokémon."
            )

        member = await self.db.fetch_member(ctx.author)
        await self.db.update_pokemon(
            ctx.author, pokemon.number, {"$set": {"pokemon.$.favorite": False}},
        )

        name = str(pokemon.species)

        if pokemon.nickname is not None:
            name += f' "{pokemon.nickname}"'

        await ctx.send(f"Unfavorited your level {pokemon.level} {name}.")

    @commands.command()
    async def start(self, ctx: commands.Context):
        """View the starter pokémon."""

        embed = discord.Embed()
        embed.color = 0xF44336
        embed.title = "Welcome to the world of Pokémon!"
        embed.description = "To start, choose one of the starter pokémon using the `p!pick <pokemon>` command. "

        for gen, pokemon in STARTER_GENERATION.items():
            embed.add_field(name=gen, value=" · ".join(pokemon), inline=False)

        await ctx.send(embed=embed)

    @commands.command()
    async def pick(self, ctx: commands.Context, *, name: str):
        """Choose a starter pokémon to get started."""

        member = await self.db.fetch_member(ctx.author)

        if member is not None:
            return await ctx.send(
                "You have already chosen a starter pokémon! View your pokémon with `p!pokemon`."
            )

        if name.lower() not in STARTER_POKEMON:
            return await ctx.send(
                "Please select one of the starter pokémon. To view them, type `p!start`."
            )

        species = GameData.species_by_name(name)

        member = mongo.Member(
            id=ctx.author.id,
            pokemon=[
                mongo.Pokemon.random(
                    number=1,
                    species_id=species.id,
                    level=1,
                    xp=0,
                    owner_id=ctx.author.id,
                )
            ],
            next_id=2,
            selected=1,
        )

        await member.commit()

        await ctx.send(
            f"Congratulations on entering the world of pokémon! {species} is your first pokémon. Type `p!info` to view it!"
        )

    @checks.has_started()
    @commands.command()
    async def info(self, ctx: commands.Context, *, number: str = None):
        """View a specific pokémon from your collection."""

        member = await self.db.fetch_member(ctx.author)

        if number is None:
            pokemon = member.selected_pokemon

        elif number.isdigit():
            try:
                pokemon = next(
                    filter(lambda x: x.number == int(number), member.pokemon)
                )
            except StopIteration:
                return await ctx.send("Could not find a pokemon with that number.")

        elif number == "latest":
            pokemon = member.pokemon[-1]

        else:
            return await ctx.send(
                "Please use `p!info` to view your selected pokémon, "
                "`p!info <number>` to view another pokémon, "
                "or `p!info latest` to view your latest pokémon."
            )

        embed = discord.Embed()
        embed.color = 0xF44336
        embed.title = f"Level {pokemon.level} {pokemon.species}"

        if pokemon.nickname is not None:
            embed.title += f' "{pokemon.nickname}"'

        embed.set_image(url=pokemon.species.image_url)
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
        embed.set_footer(
            text=f"Displaying pokémon {pokemon.number} out of {member.pokemon[-1].number}."
        )

        await ctx.send(embed=embed)

    @checks.has_started()
    @commands.command()
    async def select(self, ctx: commands.Context, *, number: int):
        """Select a specific pokémon from your collection."""

        member = await self.db.fetch_member(ctx.author)
        try:
            pokemon = next(filter(lambda x: x.number == number, member.pokemon))
        except StopIteration:
            return await ctx.send("Could not find a pokemon with that number.")

        await self.db.update_member(
            ctx.author, {"$set": {f"selected": number}},
        )

        await ctx.send(
            f"You selected your level {pokemon.level} {pokemon.species}. No. {pokemon.number}."
        )

    @checks.has_started()
    @commands.command()
    async def order(self, ctx: commands.Context, *, sort: str):
        """Change how your pokémon are ordered."""

        if (s := sort.lower()) not in ("number", "iv", "level", "abc", "pokedex"):
            return await ctx.send(
                "Please specify either `number`, `IV`, `level`, `pokedex`, or `abc`."
            )

        await self.db.update_member(
            ctx.author, {"$set": {f"order_by": s}},
        )

        await ctx.send(f"Now ordering pokemon by {'IV' if s == 'iv' else s}.")

    # Filter
    @flags.add_flag("page", nargs="?", default=1, type=int)
    @flags.add_flag("--mythical", action="store_true")
    @flags.add_flag("--legendary", action="store_true")
    @flags.add_flag("--ub", action="store_true")
    @flags.add_flag("--favorite", action="store_true")
    @flags.add_flag("--name")
    @flags.add_flag("--level", type=int)

    # Stats
    @flags.add_flag("--hp", nargs="+")
    @flags.add_flag("--atk", nargs="+")
    @flags.add_flag("--def", nargs="+")
    @flags.add_flag("--spatk", nargs="+")
    @flags.add_flag("--spdef", nargs="+")
    @flags.add_flag("--spd", nargs="+")

    # IV
    @flags.add_flag("--hpiv", nargs="+")
    @flags.add_flag("--atkiv", nargs="+")
    @flags.add_flag("--defiv", nargs="+")
    @flags.add_flag("--spatkiv", nargs="+")
    @flags.add_flag("--spdefiv", nargs="+")
    @flags.add_flag("--spdiv", nargs="+")
    @flags.add_flag("--iv", nargs="+")

    # Pokemon
    @checks.has_started()
    @flags.command()
    async def pokemon(self, ctx: commands.Context, **flags):
        """List the pokémon in your collection."""

        member = await self.db.fetch_member(ctx.author)
        pokemon = member.pokemon

        # Filter pokemon

        if flags["mythical"]:
            pokemon = [p for p in pokemon if p.species.mythical]

        if flags["legendary"]:
            pokemon = [p for p in pokemon if p.species.legendary]

        if flags["ub"]:
            pokemon = [p for p in pokemon if p.species.ultra_beast]

        if flags["favorite"]:
            pokemon = [p for p in pokemon if p.favorite]

        if flags["name"] is not None:
            pokemon = [
                p
                for p in pokemon
                if flags["name"].lower() in p.species.correct_guesses
                or flags["name"].lower() == (p.nickname or "").lower()
            ]

        if flags["level"] is not None:
            pokemon = [p for p in pokemon if p.level == flags["level"]]

        # Numerical flags

        for flag in FILTER_BY_NUMERICAL:
            if (text := flags[flag]) is not None:

                if len(text) == 0:
                    return await ctx.send(
                        f"Please specify a numerical value for `--{flag}`"
                    )

                if len(text) > 2:
                    return await ctx.send(
                        f"Received too many arguments for `--{flag} {' '.join(text)}`"
                    )

                ops = text

                # Entered just a number
                if len(text) == 1 and text[0].isdigit():
                    ops = ["=", text[0]]

                elif len(text) == 1 and not text[0][0].isdigit():
                    ops = [text[0][0], text[0][1:]]

                if ops[0] not in ("<", "=", ">") or not ops[1].isdigit():
                    return await ctx.send(f"couldn't parse `--{flag} {' '.join(text)}`")

                if ops[0] == "<":
                    pokemon = [
                        p for p in pokemon if FILTER_BY_NUMERICAL[flag](p) < int(ops[1])
                    ]
                elif ops[0] == "=":
                    pokemon = [
                        p
                        for p in pokemon
                        if FILTER_BY_NUMERICAL[flag](p) == int(ops[1])
                    ]
                elif ops[0] == ">":
                    pokemon = [
                        p for p in pokemon if FILTER_BY_NUMERICAL[flag](p) > int(ops[1])
                    ]

        # Sort pokemon

        pokemon = sorted(pokemon, key=SORTING_FUNCTIONS[member.order_by])

        # If nothing matches

        if len(pokemon) == 0:
            return await ctx.send("Found no pokémon matching those parameters.")

        # Pagination

        pgstart = (flags["page"] - 1) * 20

        if pgstart >= len(pokemon) or pgstart < 0:
            return await ctx.send("There are no pokémon on this page.")

        pgend = min(flags["page"] * 20, len(pokemon))

        def nick(p):
            name = str(p.species)
            if p.nickname is not None:
                name += f' "{p.nickname}"'
            if p.favorite:
                name = "⭐ " + name
            return name

        page = [
            f"**{nick(p)}** | Level: {p.level} | Number: {p.number} | IV: {p.iv_percentage * 100:.2f}%"
            for p in pokemon[pgstart:pgend]
        ]

        # Send embed

        embed = discord.Embed()
        embed.color = 0xF44336
        embed.title = f"Your pokémon"
        embed.description = "\n".join(page)
        embed.set_footer(text=f"Showing {pgstart + 1}–{pgend} out of {len(pokemon)}.")

        await ctx.send(embed=embed)
