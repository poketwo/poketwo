import asyncio
import math
from functools import cached_property

import discord
from discord.ext import commands, flags

from .database import Database
from .helpers import checks, mongo, converters
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

            embed.add_field(
                name="p!redeemspawn <pokémon>",
                value="Use a redeem to spawn a pokémon of your choice in the current channel (careful, if something else spawns, it'll be overrided).",
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
                "$inc": {"redeems": -1},
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

        await ctx.send(
            f"You used a redeem and received a {species}! View it with `p!info latest`."
        )

    @checks.has_started()
    @commands.command()
    async def redeemspawn(self, ctx: commands.Context, *, species: str = None):
        """Redeem spawn a pokémon."""

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

            embed.add_field(
                name="p!redeemspawn <pokémon>",
                value="Use a redeem to spawn a pokémon of your choice in the current channel *(careful, if something else spawns, it'll be overrided)*.",
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

        if ctx.channel.id == 720944005856100452:
            return await ctx.send("You can't redeemspawn a pokémon here!")

        await self.db.update_member(
            ctx.author, {"$inc": {"redeems": -1}},
        )

        await self.bot.get_cog("Spawning").spawn_pokemon(ctx.channel, species)

    @commands.command(aliases=["nick"])
    async def nickname(self, ctx: commands.Context, *, nickname: str):
        """Change the nickname for your pokémon."""

        if len(nickname) > 100:
            return await ctx.send("That nickname is too long.")

        if nickname == "reset":
            nickname = None

        member = await self.db.fetch_member_info(ctx.author)
        pokemon = await self.db.fetch_pokemon(ctx.author, member.selected)

        await self.db.update_member(
            ctx.author, {"$set": {f"pokemon.{member.selected}.nickname": nickname}},
        )

        if nickname == None:
            await ctx.send(
                f"Removed nickname for your level {pokemon.level} {pokemon.species}."
            )
        else:
            await ctx.send(
                f"Changed nickname to `{nickname}` for your level {pokemon.level} {pokemon.species}."
            )

    @commands.command(aliases=["fav"], rest_is_raw=True)
    async def favorite(self, ctx: commands.Context, *, pokemon: converters.Pokemon):
        """Mark a pokémon as a favorite."""

        pokemon, idx = pokemon

        if pokemon is None:
            return await ctx.send("Couldn't find that pokémon!")

        num = await self.db.fetch_pokemon_count(ctx.author)
        idx = idx % num

        await self.db.update_member(
            ctx.author, {"$set": {f"pokemon.{idx}.favorite": not pokemon.favorite}},
        )

        name = str(pokemon.species)

        if pokemon.nickname is not None:
            name += f' "{pokemon.nickname}"'

        if pokemon.favorite:
            await ctx.send(f"Unfavorited your level {pokemon.level} {name}.")
        else:
            await ctx.send(f"Favorited your level {pokemon.level} {name}.")

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

        starter = mongo.Pokemon.random(species_id=species.id, level=1, xp=0)

        member = mongo.Member(id=ctx.author.id, pokemon=[starter], selected=0)

        await member.commit()

        await ctx.send(
            f"Congratulations on entering the world of pokémon! {species} is your first pokémon. Type `p!info` to view it!"
        )

    @checks.has_started()
    @commands.command(rest_is_raw=True)
    async def info(self, ctx: commands.Context, *, pokemon: converters.Pokemon):
        """View a specific pokémon from your collection."""

        pokemon, idx = pokemon

        num = await self.db.fetch_pokemon_count(ctx.author)

        pidx = idx % num

        async def get_page(pidx, clear):
            pokemon = await self.db.fetch_pokemon(ctx.author, pidx)

            if pokemon is None:
                return await clear("Couldn't find that pokémon!")

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
            embed.set_footer(text=f"Displaying pokémon {pidx + 1} out of {num}.")

            return embed

        paginator = Paginator(get_page, num_pages=num)
        await paginator.send(self.bot, ctx, pidx)

    @checks.has_started()
    @commands.command(rest_is_raw=True)
    async def select(
        self, ctx: commands.Context, *, pokemon: converters.Pokemon(accept_blank=False)
    ):
        """Select a specific pokémon from your collection."""

        pokemon, idx = pokemon

        if pokemon is None:
            return await ctx.send("Couldn't find that pokémon!")

        num = await self.db.fetch_pokemon_count(ctx.author)
        idx = idx % num

        await self.db.update_member(
            ctx.author, {"$set": {f"selected": idx}},
        )

        await ctx.send(
            f"You selected your level {pokemon.level} {pokemon.species}. No. {idx + 1}."
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

    async def create_filter(self, flags, ctx):
        aggregations = []

        if "mythical" in flags and flags["mythical"]:
            aggregations.append(
                {"$match": {"pokemon.species_id": {"$in": GameData.list_mythical()}}}
            )

        if "legendary" in flags and flags["legendary"]:
            aggregations.append(
                {"$match": {"pokemon.species_id": {"$in": GameData.list_legendary()}}}
            )

        if "ub" in flags and flags["ub"]:
            aggregations.append(
                {"$match": {"pokemon.species_id": {"$in": GameData.list_ub()}}}
            )

        if "type" in flags and flags["type"]:
            aggregations.append(
                {
                    "$match": {
                        "pokemon.species_id": {"$in": GameData.list_type(flags["type"])}
                    }
                }
            )

        if "favorite" in flags and flags["favorite"]:
            aggregations.append({"$match": {"pokemon.favorite": True}})

        if "name" in flags and flags["name"] is not None:
            try:
                species = GameData.species_by_name(flags["name"])
            except SpeciesNotFoundError:
                await ctx.send("Couldn't find a pokémon species with that name.")
                return

            aggregations.append({"$match": {"pokemon.species_id": species.id}})

        if "level" in flags and flags["level"] is not None:
            aggregations.append({"$match": {"pokemon.level": flags["level"]}})

        # Numerical flags

        for flag, expr in FILTER_BY_NUMERICAL.items():
            if flag in flags and (text := flags[flag]) is not None:
                ops = self.parse_numerical_flag(text)

                if ops is None:
                    await ctx.send(f"Couldn't parse `--{flag} {' '.join(text)}`")
                    return

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

        return aggregations

    @checks.has_started()
    @commands.command()
    async def release(self, ctx: commands.Context, *args):
        """Release pokémon from your collection."""

        if ctx.author.id in self.bot.get_cog("Trading").users:
            return await ctx.send("You can't do that in a trade!")

        member = await self.db.fetch_member_info(ctx.author)
        num = await self.db.fetch_pokemon_count(ctx.author)

        converter = converters.Pokemon(accept_blank=False)

        dec = 0

        idxs = set()

        if len(args) > 1:
            await ctx.send(f"Are you sure you want to release these pokémon? [y/N]")

            def check(m):
                return m.channel.id == ctx.channel.id and m.author.id == ctx.author.id

            try:
                msg = await self.bot.wait_for("message", timeout=15, check=check)

                if msg.content.lower() != "y":
                    return await ctx.send("Aborted.")
            except asyncio.TimeoutError:
                return await ctx.send("Time's up. Aborted.")

        if len(args) >= 10:
            await ctx.send(f"Releasing {len(args)} pokémon, this might take a while...")

        for number in args:

            try:
                pokemon, idx = await converter.convert(ctx, number)
            except converters.PokemonConversionError:
                await ctx.send(f"{number}: Not a valid pokémon!")
                continue

            if pokemon is None:
                await ctx.send(f"{number}: Couldn't find that pokémon!")
                continue

            # can't release selected/fav

            if idx in idxs:
                await ctx.send(f"{number}: This pokémon is already being released!")

            if member.selected == idx:
                await ctx.send(f"{number}: You can't release your selected pokémon!")
                continue

            if pokemon.favorite:
                await ctx.send(f"{number}: You can't release favorited pokémon!")
                continue

            idxs.add(idx)

            if (idx % num) < member.selected:
                dec += 1

        if len(args) == 1:
            await ctx.send(
                f"Are you sure you want to release your level {pokemon.level} {pokemon.species}. No. {idx + 1}? This action is irreversible! [y/N]"
            )

            def check(m):
                return m.channel.id == ctx.channel.id and m.author.id == ctx.author.id

            try:
                msg = await self.bot.wait_for("message", timeout=15, check=check)

                if msg.content.lower() != "y":
                    return await ctx.send("Aborted.")
            except asyncio.TimeoutError:
                return await ctx.send("Time's up. Aborted.")

        # confirmed, release

        unsets = {f"pokemon.{idx}": 1 for idx in idxs}

        await self.db.update_member(ctx.author, {"$unset": unsets})

        await self.db.update_member(
            ctx.author, {"$inc": {f"selected": -dec}, "$pull": {f"pokemon": None}}
        )

        await ctx.send(f"Finished releasing pokémon.")

    @commands.command()
    async def healschema(self, ctx: commands.Context):
        await self.db.update_member(ctx.author, {"$pull": {f"pokemon": None}})
        await ctx.send("Trying to heal schema...")

    @flags.add_flag("--name")
    @flags.add_flag("--type", type=str)
    @flags.add_flag("--hpiv", nargs="+")
    @flags.add_flag("--atkiv", nargs="+")
    @flags.add_flag("--defiv", nargs="+")
    @flags.add_flag("--spatkiv", nargs="+")
    @flags.add_flag("--spdefiv", nargs="+")
    @flags.add_flag("--spdiv", nargs="+")
    @flags.add_flag("--iv", nargs="+")
    @checks.has_started()
    @flags.command()
    async def releaseall(self, ctx: commands.Context, **flags):
        """Release the pokémon in your collection."""

        if ctx.author.id in self.bot.get_cog("Trading").users:
            return await ctx.send("You can't do that in a trade!")

        aggregations = await self.create_filter(flags, ctx)

        if aggregations is None:
            return

        member = await self.db.fetch_member_info(ctx.author)

        aggregations.extend(
            [
                {"$match": {"idx": {"$not": {"$eq": member.selected}}}},
                {"$match": {"pokemon.favorite": {"$not": {"$eq": True}}}},
            ]
        )

        num = await self.db.fetch_pokemon_count(ctx.author, aggregations=aggregations)

        if num == 0:
            return await ctx.send(
                "Found no pokémon matching this search (excluding favorited and selected pokémon)."
            )

        # confirm

        await ctx.send(
            f"Are you sure you want to release {num} pokémon? Favorited and selected pokémon won't be removed. Type `confirm release {num}` to confirm."
        )

        def check(m):
            return m.channel.id == ctx.channel.id and m.author.id == ctx.author.id

        try:
            msg = await self.bot.wait_for("message", timeout=15, check=check)

            if msg.content != f"confirm release {num}":
                return await ctx.send("Aborted.")

        except asyncio.TimeoutError:
            return await ctx.send("Time's up. Aborted.")

        # confirmed, release all

        await ctx.send(f"Releasing {num} pokémon, this might take a while...")

        pokemon = await self.db.fetch_pokemon_list(
            ctx.author, 0, num, aggregations=aggregations
        )

        dec = len([x for x in pokemon if x["idx"] < member.selected])

        pokemon = {f'pokemon.{x["idx"]}': 1 for x in pokemon}

        await self.db.update_member(ctx.author, {"$unset": pokemon})
        await self.db.update_member(
            ctx.author, {"$inc": {f"selected": -dec}, "$pull": {"pokemon": None}}
        )

        await ctx.send(f"You have released {num} pokémon.")

    # Filter
    @flags.add_flag("page", nargs="?", type=int, default=1)
    @flags.add_flag("--mythical", action="store_true")
    @flags.add_flag("--legendary", action="store_true")
    @flags.add_flag("--ub", action="store_true")
    @flags.add_flag("--favorite", action="store_true")
    @flags.add_flag("--name")
    @flags.add_flag("--level", type=int)
    @flags.add_flag("--type", type=str)

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

        aggregations = await self.create_filter(flags, ctx)

        if aggregations is None:
            return

        # # Filter pokemon

        # Pagination

        member = await self.db.fetch_member_info(ctx.author)

        aggregations.extend(
            [
                {"$addFields": {"sorting": SORTING_FUNCTIONS[member.order_by]}},
                {"$sort": {"sorting": 1}},
            ]
        )

        do_emojis = ctx.channel.permissions_for(
            ctx.guild.get_member(self.bot.user.id)
        ).external_emojis

        def nick(p):
            if do_emojis:
                name = (
                    str(EMOJIS[p.species.dex_number]).replace("pokemon_sprite_", "")
                    + " "
                )
            else:
                name = ""

            name += str(p.species)

            if p.nickname is not None:
                name += ' "' + p.nickname + '"'

            if p.favorite:
                if do_emojis:
                    name += f" {EMOJIS.heart}".replace("red_heart", "h")
                else:
                    name += " ❤️"

            return name

        def padn(p, idx, n):
            return " " * (len(str(n)) - len(str(idx))) + str(idx)

        num = await self.db.fetch_pokemon_count(ctx.author, aggregations=aggregations)

        if num == 0:
            return await ctx.send("Found no pokémon matching this search.")

        async def get_page(pidx, clear):

            pgstart = pidx * 20
            pokemon = await self.db.fetch_pokemon_list(
                ctx.author, pgstart, 20, aggregations=aggregations
            )

            pokemon = [
                (mongo.Pokemon.build_from_mongo(x["pokemon"]), x["idx"] + 1)
                for x in pokemon
            ]

            if len(pokemon) == 0:
                return await clear("There are no pokémon on this page!")

            maxn = max(idx for x, idx in pokemon)

            page = [
                f"`{padn(p, idx, maxn)}`   **{nick(p)}**   •   Lvl. {p.level}   •   {p.iv_percentage * 100:.2f}%"
                for p, idx in pokemon
            ]

            # Send embed

            embed = discord.Embed()
            embed.color = 0xF44336
            embed.title = f"Your pokémon"
            embed.description = "\n".join(page)[:2048]

            if do_emojis:
                embed.set_footer(
                    text=f"Showing {pgstart + 1}–{min(pgstart + 20, num)} out of {num}."
                )
            else:
                embed.set_footer(
                    text=f"Showing {pgstart + 1}–{min(pgstart + 20, num)} out of {num}. Please give me permission to Use External Emojis! It'll make this menu look a lot better."
                )

            return embed

        paginator = Paginator(get_page, num_pages=math.ceil(num / 20))
        await paginator.send(self.bot, ctx, flags["page"] - 1)
