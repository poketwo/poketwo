import asyncio
import math
import typing
from datetime import datetime
from operator import itemgetter

from discord.ext import commands, flags
from helpers import checks, constants, converters, pagination
from pymongo import UpdateOne


class Pokemon(commands.Cog):
    """Pokémon-related commands."""

    def __init__(self, bot):
        self.bot = bot

    @commands.command(aliases=("renumber",))
    async def reindex(self, ctx):
        """Re-number all pokémon in your collection."""

        await ctx.send(
            "Reindexing all your pokémon... please don't do anything else during this time."
        )

        num = await self.bot.mongo.fetch_pokemon_count(ctx.author)
        await self.bot.mongo.reset_idx(ctx.author, value=num + 1)
        mons = self.bot.mongo.db.pokemon.find({"owner_id": ctx.author.id}).sort("idx")

        ops = []

        idx = 1
        async for pokemon in mons:
            ops.append(UpdateOne({"_id": pokemon["_id"]}, {"$set": {"idx": idx}}))
            idx += 1

            if len(ops) >= 1000:
                await self.bot.mongo.db.pokemon.bulk_write(ops)
                ops = []

        await self.bot.mongo.db.pokemon.bulk_write(ops)
        await ctx.send("Successfully reindexed all your pokémon!")

    @commands.command(aliases=("nick",))
    async def nickname(
        self,
        ctx: commands.Context,
        pokemon: typing.Optional[converters.PokemonConverter] = False,
        *,
        nickname: str,
    ):
        """Change the nickname for your pokémon."""

        if pokemon is False:
            pokemon = await converters.PokemonConverter().convert(ctx, "")

        if pokemon is None:
            return await ctx.send("Couldn't find that pokémon!")

        if len(nickname) > 100:
            return await ctx.send("That nickname is too long.")

        if not nickname.isalnum():
            return await ctx.send("That nickname contains non-alphanumeric characters.")

        if nickname == "reset":
            nickname = None

        await self.bot.mongo.update_pokemon(
            pokemon,
            {"$set": {f"nickname": nickname}},
        )

        if nickname is None:
            await ctx.send(
                f"Removed nickname for your level {pokemon.level} {pokemon.species}."
            )
        else:
            await ctx.send(
                f"Changed nickname to `{nickname}` for your level {pokemon.level} {pokemon.species}."
            )
         
    # Nickname
    @flags.add_flag("newname", nargs="+")

    # Filter
    @flags.add_flag("--shiny", action="store_true")
    @flags.add_flag("--alolan", action="store_true")
    @flags.add_flag("--mythical", action="store_true")
    @flags.add_flag("--legendary", action="store_true")
    @flags.add_flag("--ub", action="store_true")
    @flags.add_flag("--mega", action="store_true")
    @flags.add_flag("--name", "--n", nargs="+", action="append")
    @flags.add_flag("--nickname", nargs="+", action="append")
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

    # Rename all
    @checks.has_started()
    @commands.max_concurrency(1, commands.BucketType.user)
    @flags.command(aliases=("na",))
    async def nickall(self, ctx, **flags):
        """Mass nickname pokémon from your collection."""

        nicknameall = " ".join(flags["newname"])

        aggregations = await self.create_filter(flags, ctx)

        if aggregations is None:
            return

        # check nick length
        if len(nicknameall) > 100:
            return await ctx.send("That nickname is too long.")

        if not nicknameall.isalnum():
            return await ctx.send("That nickname contains non-alphanumeric characters.")

        # check nick reset
        if nicknameall == "reset":
            nicknameall = None
        
        # check pokemon num
        num = await self.bot.mongo.fetch_pokemon_count(
            ctx.author, aggregations=aggregations
        )

        if num == 0:
            return await ctx.send(
                "Found no pokémon matching this search."
            )
        
        # confirm
        if nicknameall is None:
            await ctx.send(
                f"Are you sure you want to **remove** nickname for {num} pokémon? Type `confirm nickname {num}` to confirm."
            )
        else:
            await ctx.send(
                f"Are you sure you want to rename {num} pokémon to `{nicknameall}`? Type `confirm nickname {num}` to confirm."
            )

        def check(m):
            return m.channel.id == ctx.channel.id and m.author.id == ctx.author.id

        try:
            msg = await self.bot.wait_for("message", timeout=30, check=check)

            if msg.content.lower() != f"confirm nickname {num}":
                return await ctx.send("Aborted.")

        except asyncio.TimeoutError:
            return await ctx.send("Time's up. Aborted.")

        # confirmed, nickname all

        num = await self.bot.mongo.fetch_pokemon_count(
            ctx.author, aggregations=aggregations
        )

        await ctx.send(f"Renaming {num} pokémon, this might take a while...")

        pokemon = await self.bot.mongo.fetch_pokemon_list(
            ctx.author, 0, num, aggregations=aggregations
        )

        await self.bot.mongo.db.pokemon.update_many(
            {"_id": {"$in": [x["pokemon"]["_id"] for x in pokemon]}},
            {"$set": {"nickname": nicknameall}},
        )
        
        if nicknameall is None:
            await ctx.send(
                f"Removed nickname for {num} pokémon."
            )
        else:
            await ctx.send(
                f"Changed nickname to `{nicknameall}` for {num} pokémon."
            )

        
    @commands.command(aliases=("fav", "favourite"), rest_is_raw=True)
    async def favorite(self, ctx, args: commands.Greedy[converters.PokemonConverter]):
        """Mark a pokémon as a favorite."""

        if len(args) == 0:
            args.append(await converters.PokemonConverter().convert(ctx, ""))

        messages = []

        async with ctx.typing():
            for pokemon in args:
                if pokemon is None:
                    continue

                await self.bot.mongo.update_pokemon(
                    pokemon,
                    {"$set": {f"favorite": not pokemon.favorite}},
                )

                name = str(pokemon.species)

                if pokemon.nickname is not None:
                    name += f' "{pokemon.nickname}"'

                if pokemon.favorite:
                    messages.append(f"Unfavorited your level {pokemon.level} {name}.")
                else:
                    messages.append(f"Favorited your level {pokemon.level} {name}.")

            longmsg = "\n".join(messages)
            for i in range(0, len(longmsg), 2000):
                await ctx.send(longmsg[i : i + 2000])

    @checks.has_started()
    @commands.command(aliases=("i",), rest_is_raw=True)
    async def info(self, ctx, *, pokemon: converters.PokemonConverter):
        """View a specific pokémon from your collection."""

        num = await self.bot.mongo.fetch_pokemon_count(ctx.author)

        if pokemon is None:
            return await ctx.send("Couldn't find that pokémon!")

        shift = 0

        async def get_page(pidx, clear, dir=0):
            nonlocal shift

            pokemon = await self.bot.mongo.fetch_pokemon(ctx.author, pidx + shift)
            while pokemon is None:
                shift += 1
                pokemon = await self.bot.mongo.fetch_pokemon(ctx.author, pidx + shift)

            embed = self.bot.Embed(color=pokemon.color or 0x9CCFFF)
            embed.title = f"{pokemon:lnf}"

            if pokemon.shiny:
                embed.set_image(url=pokemon.species.shiny_image_url)
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
                item = self.bot.data.item_by_number(pokemon.held_item)
                emote = ""
                if item.emote is not None:
                    emote = getattr(self.bot.sprites, item.emote) + " "
                embed.add_field(
                    name="Held Item", value=f"{emote}{item.name}", inline=False
                )

            embed.set_footer(
                text=f"Displaying pokémon {pokemon.idx}.\nID: {pokemon.id}"
            )

            return embed

        paginator = pagination.Paginator(get_page, num_pages=num)
        await paginator.send(self.bot, ctx, pokemon.idx)

    @checks.has_started()
    @commands.command(aliases=("s",), rest_is_raw=True)
    async def select(
        self, ctx, *, pokemon: converters.PokemonConverter(accept_blank=False)
    ):
        """Select a specific pokémon from your collection."""

        if pokemon is None:
            return await ctx.send("Couldn't find that pokémon!")

        num = await self.bot.mongo.fetch_pokemon_count(ctx.author)

        await self.bot.mongo.update_member(
            ctx.author,
            {"$set": {f"selected_id": pokemon.id}},
        )

        await ctx.send(
            f"You selected your level {pokemon.level} {pokemon.species}. No. {pokemon.idx}."
        )

    @checks.has_started()
    @commands.command(aliases=("or",))
    async def order(self, ctx, *, sort: str = ""):
        """Change how your pokémon are ordered."""

        sort = sort.lower()

        if sort not in ("number", "iv", "level", "pokedex"):
            return await ctx.send(
                "Please specify either `number`, `IV`, `level`, or `pokedex`."
            )

        await self.bot.mongo.update_member(
            ctx.author,
            {"$set": {f"order_by": sort}},
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

        if "mine" in flags and flags["mine"]:
            aggregations.append({"$match": {"user_id": ctx.author.id}})

        if "bids" in flags and flags["bids"]:
            aggregations.append({"$match": {"bidder_id": ctx.author.id}})

        for x in ("mythical", "legendary", "ub", "alolan", "mega"):
            if x in flags and flags[x]:
                aggregations.append(
                    {
                        "$match": {
                            "pokemon.species_id": {
                                "$in": getattr(self.bot.data, f"list_{x}")
                            }
                        }
                    }
                )

        if "type" in flags and flags["type"]:
            all_species = [i for x in flags["type"] for i in self.bot.data.list_type(x)]

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
                for i in self.bot.data.find_all_matches(" ".join(x))
            ]

            aggregations.append(
                {"$match": {"pokemon.species_id": {"$in": all_species}}}
            )

        if "nickname" in flags and flags["nickname"] is not None:
            aggregations.append(
                {
                    "$match": {
                        "pokemon.nickname": {
                            "$regex": "("
                            + ")|(".join(" ".join(x) for x in flags["nickname"])
                            + ")",
                            "$options": "i",
                        }
                    }
                }
            )

        if "ends" in flags and flags["ends"] is not None:
            aggregations.append(
                {"$match": {"ends": {"$lt": datetime.utcnow() + flags["ends"]}}}
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
            s = order_by[-1]
            if order_by[-1] in "+-":
                order_by, asc = order_by[:-1], 1 if s == "+" else -1
            else:
                asc = -1 if order_by in ("iv", "level") else 1

            aggregations.extend(
                [
                    {"$addFields": {"sorting": constants.SORTING_FUNCTIONS[order_by]}},
                    {"$sort": {"sorting": asc, "idx": 1, "_id": 1}},
                ]
            )

        if "skip" in flags and flags["skip"] is not None:
            aggregations.append({"$skip": flags["skip"]})

        if "limit" in flags and flags["limit"] is not None:
            aggregations.append({"$limit": flags["limit"]})

        return aggregations

    @checks.has_started()
    @commands.max_concurrency(1, commands.BucketType.user)
    @commands.command(aliases=("r",))
    async def release(self, ctx, args: commands.Greedy[converters.PokemonConverter]):
        """Release pokémon from your collection for 2pc each."""

        if await self.bot.get_cog("Trading").is_in_trade(ctx.author):
            return await ctx.send("You can't do that in a trade!")

        member = await self.bot.mongo.fetch_member_info(ctx.author)

        ids = set()
        mons = list()

        for pokemon in args:

            if pokemon is None:
                continue

            # can't release selected/fav

            if pokemon.id in ids:
                continue

            if member.selected_id == pokemon.id:
                await ctx.send(
                    f"{pokemon.idx}: You can't release your selected pokémon!"
                )
                continue

            if pokemon.favorite:
                await ctx.send(f"{pokemon.idx}: You can't release favorited pokémon!")
                continue

            ids.add(pokemon.id)
            mons.append(pokemon)

        # Confirmation msg

        if len(mons) == 0:
            return

        if len(args) == 1:
            await ctx.send(
                f"Are you sure you want to release your level {pokemon.level} {pokemon.species}. No. {pokemon.idx} for 2 pc? This action is irreversible! [y/N]"
            )
        else:
            embed = self.bot.Embed(color=0x9CCFFF)
            embed.title = f"Are you sure you want to release the following pokémon for {len(mons)*2:,} pc? [y/N]"

            embed.description = "\n".join(
                f"Level {x.level} {x.species} ({x.idx})" for x in mons
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

        await self.bot.mongo.db.pokemon.update_many(
            {"_id": {"$in": list(ids)}}, {"$set": {"owner_id": None}}
        )
        await self.bot.mongo.update_member(
            ctx.author,
            {
                "$inc": {"balance": 2 * len(mons)},
            },
        )
        await ctx.send(
            f"You released {len(mons)} pokémon. You received {2*len(mons):,} Pokécoins!"
        )

    # Filter
    @flags.add_flag("page", nargs="?", type=int, default=1)
    @flags.add_flag("--shiny", action="store_true")
    @flags.add_flag("--alolan", action="store_true")
    @flags.add_flag("--mythical", action="store_true")
    @flags.add_flag("--legendary", action="store_true")
    @flags.add_flag("--ub", action="store_true")
    @flags.add_flag("--mega", action="store_true")
    @flags.add_flag("--name", "--n", nargs="+", action="append")
    @flags.add_flag("--nickname", nargs="+", action="append")
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
    @commands.max_concurrency(1, commands.BucketType.user)
    @flags.command(aliases=("ra",))
    async def releaseall(self, ctx, **flags):
        """Mass release pokémon from your collection for 2 pc each."""

        if await self.bot.get_cog("Trading").is_in_trade(ctx.author):
            return await ctx.send("You can't do that in a trade!")

        aggregations = await self.create_filter(flags, ctx)

        if aggregations is None:
            return

        member = await self.bot.mongo.fetch_member_info(ctx.author)

        aggregations.extend(
            [
                {"$match": {"_id": {"$not": {"$eq": member.selected_id}}}},
                {"$match": {"pokemon.favorite": {"$not": {"$eq": True}}}},
            ]
        )

        num = await self.bot.mongo.fetch_pokemon_count(
            ctx.author, aggregations=aggregations
        )

        if num == 0:
            return await ctx.send(
                "Found no pokémon matching this search (excluding favorited and selected pokémon)."
            )

        # confirm

        await ctx.send(
            f"Are you sure you want to release {num} pokémon for {num*2:,} pc? Favorited and selected pokémon won't be removed. Type `confirm release {num}` to confirm."
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

        num = await self.bot.mongo.fetch_pokemon_count(
            ctx.author, aggregations=aggregations
        )

        await ctx.send(f"Releasing {num} pokémon, this might take a while...")

        pokemon = await self.bot.mongo.fetch_pokemon_list(
            ctx.author, 0, num, aggregations=aggregations
        )

        await self.bot.mongo.db.pokemon.update_many(
            {"_id": {"$in": [x["pokemon"]["_id"] for x in pokemon]}},
            {"$set": {"owner_id": None}},
        )

        await self.bot.mongo.update_member(
            ctx.author,
            {
                "$inc": {"balance": 2 * num},
            },
        )

        await ctx.send(
            f"You have released {num} pokémon. You received {2*num:,} Pokécoins!"
        )

    # Filter
    @flags.add_flag("page", nargs="?", type=int, default=1)
    @flags.add_flag("--shiny", action="store_true")
    @flags.add_flag("--alolan", action="store_true")
    @flags.add_flag("--mythical", action="store_true")
    @flags.add_flag("--legendary", action="store_true")
    @flags.add_flag("--ub", action="store_true")
    @flags.add_flag("--mega", action="store_true")
    @flags.add_flag("--favorite", action="store_true")
    @flags.add_flag("--name", "--n", nargs="+", action="append")
    @flags.add_flag("--nickname", nargs="+", action="append")
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
    @flags.command(aliases=("p",))
    async def pokemon(self, ctx, **flags):
        """View or filter the pokémon in your collection."""

        if flags["page"] < 1:
            return await ctx.send("Page must be positive!")

        member = await self.bot.mongo.fetch_member_info(ctx.author)

        aggregations = await self.create_filter(flags, ctx, order_by=member.order_by)

        if aggregations is None:
            return

        # Filter pokemon

        do_emojis = (
            ctx.guild is None
            or ctx.guild.me.permissions_in(ctx.channel).external_emojis
        )

        fixed_pokemon = False

        def padn(p, n):
            return " " * (len(str(n)) - len(str(p.idx))) + str(p.idx)

        num = await self.bot.mongo.fetch_pokemon_count(
            ctx.author, aggregations=aggregations
        )

        if num == 0:
            return await ctx.send("Found no pokémon matching this search.")

        async def get_page(pidx, clear):

            pgstart = pidx * 20
            pokemon = await self.bot.mongo.fetch_pokemon_list(
                ctx.author, pgstart, 20, aggregations=aggregations
            )

            pokemon = [
                self.bot.mongo.Pokemon.build_from_mongo(x["pokemon"]) for x in pokemon
            ]

            if len(pokemon) == 0:
                return await clear("There are no pokémon on this page!")

            maxn = max(x.idx for x in pokemon)

            page = [
                f"`{padn(p, maxn)}`　**{p:nif}**　•　Lvl. {p.level}　•　{p.iv_percentage * 100:.2f}%"
                for p in pokemon
            ]

            # Send embed

            embed = self.bot.Embed(color=0x9CCFFF)
            embed.title = f"Your pokémon"
            embed.description = "\n".join(page)[:2048]

            embed.set_footer(
                text=f"Showing {pgstart + 1}–{min(pgstart + 20, num)} out of {num}. (Page {pidx+1} of {math.ceil(num / 20)})"
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
    @flags.command(aliases=("d", "dex"))
    async def pokedex(self, ctx, **flags):
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

            num = await self.bot.mongo.fetch_pokedex_count(ctx.author)

            do_emojis = (
                ctx.guild is None
                or ctx.guild.me.permissions_in(ctx.channel).external_emojis
            )

            member = await self.bot.mongo.fetch_pokedex(ctx.author, 0, 810)
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
                if flags["legendary"] and key not in self.bot.data.list_legendary:
                    return False
                if flags["mythical"] and key not in self.bot.data.list_mythical:
                    return False
                if flags["ub"] and key not in self.bot.data.list_ub:
                    return False

                if flags["type"] and key not in self.bot.data.list_type(flags["type"]):
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

                embed = self.bot.Embed(color=0x9CCFFF)
                embed.title = f"Your pokédex"
                embed.description = f"You've caught {num} out of 809 pokémon!"

                embed.set_footer(
                    text=f"Showing {pgstart + 1}–{pgend} out of {len(pokedex)}."
                )

                # embed.description = (
                #     f"You've caught {len(member.pokedex)} out of 809 pokémon!"
                # )

                for k, v in pokedex[pgstart:pgend]:
                    species = self.bot.data.species_by_number(k)

                    if do_emojis:
                        text = f"{self.bot.sprites.cross} Not caught yet!"
                    else:
                        text = "Not caught yet!"

                    if v > 0:
                        if do_emojis:
                            text = f"{self.bot.sprites.check} {v} caught!"
                        else:
                            text = f"{v} caught!"

                    if do_emojis:
                        emoji = self.bot.sprites.get(k) + " "
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
                species = self.bot.data.species_by_number(int(search_or_page[1:]))

            else:
                search = search_or_page

                if search_or_page.lower().startswith("shiny "):
                    shiny = True
                    search = search_or_page[6:]

                species = self.bot.data.species_by_name(search)
                if species is None:
                    return await ctx.send(
                        f"Could not find a pokemon matching `{search_or_page}`."
                    )

            member = await self.bot.mongo.fetch_pokedex(
                ctx.author, species.dex_number, species.dex_number + 1
            )

            embed = self.bot.Embed(color=0x9CCFFF)
            embed.title = f"#{species.dex_number} — {species}"

            if species.description:
                embed.description = species.description.replace("\n", " ")

            if species.evolution_text:
                embed.add_field(
                    name="Evolution", value=species.evolution_text, inline=False
                )

            if shiny:
                embed.title = f"#{species.dex_number} — ✨ {species}"
                embed.set_image(url=species.shiny_image_url)
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

            embed.set_footer(text=text)

            await ctx.send(embed=embed)

    @checks.has_started()
    @commands.guild_only()
    @commands.command(rest_is_raw=True)
    async def evolve(self, ctx, *, pokemon: converters.PokemonConverter):
        """Evolve a pokémon if it has reached the target level."""

        if pokemon is None:
            return await ctx.send("Couldn't find that pokémon!")

        member = await self.bot.mongo.fetch_member_info(ctx.author)
        guild = await self.bot.mongo.fetch_guild(ctx.guild)

        if (evo := pokemon.get_next_evolution(guild.is_day)) is None:
            return await ctx.send("That pokémon can't be evolved!")

        embed = self.bot.Embed(color=0x9CCFFF)
        embed.title = f"Congratulations {ctx.author.display_name}!"

        name = str(pokemon.species)

        if pokemon.nickname is not None:
            name += f' "{pokemon.nickname}"'

        embed.add_field(
            name=f"Your {name} is evolving!",
            value=f"Your {name} has turned into a {evo}!",
        )

        if pokemon.shiny:
            embed.set_thumbnail(url=evo.shiny_image_url)
        else:
            embed.set_thumbnail(url=evo.image_url)

        await self.bot.mongo.update_pokemon(
            pokemon,
            {"$set": {f"species_id": evo.id}},
        )

        self.bot.dispatch("evolve", ctx.author, pokemon, evo)

        await ctx.send(embed=embed)

    @checks.has_started()
    @commands.command(rest_is_raw=True)
    async def unmega(self, ctx, *, pokemon: converters.PokemonConverter):
        """Switch a pokémon back to its non-mega form."""

        if pokemon is None:
            return await ctx.send("Couldn't find that pokémon!")

        fr = self.bot.data.species_by_number(pokemon.species.dex_number)

        if pokemon.species not in (
            fr.mega,
            fr.mega_x,
            fr.mega_y,
        ):
            return await ctx.send("This pokémon is not in mega form!")

        member = await self.bot.mongo.fetch_member_info(ctx.author)

        await self.bot.mongo.update_pokemon(
            pokemon,
            {"$set": {f"species_id": fr.id}},
        )

        await ctx.send("Successfully switched back to normal form.")

    @commands.command(aliases=("f",))
    async def first(self, ctx):
        if ctx.author.id not in pagination.paginators:
            return await ctx.send("Couldn't find a previous message.")

        paginator = pagination.paginators[ctx.author.id]

        await paginator.send(self.bot, ctx, 0)

    @commands.command(aliases=("n", "forward"))
    async def next(self, ctx):
        if ctx.author.id not in pagination.paginators:
            return await ctx.send("Couldn't find a previous message.")

        paginator = pagination.paginators[ctx.author.id]

        if paginator.num_pages == 0:
            return

        pidx = paginator.last_page + 1
        pidx %= paginator.num_pages

        await paginator.send(self.bot, ctx, pidx)

    @commands.command(aliases=("prev", "back", "b"))
    async def previous(self, ctx):
        if ctx.author.id not in pagination.paginators:
            return await ctx.send("Couldn't find a previous message.")

        paginator = pagination.paginators[ctx.author.id]

        if paginator.num_pages == 0:
            return

        pidx = paginator.last_page - 1
        pidx %= paginator.num_pages

        await paginator.send(self.bot, ctx, pidx)

    @commands.command(aliases=("l",))
    async def last(self, ctx):
        if ctx.author.id not in pagination.paginators:
            return await ctx.send("Couldn't find a previous message.")

        paginator = pagination.paginators[ctx.author.id]
        await paginator.send(self.bot, ctx, paginator.num_pages - 1)

    @commands.command(aliases=("page", "g"))
    async def go(self, ctx, page: int):
        if ctx.author.id not in pagination.paginators:
            return await ctx.send("Couldn't find a previous message.")

        paginator = pagination.paginators[ctx.author.id]

        if paginator.num_pages == 0:
            return

        await paginator.send(self.bot, ctx, page % paginator.num_pages)


def setup(bot):
    bot.add_cog(Pokemon(bot))
