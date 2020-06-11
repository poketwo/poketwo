import math
from functools import cached_property

import discord
from discord.ext import commands, flags

from .database import Database
from .helpers import checks, mongo
from .helpers.constants import *
from .helpers.models import GameData, SpeciesNotFoundError
from .helpers.pagination import Paginator


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

        member = await self.db.fetch_member_info(ctx.author)

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
        """Change the nickname for your pokémon."""

        if len(nickname) > 100:
            return await ctx.send("That nickname is too long.")

        if nickname == "reset":
            nickname = None

        member = await self.db.fetch_member_info(ctx.author)
        pokemon = await self.db.fetch_pokemon(ctx.author, member.selected)
        pokemon = pokemon.pokemon[0]

        await self.db.update_pokemon(
            ctx.author, member.selected, {"$set": {"pokemon.$.nickname": nickname}},
        )

        if nickname == None:
            await ctx.send(
                f"Removed nickname for your level {pokemon.level} {pokemon.species}."
            )
        else:
            await ctx.send(
                f"Changed nickname to `{nickname}` for your level {pokemon.level} {pokemon.species}."
            )

    @commands.command(aliases=["fav"])
    async def favorite(self, ctx: commands.Context, number: str = None):
        """Mark a pokémon as a favorite."""

        member = await self.db.fetch_member_info(ctx.author)

        if number is None:
            pokemon = member.selected
        elif number.isdigit():
            pokemon = int(number)
        elif number == "latest":
            pokemon = -1

        else:
            return await ctx.send(
                "Please use `p!favorite` to favorite your selected pokémon, "
                "`p!favorite <number>` to favorite another pokémon, "
                "or `p!favorite latest` to favorite your latest pokémon."
            )

        pokemon = await self.db.fetch_pokemon(ctx.author, pokemon)

        if pokemon is None:
            return await ctx.send("Couldn't find that pokémon!")

        pokemon = pokemon.pokemon[0]

        await self.db.update_pokemon(
            ctx.author,
            pokemon.number,
            {"$set": {"pokemon.$.favorite": not pokemon.favorite}},
        )

        name = str(pokemon.species)

        if pokemon.nickname is not None:
            name += f' "{pokemon.nickname}"'

        if pokemon.favorite:
            await ctx.send(f"Unfavorited your level {pokemon.level} {name}.")
        else:
            await ctx.send(f"Favorited your level {pokemon.level} {name}.")

    @commands.command(aliases=["unfav"])
    async def unfavorite(self, ctx: commands.Context, number: str = None):
        """This command has been removed. Instead, use `p!favorite`, which will toggle favorite on a pokémon."""

        await ctx.send(
            f"This command has been removed. Instead, use `p!favorite`, which will toggle favorite on a pokémon."
        )

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

        member = await self.db.fetch_member_info(ctx.author)

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

        num = await self.db.fetch_pokemon_count(ctx.author)
        num = num[0]["num_matches"]

        if number == "latest":
            pidx = -1
        else:
            if number is None:
                member = await self.db.fetch_member_info(ctx.author)
                pidx = await self.db.fetch_pokemon_idx(ctx.author, member.selected)
            elif number.isdigit():
                pidx = await self.db.fetch_pokemon_idx(ctx.author, int(number))
            else:
                return await ctx.send(
                    "Please use `p!info` to view your selected pokémon, "
                    "`p!info <number>` to view another pokémon, "
                    "or `p!info latest` to view your latest pokémon."
                )

            if len(pidx) == 0:
                return await ctx.send("Couldn't find that pokémon!")

            pidx = pidx[0]["idx"]

        async def get_page(pidx, clear):
            pokemon = await self.db.fetch_pokemon_by_idx(ctx.author, pidx)

            if pokemon is None:
                return await clear("Couldn't find that pokémon!")

            pokemon = pokemon.pokemon[0]

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
            embed.set_footer(text=f"Displaying pokémon number {pokemon.number}.")

            return embed

        paginator = Paginator(get_page, num_pages=num)
        await paginator.send(self.bot, ctx, pidx)

    @checks.has_started()
    @commands.command()
    async def select(self, ctx: commands.Context, *, number: str = ""):
        """Select a specific pokémon from your collection."""

        member = await self.db.fetch_member_info(ctx.author)

        if number.isdigit():
            number = int(number)
        elif number == "latest":
            number = -1

        else:
            return await ctx.send(
                "`p!select <number>` to select a pokémon "
                "or `p!select latest` to select your latest pokémon."
            )

        pokemon = await self.db.fetch_pokemon(ctx.author, number)

        if pokemon is None:
            return await ctx.send("Couldn't find that pokémon!")

        pokemon = pokemon.pokemon[0]

        await self.db.update_member(
            ctx.author, {"$set": {f"selected": number}},
        )

        await ctx.send(
            f"You selected your level {pokemon.level} {pokemon.species}. No. {pokemon.number}."
        )

    @checks.has_started()
    @commands.command()
    async def order(self, ctx: commands.Context, *, sort: str = ""):
        """Change how your pokémon are ordered."""

        if (s := sort.lower()) not in ("number", "iv", "level", "pokedex"):
            return await ctx.send(
                "Please specify either `number`, `IV`, `level`, or `pokedex`."
            )

        await self.db.update_member(
            ctx.author, {"$set": {f"order_by": s}},
        )

        await ctx.send(f"Now ordering pokemon by {'IV' if s == 'iv' else s}.")

    def parse_numerical_flag(self, text):
        if not (1 <= len(text) <= 2):
            return None

        ops = text

        if len(text) == 1 and text[0].isdigit():
            ops = ["=", text[0]]

        elif len(text) == 1 and not text[0][0].isdigit():
            ops = [text[0][0], text[0][1:]]

        if ops[0] not in ("<", "=", ">") or not ops[1].isdigit():
            return None

        return ops

    # Filter
    @flags.add_flag("page", nargs="?", type=int, default=1)
    @flags.add_flag("--mythical", action="store_true")
    @flags.add_flag("--legendary", action="store_true")
    @flags.add_flag("--ub", action="store_true")
    @flags.add_flag("--favorite", action="store_true")
    @flags.add_flag("--name")
    @flags.add_flag("--level", type=int)

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

        if flags["page"] < 1:
            return await ctx.send("Page must be positive!")

        aggregations = []

        # # Filter pokemon

        if flags["mythical"]:
            aggregations.append(
                {"$match": {"pokemon.species_id": {"$in": GameData.list_mythical()}}}
            )

        if flags["legendary"]:
            aggregations.append(
                {"$match": {"pokemon.species_id": {"$in": GameData.list_legendary()}}}
            )

        if flags["ub"]:
            aggregations.append(
                {"$match": {"pokemon.species_id": {"$in": GameData.list_ub()}}}
            )

        if flags["favorite"]:
            aggregations.append({"$match": {"pokemon.favorite": True}})

        if flags["name"] is not None:
            try:
                species = GameData.species_by_name(flags["name"])
            except SpeciesNotFoundError:
                return await ctx.send("Couldn't find a pokémon species with that name.")

            aggregations.append({"$match": {"pokemon.species_id": species.id}})

        if flags["level"] is not None:
            aggregations.append({"$match": {"pokemon.level": flags["level"]}})

        # Numerical flags

        for flag, expr in FILTER_BY_NUMERICAL.items():
            if (text := flags[flag]) is not None:
                ops = self.parse_numerical_flag(text)

                if ops is None:
                    return await ctx.send(f"Couldn't parse `--{flag} {' '.join(text)}`")

                if ops[0] == "<":
                    aggregations.extend(
                        [
                            {"$addFields": {flag: expr}},
                            {"$match": {flag: {"$lt": int(ops[1])}}},
                        ]
                    )
                elif ops[0] == "=":
                    aggregations.extend(
                        [
                            {"$addFields": {flag: expr}},
                            {"$match": {flag: {"$eq": int(ops[1])}}},
                        ]
                    )
                elif ops[0] == ">":
                    aggregations.extend(
                        [
                            {"$addFields": {flag: expr}},
                            {"$match": {flag: {"$gt": int(ops[1])}}},
                        ]
                    )

        # Pagination

        member = await self.db.fetch_member_info(ctx.author)

        aggregations.extend(
            [
                {"$addFields": {"sorting": SORTING_FUNCTIONS[member.order_by]}},
                {"$sort": {"sorting": 1}},
            ]
        )

        def nick(p):
            name = str(p.species)
            if p.nickname is not None:
                name += f' "{p.nickname}"'
            if p.favorite:
                name = "❤️ " + name
            return name

        pokemon = await self.db.fetch_pokemon_count(
            ctx.author, aggregations=aggregations
        )

        if len(pokemon) == 0:
            return await ctx.send("Found no pokémon matching this search.")

        num = pokemon[0]["num_matches"]

        async def get_page(pidx, clear):

            pgstart = pidx * 20
            pokemon = await self.db.fetch_pokemon_list(
                ctx.author, pgstart, 20, aggregations=aggregations
            )

            pokemon = [mongo.Pokemon.build_from_mongo(x["pokemon"]) for x in pokemon]

            if len(pokemon) == 0:
                return await clear("There are no pokémon on this page!")

            page = [
                f"**{nick(p)}** | Level: {p.level} | Number: {p.number} | IV: {p.iv_percentage * 100:.2f}%"
                for p in pokemon
            ]

            # Send embed

            embed = discord.Embed()
            embed.color = 0xF44336
            embed.title = f"Your pokémon"
            embed.description = "\n".join(page)
            embed.set_footer(
                text=f"Showing {pgstart + 1}–{min(pgstart + 20, num)} out of {num}."
            )

            return embed

        paginator = Paginator(get_page, num_pages=math.ceil(num / 20))
        await paginator.send(self.bot, ctx, flags["page"] - 1)
