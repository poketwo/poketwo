from __future__ import annotations

import asyncio
import os
import random
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import cached_property
from textwrap import dedent
from typing import TYPE_CHECKING, Any, Dict, List, Optional
from urllib.parse import urljoin

import discord
from bson.objectid import ObjectId
from discord.ext import commands, tasks
from pymongo import IndexModel

from cogs import mongo
from cogs.mongo import Member
from data import models
from data.models import Species
from helpers import checks
from helpers.context import PoketwoContext
from helpers.converters import PokemonConverter, strfdelta
from helpers.utils import unwind

if TYPE_CHECKING:
    from bot import ClusterBot


NL = "\n"

SUMMER_BANNER_URL = "/assets/summer_2023/banner.png"
# This is still needed with imgen for when there is no expedition
EXPEDITION_BANNER_URL = "/assets/summer_2023/expedition_banner.png"
SHOP_IMAGE_URL = "/assets/summer_2023/shop_banner.png"

GHOST_STORY_FORM = "https://forms.gle/wpqJzDrMbWrgT5zv6"

MAX_POKEMON = 15

FISHING_BAIT_CHANCE = 0.06
FISHING_CHANCES = {
    "pc": 0.4,
    "summer_tokens": 0.29,
    "non-event": 0.27,
    "non-event-shiny": 0.005,
    "event-smeargle": 0.02,
    "nothing": 0.015,
}
FISHING_REWARD_AMOUNTS = {
    "pc": range(500, 1500),
    "summer_tokens": range(40, 60),
    "non-event": [1],
    "non-event-shiny": [1],
    "event-smeargle": [1],
    "nothing": [1],
}

FISHING_REWARDS = [*FISHING_CHANCES.keys()]
FISHING_WEIGHTS = [*FISHING_CHANCES.values()]

# IF THIS IS EVER CHANGED< NEED TO UPDATE IMAGE
# AND THE HELP MESSAGE OF THE BUY COMMAND
SHOP_ITEMS = {
    "shards": {"name": "Shards", "amount": 50, "price": 230},
    "pokecoins": {"name": "Pokécoins", "amount": 2000, "price": 50},
    "non-event": {"name": "Non-Event Pokémon", "amount": 5, "price": 100},
    "event": {"name": "Event Pokémon", "amount": 1, "price": 250},
}

SHOP_ITEM_SHORTCUTS = {
    ("1", "shard", f'{SHOP_ITEMS["shards"]["amount"]} shards'): "shards",
    ("2", "pokecoin", "pc", f'{SHOP_ITEMS["pokecoins"]["amount"]} pokecoins'): "pokecoins",
    ("3", "pokemon", "random", "random pokemon", f'{SHOP_ITEMS["non-event"]["amount"]} random pokemon'): "non-event",
    ("4", "events", "event pokemon", f'{SHOP_ITEMS["event"]["amount"]} event pokemon'): "event",
}
SHOP_SHORTCUTS = unwind(SHOP_ITEM_SHORTCUTS, include_values=True)
# We're using % instead of abundance so it's easier
EVENT_CHANCES = {50122: 0.40, 50121: 0.21, 50123: 0.21, 50119: 0.08, 50124: 0.075, 50125: 0.025}

EVENT_REWARDS = [*EVENT_CHANCES.keys()]
EVENT_WEIGHTS = [*EVENT_CHANCES.values()]

MAX_EXPEDITION_COUNT = 1
EXPEDITION_COST = 10

# Hours: Tokens
EXPEDITION_REWARDS = {1: 50, 3: 160, 6: 350, 12: 800}
REWARDS_TO_HOURS = {v: k for k, v in EXPEDITION_REWARDS.items()}

MAIN_MENU_COLOR = 0x2C958F
SHOP_COLOR = 0xBCCA4C
CAVE_COLOR = 0x974758
LAKE_COLOR = 0x78E0D9
FOREST_COLOR = 0x2C9579
MYSTERY_COLOR = 0x53328F

EXPEDITION_FLAVOR = {
    ("Ground", "Rock", "Dark", "Steel", "Ghost", "Psychic"): (
        "🏞️ Your {pokemon} embarks on a hike into the depths of the earth.",
        CAVE_COLOR,
    ),
    ("Water", "Ice", "Flying", "Fairy", "Electric", "Dragon"): (
        "🏕️ Your {pokemon} dives straight into Clarity Lake to explore the wonders of aquatic life.",
        LAKE_COLOR,
    ),
    ("Grass", "Fire", "Fighting", "Bug", "Poison", "Normal"): (
        "🛤️ Your {pokemon} wanders off into the woods to enjoy the gifts of nature.",
        FOREST_COLOR,
    ),
    (None, "Shadow", "???"): (
        "🌌 Your {pokemon} enters a mysterious portal, curious about what it withholds.",
        MYSTERY_COLOR,
    ),
}
# Unwind the dictionary keys into individual type: text items
EXPEDITION_FLAVOR = unwind(EXPEDITION_FLAVOR)

