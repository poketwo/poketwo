from datetime import datetime, timedelta
from functools import cached_property

import discord
import humanfriendly
from discord.ext import commands, flags

from .database import Database
from .helpers import checks, mongo, converters
from .helpers.constants import *
from .helpers.models import GameData, ItemTrigger, SpeciesNotFoundError


class Shop(commands.Cog):
    """Shop-related commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @property
    def db(self) -> Database:
        return self.bot.get_cog("Database")

    async def balance(self, member: discord.Member):
        member = await self.db.fetch_member_info(member)
        return member.balance

    @checks.has_started()
    @commands.command(aliases=["balance"])
    async def bal(self, ctx: commands.Context):
        """View your current balance."""

        await ctx.send(f"You have {await self.balance(ctx.author)} Poképoints.")

    @commands.command(rest_is_raw=True)
    async def dropitem(self, ctx: commands.Context, *, pokemon: converters.Pokemon):
        """Drop a pokémon's held item."""

        pokemon, idx = pokemon

        if pokemon is None:
            return await ctx.send("Couldn't find that pokémon!")

        if pokemon.held_item is None:
            return await ctx.send("That pokémon isn't holding an item!")

        num = await self.db.fetch_pokemon_count(ctx.author)
        idx = idx % num

        await self.db.update_member(
            ctx.author, {"$set": {f"pokemon.{idx}.held_item": None}},
        )

        name = str(pokemon.species)

        if pokemon.nickname is not None:
            name += f' "{pokemon.nickname}"'

        await ctx.send(f"Dropped held item for your level {pokemon.level} {name}.")

    @commands.command()
    async def moveitem(
        self,
        ctx: commands.Context,
        from_pokemon: converters.Pokemon,
        to_pokemon: converters.Pokemon = None,
    ):
        """Move a pokémon's held item."""

        if to_pokemon is None:
            to_pokemon = from_pokemon
            converter = converters.Pokemon()
            from_pokemon = await converter.convert(ctx, "")

        from_pokemon, from_idx = from_pokemon
        to_pokemon, to_idx = to_pokemon

        if from_pokemon is None or to_pokemon is None:
            return await ctx.send("Couldn't find that pokémon!")

        if from_pokemon.held_item is None:
            return await ctx.send("That pokémon isn't holding an item!")

        if to_pokemon.held_item is not None:
            return await ctx.send("That pokémon is already holding an item!")

        num = await self.db.fetch_pokemon_count(ctx.author)
        from_idx = from_idx % num
        to_idx = to_idx % num

        await self.db.update_member(
            ctx.author,
            {
                "$set": {
                    f"pokemon.{from_idx}.held_item": None,
                    f"pokemon.{to_idx}.held_item": from_pokemon.held_item,
                }
            },
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

    @commands.command()
    async def shop(self, ctx: commands.Context, *, page: int = 0):
        """View the Pokétwo item shop."""

        member = await self.db.fetch_member_info(ctx.author)

        embed = discord.Embed()
        embed.color = 0xF44336
        embed.title = f"Pokétwo Shop — {member.balance} Poképoints"

        if page == 0:
            embed.description = "Use `p!shop <page>` to view different pages."

            embed.add_field(name="Page 1", value="XP Boosters & Candies", inline=False)
            embed.add_field(name="Page 2", value="Evolution Stones", inline=False)
            embed.add_field(name="Page 3", value="Form Change Items", inline=False)
            embed.add_field(name="Page 4", value="Held Items", inline=False)
            embed.add_field(name="Page 5", value="Nature Mints", inline=False)
            embed.add_field(name="Page 6", value="Mega Evolutions", inline=False)

        else:
            embed.description = "We have a variety of items you can buy in the shop. Some will evolve your pokémon, some will change the nature of your pokémon, and some will give you other bonuses. Use `p!buy <item>` to buy an item!"

            items = [i for i in GameData.all_items() if i.page == page]

            gguild = self.bot.get_guild(716390832034414685)

            for item in items:
                emote = ""
                if item.emote is not None:
                    try:
                        e = next(filter(lambda x: x.name == item.emote, gguild.emojis))
                        emote = f"{e} "
                    except StopIteration:
                        pass
                embed.add_field(
                    name=f"{emote}{item.name} – {item.cost} pp",
                    value=f"{item.description}",
                    inline=item.inline,
                )

            if items[0].inline:
                for i in range(-len(items) % 3):
                    embed.add_field(name="‎", value="‎")

        if member.boost_active:
            timespan = member.boost_expires - datetime.now()
            timespan = humanfriendly.format_timespan(timespan.total_seconds())
            embed.set_footer(
                text=f"You have an XP Booster active that expires in {timespan}."
            )

        await ctx.send(embed=embed)

    @commands.command()
    async def buy(self, ctx: commands.Context, *args: str):
        """Buy an item from the shop."""

        qty = 1

        if args[-1].isdigit() and args[0].lower() != "xp":
            args, qty = args[:-1], int(args[-1])

            if qty <= 0:
                return await ctx.send("Nice try...")

        try:
            item = GameData.item_by_name(" ".join(args))
        except SpeciesNotFoundError:
            return await ctx.send(f"Couldn't find an item called `{' '.join(args)}`.")

        member = await self.db.fetch_member_info(ctx.author)
        pokemon = await self.db.fetch_pokemon(ctx.author, member.selected)

        if qty > 1 and item.action != "level":
            return await ctx.send("You can't buy multiple of this item!")

        if member.balance < item.cost * qty:
            return await ctx.send("You don't have enough Poképoints for that!")

        if item.action == "level":
            if pokemon.level + qty > 100:
                return await ctx.send(
                    f"Your selected pokémon is already level {pokemon.level}! Please select a different pokémon using `p!select` and try again."
                )

        if item.action == "evolve_mega":
            if pokemon.species.mega is None:
                return await ctx.send(
                    "This item can't be used on your selected pokémon! Please select a different pokémon using `p!select` and try again."
                )

            evoto = pokemon.species.mega

            if pokemon.held_item == 13001:
                return await ctx.send(
                    "This pokémon is holding an Everstone! Please drop or move the item and try again."
                )

        if item.action == "evolve_megax":
            if pokemon.species.mega_x is None:
                return await ctx.send(
                    "This item can't be used on your selected pokémon! Please select a different pokémon using `p!select` and try again."
                )

            evoto = pokemon.species.mega_x

            if pokemon.held_item == 13001:
                return await ctx.send(
                    "This pokémon is holding an Everstone! Please drop or move the item and try again."
                )

        if item.action == "evolve_megay":
            if pokemon.species.mega_y is None:
                return await ctx.send(
                    "This item can't be used on your selected pokémon! Please select a different pokémon using `p!select` and try again."
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
                            lambda evo: isinstance(evo.trigger, ItemTrigger)
                            and evo.trigger.item == item,
                            pokemon.species.evolution_to.items,
                        )
                    ).target
                except StopIteration:
                    return await ctx.send(
                        "This item can't be used on your selected pokémon! Please select a different pokémon using `p!select` and try again."
                    )
            else:
                return await ctx.send(
                    "This item can't be used on your selected pokémon! Please select a different pokémon using `p!select` and try again."
                )

            if pokemon.held_item == 13001:
                return await ctx.send(
                    "This pokémon is holding an Everstone! Please drop or move the item and try again."
                )

        if item.action == "form_item":
            forms = GameData.all_species_by_number(pokemon.species.dex_number)
            for form in forms:
                if (
                    form.id != pokemon.species.id
                    and form.form_item is not None
                    and form.form_item == item.id
                ):
                    break
            else:
                return await ctx.send(
                    "This item can't be used on your selected pokémon! Please select a different pokémon using `p!select` and try again."
                )

        if "xpboost" in item.action:
            if member.boost_active:
                return await ctx.send(
                    "You already have an XP booster active! Please wait for it to expire before purchasing another one."
                )

            await ctx.send(f"You purchased {item.name}!")
        else:
            name = str(pokemon.species)

            if pokemon.nickname is not None:
                name += f' "{pokemon.nickname}"'

            if qty > 1:
                await ctx.send(f"You purchased {item.name} x {qty} for your {name}!")
            else:
                await ctx.send(f"You purchased a {item.name} for your {name}!")

        await self.db.update_member(
            ctx.author, {"$inc": {"balance": -item.cost * qty},},
        )

        if "evolve" in item.action:
            embed = discord.Embed()
            embed.color = 0xF44336
            embed.title = f"Congratulations {ctx.author.name}!"

            name = str(pokemon.species)

            if pokemon.nickname is not None:
                name += f' "{pokemon.nickname}"'

            embed.add_field(
                name=f"Your {name} is evolving!",
                value=f"Your {name} has turned into a {evoto}!",
            )

            await self.db.update_member(
                ctx.author,
                {"$set": {f"pokemon.{member.selected}.species_id": evoto.id}},
            )

            await ctx.send(embed=embed)

        if "xpboost" in item.action:
            mins = int(item.action.split("_")[1])

            await self.db.update_member(
                ctx.author,
                {"$set": {"boost_expires": datetime.now() + timedelta(minutes=mins)},},
            )

        if item.action == "level":
            update = {
                "$set": {f"pokemon.{member.selected}.xp": 0,},
                "$inc": {f"pokemon.{member.selected}.level": qty,},
            }
            embed = discord.Embed()
            embed.color = 0xF44336
            embed.title = f"Congratulations {ctx.author.name}!"

            name = str(pokemon.species)

            if pokemon.nickname is not None:
                name += f' "{pokemon.nickname}"'

            embed.description = f"Your {name} is now level {pokemon.level + qty}!"

            if (
                pokemon.species.level_evolution is not None
                and pokemon.held_item != 13001
            ):
                if pokemon.level + qty >= pokemon.species.level_evolution.trigger.level:
                    embed.add_field(
                        name=f"Your {name} is evolving!",
                        value=f"Your {name} has turned into a {pokemon.species.level_evolution.target}!",
                    )
                    update["$set"][
                        f"pokemon.{member.selected}.species_id"
                    ] = pokemon.species.level_evolution.target_id

                    if member.silence and pokemon.level < 99:
                        await ctx.author.send(embed=embed)

            await self.db.update_member(ctx.author, update)

            if member.silence and pokemon.level == 99:
                await ctx.author.send(embed=embed)

            if not member.silence:
                await ctx.send(embed=embed)

        if "nature" in item.action:
            idx = int(item.action.split("_")[1])

            await self.db.update_member(
                ctx.author,
                {"$set": {f"pokemon.{member.selected}.nature": NATURES[idx]}},
            )

            await ctx.send(
                f"You changed your selected pokémon's nature to {NATURES[idx]}!"
            )

        if item.action == "held_item":
            await self.db.update_member(
                ctx.author, {"$set": {f"pokemon.{member.selected}.held_item": item.id}},
            )

        if item.action == "form_item":
            forms = GameData.all_species_by_number(pokemon.species.dex_number)
            for form in forms:
                if (
                    form.id != pokemon.species.id
                    and form.form_item is not None
                    and form.form_item == item.id
                ):
                    embed = discord.Embed()
                    embed.color = 0xF44336
                    embed.title = f"Congratulations {ctx.author.name}!"

                    name = str(pokemon.species)

                    if pokemon.nickname is not None:
                        name += f' "{pokemon.nickname}"'

                    embed.add_field(
                        name=f"Your {name} is changing forms!",
                        value=f"Your {name} has turned into a {form}!",
                    )

                    await self.db.update_member(
                        ctx.author,
                        {"$set": {f"pokemon.{member.selected}.species_id": form.id}},
                    )

                    await ctx.send(embed=embed)

                    break

