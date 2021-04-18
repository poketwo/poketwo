import asyncio
import random
import typing
from datetime import datetime, timedelta

import aiohttp
import discord
import humanfriendly
from data import models
from discord.ext import commands, tasks

from helpers import checks, constants, converters
from . import mongo


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
        async with aiohttp.ClientSession() as session:
            async with session.get("https://discordbots.org/api/weekend") as r:
                if r.status == 200:
                    js = await r.json()
                    self.weekend = js["is_weekend"]

    @property
    def month_number(self):
        now = datetime.utcnow()
        return str(now.year * 12 + now.month)

    @commands.command()
    @checks.is_admin()
    async def stopincense(self, ctx):
        channel = await self.bot.mongo.fetch_channel(ctx.channel)
        if not channel.incense_active:
            return await ctx.send("There is no active incense in this channel!")

        message = await ctx.send(
            "Are you sure you want to cancel the incense? You can't undo this!"
        )
        self.bot.loop.create_task(add_reactions(message, "✅", "❌"))
        try:
            r, u = await self.bot.wait_for(
                "reaction_add",
                check=lambda r, u: u == ctx.author
                and r.message.id == message.id
                and r.emoji in ("✅", "❌"),
                timeout=60,
            )
        except asyncio.TimeoutError:
            await ctx.send("Hurry up and make up your mind. Aborted.")
            return

        if r.emoji == "❌":
            await ctx.send("OK, aborted.")
            return

        await self.bot.mongo.update_channel(
            ctx.channel,
            {
                "$set": {"spawns_remaining": 0},
            },
        )
        await ctx.send("Incense has been stopped.")

    @checks.has_started()
    @commands.command(aliases=("v", "daily", "boxes"))
    async def vote(self, ctx):
        """View information on voting rewards."""

        member = await self.bot.mongo.fetch_member_info(ctx.author)

        # if member.vote_streak > 0 and datetime.utcnow() - member.last_voted > timedelta(
        #     days=2
        # ):
        #     await self.bot.mongo.update_member(
        #         ctx.author,
        #         {
        #             "$set": {"vote_streak": 0},
        #         },
        #     )
        #     member = await self.bot.mongo.fetch_member_info(ctx.author)

        do_emojis = ctx.guild is None or ctx.guild.me.permissions_in(ctx.channel).external_emojis

        embed = self.bot.Embed(color=0x9CCFFF)
        embed.title = f"Voting Rewards"

        embed.description = (
            "[Vote for us on top.gg](https://top.gg/bot/716390085896962058/vote) to receive mystery boxes! "
            "You can vote once per 12 hours. Vote multiple days in a row to get better rewards!"
        )

        if do_emojis:
            embed.add_field(
                name="Voting Streak",
                value=str(self.bot.sprites.check) * min(member.vote_streak, 14)
                + str(self.bot.sprites.gray) * (14 - min(member.vote_streak, 14))
                + f"\nCurrent Streak: {member.vote_streak} votes!",
                inline=False,
            )
        else:
            embed.add_field(
                name="Voting Streak",
                value=f"Current Streak: {member.vote_streak} votes!",
                inline=False,
            )

        if (later := member.last_voted + timedelta(hours=12)) < datetime.utcnow():
            embed.add_field(name="Vote Timer", value="You can vote right now!")
        else:
            timespan = later - datetime.utcnow()
            formatted = humanfriendly.format_timespan(timespan.total_seconds())
            embed.add_field(name="Vote Timer", value=f"You can vote again in **{formatted}**.")

        if do_emojis:
            embed.add_field(
                name="Your Rewards",
                value=(
                    f"{self.bot.sprites.gift_normal} **Normal Mystery Box:** {member.gifts_normal}\n"
                    f"{self.bot.sprites.gift_great} **Great Mystery Box:** {member.gifts_great}\n"
                    f"{self.bot.sprites.gift_ultra} **Ultra Mystery Box:** {member.gifts_ultra}\n"
                    f"{self.bot.sprites.gift_master} **Master Mystery Box:** {member.gifts_master}\n"
                ),
                inline=False,
            )
        else:
            embed.add_field(
                name="Your Rewards",
                value=(
                    f"**Normal Mystery Box:** {member.gifts_normal}\n"
                    f"**Great Mystery Box:** {member.gifts_great}\n"
                    f"**Ultra Mystery Box:** {member.gifts_ultra}\n"
                    f"**Master Mystery Box:** {member.gifts_master}\n"
                ),
                inline=False,
            )

        embed.add_field(
            name="Claiming Rewards",
            value=f"Use `{ctx.prefix}open <normal|great|ultra|master> [amt]` to open your boxes!",
            inline=False,
        )

        embed.set_footer(text="You will automatically receive your rewards when you vote.")

        if ctx.guild and ctx.guild.id == 716390832034414685:
            embed.add_field(
                name="Server Voting",
                value="You can also vote for our server [here](https://top.gg/servers/716390832034414685/vote) to receive a colored role.",
                inline=False,
            )

        await ctx.send(embed=embed)

    @checks.has_started()
    @commands.command(aliases=("o",))
    async def open(self, ctx, type: str = "", amt: int = 1):
        """Open mystery boxes received from voting."""

        do_emojis = ctx.guild is None or ctx.guild.me.permissions_in(ctx.channel).external_emojis

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

        embed = self.bot.Embed(color=0x9CCFFF)
        if do_emojis:
            embed.title = (
                f" Opening {amt} {getattr(self.bot.sprites, f'gift_{type.lower()}')} {type.title()} Mystery Box"
                + ("" if amt == 1 else "es")
                + "..."
            )
        else:
            embed.title = (
                f" Opening {amt} {type.title()} Mystery Box" + ("" if amt == 1 else "es") + "..."
            )

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

                pokemon = {
                    "owner_id": ctx.author.id,
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

                text.append(
                    f"{self.bot.mongo.Pokemon.build_from_mongo(pokemon):lni} ({sum(ivs) / 186:.2%} IV)"
                )

                added_pokemon.append(pokemon)

        embed.add_field(name="Rewards Received", value="\n".join(text))

        await self.bot.mongo.update_member(ctx.author, update)
        if len(added_pokemon) > 0:
            await self.bot.mongo.db.pokemon.insert_many(added_pokemon)
        await ctx.send(embed=embed)

    @checks.has_started()
    @commands.command(aliases=("bal",))
    async def balance(self, ctx):
        """View your current balance."""

        member = await self.bot.mongo.fetch_member_info(ctx.author)

        embed = self.bot.Embed(color=0x9CCFFF)
        embed.title = f"{ctx.author.display_name}'s balance"
        embed.add_field(name="Pokécoins", value=f"{member.balance:,}")
        embed.add_field(name="Shards", value=f"{member.premium_balance:,}")
        embed.set_thumbnail(url=ctx.author.avatar_url)
        await ctx.send(embed=embed)

    @checks.has_started()
    @commands.command(aliases=("di",), rest_is_raw=True)
    async def dropitem(self, ctx, *, pokemon: converters.PokemonConverter):
        """Drop a pokémon's held item."""

        if pokemon is None:
            return await ctx.send("Couldn't find that pokémon!")

        if pokemon.held_item is None:
            return await ctx.send("That pokémon isn't holding an item!")

        num = await self.bot.mongo.fetch_pokemon_count(ctx.author)

        await self.bot.mongo.update_pokemon(
            pokemon,
            {"$set": {f"held_item": None}},
        )

        name = str(pokemon.species)

        if pokemon.nickname is not None:
            name += f' "{pokemon.nickname}"'

        await ctx.send(f"Dropped held item for your level {pokemon.level} {name}.")

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

        num = await self.bot.mongo.fetch_pokemon_count(ctx.author)

        await self.bot.mongo.update_pokemon(from_pokemon, {"$set": {f"held_item": None}})
        await self.bot.mongo.update_pokemon(
            to_pokemon, {"$set": {f"held_item": from_pokemon.held_item}}
        )

        from_name = str(from_pokemon.species)

        if from_pokemon.nickname is not None:
            from_name += f' "{from_pokemon.nickname}"'

        to_name = str(to_pokemon.species)

        if to_pokemon.nickname is not None:
            to_name += f' "{to_pokemon.nickname}"'

        await ctx.send(
            f"Moved held item from your level {from_pokemon.level} {from_name} to your level {to_pokemon.level} {to_name}."
        )

    @checks.has_started()
    @commands.command(aliases=("togglebal",))
    async def togglebalance(self, ctx):
        """Toggle showing balance in shop."""

        member = await self.bot.mongo.fetch_member_info(ctx.author)

        await self.bot.mongo.update_member(
            ctx.author, {"$set": {"show_balance": not member.show_balance}}
        )

        if member.show_balance:
            await ctx.send(f"Your balance is now hidden in shop pages.")
        else:
            await ctx.send("Your balance is no longer hidden in shop pages.")

    @checks.has_started()
    @commands.command(aliases=("store",))
    async def shop(self, ctx, *, page: int = 0):
        """View the Pokétwo item shop."""

        member = await self.bot.mongo.fetch_member_info(ctx.author)

        embed = self.bot.Embed(color=0x9CCFFF)
        embed.title = f"Pokétwo Shop"

        if member.show_balance:
            embed.title += f" — {member.balance:,} Pokécoins"
            if page == 7:
                embed.title += f", {member.premium_balance:,} Shards"

        if page == 0:
            embed.description = f"Use `{ctx.prefix}shop <page>` to view different pages."

            embed.add_field(name="Page 1", value="XP Boosters & Candies", inline=False)
            embed.add_field(name="Page 2", value="Evolution Stones", inline=False)
            embed.add_field(name="Page 3", value="Form Change Items", inline=False)
            embed.add_field(name="Page 4", value="Held Items", inline=False)
            embed.add_field(name="Page 5", value="Nature Mints", inline=False)
            embed.add_field(name="Page 6", value="Mega Evolutions", inline=False)
            embed.add_field(name="Page 7", value="Shard Shop", inline=False)

        else:
            embed.description = (
                "We have a variety of items you can buy in the shop. "
                "Some will evolve your pokémon, some will change the nature of your pokémon, and some will give you other bonuses. "
                f"Use `{ctx.prefix}buy <item>` to buy an item!"
            )

            if page == 7:
                embed.description = (
                    "Welcome to the shard shop! "
                    "Shards are a type of premium currency that can be used to buy special items. "
                    "Shards can be obtained by exchanging pokécoins or by purchasing them at https://poketwo.net/store."
                )

            items = [i for i in self.bot.data.all_items() if i.page == page]

            do_emojis = (
                ctx.guild is None or ctx.guild.me.permissions_in(ctx.channel).external_emojis
            )

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
            footer_text.append(f"You have an XP Booster active that expires in {timespan}.")

        if member.shiny_charm_active:
            timespan = member.shiny_charm_expires - datetime.utcnow()
            timespan = humanfriendly.format_timespan(timespan.total_seconds())
            footer_text.append(f"You have a shiny charm active that expires in {timespan}.")

        if len(footer_text) > 0:
            embed.set_footer(text="\n".join(footer_text))

        await ctx.send(embed=embed)

    @checks.has_started()
    @commands.max_concurrency(1, commands.BucketType.user, wait=True)
    @commands.guild_only()
    @commands.command()
    async def buy(self, ctx, *args: str):
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

        member = await self.bot.mongo.fetch_member_info(ctx.author)
        pokemon = await self.bot.mongo.fetch_pokemon(ctx.author, member.selected_id)

        if pokemon is None:
            return await ctx.send("You must have a pokémon selected!")

        if qty > 1 and item.action not in ("level", "shard", "redeem"):
            return await ctx.send("You can't buy multiple of this item!")

        if (member.premium_balance if item.shard else member.balance) < item.cost * qty:
            return await ctx.send(
                f"You don't have enough {'shards' if item.shard else 'Pokécoins'} for that!"
            )

        # Check to make sure it's purchasable.

        if item.action == "level":
            if pokemon.level + qty > 100:
                return await ctx.send(
                    f"Your selected pokémon is already level {pokemon.level}! Please select a different pokémon using `{ctx.prefix}select` and try again."
                )

        if item.action == "evolve_mega":
            if pokemon.species.mega is None:
                return await ctx.send(
                    f"This item can't be used on your selected pokémon! Please select a different pokémon using `{ctx.prefix}select` and try again."
                )

            evoto = pokemon.species.mega

            if pokemon.held_item == 13001:
                return await ctx.send(
                    "This pokémon is holding an Everstone! Please drop or move the item and try again."
                )

        if item.action == "evolve_megax":
            if pokemon.species.mega_x is None:
                return await ctx.send(
                    f"This item can't be used on your selected pokémon! Please select a different pokémon using `{ctx.prefix}select` and try again."
                )

            evoto = pokemon.species.mega_x

            if pokemon.held_item == 13001:
                return await ctx.send(
                    "This pokémon is holding an Everstone! Please drop or move the item and try again."
                )

        if item.action == "evolve_megay":
            if pokemon.species.mega_y is None:
                return await ctx.send(
                    f"This item can't be used on your selected pokémon! Please select a different pokémon using `{ctx.prefix}select` and try again."
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
                            lambda evo: isinstance(evo.trigger, models.ItemTrigger)
                            and evo.trigger.item == item,
                            pokemon.species.evolution_to.items,
                        )
                    ).target
                except StopIteration:
                    return await ctx.send(
                        f"This item can't be used on your selected pokémon! Please select a different pokémon using `{ctx.prefix}select` and try again."
                    )
            else:
                return await ctx.send(
                    f"This item can't be used on your selected pokémon! Please select a different pokémon using `{ctx.prefix}select` and try again."
                )

            if pokemon.held_item == 13001:
                return await ctx.send(
                    "This pokémon is holding an Everstone! Please drop or move the item and try again."
                )

        if item.action == "form_item":
            forms = self.bot.data.all_species_by_number(pokemon.species.dex_number)
            for form in forms:
                if (
                    form.id != pokemon.species.id
                    and form.form_item is not None
                    and form.form_item == item.id
                ):
                    break
            else:
                return await ctx.send(
                    f"This item can't be used on your selected pokémon! Please select a different pokémon using `{ctx.prefix}select` and try again."
                )

        if "xpboost" in item.action:
            if member.boost_active:
                return await ctx.send(
                    "You already have an XP booster active! Please wait for it to expire before purchasing another one."
                )

            await ctx.send(
                f"You purchased {item.name}! Use `p!shop` to check how much time you have remaining."
            )

        elif item.action == "shard":
            message = await ctx.send(
                f"Are you sure you want to exchange **{item.cost * qty:,}** Pokécoins for **{qty:,}** shards? Shards are non-transferable and non-refundable!"
            )
            self.bot.loop.create_task(add_reactions(message, "✅", "❌"))
            try:
                r, u = await self.bot.wait_for(
                    "reaction_add",
                    check=lambda r, u: u == ctx.author
                    and r.message.id == message.id
                    and r.emoji in ("✅", "❌"),
                    timeout=60,
                )
            except asyncio.TimeoutError:
                await ctx.send("Hurry up and make up your mind. Aborted.")
                return

            if r.emoji == "❌":
                await ctx.send("OK, aborted.")
                return

            await ctx.send(f"You purchased {qty:,} shards!")

        elif item.action == "redeem":
            await ctx.send(f"You purchased {qty} redeems!")

        elif item.action == "shiny_charm":
            if member.shiny_charm_active:
                return await ctx.send(
                    "You already have a shiny charm active! Please wait for it to expire before purchasing another one."
                )

            await ctx.send(
                f"You purchased a {item.name}! Use `p!shop` to check how much time you have remaining."
            )

        elif item.action == "incense":

            permissions = ctx.channel.permissions_for(ctx.author)

            if not permissions.administrator:
                return await ctx.send(
                    "You must have administrator permissions in order to do this!"
                )

            channel = await self.bot.mongo.fetch_channel(ctx.channel)
            if channel.incense_active:
                return await ctx.send(
                    "This channel already has an incense active! Please wait for it to end before purchasing another one."
                )

            await ctx.send(f"You purchased an {item.name}!")

        elif item.shard:
            await ctx.send(f"You purchased {'an' if item.name[0] in 'aeiou' else 'a'} {item.name}!")

        else:
            name = str(pokemon.species)

            if pokemon.nickname is not None:
                name += f' "{pokemon.nickname}"'

            if qty > 1:
                await ctx.send(f"You purchased {item.name} x {qty} for your {name}!")
            else:
                await ctx.send(f"You purchased a {item.name} for your {name}!")

        # OK to buy, go ahead

        member = await self.bot.mongo.fetch_member_info(ctx.author)

        if (member.premium_balance if item.shard else member.balance) < item.cost * qty:
            return await ctx.send(
                f"You don't have enough {'shards' if item.shard else 'Pokécoins'} for that!"
            )

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
                    "$inc": {"spawns_remaining": 180},
                },
            )

        if "evolve" in item.action:
            embed = self.bot.Embed(color=0x9CCFFF)
            embed.title = f"Congratulations {ctx.author.display_name}!"

            name = str(pokemon.species)

            if pokemon.nickname is not None:
                name += f' "{pokemon.nickname}"'

            embed.add_field(
                name=f"Your {name} is evolving!",
                value=f"Your {name} has turned into a {evoto}!",
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

            embed = self.bot.Embed(color=0x9CCFFF)
            embed.title = f"Congratulations {ctx.author.display_name}!"

            name = str(pokemon.species)

            if pokemon.nickname is not None:
                name += f' "{pokemon.nickname}"'

            embed.description = f"Your {name} is now level {pokemon.level + qty}!"

            if pokemon.shiny:
                embed.set_thumbnail(url=pokemon.species.shiny_image_url)
            else:
                embed.set_thumbnail(url=pokemon.species.image_url)

            pokemon.level += qty
            guild = await self.bot.mongo.fetch_guild(ctx.guild)
            if pokemon.get_next_evolution(guild.is_day) is not None:
                evo = pokemon.get_next_evolution(guild.is_day)
                embed.add_field(
                    name=f"Your {name} is evolving!",
                    value=f"Your {name} has turned into a {evo}!",
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
                            name=f"New move!",
                            value=f"Your {name} can now learn {move.move.name}!",
                        )
                        c += 1

                for i in range(-c % 3):
                    embed.add_field(
                        name="‎",
                        value="‎",
                    )

            await self.bot.mongo.db.pokemon.update_one(
                {"_id": pokemon.id, "level": pokemon.level - qty}, update
            )

            if member.silence and pokemon.level == 100:
                await ctx.author.send(embed=embed)

            if not member.silence:
                await ctx.send(embed=embed)

        if "nature" in item.action:
            idx = int(item.action.split("_")[1])

            await self.bot.mongo.update_pokemon(
                pokemon, {"$set": {"nature": constants.NATURES[idx]}}
            )

            await ctx.send(
                f"You changed your selected pokémon's nature to {constants.NATURES[idx]}!"
            )

        if item.action == "held_item":
            await self.bot.mongo.update_pokemon(pokemon, {"$set": {"held_item": item.id}})

        if item.action == "form_item":
            forms = self.bot.data.all_species_by_number(pokemon.species.dex_number)
            for form in forms:
                if (
                    form.id != pokemon.species.id
                    and form.form_item is not None
                    and form.form_item == item.id
                ):
                    embed = self.bot.Embed(color=0x9CCFFF)
                    embed.title = f"Congratulations {ctx.author.display_name}!"

                    name = str(pokemon.species)

                    if pokemon.nickname is not None:
                        name += f' "{pokemon.nickname}"'

                    embed.add_field(
                        name=f"Your {name} is changing forms!",
                        value=f"Your {name} has turned into a {form}!",
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
        await ctx.send(f"Changed embed color to **#{color.value:06x}** for your **{pokemon:ls}**.")

    @checks.has_started()
    @commands.command()
    async def redeem(self, ctx):
        """Use a redeem to receive a pokémon of your choice."""

        member = await self.bot.mongo.fetch_member_info(ctx.author)

        embed = self.bot.Embed(color=0x9CCFFF)
        embed.title = f"Your Redeems: {member.redeems}"
        embed.description = "You can use redeems to receive any pokémon of your choice. You can receive redeems by purchasing them with shards or through voting rewards."

        embed.add_field(
            name=f"{ctx.prefix}redeemspawn <pokémon>",
            value="Use a redeem to spawn a pokémon of your choice in the current channel (careful, if something else spawns, it'll be overrided).",
        )

        await ctx.send(embed=embed)

    @checks.has_started()
    @commands.guild_only()
    @commands.max_concurrency(1, commands.BucketType.user)
    @commands.command(aliases=("rs",))
    async def redeemspawn(self, ctx, *, species: str = None):
        """Use a redeem to spawn a pokémon of your choice."""

        # TODO I should really merge this and redeem into one function.

        member = await self.bot.mongo.fetch_member_info(ctx.author)

        if species is None:
            embed = self.bot.Embed(color=0x9CCFFF)
            embed.title = f"Your Redeems: {member.redeems}"
            embed.description = "You can use redeems to receive any pokémon of your choice. You can receive redeems by purchasing them with shards or through voting rewards."

            embed.add_field(
                name=f"{ctx.prefix}redeemspawn <pokémon>",
                value="Use a redeem to spawn a pokémon of your choice in the current channel *(careful, if something else spawns, it'll be overrided)*.",
            )

            return await ctx.send(embed=embed)

        if member.redeems <= 0:
            return await ctx.send("You don't have any redeems!")

        species = self.bot.data.species_by_name(species)

        if species is None:
            return await ctx.send(f"Could not find a pokemon matching `{species}`.")

        if not species.catchable or "Alolan" in species.name:
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


def setup(bot):
    bot.add_cog(Shop(bot))
