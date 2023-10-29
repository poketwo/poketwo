import random
import typing
from datetime import datetime, timedelta

import discord
import humanfriendly
from discord.ext import commands, tasks

from cogs import mongo
from data import models
from helpers import checks, constants, converters


async def add_reactions(message, *emojis):
    for emoji in emojis:
        await message.add_reaction(emoji)


class Shop(commands.Cog):
    """Shop-related commands."""

    def __init__(self, bot):
        self.bot = bot
        self.check_weekend.start()

    @tasks.loop(minutes=5)
    async def check_weekend(self):
        async with self.bot.http_session.get("https://discordbots.org/api/weekend") as r:
            if r.status == 200:
                js = await r.json()
                self.weekend = js["is_weekend"]

    @check_weekend.before_loop
    async def before_check_weekend(self):
        await self.bot.wait_until_ready()

    @property
    def month_number(self):
        now = datetime.utcnow()
        return str(now.year * 12 + now.month)

    @commands.command()
    @checks.is_admin()
    async def stopincense(self, ctx):
        channel = await self.bot.mongo.fetch_channel(ctx.channel)
        if not channel.incense_active:
            return await ctx.send(ctx._("no-active-incense"))

        result = await ctx.confirm(ctx._("confirm-incense-cancellation"))
        if result is None:
            return await ctx.send(ctx._("times-up"))
        if result is False:
            return await ctx.send(ctx._("aborted"))

        await self.bot.mongo.update_channel(
            ctx.channel,
            {
                "$set": {"spawns_remaining": 0},
            },
        )
        await ctx.send(ctx._("incense-stopped"))

    @checks.has_started()
    @commands.command(aliases=("o",))
    async def open(self, ctx, type: str = "", amt: int = 1):
        """Open mystery boxes received from voting."""

        do_emojis = ctx.guild is None or ctx.channel.permissions_for(ctx.guild.me).external_emojis

        if type.lower() not in ("normal", "great", "ultra", "master"):
            if type.lower() in ("n", "g", "u", "m"):
                type = constants.BOXES[type.lower()]
            else:
                return await ctx.send(ctx._("invalid-box-type"))

        member = await self.bot.mongo.fetch_member_info(ctx.author)

        if amt <= 0:
            return await ctx.send(ctx._("nice-try"))

        if amt > 15:
            return await ctx.send(ctx._("too-many-boxes-at-once", limit=15))

        try:
            await self.bot.mongo.db.member.find_one_and_update(
                {"$and": [{"_id": ctx.author.id}, {f"gifts_{type.lower()}": {"$gte": amt}}]},
                {"$inc": {f"gifts_{type.lower()}": -amt}},
                upsert=True,
            )
        except:
            return await ctx.send(ctx._("not-enough-boxes"))

        rewards = random.choices(constants.REWARDS, constants.REWARD_WEIGHTS[type.lower()], k=amt)

        update = {
            "$inc": {"balance": 0, "redeems": 0},
        }

        added_pokemon = []

        embed = self.bot.Embed()
        embed.title = ctx._(
            "opening-box-with-sprite" if do_emojis else "opening-box-simple",
            amount=amt,
            sprite=getattr(self.bot.sprites, f"gift_{type.lower()}"),
            type=type.title(),
        )

        text = []

        for reward in rewards:
            if reward["type"] == "pp":
                update["$inc"]["balance"] += reward["value"]
                text.append(ctx._("box-reward-pokecoins", coins=reward["value"]))
            elif reward["type"] == "redeem":
                update["$inc"]["redeems"] += reward["value"]
                text.append(ctx._("box-reward-redeems", redeems=reward["value"]))
            elif reward["type"] == "pokemon":
                species = self.bot.data.random_spawn(rarity=reward["value"])
                level = min(max(int(random.normalvariate(70, 10)), 1), 100)
                shiny = reward["value"] == "shiny" or member.determine_shiny(species)

                lower_bound = 0
                absolute_lower_bound = 0

                if reward["value"] == "iv1":
                    lower_bound = 21

                if reward["value"] == "iv2":
                    lower_bound = 25

                if reward["value"] == "iv3":
                    lower_bound = 25
                    absolute_lower_bound = 10

                ivs = [
                    random.randint(lower_bound, 31),
                    random.randint(lower_bound, 31),
                    random.randint(lower_bound, 31),
                    random.randint(absolute_lower_bound, 31),
                    random.randint(absolute_lower_bound, 31),
                    random.randint(0, 31),
                ]

                random.shuffle(ivs)

                pokemon = {
                    "owner_id": ctx.author.id,
                    "owned_by": "user",
                    "species_id": species.id,
                    "level": level,
                    "xp": 0,
                    "nature": mongo.random_nature(),
                    "iv_hp": ivs[0],
                    "iv_atk": ivs[1],
                    "iv_defn": ivs[2],
                    "iv_satk": ivs[3],
                    "iv_sdef": ivs[4],
                    "iv_spd": ivs[5],
                    "iv_total": sum(ivs),
                    "shiny": shiny,
                    "idx": await self.bot.mongo.fetch_next_idx(ctx.author),
                }

                pokemon_model = self.bot.mongo.Pokemon.build_from_mongo(pokemon)
                text.append(ctx._("box-reward-pokemon", pokemon=f"{pokemon_model:lni}", iv=sum(ivs) / 186 * 100))

                added_pokemon.append(pokemon)

        embed.add_field(name=ctx._("box-reward-field-title"), value="\n".join(text))

        await self.bot.mongo.update_member(ctx.author, update)
        if len(added_pokemon) > 0:
            await self.bot.mongo.db.pokemon.insert_many(added_pokemon)
        self.bot.dispatch("open_box", ctx.author, amt)
        await ctx.send(embed=embed)

    @checks.has_started()
    @commands.command(aliases=("bal",))
    async def balance(self, ctx):
        """View your current balance."""

        member = await self.bot.mongo.fetch_member_info(ctx.author)

        embed = ctx.localized_embed(
            "balance-embed",
            user=ctx.author.display_name,
            coins=member.balance,
            shards=member.premium_balance,
            field_ordering=["coins", "shards"],
        )
        embed.color = constants.PINK
        embed.set_thumbnail(url=ctx.author.display_avatar.url)
        await ctx.send(embed=embed)

    @checks.has_started()
    @commands.command(aliases=("di",), rest_is_raw=True)
    async def dropitem(self, ctx, *, pokemon: converters.PokemonConverter):
        """Drop a pokémon's held item."""

        if pokemon is None:
            return await ctx.send(ctx._("unknown-pokemon"))

        if pokemon.held_item is None:
            return await ctx.send(ctx._("pokemon-not-holding-item"))

        num = await self.bot.mongo.fetch_pokemon_count(ctx.author)

        await self.bot.mongo.update_pokemon(
            pokemon,
            {"$set": {f"held_item": None}},
        )

        name = str(pokemon.species)

        if pokemon.nickname is not None:
            name += f' "{pokemon.nickname}"'

        await ctx.send(ctx._("pokemon-dropped-item", level=pokemon.level, name=name))

    @checks.has_started()
    @commands.command(aliases=("mvi",))
    async def moveitem(
        self,
        ctx,
        from_pokemon: converters.PokemonConverter,
        to_pokemon: converters.PokemonConverter = None,
    ):
        """Move a pokémon's held item."""

        if to_pokemon is None:
            to_pokemon = from_pokemon
            converter = converters.PokemonConverter()
            from_pokemon = await converter.convert(ctx, "")

        if to_pokemon is None:
            return await ctx.send(ctx._("unknown-pokemon"))

        if from_pokemon is None or to_pokemon is None:
            return await ctx.send(ctx._("unknown-pokemon"))

        if from_pokemon.held_item is None:
            return await ctx.send(ctx._("pokemon-not-holding-item"))

        if to_pokemon.held_item is not None:
            return await ctx.send(ctx._("pokemon-already-holding-item"))

        num = await self.bot.mongo.fetch_pokemon_count(ctx.author)

        await self.bot.mongo.update_pokemon(from_pokemon, {"$set": {f"held_item": None}})
        await self.bot.mongo.update_pokemon(to_pokemon, {"$set": {f"held_item": from_pokemon.held_item}})

        from_name = str(from_pokemon.species)

        if from_pokemon.nickname is not None:
            from_name += f' "{from_pokemon.nickname}"'

        to_name = str(to_pokemon.species)

        if to_pokemon.nickname is not None:
            to_name += f' "{to_pokemon.nickname}"'

        await ctx.send(
            ctx._(
                "moved-items",
                fromLevel=from_pokemon.level,
                fromName=from_name,
                toLevel=to_pokemon.level,
                toName=to_name,
            )
        )

    @checks.has_started()
    @commands.command(aliases=("togglebal",))
    async def togglebalance(self, ctx):
        """Toggle showing balance in shop."""

        member = await self.bot.mongo.fetch_member_info(ctx.author)

        await self.bot.mongo.update_member(ctx.author, {"$set": {"show_balance": not member.show_balance}})

        if member.show_balance:
            await ctx.send(ctx._("balance-now-hidden"))
        else:
            await ctx.send(ctx._("balance-no-longer-hidden"))

    @checks.has_started()
    @commands.command(aliases=("store",))
    async def shop(self, ctx, *, page: int = 0):
        """View the Pokétwo item shop."""

        member = await self.bot.mongo.fetch_member_info(ctx.author)

        embed = self.bot.Embed(title=ctx._("shop-title"))

        if member.show_balance:
            if page == 7:
                embed.title = ctx._("shop-title-balance-shards", coins=member.balance, shards=member.premium_balance)
            else:
                embed.title = ctx._("shop-title-balance", coins=member.balance)

        if page == 0:
            embed.description = ctx._("shop-page-cta")

            embed.add_field(name="Page 1", value=ctx._("shop-page-1-title"), inline=False)
            embed.add_field(name="Page 2", value=ctx._("shop-page-2-title"), inline=False)
            embed.add_field(name="Page 3", value=ctx._("shop-page-3-title"), inline=False)
            embed.add_field(name="Page 4", value=ctx._("shop-page-4-title"), inline=False)
            embed.add_field(name="Page 5", value=ctx._("shop-page-5-title"), inline=False)
            embed.add_field(name="Page 6", value=ctx._("shop-page-6-title"), inline=False)
            embed.add_field(name="Page 7", value=ctx._("shop-page-7-title"), inline=False)

        else:
            embed.description = ctx._("shop-description")

            if page == 7:
                embed.description = ctx._("shop-description-shards")

            items = [i for i in self.bot.data.all_items() if i.page == page]

            do_emojis = ctx.guild is None or ctx.channel.permissions_for(ctx.guild.me).external_emojis

            for item in items:
                emote = ""
                if do_emojis and item.emote is not None:
                    emote = getattr(self.bot.sprites, item.emote) + " "

                name = f"{emote}{item.name}"
                if item.action == "level":
                    name = name[:-1] + "ies"
                if item.action in ("shard", "redeem"):
                    name += "s"

                if item.description:
                    name += f" – {item.cost} {'shards' if item.shard else 'pc'}"
                    if item.action in ("level", "shard", "redeem"):
                        name += " each"
                    value = item.description

                else:
                    value = f"{item.cost} {'shards' if item.shard else 'pc'}"
                    if item.action in ("level", "shard", "redeem"):
                        value += " each"

                embed.add_field(name=name, value=value, inline=item.inline)

            if items[-1].inline:
                for i in range(-len(items) % 3):
                    embed.add_field(name="‎", value="‎")

        footer_text = []

        if member.boost_active:
            timespan = member.boost_expires - datetime.utcnow()
            timespan = humanfriendly.format_timespan(timespan.total_seconds())
            footer_text.append(ctx._("shop-booster-active", expires=timespan))

        if member.shiny_charm_active:
            timespan = member.shiny_charm_expires - datetime.utcnow()
            timespan = humanfriendly.format_timespan(timespan.total_seconds())
            footer_text.append(ctx._("shop-shiny-charm-active", expires=timespan))

        if len(footer_text) > 0:
            embed.set_footer(text="\n".join(footer_text))

        await ctx.send(embed=embed)

    @checks.has_started()
    @commands.max_concurrency(1, commands.BucketType.user, wait=True)
    @commands.guild_only()
    @commands.command()
    @checks.is_not_in_trade()
    async def buy(self, ctx, *args: str):
        """Purchase an item from the shop."""

        if len(args) == 0:
            return

        qty = 1

        if args[-1].isdigit() and args[0].lower() != "xp":
            args, qty = args[:-1], int(args[-1])

            if qty <= 0:
                return await ctx.send(ctx._("nice-try"))

        search = " ".join(args)
        if search.lower() == "shards":
            search = "shard"
        if search.lower() == "redeems":
            search = "redeem"
        if search.lower() == "rare candies":
            search = "rare candy"
        item = self.bot.data.item_by_name(search)
        if item is None:
            return await ctx.send(ctx._("buy-unknown-item", item=" ".join(args)))

        member = await self.bot.mongo.fetch_member_info(ctx.author)
        pokemon = await self.bot.mongo.fetch_pokemon(ctx.author, member.selected_id)

        if pokemon is None:
            return await ctx.send(ctx._("pokemon-must-be-selected"))

        if qty > 1 and item.action not in ("level", "shard", "redeem"):
            return await ctx.send(ctx._("cannot-buy-multiple"))

        if (member.premium_balance if item.shard else member.balance) < item.cost * qty:
            return await ctx.send(ctx._("not-enough-shards") if item.shard else ctx._("not-enough-coins"))

        # Check to make sure it's purchasable.

        if item.action == "level":
            if pokemon.level + qty > 100:
                return await ctx.send(ctx._("cannot-overlevel-pokemon", level=pokemon.level))

        if item.action == "evolve_mega":
            if pokemon.species.mega is None:
                return await ctx.send(ctx._("item-not-applicable"))

            evoto = pokemon.species.mega

            if pokemon.held_item == 13001:
                return await ctx.send(ctx._("pokemon-holding-everstone"))

        if item.action == "evolve_megax":
            if pokemon.species.mega_x is None:
                return await ctx.send(ctx._("item-not-applicable"))

            evoto = pokemon.species.mega_x

            if pokemon.held_item == 13001:
                return await ctx.send(ctx._("pokemon-holding-everstone"))

        if item.action == "evolve_megay":
            if pokemon.species.mega_y is None:
                return await ctx.send(ctx._("item-not-applicable"))

            evoto = pokemon.species.mega_y

            if pokemon.held_item == 13001:
                return await ctx.send(ctx._("pokemon-holding-everstone"))

        if item.action == "evolve_normal":
            if pokemon.species.evolution_to is not None:
                try:
                    evoto = next(
                        filter(
                            lambda evo: isinstance(evo.trigger, models.ItemTrigger) and evo.trigger.item == item,
                            pokemon.species.evolution_to.items,
                        )
                    ).target
                except StopIteration:
                    return await ctx.send(ctx._("item-not-applicable"))
            else:
                return await ctx.send(ctx._("item-not-applicable"))

            if pokemon.held_item == 13001:
                return await ctx.send(ctx._("pokemon-holding-everstone"))

        if item.action == "form_item":
            forms = self.bot.data.all_species_by_number(pokemon.species.dex_number)
            for form in forms:
                if form.id != pokemon.species.id and form.form_item is not None and form.form_item == item.id:
                    break
            else:
                return await ctx.send(ctx._("item-not-applicable"))

        if "xpboost" in item.action:
            if member.boost_active:
                return await ctx.send(ctx._("xp-booster-already-active"))

            await ctx.send(ctx._("purchased-time-remaining", item=item.name))

        elif item.action == "shard":
            result = await ctx.confirm(ctx._("shard-exchange-prompt", coins=item.cost * qty, shards=qty))
            if result is None:
                return await ctx.send(ctx._("times-up"))
            if result is False:
                return await ctx.send(ctx._("aborted"))

            await ctx.send(ctx._("purchased-shards", shards=qty))

        elif item.action == "redeem":
            await ctx.send(ctx._("purchased-redeems", redeems=qty))

        elif item.action == "shiny_charm":
            if member.shiny_charm_active:
                return await ctx.send(ctx._("shiny-charm-already-active"))

            await ctx.send(ctx._("purchased-time-remaining", item=item.name))

        elif item.action == "incense":

            permissions = ctx.channel.permissions_for(ctx.author)

            if (
                not permissions.administrator
                and discord.utils.find(lambda r: r.name.lower() == "incense", ctx.author.roles) is None
            ):
                return await ctx.send(ctx._("missing-incense-permissions"))

            if await self.bot.redis.get("incense_disabled") is not None:
                return await ctx.send(ctx._("incense-unavailable"))

            channel = await self.bot.mongo.fetch_channel(ctx.channel)
            if channel.incense_active:
                return await ctx.send(ctx._("incense-already-active"))

            await ctx.send(ctx._("purchased-generic-vowel", item=item.name))
        elif item.shard:
            begins_with_vowel = item.name[0] in "aeiou"
            await ctx.send(ctx._("purchased-generic-vowel" if begins_with_vowel else "purchased-generic"))
        else:
            name = str(pokemon.species)

            if pokemon.nickname is not None:
                name += f' "{pokemon.nickname}"'

            if qty > 1:
                await ctx.send(ctx._("purchased-for-pokemon-qty", item=item.name, qty=qty, pokemon=name))
            else:
                await ctx.send(ctx._("purchased-for-pokemon", item=item.name, pokemon=name))

        # OK to buy, go ahead

        member = await self.bot.mongo.fetch_member_info(ctx.author)

        if (member.premium_balance if item.shard else member.balance) < item.cost * qty:
            return await ctx.send(ctx._("not-enough-shards" if item.shard else "not-enough-coins"))

        await self.bot.mongo.update_member(
            ctx.author,
            {
                "$inc": {
                    "premium_balance" if item.shard else "balance": -item.cost * qty,
                },
            },
        )

        if item.action == "shard":
            await self.bot.mongo.update_member(ctx.author, {"$inc": {"premium_balance": qty}})

        if item.action == "redeem":
            await self.bot.mongo.update_member(
                ctx.author,
                {
                    "$inc": {
                        "redeems": qty,
                    }
                },
            )

        if item.action == "shiny_charm":
            await self.bot.mongo.update_member(
                ctx.author,
                {
                    "$set": {"shiny_charm_expires": datetime.utcnow() + timedelta(weeks=1)},
                },
            )

        if item.action == "incense":
            await self.bot.mongo.update_channel(
                ctx.channel,
                {
                    "$set": {"guild_id": ctx.guild.id},
                    "$inc": {"spawns_remaining": 180},
                },
            )

        if "evolve" in item.action:
            embed = self.bot.Embed(title=ctx._("congratulations", name=ctx.author.display_name))

            name = str(pokemon.species)

            if pokemon.nickname is not None:
                name += f' "{pokemon.nickname}"'

            embed.add_field(
                name=ctx._("pokemon-evolving", pokemon=name),
                value=ctx._("pokemon-turned-into", old=name, new=str(evoto)),
            )

            self.bot.dispatch("evolve", ctx.author, pokemon, evoto)

            await self.bot.mongo.update_pokemon(pokemon, {"$set": {"species_id": evoto.id}})

            await ctx.send(embed=embed)

        if "xpboost" in item.action:
            mins = int(item.action.split("_")[1])

            await self.bot.mongo.update_member(
                ctx.author,
                {
                    "$set": {"boost_expires": datetime.utcnow() + timedelta(minutes=mins)},
                },
            )

        if item.action == "level":
            update = {"$set": {"xp": 0}, "$inc": {"level": qty}}

            # TODO this code is repeated too many times.

            embed = self.bot.Embed(title=ctx._("congratulations", name=ctx.author.display_name))

            name = str(pokemon.species)

            if pokemon.nickname is not None:
                name += f' "{pokemon.nickname}"'

            embed.description = ctx._("pokemon-level-is-now", pokemon=name, level=pokemon.level + qty)

            if pokemon.shiny:
                embed.set_thumbnail(url=pokemon.species.shiny_image_url)
            else:
                embed.set_thumbnail(url=pokemon.species.image_url)

            pokemon.level += qty
            guild = await self.bot.mongo.fetch_guild(ctx.guild)
            if pokemon.get_next_evolution(guild.is_day) is not None:
                evo = pokemon.get_next_evolution(guild.is_day)
                embed.add_field(
                    name=ctx._("pokemon-evolving", pokemon=name),
                    value=ctx._("pokemon-turned-into", old=name, new=str(evo)),
                )

                if pokemon.shiny:
                    embed.set_thumbnail(url=evo.shiny_image_url)
                else:
                    embed.set_thumbnail(url=evo.image_url)

                update["$set"]["species_id"] = evo.id

                if member.silence and pokemon.level < 99:
                    await ctx.author.send(embed=embed)

                self.bot.dispatch("evolve", ctx.author, pokemon, evo)

            else:
                c = 0
                for move in pokemon.species.moves:
                    if pokemon.level >= move.method.level > pokemon.level - qty:
                        embed.add_field(
                            name=ctx._("new-move"),
                            value=ctx._("pokemon-can-now-learn", pokemon=name, move=move.move.name),
                        )
                        c += 1

                for i in range(-c % 3):
                    embed.add_field(
                        name="‎",
                        value="‎",
                    )

            await self.bot.mongo.db.pokemon.update_one({"_id": pokemon.id, "level": pokemon.level - qty}, update)

            if member.silence and pokemon.level == 100:
                await ctx.author.send(embed=embed)

            if not member.silence:
                await ctx.send(embed=embed)

        if "nature" in item.action:
            idx = int(item.action.split("_")[1])

            await self.bot.mongo.update_pokemon(pokemon, {"$set": {"nature": constants.NATURES[idx]}})

            await ctx.send(ctx._("pokemon-nature-changed", nature=constants.NATURES[idx]))

        if item.action == "held_item":
            await self.bot.mongo.update_pokemon(pokemon, {"$set": {"held_item": item.id}})

        if item.action == "form_item":
            forms = self.bot.data.all_species_by_number(pokemon.species.dex_number)
            for form in forms:
                if form.id != pokemon.species.id and form.form_item is not None and form.form_item == item.id:
                    embed = self.bot.Embed(title=ctx._("congratulations", name=ctx.author.display_name))

                    name = str(pokemon.species)

                    if pokemon.nickname is not None:
                        name += f' "{pokemon.nickname}"'

                    embed.add_field(
                        name=ctx._("pokemon-changing-forms", pokemon=name),
                        value=ctx._("pokemon-turned-into", old=name, new=str(form)),
                    )

                    await self.bot.mongo.update_pokemon(pokemon, {"$set": {f"species_id": form.id}})

                    await ctx.send(embed=embed)

                    break

    @checks.has_started()
    @commands.command(aliases=("ec",))
    @commands.max_concurrency(1, commands.BucketType.user)
    async def embedcolor(
        self,
        ctx,
        pokemon: typing.Optional[converters.PokemonConverter] = False,
        color: discord.Color = None,
    ):
        """Change the embed colors for a pokémon."""

        if pokemon is False:
            pokemon = await converters.PokemonConverter().convert(ctx, "")

        if pokemon is None:
            return await ctx.send(ctx._("unknown-pokemon"))

        if not pokemon.has_color:
            return await ctx.send(ctx._("pokemon-cannot-use-custom-embed-colors"))

        if color is None:
            color = pokemon.color or 0x9CCFFF
            return await ctx.send(ctx._("pokemon-current-embed-color", color=f"#{color:06x}"))

        if color.value == 0xFFFFFF:
            return await ctx.send(ctx._("embed-color-white-limitation"))

        await self.bot.mongo.update_pokemon(pokemon, {"$set": {"color": color.value}})
        await ctx.send(ctx._("pokemon-embed-color-changed", color=f"#{color.value:06x}", pokemon=f"{pokemon:ls}"))

    @checks.has_started()
    @commands.command()
    async def redeem(self, ctx):
        """Use a redeem to receive a pokémon of your choice."""

        member = await self.bot.mongo.fetch_member_info(ctx.author)

        embed = ctx.localized_embed("redeem-embed", redeems=member.redeems)
        embed.color = constants.PINK

        await ctx.send(embed=embed)

    @checks.has_started()
    @checks.is_not_in_trade()
    @commands.guild_only()
    @commands.max_concurrency(1, commands.BucketType.user)
    @commands.command(aliases=("rs",))
    async def redeemspawn(self, ctx, *, species: str = None):
        """Use a redeem to spawn a pokémon of your choice."""

        # TODO I should really merge this and redeem into one function.

        member = await self.bot.mongo.fetch_member_info(ctx.author)

        if species is None:
            embed = ctx.localized_embed("redeem-embed", redeems=member.redeems)
            embed.color = constants.PINK
            return await ctx.send(embed=embed)

        if member.redeems <= 0:
            return await ctx.send(ctx._("no-redeems"))

        species = self.bot.data.species_by_name(species)

        if species is None:
            return await ctx.send(ctx._("unknown-pokemon-matching", matching=species))

        if not species.catchable:
            return await ctx.send(ctx._("cannot-redeem"))

        if ctx.channel.id == 759559123657293835:
            return await ctx.send(ctx._("cannot-redeem-here"))

        if await self.bot.get_cog("Spawning").spawn_pokemon(ctx.channel, species, redeem=True):
            await self.bot.mongo.update_member(
                ctx.author,
                {"$inc": {"redeems": -1}},
            )

    def cog_unload(self):
        self.check_weekend.cancel()


async def setup(bot: commands.Bot):
    await bot.add_cog(Shop(bot))
