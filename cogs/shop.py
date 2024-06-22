import math
import random
import textwrap
import typing
from datetime import datetime, timedelta

import discord
import humanfriendly
from discord.ext import commands, tasks

from cogs import mongo
from data import models
from helpers import checks, constants, converters, pagination
from helpers.context import PoketwoContext
from helpers.views import CommandInvocation, CommandInvokeView


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

    @checks.has_started()
    @commands.command(aliases=("o",))
    async def open(self, ctx, type: str = "", amt: int = 1):
        """Open mystery boxes received from voting."""

        do_emojis = ctx.guild is None or ctx.channel.permissions_for(ctx.guild.me).external_emojis

        if type.lower() not in ("normal", "great", "ultra", "master"):
            if type.lower() in ("n", "g", "u", "m"):
                type = constants.BOXES[type.lower()]
            else:
                return await ctx.send("Please type `normal`, `great`, `ultra`, or `master`!")

        member = await self.bot.mongo.fetch_member_info(ctx.author)

        if amt <= 0:
            return await ctx.send("Nice try...")

        if amt > 15:
            return await ctx.send("You can only open 15 boxes at once!")

        try:
            await self.bot.mongo.db.member.find_one_and_update(
                {"$and": [{"_id": ctx.author.id}, {f"gifts_{type.lower()}": {"$gte": amt}}]},
                {"$inc": {f"gifts_{type.lower()}": -amt}},
                upsert=True,
            )
        except:
            return await ctx.send("You don't have enough boxes to do that!")

        rewards = random.choices(constants.REWARDS, constants.REWARD_WEIGHTS[type.lower()], k=amt)

        update = {
            "$inc": {"balance": 0, "redeems": 0},
        }

        added_pokemon = []

        embed = self.bot.Embed()
        if do_emojis:
            embed.title = (
                f" Opening {amt:,} {getattr(self.bot.sprites, f'gift_{type.lower()}')} {type.title()} Mystery Box"
                + ("" if amt == 1 else "es")
                + "..."
            )
        else:
            embed.title = f" Opening {amt:,} {type.title()} Mystery Box" + ("" if amt == 1 else "es") + "..."

        text = []

        for reward in rewards:
            if reward["type"] == "pp":
                update["$inc"]["balance"] += reward["value"]
                text.append(f"{reward['value']} Pokécoins")
            elif reward["type"] == "redeem":
                update["$inc"]["redeems"] += reward["value"]
                text.append(f"{reward['value']} redeem" + ("" if reward["value"] == 1 else "s"))
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

                iv_fields = {
                    "iv_hp": ivs[0],
                    "iv_atk": ivs[1],
                    "iv_defn": ivs[2],
                    "iv_satk": ivs[3],
                    "iv_sdef": ivs[4],
                    "iv_spd": ivs[5],
                    "iv_total": sum(ivs),
                }

                pokemon = await self.bot.mongo.make_pokemon(member, species, level=level, shiny=shiny, **iv_fields)

                text.append(f"{self.bot.mongo.Pokemon.build_from_mongo(pokemon):lngiP}")

                added_pokemon.append(pokemon)

        embed.add_field(name="Rewards Received", value="\n".join(text))

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

        embed = self.bot.Embed(title=f"{ctx.author.display_name}'s balance")
        embed.add_field(name="Pokécoins", value=f"{member.balance:,}")
        embed.add_field(name="Shards", value=f"{member.premium_balance:,}")
        embed.set_thumbnail(url=ctx.author.display_avatar.url)
        await ctx.send(embed=embed)

    @checks.has_started()
    @commands.command(aliases=("di",), rest_is_raw=True)
    async def dropitem(self, ctx, *, pokemon: converters.PokemonConverter):
        """Drop a pokémon's held item."""

        if pokemon is None:
            return await ctx.send("Couldn't find that pokémon!")

        if pokemon.held_item is None:
            return await ctx.send("That pokémon isn't holding an item!")

        await self.bot.mongo.update_pokemon(
            pokemon,
            {"$set": {f"held_item": None}},
        )

        await ctx.send(f"Dropped held item for your **{pokemon:lnx}**.")

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
            return await ctx.send("Couldn't find that pokémon!")

        if from_pokemon is None or to_pokemon is None:
            return await ctx.send("Couldn't find that pokémon!")

        if from_pokemon.held_item is None:
            return await ctx.send("That pokémon isn't holding an item!")

        if to_pokemon.held_item is not None:
            return await ctx.send("That pokémon is already holding an item!")

        await self.bot.mongo.update_pokemon(from_pokemon, {"$set": {f"held_item": None}})
        await self.bot.mongo.update_pokemon(to_pokemon, {"$set": {f"held_item": from_pokemon.held_item}})

        await ctx.send(f"Moved held item from your **{from_pokemon:lnx}** to your **{to_pokemon:lnx}**.")

    @checks.has_started()
    @commands.command(aliases=("togglebal",))
    async def togglebalance(self, ctx):
        """Toggle showing balance in shop."""

        member = await self.bot.mongo.fetch_member_info(ctx.author)

        await self.bot.mongo.update_member(ctx.author, {"$set": {"show_balance": not member.show_balance}})

        if member.show_balance:
            await ctx.send(f"Your balance is now hidden in shop pages.")
        else:
            await ctx.send("Your balance is no longer hidden in shop pages.")

    @checks.has_started()
    @commands.command(aliases=("store",))
    async def shop(self, ctx, *, page: int = 0):
        """View the Pokétwo item shop."""

        PAGES = [
            "XP Boosters & Candies",
            "Evolution Stones",
            "Form Change Items",
            "Held Items",
            "Nature Mints",
            "Mega Evolutions & Transformation",
            "Shard Shop",
        ]

        member = await self.bot.mongo.fetch_member_info(ctx.author)
        embed = self.bot.Embed(title=f"Pokétwo Shop")

        if member.show_balance:
            embed.title += f" — {member.balance:,} Pokécoins"
            if page == 7:
                embed.title += f", {member.premium_balance:,} Shards"

        if page == 0:
            embed.description = f"Use `{ctx.clean_prefix}shop <page>` to view different pages."

            for page_no, description in enumerate(PAGES, 1):
                embed.add_field(name=f"Page {page_no}", value=description, inline=False)

        else:
            embed.description = (
                "We have a variety of items you can buy in the shop. "
                "Some will evolve your pokémon, some will change the nature of your pokémon, and some will give you other bonuses. "
                f"Use `{ctx.clean_prefix}buy <item>` to buy an item!"
            )

            if page == 7:
                embed.description = (
                    "Welcome to the shard shop! "
                    "Shards are a type of premium currency that can be used to buy special items. "
                    "Shards can be obtained by exchanging pokécoins or by purchasing them at https://poketwo.net/store."
                )

            items = [i for i in self.bot.data.all_items() if i.page == page]
            sticky_items = [item for item in items if not item.inline]
            items = [item for item in items if item.inline]

            do_emojis = ctx.guild is None or ctx.channel.permissions_for(ctx.guild.me).external_emojis

            PER_PAGE = 15

            async def get_page(source, menu, pidx):
                embed.clear_fields()

                pgstart = pidx * PER_PAGE
                pgend = min(pgstart + PER_PAGE, len(items))

                page_items = sticky_items + items[pgstart:pgend]
                for item in page_items:
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
                        elif item.action == "incense":
                            name += " (default, customizable)"

                        value = item.description

                    else:
                        value = f"{item.cost} {'shards' if item.shard else 'pc'}"
                        if item.action in ("level", "shard", "redeem"):
                            value += " each"

                    embed.add_field(name=name, value=value, inline=item.inline)

                if page_items[-1].inline and len(page_items) < 25:
                    for i in range(-len(page_items) % 3):
                        embed.add_field(name="‎", value="‎")

                return embed

        footer_text = []

        if member.boost_active:
            timespan = member.boost_expires - datetime.utcnow()
            timespan = humanfriendly.format_timespan(timespan.total_seconds())
            footer_text.append(f"You have an XP Booster active that expires in {timespan}.")

        if member.shiny_charm_active:
            timespan = member.shiny_charm_expires - datetime.utcnow()
            timespan = humanfriendly.format_timespan(timespan.total_seconds())
            footer_text.append(f"You have a shiny charm active that expires in {timespan}.")

        if len(footer_text) > 0:
            embed.set_footer(text="\n".join(footer_text))

        if page == 0:
            view = CommandInvokeView(
                ctx,
                [
                    CommandInvocation(
                        label=f"Page {page_no}",
                        command=self.shop,
                        kwargs={"page": page_no},
                        description=description,
                    )
                    for page_no, description in enumerate(PAGES, 1)
                ],
                placeholder="Open a page",
            )
            view.message = await ctx.send(embed=embed, view=view)
        else:
            pages = pagination.ContinuablePages(
                pagination.FunctionPageSource(math.ceil(len(items) / PER_PAGE), get_page)
            )
            self.bot.menus[ctx.author.id] = pages
            await pages.start(ctx)

    @checks.has_started()
    @commands.max_concurrency(1, commands.BucketType.user, wait=True)
    @commands.guild_only()
    @commands.command()
    @checks.is_not_in_trade()
    async def buy(self, ctx: PoketwoContext, *args: str):
        """Purchase an item from the shop."""

        if len(args) == 0:
            return

        qty = 1

        if args[-1].isdigit() and args[0].lower() != "xp":
            args, qty = args[:-1], int(args[-1])

            if qty <= 0:
                return await ctx.send("Nice try...")

        search = " ".join(args)
        if search.lower() == "shards":
            search = "shard"
        if search.lower() == "redeems":
            search = "redeem"
        if search.lower() == "rare candies":
            search = "rare candy"
        item = self.bot.data.item_by_name(search)
        if item is None:
            return await ctx.send(f"Couldn't find an item called `{' '.join(args)}`.")

        if item.action == "incense":
            return await ctx.send(
                f"This command has migrated to `{ctx.clean_prefix}incense buy`, please use that instead!"
            )

        member = await self.bot.mongo.fetch_member_info(ctx.author)
        pokemon = await self.bot.mongo.fetch_pokemon(ctx.author, member.selected_id)

        if pokemon is None:
            return await ctx.send("You must have a pokémon selected!")

        if qty > 1 and item.action not in ("level", "shard", "redeem"):
            return await ctx.send("You can't buy multiple of this item!")

        if (member.premium_balance if item.shard else member.balance) < item.cost * qty:
            return await ctx.send(f"You don't have enough {'shards' if item.shard else 'Pokécoins'} for that!")

        # Check to make sure it's purchasable.

        if item.action == "level":
            if pokemon.level + qty > 100:
                return await ctx.send(
                    f"Your selected pokémon is already level {pokemon.level}! Please select a different pokémon using `{ctx.clean_prefix}select` and try again."
                )

        if item.action == "evolve_mega":
            if pokemon.species.mega is None:
                return await ctx.send(
                    f"This item can't be used on your selected pokémon! Please select a different pokémon using `{ctx.clean_prefix}select` and try again."
                )

            evoto = pokemon.species.mega

            if pokemon.held_item == 13001:
                return await ctx.send(
                    "This pokémon is holding an Everstone! Please drop or move the item and try again."
                )

        if item.action == "evolve_megax":
            if pokemon.species.mega_x is None:
                return await ctx.send(
                    f"This item can't be used on your selected pokémon! Please select a different pokémon using `{ctx.clean_prefix}select` and try again."
                )

            evoto = pokemon.species.mega_x

            if pokemon.held_item == 13001:
                return await ctx.send(
                    "This pokémon is holding an Everstone! Please drop or move the item and try again."
                )

        if item.action == "evolve_megay":
            if pokemon.species.mega_y is None:
                return await ctx.send(
                    f"This item can't be used on your selected pokémon! Please select a different pokémon using `{ctx.clean_prefix}select` and try again."
                )

            evoto = pokemon.species.mega_y

            if pokemon.held_item == 13001:
                return await ctx.send(
                    "This pokémon is holding an Everstone! Please drop or move the item and try again."
                )

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
                    return await ctx.send(
                        f"This item can't be used on your selected pokémon! Please select a different pokémon using `{ctx.clean_prefix}select` and try again."
                    )
            else:
                return await ctx.send(
                    f"This item can't be used on your selected pokémon! Please select a different pokémon using `{ctx.clean_prefix}select` and try again."
                )

            if pokemon.held_item == 13001:
                return await ctx.send(
                    "This pokémon is holding an Everstone! Please drop or move the item and try again."
                )

        if item.action == "form_item":
            forms = self.bot.data.all_species_by_number(pokemon.species.dex_number)
            possible_forms = []
            for form in forms:
                # Shouldn't be able to transform event pokemon
                if pokemon.species.event:
                    break

                # Shouldn't be able to transform to an event version
                if form.event:
                    continue

                # This will allow inter-form transformations more clear in the select menu by including current
                if pokemon.species.id == form.id and not (
                    pokemon.species.form_item is not None and pokemon.species.form_item == item.id
                ):
                    continue

                # If the item is Transformation, continue to next form if current pokemon is also a form or
                # if current pokemon has a form_item field that is also Transformation
                if item.id == 20000 and (pokemon.species.is_form or pokemon.species.form_item == item.id):
                    continue

                if form.form_item is not None and form.form_item == item.id:
                    possible_forms.append(form)

            match len(possible_forms):
                case 0:
                    selected_form = None
                case 1:
                    selected_form = possible_forms[0]
                case _:
                    form_ids = await ctx.select(
                        "Your pokémon can transform into multiple forms using this item. Please select a form to transform it into.",
                        options=[
                            discord.SelectOption(
                                label=form.name,
                                value=str(form.id),
                                description=textwrap.shorten(form.description, 100) if form.description else None,
                                emoji=self.bot.sprites.get(form),
                                default=form.id == pokemon.species.id,
                            )
                            for form in possible_forms
                        ],
                    )
                    if form_ids is None:
                        return await ctx.send("Time's up. Aborted.")

                    selected_form = discord.utils.get(possible_forms, id=int(form_ids[0]))

            if selected_form is None or selected_form == pokemon.species:
                return await ctx.send(
                    f"This item can't be used on your selected pokémon! Please select a different pokémon using "
                    f"`{ctx.clean_prefix}select` and try again. If you want to reverse transformation, try `{ctx.clean_prefix}untransform`."
                )

        if "xpboost" in item.action:
            if member.boost_active:
                return await ctx.send(
                    "You already have an XP booster active! Please wait for it to expire before purchasing another one."
                )

            await ctx.send(
                f"You purchased {item.name}! Use `{ctx.clean_prefix}shop` to check how much time you have remaining."
            )

        elif item.action == "shard":
            result = await ctx.confirm(
                f"Are you sure you want to exchange **{item.cost * qty:,}** Pokécoins for **{qty:,}** shards? Shards are non-transferable and non-refundable!"
            )
            if result is None:
                return await ctx.send("Time's up. Aborted.")
            if result is False:
                return await ctx.send("Aborted.")

            await ctx.send(f"You purchased {qty:,} shards!")

        elif item.action == "redeem":
            await ctx.send(f"You purchased {qty} redeems!")

        elif item.action == "shiny_charm":
            if member.shiny_charm_active:
                return await ctx.send(
                    f"You already have a shiny charm active until {discord.utils.format_dt(member.shiny_charm_expires)}! Please wait for it to expire before purchasing another one."
                )

            await ctx.send(
                f"You purchased a {item.name}! Use `{ctx.clean_prefix}shop` to check how much time you have remaining."
            )

        elif item.shard:
            await ctx.send(f"You purchased {'an' if item.name[0] in 'aeiou' else 'a'} {item.name}!")

        else:
            name = str(pokemon.species)

            if pokemon.nickname is not None:
                name += f' "{pokemon.nickname}"'

            price = item.cost * qty
            if qty > 1:
                await ctx.send(f"You purchased {item.name} x {qty} for your {name} for **{price:,}** Pokécoins!")
            else:
                await ctx.send(f"You purchased a {item.name} for your {name} for **{price:,}** Pokécoins!")

        # OK to buy, go ahead

        member = await self.bot.mongo.fetch_member_info(ctx.author)
        pokemon = await self.bot.mongo.fetch_pokemon(ctx.author, member.selected_id)

        if pokemon is None:
            return await ctx.send("You must have a pokémon selected!")

        if (member.premium_balance if item.shard else member.balance) < item.cost * qty:
            return await ctx.send(f"You don't have enough {'shards' if item.shard else 'Pokécoins'} for that!")

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

        if "evolve" in item.action:
            embed = self.bot.Embed(title=f"Congratulations {ctx.author.display_name}!")

            name = str(pokemon.species)

            if pokemon.nickname is not None:
                name += f' "{pokemon.nickname}"'

            embed.add_field(
                name=f"Your {name} is evolving!",
                value=f"Your {name} has turned into a {evoto}!",
            )
            embed.set_thumbnail(url=evoto.get_image_url(pokemon.shiny, pokemon.gender))

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

            embed = self.bot.Embed(title=f"Congratulations {ctx.author.display_name}!")

            name = str(pokemon.species)

            if pokemon.nickname is not None:
                name += f' "{pokemon.nickname}"'

            embed.description = f"Your {name} is now level {pokemon.level + qty}!"

            embed.set_thumbnail(url=pokemon.image_url)

            pokemon.level += qty
            guild = await self.bot.mongo.fetch_guild(ctx.guild)
            evo = pokemon.get_next_evolution(guild.time)
            if evo is not None:
                embed.add_field(
                    name=f"Your {name} is evolving!",
                    value=f"Your {name} has turned into a {evo}!",
                )
                embed.set_thumbnail(url=evo.get_image_url(pokemon.shiny, pokemon.gender))

                update["$set"]["species_id"] = evo.id

                self.bot.dispatch("evolve", ctx.author, pokemon, evo)

            else:
                c = 0
                for move in pokemon.species.moves:
                    if pokemon.level >= move.method.level > pokemon.level - qty:
                        embed.add_field(
                            name=f"New move!",
                            value=f"Your {name} can now learn {move.move.name}!",
                        )
                        c += 1

                for i in range(-c % 3):
                    embed.add_field(
                        name="‎",
                        value="‎",
                    )

            await self.bot.mongo.db.pokemon.update_one({"_id": pokemon.id, "level": pokemon.level - qty}, update)

            if member.silence and (evo is not None or pokemon.level == 100):
                await ctx.author.send(embed=embed)

            if not member.silence:
                await ctx.send(embed=embed)

        if "nature" in item.action:
            idx = int(item.action.split("_")[1])

            await self.bot.mongo.update_pokemon(pokemon, {"$set": {"nature": constants.NATURES[idx]}})

            await ctx.send(f"You changed your selected pokémon's nature to {constants.NATURES[idx]}!")

        if item.action == "held_item":
            await self.bot.mongo.update_pokemon(pokemon, {"$set": {"held_item": item.id}})

        if item.action == "form_item":
            embed = self.bot.Embed(title=f"Congratulations {ctx.author.display_name}!")

            name = format(pokemon, "n")
            embed.add_field(
                name=f"Your {name} is changing forms!",
                value=f"Your {name} has turned into a {selected_form}!",
            )
            embed.set_thumbnail(url=selected_form.get_image_url(pokemon.shiny, pokemon.gender))

            await self.bot.mongo.update_pokemon(pokemon, {"$set": {f"species_id": selected_form.id}})

            await ctx.send(embed=embed)

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
            return await ctx.send("Couldn't find that pokémon!")

        if not pokemon.has_color:
            return await ctx.send("That pokémon cannot use custom embed colors!")

        if color is None:
            color = pokemon.color or 0x9CCFFF
            return await ctx.send(f"That pokémon's embed color is currently **#{color:06x}**.")

        if color.value == 0xFFFFFF:
            return await ctx.send(
                "Due to a Discord limitation, you cannot set the embed color to pure white. Try **#fffffe** instead."
            )

        await self.bot.mongo.update_pokemon(pokemon, {"$set": {"color": color.value}})
        await ctx.send(f"Changed embed color to **#{color.value:06x}** for your **{pokemon}**.")

    @checks.has_started()
    @commands.command()
    async def redeem(self, ctx):
        """Use a redeem to receive a pokémon of your choice."""

        member = await self.bot.mongo.fetch_member_info(ctx.author)

        embed = self.bot.Embed(
            title=f"Your Redeems: {member.redeems}",
            description="You can use redeems to receive any pokémon of your choice. You can receive redeems by purchasing them with shards or through voting rewards.",
        )

        embed.add_field(
            name=f"{ctx.clean_prefix}redeemspawn <pokémon>",
            value="Use a redeem to spawn a pokémon of your choice in the current channel (careful, if something else spawns, it'll be overridden).",
        )

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
            embed = self.bot.Embed(
                title=f"Your Redeems: {member.redeems}",
                description="You can use redeems to receive any pokémon of your choice. You can receive redeems by purchasing them with shards or through voting rewards.",
            )

            embed.add_field(
                name=f"{ctx.clean_prefix}redeemspawn <pokémon>",
                value="Use a redeem to spawn a pokémon of your choice in the current channel *(careful, if something else spawns, it'll be overridden)*.",
            )

            return await ctx.send(embed=embed)

        if member.redeems <= 0:
            return await ctx.send("You don't have any redeems!")

        species = self.bot.data.species_by_name(species)

        if species is None:
            return await ctx.send(f"Could not find a pokemon matching `{species}`.")

        if not species.catchable:
            return await ctx.send("You can't redeem this pokémon!")

        if ctx.channel.id == 759559123657293835:
            return await ctx.send("You can't redeemspawn a pokémon here!")

        if await self.bot.get_cog("Spawning").spawn_pokemon(ctx.channel, species, redeem=True):
            await self.bot.mongo.update_member(
                ctx.author,
                {"$inc": {"redeems": -1}},
            )

    def cog_unload(self):
        self.check_weekend.cancel()


async def setup(bot: commands.Bot):
    await bot.add_cog(Shop(bot))