# Each main riddle type and how many minutes they reduce
RIDDLE_MAIN_TYPES = {
    "image": 10,
    "description": 10,
}
# Each sub riddle type and how many minutes they reduce
RIDDLE_SUB_TYPES = {"types": 5, "region": 10, "appearance": 10, "rarity": 5}
# Each riddle type and how many minutes they reduce
RIDDLE_SKIPS = RIDDLE_MAIN_TYPES | RIDDLE_SUB_TYPES
RIDDLE_ATTEMPTS = 3
SILHOUETTES_PATH = f"data/silhouettes/%s.png"
RIDDLE_IMG_NAME = "silhouette.png"

RARITIES = {"legendary": "Legendary", "mythical": "Mythical", "ultra_beast": "Ultra Beast", "event": "Event"}


@dataclass
class FlavorString:
    string: str
    emoji: Optional[str] = None
    plural: Optional[str] = None

    def __post_init__(self):
        self.plural = self.plural or f"{self.string}s"

    def __format__(self, format_spec) -> str:
        val = self.string
        emoji = self.emoji

        # Whether to use plural
        if "s" in format_spec:
            val = self.plural

        # Whether to not show emoji
        if "!e" not in format_spec and emoji is not None:
            val = f"{emoji} {val}"

        # Whether to bold
        if "b" in format_spec:
            val = f"**{val}**"

        return val

    def __str__(self) -> str:
        return f"{self}"

    def __repr__(self) -> str:
        return self.__str__()


class FlavorStrings:
    """Holds various flavor strings"""

    clarity_lake = FlavorString("Clarity Lake", "🏕️")
    bait = FlavorString("Fishing Bait", "🪱")
    tokens = FlavorString("Summer Tokens", "☀️")
    pokecoins = FlavorString("Pokécoins")  # TODO: Pokecoins emoji?
    shards = FlavorString("Shards")  # TODO: Shards emoji?
    shop = FlavorString("Camper Shop")
    charjabug = FlavorString("Camper Charjabug")


# Command strings
CMD_SUMMER = "`{0} summer`"
CMD_FISH = "`{0} summer fish`"
CMD_EXPEDITION = "`{0} expedition`"
CMD_EXPEDITION_COLLECT = "`{0} collect`"
CMD_EXPEDITION_SEND = "`{0} expedition send <pokemon_id>`"
CMD_SOLVERIDDLE = "`{0} expedition solveriddle <pokemon_guess>`"
CMD_SHOP = "`{0} summer shop`"
CMD_BUY = "`{0} summer buy <item_name> <quantity>`"
CMD_HELP_BUY = "`{0} help summer buy`"


