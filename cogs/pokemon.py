import asyncio
import math
import random
from datetime import datetime
from functools import cached_property
from operator import itemgetter

import discord
from discord.ext import commands, flags

from helpers import checks, constants, converters, models, mongo, pagination

from .database import Database


class Pokemon(commands.Cog):
    """Pokémon-related commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @property
    def db(self) -> Database:
        return self.bot.get_cog("Database")

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

    @commands.command(aliases=["f", "fav", "favourite"], rest_is_raw=True)
    async def favorite(
        self, ctx: commands.Context, args: commands.Greedy[converters.Pokemon]
    ):
        """Mark a pokémon as a favorite."""

        if len(args) == 0:
            args.append(await converters.Pokemon().convert(ctx, ""))

        for pokemon, idx in args:
            if pokemon is None:
                await ctx.send(f"{idx + 1}: Couldn't find that pokémon!")
                continue

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

    @checks.has_started()
    @commands.command(rest_is_raw=True)
    @commands.bot_has_permissions(manage_messages=True)
    async def info(self, ctx: commands.Context, *, pokemon: converters.Pokemon):
        """View a specific pokémon from your collection."""

        pokemon, pidx = pokemon

        num = await self.db.fetch_pokemon_count(ctx.author)

        async def get_page(pidx, clear):
            pokemon = await self.db.fetch_pokemon(ctx.author, pidx)

            if pokemon is None:
                return await clear("Couldn't find that pokémon!")

            embed = discord.Embed()
            embed.color = 0xF44336
            embed.title = f"Level {pokemon.level} {pokemon.species}"

            if pokemon.nickname is not None:
                embed.title += f' "{pokemon.nickname}"'

            extrafooter = ""

            if pokemon.shiny:
                embed.title += " ✨"
                embed.set_image(url=pokemon.species.shiny_image_url)
                extrafooter = " Note that we don't have artwork for all shiny pokémon yet! We're working hard to make all the shiny pokémon look shiny."
            else:
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

            if pokemon.held_item:
                item = models.GameData.item_by_number(pokemon.held_item)
                gguild = self.bot.get_guild(725819081835544596)
                emote = ""
                if item.emote is not None:
                    try:
                        e = next(filter(lambda x: x.name == item.emote, gguild.emojis))
                        emote = f"{e} "
                    except StopIteration:
                        pass
                embed.add_field(
                    name="Held Item", value=f"{emote}{item.name}", inline=False
                )

            embed.set_footer(
                text=f"Displaying pokémon {pidx + 1} out of {num}." + extrafooter
            )

            return embed

        paginator = pagination.Paginator(get_page, num_pages=num)
        await paginator.send(self.bot, ctx, pidx)

    @checks.has_started()
    @commands.command(aliases=["s"], rest_is_raw=True)
    async def select(
        self, ctx: commands.Context, *, pokemon: converters.Pokemon(accept_blank=False)
    ):
        """Select a specific pokémon from your collection."""

        pokemon, idx = pokemon

        if pokemon is None:
            return await ctx.send("Couldn't find that pokémon!")

        num = await self.db.fetch_pokemon_count(ctx.author)

        await self.db.update_member(
            ctx.author, {"$set": {f"selected": idx}},
        )

        await ctx.send(
            f"You selected your level {pokemon.level} {pokemon.species}. No. {idx + 1}."
        )

    @checks.has_started()
    @commands.command(aliases=["or"])
    async def order(self, ctx: commands.Context, *, sort: str = ""):
        """Change how your pokémon are ordered."""

        sort = sort.lower()

        if sort not in ("number", "iv", "level", "pokedex"):
            return await ctx.send(
                "Please specify either `number`, `IV`, `level`, or `pokedex`."
            )

        await self.db.update_member(
            ctx.author, {"$set": {f"order_by": sort}},
        )

        await ctx.send(f"Now ordering pokemon by `{sort}`.")

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

    async def create_filter(self, flags, ctx, order_by=None):
        aggregations = []

        for x in ("mythical", "legendary", "ub", "alolan", "mega"):
            if x in flags and flags[x]:
                aggregations.append(
                    {
                        "$match": {
                            "pokemon.species_id": {
                                "$in": getattr(models.GameData, f"list_{x}")()
                            }
                        }
                    }
                )

        if "type" in flags and flags["type"]:
            all_species = [
                i for x in flags["type"] for i in models.GameData.list_type(x)
            ]

            aggregations.append(
                {"$match": {"pokemon.species_id": {"$in": all_species}}}
            )

        if "favorite" in flags and flags["favorite"]:
            aggregations.append({"$match": {"pokemon.favorite": True}})

        if "shiny" in flags and flags["shiny"]:
            aggregations.append({"$match": {"pokemon.shiny": True}})

        if "name" in flags and flags["name"] is not None:
            all_species = [
                i
                for x in flags["name"]
                for i in models.GameData.find_all_matches(" ".join(x))
            ]

            aggregations.append(
                {"$match": {"pokemon.species_id": {"$in": all_species}}}
            )

        # Numerical flags

        for flag, expr in constants.FILTER_BY_NUMERICAL.items():
            for text in flags[flag] or []:
                ops = self.parse_numerical_flag(text)

                if ops is None:
                    raise commands.BadArgument(
                        f"Couldn't parse `--{flag} {' '.join(text)}`"
                    )

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

        if order_by is not None:
            aggregations.extend(
                [
                    {"$addFields": {"sorting": constants.SORTING_FUNCTIONS[order_by]}},
                    {"$sort": {"sorting": 1}},
                ]
            )

        if "skip" in flags and flags["skip"] is not None:
            aggregations.append({"$skip": flags["skip"]})

        if "limit" in flags and flags["limit"] is not None:
            aggregations.append({"$limit": flags["limit"]})

        return aggregations

    @checks.has_started()
    @commands.command(aliases=["r"])
    async def release(
        self, ctx: commands.Context, args: commands.Greedy[converters.Pokemon]
    ):
        """Release pokémon from your collection."""

        if ctx.author.id in self.bot.trades:
            return await ctx.send("You can't do that in a trade!")

        member = await self.db.fetch_member_info(ctx.author)
        num = await self.db.fetch_pokemon_count(ctx.author)

        converter = converters.Pokemon(accept_blank=False)

        dec = 0

        idxs = set()
        mons = list()

        for pokemon, idx in args:

            if pokemon is None:
                await ctx.send(f"{idx + 1}: Couldn't find that pokémon!")
                continue

            # can't release selected/fav

            if idx in idxs:
                continue

            if member.selected == idx:
                await ctx.send(f"{idx + 1}: You can't release your selected pokémon!")
                continue

            if pokemon.favorite:
                await ctx.send(f"{idx + 1}: You can't release favorited pokémon!")
                continue

            idxs.add(idx)
            mons.append((pokemon, idx))

            if (idx % num) < member.selected:
                dec += 1

        # Confirmation msg

        if len(mons) == 0:
            return

        if len(args) == 1:
            await ctx.send(
                f"Are you sure you want to release your level {pokemon.level} {pokemon.species}. No. {idx + 1}? This action is irreversible! [y/N]"
            )
        else:
            embed = discord.Embed()
            embed.color = 0xF44336
            embed.title = (
                f"Are you sure you want to release the following pokémon? [y/N]"
            )

            embed.description = "\n".join(
                f"Level {x[0].level} {x[0].species} ({x[1] + 1})" for x in mons
            )

            await ctx.send(embed=embed)

        def check(m):
            return m.channel.id == ctx.channel.id and m.author.id == ctx.author.id

        try:
            msg = await self.bot.wait_for("message", timeout=30, check=check)

            if msg.content.lower() != "y":
                return await ctx.send("Aborted.")
        except asyncio.TimeoutError:
            return await ctx.send("Time's up. Aborted.")

        # confirmed, release

        unsets = {f"pokemon.{idx}": 1 for idx in idxs}

        # mongo is bad so we have to do two steps here

        await self.db.update_member(ctx.author, {"$unset": unsets})
        await self.db.update_member(
            ctx.author, {"$pull": {f"pokemon": {"species_id": {"$exists": False}}}},
        )
        await self.db.update_member(
            ctx.author, {"$pull": {f"pokemon": None}, "$inc": {f"selected": -dec}}
        )

        await ctx.send(f"You released {len(mons)} pokémon.")

    # Filter
    @flags.add_flag("page", nargs="?", type=int, default=1)
    @flags.add_flag("--shiny", action="store_true")
    @flags.add_flag("--alolan", action="store_true")
    @flags.add_flag("--mythical", action="store_true")
    @flags.add_flag("--legendary", action="store_true")
    @flags.add_flag("--ub", action="store_true")
    @flags.add_flag("--mega", action="store_true")
    @flags.add_flag("--name", nargs="+", action="append")
    @flags.add_flag("--type", type=str, action="append")

    # IV
    @flags.add_flag("--level", nargs="+", action="append")
    @flags.add_flag("--hpiv", nargs="+", action="append")
    @flags.add_flag("--atkiv", nargs="+", action="append")
    @flags.add_flag("--defiv", nargs="+", action="append")
    @flags.add_flag("--spatkiv", nargs="+", action="append")
    @flags.add_flag("--spdefiv", nargs="+", action="append")
    @flags.add_flag("--spdiv", nargs="+", action="append")
    @flags.add_flag("--iv", nargs="+", action="append")

    # Skip/limit
    @flags.add_flag("--skip", type=int)
    @flags.add_flag("--limit", type=int)

    # Release all
    @checks.has_started()
    @flags.command(aliases=["ra"])
    async def releaseall(self, ctx: commands.Context, **flags):
        """Mass release pokémon from your collection."""

        if ctx.author.id in self.bot.trades:
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
            msg = await self.bot.wait_for("message", timeout=30, check=check)

            if msg.content.lower() != f"confirm release {num}":
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
    @flags.add_flag("--shiny", action="store_true")
    @flags.add_flag("--alolan", action="store_true")
    @flags.add_flag("--mythical", action="store_true")
    @flags.add_flag("--legendary", action="store_true")
    @flags.add_flag("--ub", action="store_true")
    @flags.add_flag("--mega", action="store_true")
    @flags.add_flag("--favorite", action="store_true")
    @flags.add_flag("--name", nargs="+", action="append")
    @flags.add_flag("--type", type=str, action="append")

    # IV
    @flags.add_flag("--level", nargs="+", action="append")
    @flags.add_flag("--hpiv", nargs="+", action="append")
    @flags.add_flag("--atkiv", nargs="+", action="append")
    @flags.add_flag("--defiv", nargs="+", action="append")
    @flags.add_flag("--spatkiv", nargs="+", action="append")
    @flags.add_flag("--spdefiv", nargs="+", action="append")
    @flags.add_flag("--spdiv", nargs="+", action="append")
    @flags.add_flag("--iv", nargs="+", action="append")

    # Skip/limit
    @flags.add_flag("--skip", type=int)
    @flags.add_flag("--limit", type=int)

    # Pokemon
    @checks.has_started()
    @flags.command(aliases=["p"])
    @commands.bot_has_permissions(manage_messages=True, use_external_emojis=True)
    async def pokemon(self, ctx: commands.Context, **flags):
        """View or filter the pokémon in your collection."""

        if flags["page"] < 1:
            return await ctx.send("Page must be positive!")

        member = await self.db.fetch_member_info(ctx.author)

        aggregations = await self.create_filter(flags, ctx, order_by=member.order_by)

        if aggregations is None:
            return

        # Filter pokemon

        do_emojis = (
            ctx.channel.permissions_for(
                ctx.guild.get_member(self.bot.user.id)
            ).external_emojis
            and constants.EMOJIS.get_status()
        )

        fixed_pokemon = False

        async def fix_pokemon():
            # TODO This is janky way of removing bad database entries, I should fix this

            nonlocal fixed_pokemon

            if fixed_pokemon:
                return

            await self.db.update_member(
                ctx.author, {"$pull": {f"pokemon": {"species_id": {"$exists": False}}}},
            )
            await self.db.update_member(ctx.author, {"$pull": {f"pokemon": None}})

            fixed_pokemon = True

        def nick(p):
            if p.species is None:
                asyncio.create_task(fix_pokemon())
                return None

            if do_emojis:
                name = (
                    str(constants.EMOJIS.get(p.species.dex_number, shiny=p.shiny))
                    .replace("pokemon_sprite_", "")
                    .replace("_shiny", "")
                    + " "
                )
            else:
                name = ""

            name += str(p.species)

            if p.shiny:
                name += " ✨"

            if p.nickname is not None:
                name += ' "' + p.nickname + '"'

            if p.favorite:
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
                f"`{padn(p, idx, maxn)}`⠀**{txt}**⠀•⠀Lvl. {p.level}⠀•⠀{p.iv_percentage * 100:.2f}%"
                for p, idx in pokemon
                if (txt := nick(p)) is not None
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

        paginator = pagination.Paginator(get_page, num_pages=math.ceil(num / 20))
        await paginator.send(self.bot, ctx, flags["page"] - 1)

    @flags.add_flag("page", nargs="*", type=str, default="1")
    @flags.add_flag("--caught", action="store_true")
    @flags.add_flag("--uncaught", action="store_true")
    @flags.add_flag("--legendary", action="store_true")
    @flags.add_flag("--mythical", action="store_true")
    @flags.add_flag("--orderd", action="store_true")
    @flags.add_flag("--ordera", action="store_true")
    @flags.add_flag("--ub", action="store_true")
    @flags.add_flag("--type", type=str)
    @checks.has_started()
    @flags.command(aliases=["d", "dex"])
    @commands.bot_has_permissions(manage_messages=True, use_external_emojis=True)
    async def pokedex(self, ctx: commands.Context, **flags):
        """View your pokédex, or search for a pokémon species."""

        search_or_page = " ".join(flags["page"])

        if flags["orderd"] and flags["ordera"]:
            return await ctx.send(
                "You can use either --orderd or --ordera, but not both."
            )

        if flags["caught"] and flags["uncaught"]:
            return await ctx.send(
                "You can use either --caught or --uncaught, but not both."
            )

        if flags["mythical"] + flags["legendary"] + flags["ub"] > 1:
            return await ctx.send("You can't use more than one rarity flag!")

        if search_or_page is None:
            search_or_page = "1"

        if search_or_page.isdigit():
            pgstart = (int(search_or_page) - 1) * 20

            if pgstart >= 809 or pgstart < 0:
                return await ctx.send("There are no pokémon on this page.")

            num = await self.db.fetch_pokedex_count(ctx.author)

            do_emojis = (
                ctx.channel.permissions_for(
                    ctx.guild.get_member(self.bot.user.id)
                ).external_emojis
                and constants.EMOJIS.get_status()
            )

            member = await self.db.fetch_pokedex(ctx.author, 0, 810)
            pokedex = member.pokedex

            if not flags["uncaught"] and not flags["caught"]:
                for i in range(1, 810):
                    if str(i) not in pokedex:
                        pokedex[str(i)] = 0
            elif flags["uncaught"]:
                for i in range(1, 810):
                    if str(i) not in pokedex:
                        pokedex[str(i)] = 0
                    else:
                        del pokedex[str(i)]

            def include(key):
                if flags["legendary"] and key not in models.GameData.list_legendary():
                    return False
                if flags["mythical"] and key not in models.GameData.list_mythical():
                    return False
                if flags["ub"] and key not in models.GameData.list_ub():
                    return False

                if flags["type"] and key not in models.GameData.list_type(
                    flags["type"]
                ):
                    return False

                return True

            pokedex = {int(k): v for k, v in pokedex.items() if include(int(k))}

            if flags["ordera"]:
                pokedex = sorted(pokedex.items(), key=itemgetter(1))
            elif flags["orderd"]:
                pokedex = sorted(pokedex.items(), key=itemgetter(1), reverse=True)
            else:
                pokedex = sorted(pokedex.items(), key=itemgetter(0))

            async def get_page(pidx, clear):
                pgstart = (pidx) * 20
                pgend = min(pgstart + 20, len(pokedex))

                # Send embed

                embed = discord.Embed()
                embed.color = 0xF44336
                embed.title = f"Your pokédex"
                embed.description = f"You've caught {num} out of 809 pokémon!"

                if do_emojis:
                    embed.set_footer(
                        text=f"Showing {pgstart + 1}–{pgend} out of {len(pokedex)}."
                    )
                else:
                    embed.set_footer(
                        text=f"Showing {pgstart + 1}–{pgend} out of 809. Please give me permission to Use External Emojis! It'll make this menu look a lot better."
                    )

                # embed.description = (
                #     f"You've caught {len(member.pokedex)} out of 809 pokémon!"
                # )

                for k, v in pokedex[pgstart:pgend]:
                    species = models.GameData.species_by_number(k)

                    if do_emojis:
                        text = f"{constants.EMOJIS.cross} Not caught yet!"
                    else:
                        text = "Not caught yet!"

                    if v > 0:
                        if do_emojis:
                            text = f"{constants.EMOJIS.check} {v} caught!"
                        else:
                            text = f"{v} caught!"

                    if do_emojis:
                        emoji = (
                            str(constants.EMOJIS.get(k)).replace("pokemon_sprite_", "")
                            + " "
                        )
                    else:
                        emoji = ""

                    embed.add_field(
                        name=f"{emoji}{species.name} #{species.id}", value=text
                    )

                if pgend != 809:
                    embed.add_field(name="‎", value="‎")

                return embed

            paginator = pagination.Paginator(
                get_page, num_pages=math.ceil(len(pokedex) / 20)
            )
            await paginator.send(self.bot, ctx, int(search_or_page) - 1)

        else:
            shiny = False

            if search_or_page[0] in "Nn#" and search_or_page[1:].isdigit():
                species = models.GameData.species_by_number(int(search_or_page[1:]))

            else:
                search = search_or_page

                if search_or_page.lower().startswith("shiny "):
                    shiny = True
                    search = search_or_page[6:]

                species = models.GameData.species_by_name(search)
                if species is None:
                    return await ctx.send(
                        f"Could not find a pokemon matching `{search_or_page}`."
                    )

            member = await self.db.fetch_pokedex(
                ctx.author, species.dex_number, species.dex_number + 1
            )

            embed = discord.Embed()
            embed.color = 0xF44336
            embed.title = f"#{species.dex_number} — {species}"

            if species.description:
                embed.description = species.description.replace("\n", " ")

            if species.evolution_text:
                embed.add_field(
                    name="Evolution", value=species.evolution_text, inline=False
                )

            extrafooter = ""

            if shiny:
                embed.title += " ✨"
                embed.set_image(url=species.shiny_image_url)
                extrafooter = " Note that we don't have artwork for all shiny pokémon yet! We're working hard to make all the shiny pokémon look shiny."
            else:
                embed.set_image(url=species.image_url)

            base_stats = (
                f"**HP:** {species.base_stats.hp}",
                f"**Attack:** {species.base_stats.atk}",
                f"**Defense:** {species.base_stats.defn}",
                f"**Sp. Atk:** {species.base_stats.satk}",
                f"**Sp. Def:** {species.base_stats.sdef}",
                f"**Speed:** {species.base_stats.spd}",
            )

            embed.add_field(
                name="Names",
                value="\n".join(f"{x} {y}" for x, y in species.names),
                inline=False,
            )
            embed.add_field(name="Base Stats", value="\n".join(base_stats))
            embed.add_field(
                name="Appearance",
                value=f"Height: {species.height} m\nWeight: {species.weight} kg",
            )
            embed.add_field(name="Types", value="\n".join(species.types))

            text = "You haven't caught this pokémon yet!"
            if str(species.dex_number) in member.pokedex:
                text = f"You've caught {member.pokedex[str(species.dex_number)]} of this pokémon!"

            embed.set_footer(text=text + extrafooter)

            await ctx.send(embed=embed)

    @checks.has_started()
    @commands.command(rest_is_raw=True)
    async def evolve(self, ctx: commands.Context, *, pokemon: converters.Pokemon):
        """Evolve a pokémon if it has reached the target level."""

        pokemon, idx = pokemon

        member = await self.db.fetch_member_info(ctx.author)

        if (
            pokemon.species.level_evolution is not None
            and pokemon.held_item != 13001
            and pokemon.level >= pokemon.species.level_evolution.trigger.level
        ):
            embed = discord.Embed()
            embed.color = 0xF44336
            embed.title = f"Congratulations {ctx.author.name}!"

            name = str(pokemon.species)

            if pokemon.nickname is not None:
                name += f' "{pokemon.nickname}"'

            embed.add_field(
                name=f"Your {name} is evolving!",
                value=f"Your {name} has turned into a {pokemon.species.level_evolution.target}!",
            )

            await self.db.update_member(
                ctx.author,
                {
                    "$set": {
                        f"pokemon.{idx}.species_id": pokemon.species.level_evolution.target_id
                    }
                },
            )

            await ctx.send(embed=embed)
        else:
            await ctx.send("That pokémon can't be evolved!")

    @checks.has_started()
    @commands.command(rest_is_raw=True)
    async def unmega(self, ctx: commands.Context, *, pokemon: converters.Pokemon):
        """Switch a pokémon back to its non-mega form."""

        pokemon, idx = pokemon

        fr = models.GameData.species_by_number(pokemon.species.dex_number)

        if pokemon.species not in (fr.mega, fr.mega_x, fr.mega_y,):
            return await ctx.send("This pokémon is not in mega form!")

        member = await self.db.fetch_member_info(ctx.author)

        await self.db.update_member(
            ctx.author, {"$set": {f"pokemon.{idx}.species_id": fr.id}},
        )

        await ctx.send("Successfully switched back to normal form.")

    @commands.command(aliases=["n"])
    async def next(self, ctx: commands.Context):
        if ctx.author.id not in pagination.paginators:
            return await ctx.send("Couldn't find a previous message.")

        paginator = pagination.paginators[ctx.author.id]

        pidx = paginator.last_page + 1
        pidx %= paginator.num_pages

        await paginator.send(self.bot, ctx, pidx)

    @commands.command(aliases=["b"])
    async def back(self, ctx: commands.Context):
        if ctx.author.id not in pagination.paginators:
            return await ctx.send("Couldn't find a previous message.")

        paginator = pagination.paginators[ctx.author.id]

        pidx = paginator.last_page - 1
        pidx %= paginator.num_pages

        await paginator.send(self.bot, ctx, pidx)


def setup(bot: commands.Bot):
    bot.add_cog(Pokemon(bot))
