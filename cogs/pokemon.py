import contextlib
import itertools
import math
import typing
from datetime import datetime
from operator import itemgetter

from discord.errors import DiscordException
from discord.ext import commands
from pymongo import UpdateOne

from helpers import checks, constants, converters, flags, pagination


def isfloat(x):
    try:
        float(x)
    except ValueError:
        return False
    else:
        return True


class Pokemon(commands.Cog):
    """Pokémon-related commands."""

    def __init__(self, bot):
        self.bot = bot

    @checks.has_started()
    @commands.command(aliases=("renumber",))
    async def reindex(self, ctx):
        """Re-number all pokémon in your collection."""

        await ctx.send(ctx._("reindexing-pokemon"))

        num = await self.bot.mongo.fetch_pokemon_count(ctx.author)
        await self.bot.mongo.reset_idx(ctx.author, value=num + 1)
        mons = self.bot.mongo.db.pokemon.find({"owner_id": ctx.author.id, "owned_by": "user"}).sort("idx")

        ops = []

        idx = 1
        async for pokemon in mons:
            ops.append(UpdateOne({"_id": pokemon["_id"]}, {"$set": {"idx": idx}}))
            idx += 1

            if len(ops) >= 1000:
                await self.bot.mongo.db.pokemon.bulk_write(ops)
                ops = []

        await self.bot.mongo.db.pokemon.bulk_write(ops)
        await ctx.send(ctx._("successfully-reindexed-pokemon"))

    @checks.has_started()
    @commands.command(aliases=("nick",))
    async def nickname(
        self,
        ctx: commands.Context,
        pokemon: typing.Optional[converters.PokemonConverter] = False,
        *nickname,
    ):
        """Change the nickname for your pokémon."""

        if pokemon is False:
            pokemon = await converters.PokemonConverter().convert(ctx, "")

        if pokemon is None:
            return await ctx.send(ctx._("unknown-pokemon"))

        nickname = " ".join(nickname)

        if len(nickname) > 100:
            return await ctx.send(ctx._("nickname-too-long"))

        if constants.URL_REGEX.search(nickname):
            return await ctx.send(ctx._("nickname-contains-urls"))

        if nickname == "reset":
            nickname = None

        await self.bot.mongo.update_pokemon(
            pokemon,
            {"$set": {f"nickname": nickname}},
        )

        if nickname is None:
            await ctx.send(ctx._("removed-nickname", level=pokemon.level, pokemon=str(pokemon.species)))
        else:
            await ctx.send(
                ctx._("changed-nickname", nickname=nickname, level=pokemon.level, pokemon=str(pokemon.species))
            )

    # Nickname
    @flags.add_flag("newname", nargs="+")

    # Filter
    @flags.add_flag("--shiny", action="store_true")
    @flags.add_flag("--alolan", action="store_true")
    @flags.add_flag("--galarian", action="store_true")
    @flags.add_flag("--hisuian", action="store_true")
    @flags.add_flag("--mythical", action="store_true")
    @flags.add_flag("--legendary", action="store_true")
    @flags.add_flag("--ub", action="store_true")
    @flags.add_flag("--event", action="store_true")
    @flags.add_flag("--mega", action="store_true")
    @flags.add_flag("--favorite", action="store_true")
    @flags.add_flag("--embedcolor", "--ec", action="store_true")
    @flags.add_flag("--name", "--n", nargs="+", action="append")
    @flags.add_flag("--nickname", nargs="*", action="append")
    @flags.add_flag("--type", "--t", type=str, action="append")
    @flags.add_flag("--region", "--r", type=str, action="append")

    # IV
    @flags.add_flag("--level", nargs="+", action="append")
    @flags.add_flag("--hpiv", nargs="+", action="append")
    @flags.add_flag("--atkiv", nargs="+", action="append")
    @flags.add_flag("--defiv", nargs="+", action="append")
    @flags.add_flag("--spatkiv", nargs="+", action="append")
    @flags.add_flag("--spdefiv", nargs="+", action="append")
    @flags.add_flag("--spdiv", nargs="+", action="append")
    @flags.add_flag("--iv", nargs="+", action="append")

    # Duplicate IV's
    @flags.add_flag("--triple", "--three", type=int)
    @flags.add_flag("--quadruple", "--four", "--quadra", "--quad", "--tetra", type=int)
    @flags.add_flag("--pentuple", "--quintuple", "--penta", "--pent", "--five", type=int)
    @flags.add_flag("--hextuple", "--sextuple", "--hexa", "--hex", "--six", type=int)

    # Skip/limit
    @flags.add_flag("--skip", type=int)
    @flags.add_flag("--limit", type=int)

    # Rename all
    @checks.has_started()
    @commands.max_concurrency(1, commands.BucketType.user)
    @commands.cooldown(1, 5, commands.BucketType.user)
    @flags.command(aliases=("na",))
    async def nickall(self, ctx, **flags):
        """Mass nickname pokémon from your collection."""

        nicknameall = " ".join(flags["newname"])

        member = await self.bot.mongo.fetch_member_info(ctx.author)
        aggregations = await self.create_filter(flags, ctx, order_by=member.order_by)

        if aggregations is None:
            return

        # check nick length
        if len(nicknameall) > 100:
            return await ctx.send(ctx._("nickname-too-long"))

        if constants.URL_REGEX.search(nicknameall):
            return await ctx.send(ctx._("nickname-contains-urls"))

        # check nick reset
        if nicknameall == "reset":
            nicknameall = None

        # check pokemon num
        num = await self.bot.mongo.fetch_pokemon_count(ctx.author, aggregations=aggregations)

        if num == 0:
            return await ctx.send(ctx._("found-no-pokemon-matching"))

        # confirm
        if nicknameall is None:
            message = ctx._("confirm-mass-unnick", number=num)
        else:
            message = ctx._("confirm-mass-nick", number=num, nickname=nicknameall)

        result = await ctx.confirm(message)
        if result is None:
            return await ctx.send(ctx._("times-up"))
        if result is False:
            return await ctx.send(ctx._("aborted"))

        # confirmed, nickname all
        await ctx.send(ctx._("nickall-in-progress", number=num))

        pokemon = self.bot.mongo.fetch_pokemon_list(ctx.author, aggregations)

        await self.bot.mongo.db.pokemon.update_many(
            {"_id": {"$in": [x.id async for x in pokemon]}},
            {"$set": {"nickname": nicknameall}},
        )

        if nicknameall is None:
            await ctx.send(ctx._("nickall-completed-removed", number=num))
        else:
            await ctx.send(ctx._("nickall-completed", number=num, nickname=nicknameall))

    @checks.has_started()
    @commands.command(
        aliases=(
            "favourite",
            "fav",
        ),
        rest_is_raw=True,
    )
    async def favorite(self, ctx, args: commands.Greedy[converters.PokemonConverter]):
        """Mark a pokémon as a favorite."""

        if len(args) == 0:
            args.append(await converters.PokemonConverter().convert(ctx, ""))

        messages = []
        ids = set()

        async with ctx.typing():
            for pokemon in args:
                if pokemon is None:
                    continue
                if pokemon.id in ids:
                    continue
                ids.add(pokemon.id)

                name = str(pokemon.species)

                if pokemon.nickname is not None:
                    name += f' "{pokemon.nickname}"'

                if pokemon.favorite:
                    messages.append(ctx._("already-favorited-pokemon", level=pokemon.level, pokemon=name))
                else:
                    await self.bot.mongo.update_pokemon(
                        pokemon,
                        {"$set": {f"favorite": True}},
                    )
                    messages.append(ctx._("favorited-pokemon", level=pokemon.level, name=name))

            longmsg = "\n".join(messages)
            for i in range(0, len(longmsg), 2000):
                await ctx.send(longmsg[i : i + 2000])

    @checks.has_started()
    @commands.command(
        aliases=(
            "unfavourite",
            "unfav",
        ),
        rest_is_raw=True,
    )
    async def unfavorite(self, ctx, args: commands.Greedy[converters.PokemonConverter]):
        """Unfavorite a selected pokemon."""

        if len(args) == 0:
            args.append(await converters.PokemonConverter().convert(ctx, ""))

        messages = []

        async with ctx.typing():
            for pokemon in args:
                if pokemon is None:
                    continue

                await self.bot.mongo.update_pokemon(
                    pokemon,
                    {"$set": {f"favorite": False}},
                )

                name = str(pokemon.species)

                if pokemon.nickname is not None:
                    name += f' "{pokemon.nickname}"'

                messages.append(ctx._("unfavorited-pokemon", level=pokemon.level, pokemon=name))

            longmsg = "\n".join(messages)
            for i in range(0, len(longmsg), 2000):
                await ctx.send(longmsg[i : i + 2000])

    # Filter
    @flags.add_flag("--shiny", action="store_true")
    @flags.add_flag("--alolan", action="store_true")
    @flags.add_flag("--galarian", action="store_true")
    @flags.add_flag("--hisuian", action="store_true")
    @flags.add_flag("--mythical", action="store_true")
    @flags.add_flag("--legendary", action="store_true")
    @flags.add_flag("--ub", action="store_true")
    @flags.add_flag("--event", action="store_true")
    @flags.add_flag("--mega", action="store_true")
    @flags.add_flag("--embedcolor", "--ec", action="store_true")
    @flags.add_flag("--name", "--n", nargs="+", action="append")
    @flags.add_flag("--nickname", nargs="*", action="append")
    @flags.add_flag("--type", "--t", type=str, action="append")
    @flags.add_flag("--region", "--r", type=str, action="append")

    # IV
    @flags.add_flag("--level", nargs="+", action="append")
    @flags.add_flag("--hpiv", nargs="+", action="append")
    @flags.add_flag("--atkiv", nargs="+", action="append")
    @flags.add_flag("--defiv", nargs="+", action="append")
    @flags.add_flag("--spatkiv", nargs="+", action="append")
    @flags.add_flag("--spdefiv", nargs="+", action="append")
    @flags.add_flag("--spdiv", nargs="+", action="append")
    @flags.add_flag("--iv", nargs="+", action="append")

    # Duplicate IV's
    @flags.add_flag("--triple", "--three", type=int)
    @flags.add_flag("--quadruple", "--four", "--quadra", "--quad", "--tetra", type=int)
    @flags.add_flag("--pentuple", "--quintuple", "--penta", "--pent", "--five", type=int)
    @flags.add_flag("--hextuple", "--sextuple", "--hexa", "--hex", "--six", type=int)

    # Skip/limit
    @flags.add_flag("--skip", type=int)
    @flags.add_flag("--limit", type=int)

    # Rename all
    @checks.has_started()
    @commands.max_concurrency(1, commands.BucketType.user)
    @flags.command(
        aliases=(
            "favouriteall",
            "favall",
            "fa",
        )
    )
    async def favoriteall(self, ctx, **flags):
        """Mass favorite selected pokemon."""

        member = await self.bot.mongo.fetch_member_info(ctx.author)
        aggregations = await self.create_filter(flags, ctx, order_by=member.order_by)

        if aggregations is None:
            return

        # Check pokemon and unfavorited pokemon num
        num = await self.bot.mongo.fetch_pokemon_count(ctx.author, aggregations=aggregations)

        aggregations.append({"$match": {"favorite": {"$ne": True}}})
        unfavnum = await self.bot.mongo.fetch_pokemon_count(ctx.author, aggregations=aggregations)

        if num == 0:
            return await ctx.send(ctx._("found-no-pokemon-matching"))
        elif unfavnum == 0:
            return await ctx.send(ctx._("favoriteall-none-found"))

        # Fetch pokemon list
        pokemon = self.bot.mongo.fetch_pokemon_list(ctx.author, aggregations)

        # confirm

        result = await ctx.confirm(ctx._("favoriteall-confirm", number=unfavnum))
        if result is None:
            return await ctx.send(ctx._("times-up"))
        if result is False:
            return await ctx.send(ctx._("aborted"))

        await self.bot.mongo.db.pokemon.update_many(
            {"_id": {"$in": [x.id async for x in pokemon]}},
            {"$set": {"favorite": True}},
        )

        await ctx.send(ctx._("favoriteall-completed", nowFavorited=unfavnum, totalSelected=num))

    # Filter
    @flags.add_flag("--shiny", action="store_true")
    @flags.add_flag("--alolan", action="store_true")
    @flags.add_flag("--galarian", action="store_true")
    @flags.add_flag("--hisuian", action="store_true")
    @flags.add_flag("--mythical", action="store_true")
    @flags.add_flag("--legendary", action="store_true")
    @flags.add_flag("--ub", action="store_true")
    @flags.add_flag("--event", action="store_true")
    @flags.add_flag("--mega", action="store_true")
    @flags.add_flag("--favorite", action="store_true")
    @flags.add_flag("--embedcolor", "--ec", action="store_true")
    @flags.add_flag("--name", "--n", nargs="+", action="append")
    @flags.add_flag("--nickname", nargs="*", action="append")
    @flags.add_flag("--type", "--t", type=str, action="append")
    @flags.add_flag("--region", "--r", type=str, action="append")

    # IV
    @flags.add_flag("--level", nargs="+", action="append")
    @flags.add_flag("--hpiv", nargs="+", action="append")
    @flags.add_flag("--atkiv", nargs="+", action="append")
    @flags.add_flag("--defiv", nargs="+", action="append")
    @flags.add_flag("--spatkiv", nargs="+", action="append")
    @flags.add_flag("--spdefiv", nargs="+", action="append")
    @flags.add_flag("--spdiv", nargs="+", action="append")
    @flags.add_flag("--iv", nargs="+", action="append")

    # Duplicate IV's
    @flags.add_flag("--triple", "--three", type=int)
    @flags.add_flag("--quadruple", "--four", "--quadra", "--quad", "--tetra", type=int)
    @flags.add_flag("--pentuple", "--quintuple", "--penta", "--pent", "--five", type=int)
    @flags.add_flag("--hextuple", "--sextuple", "--hexa", "--hex", "--six", type=int)

    # Skip/limit
    @flags.add_flag("--skip", type=int)
    @flags.add_flag("--limit", type=int)

    # Rename all
    @checks.has_started()
    @commands.max_concurrency(1, commands.BucketType.user)
    @flags.command(
        aliases=(
            "unfavouriteall",
            "unfavall",
            "ufa",
        )
    )
    async def unfavoriteall(self, ctx, **flags):
        """Mass unfavorite selected pokemon."""

        member = await self.bot.mongo.fetch_member_info(ctx.author)
        aggregations = await self.create_filter(flags, ctx, order_by=member.order_by)

        if aggregations is None:
            return

        # Check pokemon and unfavorited pokemon num
        num = await self.bot.mongo.fetch_pokemon_count(ctx.author, aggregations=aggregations)

        aggregations.append({"$match": {"favorite": True}})
        favnum = await self.bot.mongo.fetch_pokemon_count(ctx.author, aggregations=aggregations)

        if num == 0:
            return await ctx.send(ctx._("found-no-pokemon-matching"))
        elif favnum == 0:
            return await ctx.send(ctx._("unfavoriteall-non-found"))

        # Fetch pokemon list
        pokemon = self.bot.mongo.fetch_pokemon_list(ctx.author, aggregations)

        # confirm

        result = await ctx.confirm(ctx._("unfavoriteall-confirm", number=favnum))
        if result is None:
            return await ctx.send(ctx._("times-up"))
        if result is False:
            return await ctx.send(ctx._("aborted"))

        await self.bot.mongo.db.pokemon.update_many(
            {"_id": {"$in": [x.id async for x in pokemon]}},
            {"$set": {"favorite": False}},
        )

        await ctx.send(ctx._("unfavoriteall-completed", totalSelected=num, nowUnfavorited=favnum))

    @checks.has_started()
    @commands.cooldown(3, 5, commands.BucketType.user)
    @commands.command(aliases=("i",), rest_is_raw=True)
    async def info(self, ctx, *, pokemon: converters.PokemonConverter):
        """View a specific pokémon from your collection."""

        if pokemon is None:
            return await ctx.send(ctx._("unknown-pokemon"))

        ## Hacky way using 0=first, 1=prev, 2=curr, 3=next, 4=last page LOL

        async def get_page(source, menu, pidx):
            nonlocal pokemon

            menu.current_page = 2

            agg = None

            if pidx == 4:
                agg = [{"$sort": {"idx": -1}}]
            elif pidx == 3:
                agg = [{"$match": {"idx": {"$gt": pokemon.idx}}}]
            elif pidx == 1:
                agg = [
                    {"$match": {"idx": {"$lt": pokemon.idx}}},
                    {"$sort": {"idx": -1}},
                ]
            elif pidx == 0:
                agg = []

            if agg is not None:
                it = self.bot.mongo.fetch_pokemon_list(ctx.author, agg)
                async for x in it:
                    pokemon = x
                    break

            field_values = {}
            if pokemon.held_item:
                item = self.bot.data.item_by_number(pokemon.held_item)
                emote = ""
                if item.emote is not None:
                    emote = getattr(self.bot.sprites, item.emote) + " "
                field_values["held-item"] = f"{emote}{item.name}"

            embed = ctx.localized_embed(
                "pokemon-info-embed",
                droppable_fields=["held-item"],
                field_ordering=["details", "stats", "held-item"],
                block_fields=True,
                xp=pokemon.xp,
                maxXP=pokemon.max_xp,
                nature=pokemon.nature,
                hp=pokemon.hp,
                ivHp=pokemon.iv_hp,
                atk=pokemon.atk,
                ivAtk=pokemon.iv_atk,
                defn=pokemon.defn,
                ivDefn=pokemon.iv_defn,
                satk=pokemon.satk,
                ivSatk=pokemon.iv_satk,
                sdef=pokemon.sdef,
                ivSdef=pokemon.iv_sdef,
                spd=pokemon.spd,
                ivSpd=pokemon.iv_spd,
                ivPercentage=pokemon.iv_percentage * 100,
                index=pokemon.idx,
                id=str(pokemon.id),
            )

            embed.title = f"{pokemon:lnf}"
            embed.color = pokemon.color or 0x9CCFFF

            if pokemon.shiny:
                embed.set_image(url=pokemon.species.shiny_image_url)
            else:
                embed.set_image(url=pokemon.species.image_url)

            embed.set_thumbnail(url=ctx.author.display_avatar.url)

            return embed

        pages = pagination.ContinuablePages(pagination.FunctionPageSource(5, get_page), allow_go=False)
        pages.current_page = 2
        ctx.bot.menus[ctx.author.id] = pages
        await pages.start(ctx)

    @checks.has_started()
    @checks.is_not_in_trade()
    @commands.command(aliases=("s",), rest_is_raw=True)
    async def select(self, ctx, *, pokemon: converters.PokemonConverter(accept_blank=False)):
        """Select a specific pokémon from your collection."""

        if pokemon is None:
            return await ctx.send(ctx._("unknown-pokemon"))

        await self.bot.mongo.update_member(
            ctx.author,
            {"$set": {f"selected_id": pokemon.id}},
        )

        await ctx.send(ctx._("selected-pokemon", index=pokemon.idx, level=pokemon.level, species=pokemon.species))

    @checks.has_started()
    @commands.command(aliases=("or",))
    async def order(self, ctx, *, sort: str = ""):
        """Change how your pokémon are ordered."""

        sort = sort.lower()

        if sort not in [a + b for a in ("number", "iv", "level", "pokedex") for b in ("+", "-", "")]:
            return await ctx.send(ctx._("invalid-order-specifier"))

        await self.bot.mongo.update_member(
            ctx.author,
            {"$set": {f"order_by": sort}},
        )

        await ctx.send(ctx._("now-ordering-pokemon-by", sort=sort))

    def parse_numerical_flag(self, text):
        if not (1 <= len(text) <= 2):
            return None

        ops = text

        if len(text) == 1 and isfloat(text[0]):
            ops = ["=", text[0]]

        elif len(text) == 1 and not isfloat(text[0][0]):
            ops = [text[0][0], text[0][1:]]

        if ops[0] not in ("<", "=", ">") or not isfloat(ops[1]):
            return None

        return ops

    async def create_filter(self, flags, ctx, order_by=None, map_field=lambda x: x):
        aggregations = []

        if "mine" in flags and flags["mine"]:
            aggregations.append({"$match": {map_field("owner_id"): ctx.author.id}})

        if "bids" in flags and flags["bids"]:
            aggregations.append({"$match": {"auction_data.bidder_id": ctx.author.id}})

        rarity = []
        for x in ("mythical", "legendary", "ub"):
            if x in flags and flags[x]:
                rarity += getattr(self.bot.data, f"list_{x}")
        if rarity:
            aggregations.append({"$match": {map_field("species_id"): {"$in": rarity}}})

        for x in ("alolan", "galarian", "hisuian", "mega", "event"):
            if x in flags and flags[x]:
                aggregations.append({"$match": {map_field("species_id"): {"$in": getattr(self.bot.data, f"list_{x}")}}})

        if "type" in flags and flags["type"]:
            all_species = [i for x in flags["type"] for i in self.bot.data.list_type(x)]
            aggregations.append({"$match": {map_field("species_id"): {"$in": all_species}}})

        if "region" in flags and flags["region"]:
            all_species = [i for x in flags["region"] for i in self.bot.data.list_region(x)]
            aggregations.append({"$match": {map_field("species_id"): {"$in": all_species}}})

        if "favorite" in flags and flags["favorite"]:
            aggregations.append({"$match": {map_field("favorite"): True}})

        if "shiny" in flags and flags["shiny"]:
            aggregations.append({"$match": {map_field("shiny"): True}})

        if "name" in flags and flags["name"] is not None:
            all_species = [i for x in flags["name"] for i in self.bot.data.find_all_matches(" ".join(x))]

            aggregations.append({"$match": {map_field("species_id"): {"$in": all_species}}})

        if "nickname" in flags and flags["nickname"] is not None:
            aggregations.append(
                {
                    "$match": {
                        map_field("nickname"): {
                            "$regex": "(" + ")|(".join(" ".join(x) for x in flags["nickname"]) + ")",
                            "$options": "i",
                        }
                    }
                }
            )

        if "embedcolor" in flags and flags["embedcolor"]:
            aggregations.append({"$match": {map_field("has_color"): True}})

        if "ends" in flags and flags["ends"] is not None:
            aggregations.append({"$match": {"auction_data.ends": {"$lt": datetime.utcnow() + flags["ends"]}}})

        # Numerical flags

        for flag, expr in constants.FILTER_BY_NUMERICAL.items():
            for text in flags[flag] or []:
                ops = self.parse_numerical_flag(text)

                if ops is None:
                    raise commands.BadArgument(ctx._("filter-invalid-numerical", flag=flag, arguments=" ".join(text)))

                ops[1] = float(ops[1])

                if flag == "iv":
                    ops[1] = float(ops[1]) * 186 / 100

                if ops[0] == "<":
                    aggregations.append(
                        {"$match": {map_field(expr): {"$lt": math.ceil(ops[1])}}},
                    )
                elif ops[0] == "=":
                    aggregations.append(
                        {"$match": {map_field(expr): {"$eq": round(ops[1])}}},
                    )
                elif ops[0] == ">":
                    aggregations.append(
                        {"$match": {map_field(expr): {"$gt": math.floor(ops[1])}}},
                    )

        for flag, amt in constants.FILTER_BY_DUPLICATES.items():
            if flag in flags and flags[flag] is not None:
                iv = int(flags[flag])

                # Processing combinations
                combinations = [
                    {map_field(field): iv for field in combo}
                    for combo in itertools.combinations(constants.IV_FIELDS, amt)
                ]
                aggregations.append({"$match": {"$or": combinations}})

        if order_by is not None:
            s = order_by[-1]
            if order_by[-1] in "+-":
                order_by, asc = order_by[:-1], 1 if s == "+" else -1
            else:
                asc = -1 if order_by in constants.DEFAULT_DESCENDING else 1

            aggregations.append({"$sort": {map_field(constants.SORTING_FUNCTIONS[order_by]): asc}})

        if "skip" in flags and flags["skip"] is not None:
            aggregations.append({"$skip": flags["skip"]})

        if "limit" in flags and flags["limit"] is not None:
            aggregations.append({"$limit": flags["limit"]})

        return aggregations

    @checks.has_started()
    @checks.is_not_in_trade()
    @commands.max_concurrency(1, commands.BucketType.user)
    @commands.command(aliases=("r",))
    async def release(self, ctx, args: commands.Greedy[converters.PokemonConverter]):
        """Release pokémon from your collection for 2pc each."""

        member = await self.bot.mongo.fetch_member_info(ctx.author)

        ids = set()
        mons = list()

        for pokemon in args:

            if pokemon is not None:
                # can't release selected/fav

                if pokemon.id in ids:
                    continue

                if member.selected_id == pokemon.id:
                    await ctx.send(ctx._("cannot-release-selected", index=pokemon.idx))
                    continue

                if pokemon.favorite:
                    await ctx.send(ctx._("cannot-release-favorited", index=pokemon.idx))
                    continue

                ids.add(pokemon.id)
                mons.append(pokemon)

        if len(args) != len(mons):
            await ctx.send(ctx._("release-failsafe-mismatch", difference=len(args) - len(mons)))

        # Confirmation msg

        if len(mons) == 0:
            return

        if len(mons) == 1:
            message = ctx._("release-confirm-single", pokemon=f"{mons[0]:spl}", index=mons[0].idx)
        else:
            message = ctx._(
                "release-confirm-multiple", amount=len(mons * 2), pokemon="\n".join(f"{x:spl} ({x.idx})" for x in mons)
            )

        result = await ctx.confirm(message)
        if result is None:
            return await ctx.send(ctx._("times-up"))
        if result is False:
            return await ctx.send(ctx._("aborted"))

        if await self.bot.get_cog("Trading").is_in_trade(ctx.author):
            return await ctx.send(ctx._("forbidden-during-trade"))

        # confirmed, release

        result = await self.bot.mongo.db.pokemon.update_many(
            {"owner_id": ctx.author.id, "_id": {"$in": list(ids)}},
            {"$set": {"owned_by": "released"}},
        )
        await self.bot.mongo.update_member(
            ctx.author,
            {
                "$inc": {"balance": 2 * result.modified_count},
            },
        )
        await ctx.send(ctx._("release-completed", modifiedCount=result.modified_count, coins=2 * result.modified_count))
        self.bot.dispatch("release", ctx.author, result.modified_count)

    # Filter
    @flags.add_flag("page", nargs="?", type=int, default=1)
    @flags.add_flag("--shiny", action="store_true")
    @flags.add_flag("--alolan", action="store_true")
    @flags.add_flag("--galarian", action="store_true")
    @flags.add_flag("--hisuian", action="store_true")
    @flags.add_flag("--mythical", action="store_true")
    @flags.add_flag("--legendary", action="store_true")
    @flags.add_flag("--ub", action="store_true")
    @flags.add_flag("--event", action="store_true")
    @flags.add_flag("--mega", action="store_true")
    @flags.add_flag("--embedcolor", "--ec", action="store_true")
    @flags.add_flag("--name", "--n", nargs="+", action="append")
    @flags.add_flag("--nickname", nargs="*", action="append")
    @flags.add_flag("--type", "--t", type=str, action="append")
    @flags.add_flag("--region", "--r", type=str, action="append")

    # IV
    @flags.add_flag("--level", nargs="+", action="append")
    @flags.add_flag("--hpiv", nargs="+", action="append")
    @flags.add_flag("--atkiv", nargs="+", action="append")
    @flags.add_flag("--defiv", nargs="+", action="append")
    @flags.add_flag("--spatkiv", nargs="+", action="append")
    @flags.add_flag("--spdefiv", nargs="+", action="append")
    @flags.add_flag("--spdiv", nargs="+", action="append")
    @flags.add_flag("--iv", nargs="+", action="append")

    # Duplicate IV's
    @flags.add_flag("--triple", "--three", type=int)
    @flags.add_flag("--quadruple", "--four", "--quadra", "--quad", "--tetra", type=int)
    @flags.add_flag("--pentuple", "--quintuple", "--penta", "--pent", "--five", type=int)
    @flags.add_flag("--hextuple", "--sextuple", "--hexa", "--hex", "--six", type=int)

    # Skip/limit
    @flags.add_flag("--skip", type=int)
    @flags.add_flag("--limit", type=int)

    # Release all
    @checks.has_started()
    @checks.is_not_in_trade()
    @commands.max_concurrency(1, commands.BucketType.user)
    @commands.cooldown(1, 5, commands.BucketType.user)
    @flags.command(aliases=("ra",))
    async def releaseall(self, ctx, **flags):
        """Mass release pokémon from your collection for 2 pc each."""

        member = await self.bot.mongo.fetch_member_info(ctx.author)
        aggregations = await self.create_filter(flags, ctx, order_by=member.order_by)

        if aggregations is None:
            return

        member = await self.bot.mongo.fetch_member_info(ctx.author)

        aggregations.extend(
            [
                {"$match": {"_id": {"$not": {"$eq": member.selected_id}}}},
                {"$match": {"favorite": {"$not": {"$eq": True}}}},
            ]
        )

        num = await self.bot.mongo.fetch_pokemon_count(ctx.author, aggregations=aggregations)

        if num == 0:
            return await ctx.send(ctx._("found-no-pokemon-matching-excluding-favorited-and-selected"))

        # confirm

        result = await ctx.confirm(ctx._("releaseall-confirm", coins=f"{num*2:,}", number=num))
        if result is None:
            return await ctx.send(ctx._("times-up"))
        if result is False:
            return await ctx.send(ctx._("aborted"))

        if await self.bot.get_cog("Trading").is_in_trade(ctx.author):
            return await ctx.send(ctx._("forbidden-during-trade"))

        # confirmed, release all

        num = await self.bot.mongo.fetch_pokemon_count(ctx.author, aggregations=aggregations)

        await ctx.send(ctx._("releaseall-in-progress", number=num))

        pokemon = self.bot.mongo.fetch_pokemon_list(ctx.author, aggregations)

        result = await self.bot.mongo.db.pokemon.update_many(
            {"owner_id": ctx.author.id, "_id": {"$in": [x.id async for x in pokemon]}},
            {"$set": {"owned_by": "released"}},
        )

        await self.bot.mongo.update_member(
            ctx.author,
            {
                "$inc": {"balance": 2 * result.modified_count},
            },
        )

        await ctx.send(
            ctx._("releaseall-completed", coins=2 * result.modified_count, modifiedCount=result.modified_count)
        )
        self.bot.dispatch("release", ctx.author, result.modified_count)

    # Filter
    @flags.add_flag("page", nargs="?", type=int, default=1)
    @flags.add_flag("--shiny", action="store_true")
    @flags.add_flag("--alolan", action="store_true")
    @flags.add_flag("--galarian", action="store_true")
    @flags.add_flag("--hisuian", action="store_true")
    @flags.add_flag("--mythical", action="store_true")
    @flags.add_flag("--legendary", action="store_true")
    @flags.add_flag("--ub", action="store_true")
    @flags.add_flag("--event", action="store_true")
    @flags.add_flag("--mega", action="store_true")
    @flags.add_flag("--favorite", action="store_true")
    @flags.add_flag("--embedcolor", "--ec", action="store_true")
    @flags.add_flag("--name", "--n", nargs="+", action="append")
    @flags.add_flag("--nickname", nargs="*", action="append")
    @flags.add_flag("--type", "--t", type=str, action="append")
    @flags.add_flag("--region", "--r", type=str, action="append")

    # IV
    @flags.add_flag("--level", nargs="+", action="append")
    @flags.add_flag("--hpiv", nargs="+", action="append")
    @flags.add_flag("--atkiv", nargs="+", action="append")
    @flags.add_flag("--defiv", nargs="+", action="append")
    @flags.add_flag("--spatkiv", nargs="+", action="append")
    @flags.add_flag("--spdefiv", nargs="+", action="append")
    @flags.add_flag("--spdiv", nargs="+", action="append")
    @flags.add_flag("--iv", nargs="+", action="append")

    # Duplicate IV's
    @flags.add_flag("--triple", "--three", type=int)
    @flags.add_flag("--quadruple", "--four", "--quadra", "--quad", "--tetra", type=int)
    @flags.add_flag("--pentuple", "--quintuple", "--penta", "--pent", "--five", type=int)
    @flags.add_flag("--hextuple", "--sextuple", "--hexa", "--hex", "--six", type=int)

    # Skip/limit
    @flags.add_flag("--skip", type=int)
    @flags.add_flag("--limit", type=int)

    # Pokemon
    @checks.has_started()
    @commands.cooldown(1, 5, commands.BucketType.user)
    @flags.command(aliases=("p",))
    async def pokemon(self, ctx, **flags):
        """View or filter the pokémon in your collection."""

        if flags["page"] < 1:
            return await ctx.send(ctx._("page-must-be-positive"))

        member = await self.bot.mongo.fetch_member_info(ctx.author)

        aggregations = await self.create_filter(flags, ctx, order_by=member.order_by)
        if aggregations is None:
            return

        # Filter pokemon

        def padn(p, n):
            return " " * (len(str(n)) - len(str(p.idx))) + str(p.idx)

        def prepare_page(menu, items):
            menu.maxn = max(x.idx for x in items)

        def format_item(menu, p):
            return ctx._(
                "pokemon-page-line",
                paddedNumeral=padn(p, menu.maxn),
                pokemon=f"{p:nif}",
                iv=(p.iv_total / 186) * 100,
                level=p.level,
            )

        count = await self.bot.mongo.fetch_pokemon_count(ctx.author, aggregations)
        pokemon = self.bot.mongo.fetch_pokemon_list(ctx.author, aggregations)

        pages = pagination.ContinuablePages(
            pagination.AsyncListPageSource(
                pokemon,
                title=ctx._("pokemon-page-title"),
                prepare_page=prepare_page,
                format_item=format_item,
                per_page=20,
                count=count,
            )
        )
        pages.current_page = flags["page"] - 1
        self.bot.menus[ctx.author.id] = pages

        try:
            await pages.start(ctx)
        except IndexError:
            await ctx.send(ctx._("no-pokemon-found"))

    @flags.add_flag("page", nargs="*", type=str, default="1")
    @flags.add_flag("--caught", action="store_true")
    @flags.add_flag("--uncaught", action="store_true")
    @flags.add_flag("--legendary", action="store_true")
    @flags.add_flag("--mythical", action="store_true")
    @flags.add_flag("--orderd", action="store_true")
    @flags.add_flag("--ordera", action="store_true")
    @flags.add_flag("--ub", action="store_true")
    @flags.add_flag("--type", "--t", type=str)
    @flags.add_flag("--region", "--r", type=str)
    @checks.has_started()
    @flags.command(aliases=("d", "dex"))
    async def pokedex(self, ctx, **flags):
        """View your pokédex, or search for a pokémon species."""

        search_or_page = " ".join(flags["page"])

        if flags["orderd"] and flags["ordera"]:
            return await ctx.send(ctx._("pokedex-orderd-ordera-mutually-exclusive"))

        if flags["caught"] and flags["uncaught"]:
            return await ctx.send(ctx._("pokedex-caught-uncaught-mutually-exclusive"))

        if flags["mythical"] + flags["legendary"] + flags["ub"] > 1:
            return await ctx.send(ctx._("pokedex-only-one-rarity-flag"))

        if search_or_page is None:
            search_or_page = "1"

        total_count = sum(x.catchable and x.id < 10000 for x in self.bot.data.all_pokemon())

        if search_or_page.isdigit():
            pgstart = (int(search_or_page) - 1) * 20

            if pgstart >= total_count or pgstart < 0:
                return await ctx.send(ctx._("no-pokemon-on-this-page"))

            num = await self.bot.mongo.fetch_pokedex_count(ctx.author)

            do_emojis = ctx.guild is None or ctx.channel.permissions_for(ctx.guild.me).external_emojis

            member = await self.bot.mongo.fetch_pokedex(ctx.author, 0, total_count + 1)
            pokedex = member.pokedex

            if not flags["uncaught"] and not flags["caught"]:
                for i in range(1, total_count + 1):
                    if str(i) not in pokedex:
                        pokedex[str(i)] = 0
            elif flags["uncaught"]:
                for i in range(1, total_count + 1):
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
                if flags["region"] and key not in self.bot.data.list_region(flags["region"]):
                    return False

                return True

            pokedex = {int(k): v for k, v in pokedex.items() if include(int(k))}

            if flags["ordera"]:
                pokedex = sorted(pokedex.items(), key=itemgetter(1))
            elif flags["orderd"]:
                pokedex = sorted(pokedex.items(), key=itemgetter(1), reverse=True)
            else:
                pokedex = sorted(pokedex.items(), key=itemgetter(0))

            async def get_page(source, menu, pidx):
                pgstart = pidx * 20
                pgend = min(pgstart + 20, len(pokedex))

                # Send embed

                embed = ctx.localized_embed(
                    "pokedex-embed",
                    caught=num,
                    allTotalPokemon=total_count,
                    beginning=pgstart + 1,
                    end=pgend,
                    totalFiltered=len(pokedex),
                )

                for k, v in pokedex[pgstart:pgend]:
                    species = self.bot.data.species_by_number(k)

                    text = ctx._("pokedex-not-caught-yet")
                    if do_emojis:
                        text = self.bot.sprites.cross + f" {text}"

                    if v > 0:
                        text = ctx._("pokedex-n-caught", caught=v)
                        if do_emojis:
                            text = self.bot.sprites.check + f" {text}"

                    if do_emojis:
                        emoji = self.bot.sprites.get(k) + " "
                    else:
                        emoji = ""

                    embed.add_field(name=f"{emoji}{species.name} #{species.id}", value=text)

                if pgend != total_count:
                    embed.add_field(name="‎", value="‎")

                return embed

            pages = pagination.ContinuablePages(pagination.FunctionPageSource(math.ceil(total_count / 20), get_page))
            pages.current_page = int(search_or_page) - 1
            self.bot.menus[ctx.author.id] = pages
            await pages.start(ctx)

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
                    return await ctx.send(ctx._("unknown-pokemon-matching", matching=search_or_page))

            member = await self.bot.mongo.fetch_pokedex(ctx.author, species.dex_number, species.dex_number + 1)

            # Pokemon Rarity
            rarity = []
            if species.mythical:
                rarity.append(ctx._("rarity-mythical"))
            if species.legendary:
                rarity.append(ctx._("rarity-legendary"))
            if species.ultra_beast:
                rarity.append(ctx._("rarity-ultra-beast"))
            if species.event:
                rarity.append(ctx._("rarity-event"))

            embed = ctx.localized_embed(
                "pokedex-species-embed",
                field_ordering=[
                    "rarity",
                    "evolution",
                    "types",
                    "region",
                    "catchable",
                    "base-stats",
                    "names",
                    "appearance",
                ],
                field_values={
                    "rarity": ", ".join(rarity),
                    "evolution": species.evolution_text,
                    "types": "\n".join(species.types),
                    "region": species.region.title(),
                    "catchable": "Yes" if species.catchable else "No",
                    "names": "\n".join(f"{x} {y}" for x, y in species.names),
                    "appearance": f"Height: {species.height} m\nWeight: {species.weight} kg",
                },
                block_fields=["rarity", "evolution"],
                dexNumber=species.dex_number,
                hp=species.base_stats.hp,
                atk=species.base_stats.atk,
                defn=species.base_stats.defn,
                satk=species.base_stats.satk,
                sdef=species.base_stats.sdef,
                spd=species.base_stats.spd,
                species=str(species),
            )

            if species.description:
                embed.description = species.description.replace("\n", " ")

            if shiny:
                embed.title = ctx._(
                    "pokedex-species-embed-title-shiny", dexNumber=species.dex_number, species=str(species)
                )
                embed.set_image(url=species.shiny_image_url)
            else:
                embed.set_image(url=species.image_url)

            text = ctx._("pokedex-you-havent-caught-yet")
            if str(species.dex_number) in member.pokedex:
                text = ctx._("pokedex-caught-n-of-this-pokemon", amount=member.pokedex[str(species.dex_number)])

            if species.art_credit:
                text = ctx._("pokedex-art-credit", artist=species.art_credit) + "\n" + text

            embed.set_footer(text=text)

            await ctx.send(embed=embed)

    @checks.has_started()
    @commands.guild_only()
    @commands.command(rest_is_raw=True)
    async def evolve(self, ctx, args: commands.Greedy[converters.PokemonConverter]):
        """Evolve a pokémon if it has reached the target level."""

        args = list({p.id: p for p in args}.values())  # Remove duplicates based on id

        if len(args) == 0:
            args.append(await converters.PokemonConverter().convert(ctx, ""))

        if not all(pokemon is not None for pokemon in args):
            return await ctx.send(ctx._("unknown-pokemon"))

        member = await self.bot.mongo.fetch_member_info(ctx.author)
        guild = await self.bot.mongo.fetch_guild(ctx.guild)

        embed = self.bot.Embed(description="", title=ctx._("congratulations", name=ctx.author.display_name))

        evolved = []

        if len(args) > 30:
            return await ctx.send(ctx._("too-many-evolutions-at-once", limit=30))

        for pokemon in args:
            name = format(pokemon, "n")

            if (evo := pokemon.get_next_evolution(guild.is_day)) is None:
                return await ctx.send(ctx._("cannot-be-evolved", pokemon=name))

            if len(args) < 20:
                embed.add_field(
                    name=ctx._("pokemon-evolving", pokemon=name),
                    value=ctx._("pokemon-turned-into", old=name, new=evo),
                    inline=True,
                )

            else:
                embed.description += ctx._("evolved-compact-line", old=name, new=evo)

            if len(args) == 1:
                if pokemon.shiny:
                    embed.set_thumbnail(url=evo.shiny_image_url)
                else:
                    embed.set_thumbnail(url=evo.image_url)

            evolved.append((pokemon, evo))

        for pokemon, evo in evolved:
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
            return await ctx.send(ctx._("unknown-pokemon"))

        fr = self.bot.data.species_by_number(pokemon.species.dex_number)

        if pokemon.species not in (
            fr.mega,
            fr.mega_x,
            fr.mega_y,
        ):
            return await ctx.send(ctx._("pokemon-must-be-mega"))

        # confirm

        result = await ctx.confirm(ctx._("unmega-confirm", pokemon=f"{pokemon:spl}"))
        if result is None:
            return await ctx.send(ctx._("times-up"))
        if result is False:
            return await ctx.send(ctx._("aborted"))

        await self.bot.mongo.update_pokemon(
            pokemon,
            {"$set": {f"species_id": fr.id}},
        )

        await ctx.send(ctx._("unmega-completed"))

    @checks.has_started()
    @commands.command(aliases=("f",))
    async def first(self, ctx):
        if ctx.author.id not in self.bot.menus:
            return await ctx.send(ctx._("no-previous-menu-to-navigate"))

        pages = self.bot.menus[ctx.author.id]
        with contextlib.suppress(TypeError, DiscordException):
            await pages.message.clear_reactions()
        await pages.continue_at(ctx, 0)

    @checks.has_started()
    @commands.command(aliases=("n", "forward"))
    async def next(self, ctx):
        if ctx.author.id not in self.bot.menus:
            return await ctx.send(ctx._("no-previous-menu-to-navigate"))

        pages = self.bot.menus[ctx.author.id]
        with contextlib.suppress(AttributeError, TypeError, DiscordException):
            await pages.message.clear_reactions()
        await pages.continue_at(ctx, pages.current_page + 1)

    @checks.has_started()
    @commands.command(aliases=("prev", "back", "b"))
    async def previous(self, ctx):
        if ctx.author.id not in self.bot.menus:
            return await ctx.send(ctx._("no-previous-menu-to-navigate"))

        pages = self.bot.menus[ctx.author.id]
        if pages.current_page == 0 and not pages.allow_last:
            return await ctx.send(ctx._("pagination-market-cannot-jump-to-last-page"))
        with contextlib.suppress(AttributeError, TypeError, DiscordException):
            await pages.message.clear_reactions()
        await pages.continue_at(ctx, pages.current_page - 1)

    @checks.has_started()
    @commands.command(aliases=("l",))
    async def last(self, ctx):
        if ctx.author.id not in self.bot.menus:
            return await ctx.send(ctx._("no-previous-menu-to-navigate"))

        pages = self.bot.menus[ctx.author.id]
        if not pages.allow_last:
            return await ctx.send(ctx._("pagination-market-command-unsupported"))
        with contextlib.suppress(AttributeError, TypeError, DiscordException):
            await pages.message.clear_reactions()
        await pages.continue_at(ctx, pages._source.get_max_pages() - 1)

    @checks.has_started()
    @commands.command(aliases=("page", "g"))
    async def go(self, ctx, page: int):
        if ctx.author.id not in self.bot.menus:
            return await ctx.send(ctx._("no-previous-menu-to-navigate"))

        pages = self.bot.menus[ctx.author.id]
        if not pages.allow_go:
            return await ctx.send(ctx._("pagination-market-info-command-unsupported"))
        with contextlib.suppress(AttributeError, TypeError, DiscordException):
            await pages.message.clear_reactions()
        await pages.continue_at(ctx, page - 1)


async def setup(bot: commands.Bot):
    await bot.add_cog(Pokemon(bot))