class Summer(commands.Cog):
    """Summer 2023 commands."""

    def __init__(self, bot: ClusterBot):
        self.bot = bot
        if self.bot.cluster_idx == 0:
            self.collect_expeditions.start()
            self.notify_riddles.start()

    # async def cog_load(self):
    #     self.bot.log.info("creating indexes", cog="summer_2023")
    #     await self.bot.mongo.db.pokemon.create_indexes(
    #         [
    #             IndexModel("expedition_data.ends", partialFilterExpression={"owned_by": "expedition"}),
    #             IndexModel("expedition_data.riddles.time", partialFilterExpression={"owned_by": "expedition"}),
    #         ]
    #     )

    async def cog_unload(self):
        if self.bot.cluster_idx == 0:
            self.collect_expeditions.cancel()
            self.notify_riddles.cancel()

    @cached_property
    def pools(self) -> Dict[str, List[Species]]:
        p = {
            "event-smeargle": [50120],
            "non-event": self.bot.data.pokemon.keys(),
        }
        return {k: [self.bot.data.species_by_number(i) for i in v] for k, v in p.items()}

    @commands.Cog.listener(name="on_catch")
    async def drop_fishing_bait(self, ctx: PoketwoContext, species: Species, _id: int):
        count = await self.bot.redis.hincrby("summer_fishing_pity", ctx.author.id, 1)
        if random.random() <= FISHING_BAIT_CHANCE or count == round(1 / FISHING_BAIT_CHANCE):
            await self.bot.mongo.update_member(ctx.author, {"$inc": {"summer_2023_fishing_bait": 1}})
            await self.bot.redis.hdel("summer_fishing_pity", ctx.author.id)
            await ctx.send(
                f"You found a {FlavorStrings.bait:b}! Use {CMD_SUMMER.format(ctx.clean_prefix.strip())} for more info."
            )

    @checks.has_started()
    @commands.group(invoke_without_command=True, case_insensitive=True, aliases=("event", "ev"))
    async def summer(self, ctx: PoketwoContext):
        """Summer 2023 event commands."""

        prefix = ctx.clean_prefix.strip()
        member = await self.bot.mongo.fetch_member_info(ctx.author)
        description = dedent(
            f"""
            Here, you can:
            - Embark on expeditions and explore {FlavorStrings.clarity_lake:!e} 🏞️
                - {CMD_EXPEDITION.format(prefix)}
            - Fish at the lake for various rewards with {FlavorStrings.bait:sb!e} 🎣
                - {CMD_FISH.format(prefix)}
            - Visit the {FlavorStrings.shop} to spend {FlavorStrings.tokens:b!e} 🏕️
                - {CMD_SHOP.format(prefix)}
            - Tell your story at the campfire Ghost Story Contest 🔥
                - {GHOST_STORY_FORM}
            """
        )
        embed = self.bot.Embed(
            title=f"Welcome to the Summer camp at {FlavorStrings.clarity_lake}!", description=description
        )
        embed.color = MAIN_MENU_COLOR
        embed.set_image(url=self.bot.data.asset(SUMMER_BANNER_URL))

        embed.add_field(
            name=f"{FlavorStrings.bait} — {member.summer_2023_fishing_bait}",
            value=(
                f"You'll occasionally receive {FlavorStrings.bait:sb!e} from wild catches,"
                f" with which you can try your luck in the waters for various rewards!"
                f" And with luck, you might even hook a special Pokémon...."
            ),
            inline=False,
        )
        embed.add_field(
            name=f"{FlavorStrings.tokens} — {member.summer_2023_tokens}",
            value=(
                f"You can earn {FlavorStrings.tokens:b!e} from expeditions and sometimes from fishing!"
                f" These can be spent at the {FlavorStrings.shop} for various items and souvenirs!"
            ),
            inline=False,
        )

        await ctx.send(embed=embed)

    async def make_pokemon(
        self, owner: discord.User | discord.Member, member: Member, *, species: Species, shiny_boost: Optional[int] = 1
    ):
        ivs = [mongo.random_iv() for _ in range(6)]
        shiny = member.determine_shiny(species, boost=shiny_boost)
        return {
            "owner_id": member.id,
            "owned_by": "user",
            "species_id": species.id,
            "level": min(max(int(random.normalvariate(20, 10)), 1), 50),
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
            "idx": await self.bot.mongo.fetch_next_idx(owner),
        }

    @checks.has_started()
    @checks.is_not_in_trade()
    @summer.command()
    async def fish(self, ctx: PoketwoContext, *, qty: int = 1):
        """Fish for rewards."""

        member = await self.bot.mongo.fetch_member_info(ctx.author)
        if member.summer_2023_fishing_bait < qty:
            return await ctx.send(f"You don't have enough {FlavorStrings.bait}!")

        if qty <= 0:
            return await ctx.send(f"Nice try...")

        if qty > MAX_POKEMON:
            return await ctx.send(f"You can only fish {MAX_POKEMON} times at once!")

        await self.bot.mongo.update_member(ctx.author, {"$inc": {"summer_2023_fishing_bait": -qty}})

        embed = self.bot.Embed(
            title=f"You cast your line into the water at {FlavorStrings.clarity_lake:!e}...",
            description=None,
            color=LAKE_COLOR,
        )
        embed.set_author(icon_url=ctx.author.display_avatar.url, name=str(ctx.author))
        message = await ctx.reply(embed=embed, mention_author=False)

        update = {"$inc": {"balance": 0, "summer_2023_tokens": 0}}
        inserts = []
        text = []
        smeargles = 0

        for reward in random.choices(FISHING_REWARDS, weights=FISHING_WEIGHTS, k=qty):
            count = random.choice(FISHING_REWARD_AMOUNTS[reward])

            match reward:
                case "nothing":
                    text.append("- Trash :(")
                case "summer_tokens":
                    text.append(f"- {count} {FlavorStrings.tokens:!e}")
                    update["$inc"]["summer_2023_tokens"] += count
                case "pc":
                    text.append(f"- {count} {FlavorStrings.pokecoins:!e}")
                    update["$inc"]["balance"] += count
                case "event-smeargle" | "non-event" | "non-event-shiny":
                    shiny_boost = 1
                    if reward in ("non-event", "non-event-shiny"):
                        pool = [x for x in self.pools["non-event"] if x.catchable]
                        species = random.choices(pool, weights=[x.abundance for x in pool], k=1)[0]
                        if reward == "non-event-shiny":
                            shiny_boost = 4096  # Guarantee shiny
                    else:
                        species = smeargle = self.pools[reward][0]
                        shiny_boost = 10  # 10x shiny boost for smeargle
                        smeargles += 1

                    pokemon = await self.make_pokemon(ctx.author, member, species=species, shiny_boost=shiny_boost)
                    pokemon_obj = self.bot.mongo.Pokemon.build_from_mongo(pokemon)

                    text.append(f"- {pokemon_obj:liP}")
                    inserts.append(pokemon)

        await self.bot.mongo.update_member(ctx.author, update)
        if len(inserts) > 0:
            await self.bot.mongo.db.pokemon.insert_many(inserts)

        embed.title = f"From fishing {qty} times, you got..."
        embed.description = "\n".join(text)
        await message.edit(content=f"Woah, you got **{smeargles}x {smeargle}**!" if smeargles else None, embed=embed)

    @checks.has_started()
    @summer.command()
    async def shop(self, ctx: PoketwoContext):
        """Buy various items using Summer Tokens."""

        prefix = ctx.clean_prefix.strip()
        member = await self.bot.mongo.fetch_member_info(ctx.author)

        embed = self.bot.Embed(
            title=f"Welcome to the {FlavorStrings.shop}!",
            description=(
                f"Looks like {FlavorStrings.charjabug} has various items on sale for you.\n"
                f"You can use your {FlavorStrings.tokens:b!e} to buy them!"
            ),
            color=SHOP_COLOR,
        )
        embed.add_field(
            name=f"{FlavorStrings.tokens} — {member.summer_2023_tokens}",
            value=(
                f"You can earn {FlavorStrings.tokens:b!e} from expeditions ({CMD_EXPEDITION.format(prefix)}) and sometimes from fishing ({CMD_FISH.format(prefix)})!"
                f"\n\n> Use {CMD_BUY.format(prefix)} to buy an item!"
            ),
            inline=False,
        )
        embed.set_image(url=self.bot.data.asset(SHOP_IMAGE_URL))

        await ctx.send(embed=embed)

    @checks.has_started()
    @checks.is_not_in_trade()
    @summer.command(
        description=(
            "- `item_and_qty` - The name of the item that you want to buy, followed by the quantity (default=1). "
            "\n> Possible item choices:\n"
            f"""{
                NL.join(
                    [
                        f"> {idx + 1}. `{name}/{'/'.join(sh[1:])}`"
                        for idx, (sh, name)
                        in enumerate(SHOP_ITEM_SHORTCUTS.items())
                    ]
                )
            }"""
            "\n> It can also be the index of the item."
            f"\n\nE.g. `summer buy shards 2` means you will buy a total of `(50 x 2)` = 100 {FlavorStrings.shards}."
        )
    )
    async def buy(
        self,
        ctx: PoketwoContext,
        *,
        item_and_qty: Optional[str] = None,
    ):
        """Buy items from the Camper Shop"""

        # If no item provided, show the shop
        if item_and_qty is None:
            return await ctx.invoke(self.shop)

        # Greedily consume the arg until the last one for
        # item and make the last one quantity if it's a digit
        if len(split := item_and_qty.split()) > 1 and split[-1].isdigit():
            item = " ".join(split[:-1])
            qty = int(split[-1])
        else:
            item = item_and_qty
            qty = 1

        if qty <= 0:
            return await ctx.send(f"Nice try...")

        # Checks

        item_id = item.lower()
        try:
            item_id = SHOP_SHORTCUTS[item_id.lower()]
            item = SHOP_ITEMS[item_id]
        except KeyError:
            await ctx.send(
                f"Couldn't find an item called `{item}`. Use {CMD_HELP_BUY.format(ctx.clean_prefix.strip())} for help."
            )

        item_name = item["name"]
        amount = item["amount"] * qty
        price = item["price"] * qty

        member = await self.bot.mongo.fetch_member_info(ctx.author)
        if member.summer_2023_tokens < price:
            return await ctx.send(f"You don't have enough {FlavorStrings.tokens:!e} to buy that!")

        if item_id in ("non-event", "event") and amount > MAX_POKEMON:
            return await ctx.send(f"You can't buy more than a **total of {MAX_POKEMON}** of that item!")

        # Confirmation

        confirm = await ctx.confirm(
            f"Are you sure you want to buy **{amount} {item_name}** for **{price} {FlavorStrings.tokens}**?"
        )
        if confirm is None:
            return await ctx.send("Time's up. Aborted.")
        if not confirm:
            return await ctx.send("Aborted.")

        # Confirmed, proceed

        # Check if tokens have gone down since last check
        member = await self.bot.mongo.fetch_member_info(ctx.author)
        if member.summer_2023_tokens < price:
            return await ctx.send(f"You don't have enough {FlavorStrings.tokens:!e} to buy that!")

        # Deduct the total tokens
        await self.bot.mongo.update_member(ctx.author, {"$inc": {"summer_2023_tokens": -price}})

        embed = self.bot.Embed(title=FlavorStrings.shop, description=f"Thank you for your purchase, please come again!")
        embed.set_author(icon_url=ctx.author.display_avatar.url, name=str(ctx.author))
        embed.color = SHOP_COLOR

        # Parse the rewards
        text = []
        inserts = []
        match item_id:
            case "shards" | "pokecoins":
                field = "balance" if item_id == "pokecoins" else "premium_balance"
                await self.bot.mongo.update_member(ctx.author, {"$inc": {field: amount}})
                text.append(f"- **{amount}** {item_name}")

            case "event" | "non-event":
                if item_id == "non-event":
                    shiny_boost = 1
                    pool = [x for x in self.pools[item_id] if x.catchable]
                    species = random.choices(pool, weights=[x.abundance for x in pool], k=amount)
                else:
                    shiny_boost = 20  # 20x shiny boost for event pokemon
                    species = [
                        self.bot.data.species_by_number(s_id)
                        for s_id in random.choices(EVENT_REWARDS, weights=EVENT_WEIGHTS, k=amount)
                    ]

                for sp in species:
                    pokemon = await self.make_pokemon(ctx.author, member, species=sp, shiny_boost=shiny_boost)
                    pokemon_obj = self.bot.mongo.Pokemon.build_from_mongo(pokemon)

                    text.append(f"- {pokemon_obj:liP}")
                    inserts.append(pokemon)

        # Insert the pokemon
        if len(inserts) > 0:
            await self.bot.mongo.db.pokemon.insert_many(inserts)

        embed.add_field(name=f"Total spent: {price} {FlavorStrings.tokens}", value="\n".join(text), inline=False)
        await ctx.reply(embed=embed, mention_author=False)

    @tasks.loop(seconds=30)
    async def collect_expeditions(self):
        # Auto collect ended expeditions
        expeditions = self.bot.mongo.db.pokemon.find(
            {"owned_by": "expedition", "expedition_data.ends": {"$lte": datetime.utcnow()}}
        )
        async for pokemon in expeditions:
            asyncio.create_task(self.collect_expedition(pokemon["_id"], discord.Object(pokemon["owner_id"])))

    async def collect_expedition(self, pokemon_id: ObjectId, owner: discord.Object):
        pokemon = await self.bot.mongo.db.pokemon.find_one_and_update(
            {"_id": pokemon_id, "owned_by": "expedition"},
            {
                "$set": {"owned_by": "user", "idx": await self.bot.mongo.fetch_next_idx(owner)},
                "$unset": {"expedition_data": 1},
            },
        )
        pokemon_obj = self.bot.mongo.Pokemon.build_from_mongo(pokemon)
        await self.bot.mongo.update_member(
            owner, {"$inc": {"summer_2023_tokens": pokemon["expedition_data"]["reward"]}}
        )
        await self.bot.send_dm(
            owner,
            f"Your **{pokemon_obj:lip}** has returned from its expedition with **{pokemon['expedition_data']['reward']} {FlavorStrings.tokens}**!",
        )

    @collect_expeditions.before_loop
    async def before_collect_expeditions(self):
        await self.bot.wait_until_ready()

    @tasks.loop(seconds=20)
    async def notify_riddles(self):
        # Notify users about new available riddles
        riddle_pokemon = self.bot.mongo.db.pokemon.find(
            {
                "owned_by": "expedition",
                "expedition_data.riddles": {
                    "$elemMatch": {
                        "time": {"$lte": datetime.utcnow()},
                        "attempts": {"$gt": 0},
                        "notified": False,
                    }
                },
            }
        )
        async for pokemon in riddle_pokemon:
            t = await self.bot.mongo.db.pokemon.find_one_and_update(
                {
                    "_id": pokemon["_id"],
                    "owned_by": "expedition",
                    "expedition_data.riddles.time": {"$lte": datetime.utcnow()},
                },
                {"$set": {"expedition_data.riddles.$[].notified": True}},
            )

            await self.bot.send_dm(
                pokemon["owner_id"],
                f"During its expedition, your Pokémon stumbled upon a shortcut passage. To use it, you must solve a riddle... Use {CMD_EXPEDITION.format('@Pokétwo')} to learn more!",
            )

    @notify_riddles.before_loop
    async def before_notify_loop(self):
        await self.bot.wait_until_ready()

    def get_silhouette(self, species_id: int) -> discord.File:
        return discord.File(SILHOUETTES_PATH % species_id, RIDDLE_IMG_NAME)

    @checks.has_started()
    @commands.group(invoke_without_command=True, aliases=("exp",))
    async def expedition(self, ctx: PoketwoContext):
        """View your current expedition."""

        prefix = ctx.clean_prefix.strip()

        pokemon = await self.bot.mongo.db.pokemon.find_one({"owner_id": ctx.author.id, "owned_by": "expedition"})

        embed = self.bot.Embed(title="Your Expedition", description=None)

        if pokemon is None:
            rewards = [
                f"- **{strfdelta(timedelta(hours=dur), long=True)}** -> **{reward}** {FlavorStrings.tokens}"
                for dur, reward in EXPEDITION_REWARDS.items()
            ]
            embed.description = (
                dedent(
                    f"""
                    You can send Pokémon on expeditions to various areas around {FlavorStrings.clarity_lake} to search for some rewards!
                    - {CMD_EXPEDITION_SEND.format(prefix)}

                    The longer you have the Pokémon on expedition, the more tokens they will be able to find.
                    ### **Expedition lengths and earnings**
                    """
                )
                + NL.join(rewards)
            )
            embed.set_image(url=self.bot.data.asset(EXPEDITION_BANNER_URL))
            return await ctx.send(embed=embed)

        file = None
        p = self.bot.mongo.Pokemon.build_from_mongo(pokemon)

        total_duration = REWARDS_TO_HOURS[pokemon["expedition_data"]["reward"]] * 3600  # In seconds
        ends = pokemon["expedition_data"]["ends"]
        time_left = ends - datetime.utcnow()

        url = urljoin(
            self.bot.config.EXT_SERVER_URL, f"summer_2023?progress={1 - time_left.total_seconds()/total_duration}"
        )
        embed.set_image(url=url)

        embed.description = f"Your **`{p.idx}` {p:Lip}** will be back in `{strfdelta(time_left)}` 🏞️"
        # Decide the embed color based on pokemon's first type
        types = p.species.types or (None,)
        embed.color = EXPEDITION_FLAVOR[types[0]][1]

        # Construct the riddles part of the embed

        all_riddles, riddles, unsolved_riddles = self.get_expedition_riddles(pokemon)

        if len(unsolved_riddles) > 0 and time_left.total_seconds() > 0:
            riddle = unsolved_riddles[0]
            species = self.bot.data.species_by_number(riddle["species_id"])
            types = riddle["types"]
            skip_minutes = self.riddle_time_skip(riddle)

            # Construct the hint message
            hints = []
            if "image" in types:
                hints.append("*In the dance of shade and light,\nwho is that at the top right?*")
                file = await self.bot.loop.run_in_executor(None, self.get_silhouette, species.id)
                embed.set_thumbnail(url=f"attachment://{RIDDLE_IMG_NAME}")
            elif "description" in types:
                u = r"\_" * 8
                description = species.description
                # Censor the species name if it's in the description
                for _, name in species.names:
                    description = description.replace(name, u).replace(name.casefold(), u)

                hints.append(description)

            if "types" in types:
                hints.append(f"**Type(s)**: {' & '.join(map(lambda t: t.capitalize(), species.types))}")
            elif "region" in types:
                hints.append(f"**Region**: {species.region.capitalize()}")
            elif "appearance" in types:
                hints.append(f"**Height**: {species.height} m\n**Weight**: {species.weight} kg")
            elif "rarity" in types:
                hints.append(
                    "**Rarity**: "
                    + ", ".join([text for rarity, text in RARITIES.items() if bool(getattr(species, rarity, 0))])
                )

            hint = f">>> {(NL*2).join(hints)}"
            field_name = f"Riddle {len(riddles) - len(unsolved_riddles) + 1}/{len(riddles)}"
            field_value = (
                dedent(
                    f"""
                    Your Pokémon discovered a shortcut passage! Walking this route instead could save it **{skip_minutes} minutes**, but you must solve a riddle first…
                    {CMD_SOLVERIDDLE.format(prefix)}

                    **Who's that Pokémon? (*`{riddle['attempts']}/{RIDDLE_ATTEMPTS}` attempts left*)**
                    """
                )
                + hint
            )
        else:
            field_name = f"Riddle"
            field_value = "*Nothing to see here... maybe check back later?*"

        embed.add_field(name=field_name, value=field_value)

        await ctx.send(embed=embed, file=file)

    def get_expedition_riddles(self, pokemon: Dict[str, Any]):
        # All riddles
        all_riddles = pokemon["expedition_data"]["riddles"]
        # All riddles excluding future ones
        riddles = [riddle for riddle in all_riddles if riddle["time"] <= datetime.utcnow()]
        # All riddles excluding future ones that are unsolved
        unsolved_riddles = [riddle for riddle in riddles if riddle["attempts"] > 0]

        return all_riddles, riddles, unsolved_riddles

    def riddle_time_skip(self, riddle: Dict[str, Any]):
        return sum(RIDDLE_SKIPS[type] for type in riddle["types"])

    @checks.has_started()
    @expedition.command(aliases=("solve", "riddle"))
    async def solveriddle(self, ctx: PoketwoContext, *, answer: str):
        pokemon = await self.bot.mongo.db.pokemon.find_one({"owner_id": ctx.author.id, "owned_by": "expedition"})

        if pokemon is None:
            return await ctx.send("You don't have an expedition running!")

        all_riddles, riddles, unsolved_riddles = self.get_expedition_riddles(pokemon)
        if len(unsolved_riddles) == 0:
            return await ctx.send("No riddle to solve at the moment.")

        riddle = unsolved_riddles[0]
        riddle_species = self.bot.data.species_by_number(riddle["species_id"])

        if models.deaccent(answer.lower().replace("′", "'")) in riddle_species.correct_guesses:
            riddle["attempts"] = 0
            total_skip = self.riddle_time_skip(riddle)
            skip_minutes = timedelta(minutes=total_skip)

            # Reduce expedition end time
            pokemon["expedition_data"]["ends"] -= skip_minutes
            # Gotta reduce the riddles' times too to make sure they don't exceed expedition
            for r in riddles:
                r["time"] -= skip_minutes

            msg = (
                f"Congratulations, `{riddle_species}` was the correct Pokémon and the passage was revealed! "
                f"Taking this route saves your Pokémon `{total_skip} minutes` of expedition time."
            )
        else:
            species = self.bot.data.species_by_name(answer)
            if species is None:
                return await ctx.send(f"Could not find a Pokémon matching `{answer}`.")

            riddle["attempts"] -= 1
            msg = f"`{species}` is not the correct Pokémon! "

            if riddle["attempts"] > 0:
                msg += f"`{riddle['attempts']}` more attempt(s) remaining."
            else:
                msg += (
                    f"You've run out of attempts, the correct Pokémon was `{riddle_species}`. Better luck next time :("
                )

        await self.bot.mongo.update_pokemon(
            pokemon,
            {
                "$set": {
                    "expedition_data.ends": pokemon["expedition_data"]["ends"],
                    "expedition_data.riddles": all_riddles,
                }
            },
        )
        await ctx.send(msg)

    def make_random_riddle(self, exp_starts: datetime, exp_ends: datetime) -> Dict[str, Any]:
        species = None
        while species is None:
            main_types = list(RIDDLE_MAIN_TYPES.keys())
            sub_types = list(RIDDLE_SUB_TYPES.keys())
            candidate = random.choice([x for x in self.pools["non-event"] if x.catchable])

            # Make sure to pick hints only on the fields available
            if not os.path.exists(SILHOUETTES_PATH % candidate.id):
                main_types.remove("image")
            if not candidate.description:
                main_types.remove("description")

            if not candidate.height or not candidate.weight:
                sub_types.remove("appearance")
            if not candidate.types:
                sub_types.remove("types")
            if not candidate.region:
                sub_types.remove("region")
            if not any((candidate.legendary, candidate.mythical, candidate.ultra_beast, candidate.event)):
                sub_types.remove("rarity")

            # If no main or sub hint types, choose again
            if all((main_types, sub_types)):
                species = candidate

        # Picks a random main type and sub type
        types = random.choice(main_types), random.choice(sub_types)

        # Set a random time between start and end of expedition
        time = exp_starts + (exp_ends - exp_starts) * random.random()

        return {"species_id": species.id, "types": types, "time": time, "attempts": RIDDLE_ATTEMPTS, "notified": False}

    @checks.has_started()
    @checks.is_not_in_trade()
    @expedition.command(aliases=("start",))
    async def send(self, ctx: PoketwoContext, pokemon: PokemonConverter):
        """Send your Pokémon on an expedition."""

        if pokemon is None:
            return await ctx.send("Couldn't find that pokémon!")

        member = await self.bot.mongo.fetch_member_info(ctx.author)
        if pokemon.id == member.selected_id:
            return await ctx.send("Can't send selected pokémon to expedition!")

        count = await self.bot.mongo.db.pokemon.count_documents({"owner_id": ctx.author.id, "owned_by": "expedition"})
        if count >= MAX_EXPEDITION_COUNT:
            return await ctx.send(f"You can only have {MAX_EXPEDITION_COUNT} expedition running at a time!")
        if member.summer_2023_tokens < EXPEDITION_COST:
            return await ctx.send("You need at least 10 summer tokens to send your Pokémon on an expedition!")

        duration = await ctx.select(
            f"How long should your **No. {pokemon.idx} {pokemon:lni}** explore for?",
            options=[
                *[
                    discord.SelectOption(
                        label=strfdelta(timedelta(hours=dur), long=True),
                        description=f"Reward: {reward} {FlavorStrings.tokens}",
                        value=str(dur),
                    )
                    for dur, reward in EXPEDITION_REWARDS.items()
                ],
                discord.SelectOption(label="Cancel", value="cancel"),
            ],
        )
        if duration is None:
            return await ctx.send("Time's up. Aborted.")
        if duration[0] == "cancel":
            return await ctx.send("Aborted.")

        # re-check conditions after waiting
        if await ctx.bot.mongo.fetch_pokemon(ctx.author, pokemon.idx) is None:
            return await ctx.send("Couldn't find that pokémon!")

        member = await self.bot.mongo.fetch_member_info(ctx.author)
        count = await self.bot.mongo.db.pokemon.count_documents({"owner_id": ctx.author.id, "owned_by": "expedition"})
        if count >= MAX_EXPEDITION_COUNT:
            return await ctx.send(f"You can only have {MAX_EXPEDITION_COUNT} expedition running at a time!")
        if member.summer_2023_tokens < EXPEDITION_COST:
            return await ctx.send("You need at least 10 summer tokens to send your Pokémon on an expedition!")

        # ok, go

        duration_selection = float(duration[0])
        duration = timedelta(hours=duration_selection)
        expedition_starts = datetime.utcnow()
        expedition_ends = expedition_starts + duration

        # How many riddles you get is determined by the selected duration
        riddles = sorted(
            [
                self.make_random_riddle(expedition_starts, expedition_ends)
                for _ in range(sorted(EXPEDITION_REWARDS.keys()).index(duration_selection) + 1)
            ],
            key=lambda r: r["time"],
        )

        await self.bot.mongo.update_member(ctx.author, {"$inc": {"summer_2023_tokens": -EXPEDITION_COST}})
        await self.bot.mongo.update_pokemon(
            pokemon,
            {
                "$set": {
                    "owned_by": "expedition",
                    "expedition_data": {
                        "reward": EXPEDITION_REWARDS[duration_selection],
                        "ends": expedition_ends,
                        "riddles": riddles,
                    },
                }
            },
        )

        # Decide the flavor text based on pokemon's first type
        types = pokemon.species.types or (None,)
        expedition_text = EXPEDITION_FLAVOR[types[0]][0].format(pokemon=f"**No. {pokemon.idx} {pokemon:lni}**")

        await ctx.send(expedition_text + f" It will be back in **{strfdelta(duration, long=True)}**")

    @checks.has_started()
    @checks.is_not_in_trade()
    @expedition.command()
    async def cancel(self, ctx: PoketwoContext):
        """Cancel an expedition."""

        pokemon = await self.bot.mongo.db.pokemon.find_one({"owner_id": ctx.author.id, "owned_by": "expedition"})
        if pokemon is None:
            return await ctx.send("You don't have an expedition running!")

        pokemon = self.bot.mongo.Pokemon.build_from_mongo(pokemon)

        result = await ctx.confirm(
            f"Are you sure you want your {pokemon.species} to return from its expedition? You will not receive any rewards."
        )
        if result is None:
            return await ctx.send("Time's up. Aborted.")
        if not result:
            return await ctx.send("Aborted.")

        await self.bot.mongo.update_pokemon(
            pokemon,
            {
                "$set": {"owned_by": "user", "idx": await self.bot.mongo.fetch_next_idx(ctx.author)},
                "$unset": {"expedition_data": 1},
            },
        )
        await ctx.send(f"Your {pokemon.species} takes a rain check and returns from its expedition early.")


async def setup(bot: commands.Bot):
    await bot.add_cog(Summer(bot))
