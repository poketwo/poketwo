from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from enum import Enum
import io
import random
import contextlib
from textwrap import dedent
from typing import TYPE_CHECKING, Dict, List, Optional
from urllib.parse import urlencode, urljoin

import discord
from discord.ext import commands


from cogs.mongo import Member
from data.models import Species
from data.utils import comma_formatted
from helpers import checks
from helpers.context import ConfirmationAcceptDeclineView, PoketwoContext
from helpers.converters import EnumConverter, GreedyEnumConverter
from helpers.utils import BaseItemEnum, FlavorString

from lib.box_rewards import Reward, RewardItem, give_rewards, simulate_rewards

if TYPE_CHECKING:
    from bot import ClusterBot


# region CONSTANTS
EVENT_PREFIX = "day_of_the_dead_2024"

EMBED_COLOR = 0xDF8D34

EVENT_SHINY_BOOST = 5
SET_COMPLETION_BOXES = 1
OFRENDA_COMPLETION_BOXES = 5

MAX_ITEMS = 5
EMPTY_ITEM_ID = 0


# Alebrijes/Quests
QUEST_ENCOUNTER_CHANCE = 0.15
QUEST_PC_REWARD = 1000
QUESTS = [
    lambda: {
        "event": "catch",
        "count": (count := random.randint(15, 25)),
        "description": f"Catch {count} pokémon",
    },
    lambda: {
        "event": "trade",
        "count": (count := random.randint(2, 3)),
        "description": f"Trade with {count} people",
    },
    lambda: {
        "event": "evolve",
        "count": (count := random.randint(3, 5)),
        "description": f"Evolve {count} pokémon",
    },
    lambda: {
        "event": "release",
        "count": (count := random.randint(5, 10)),
        "description": f"Release {count} pokémon",
    },
    lambda: {
        "event": "market_buy",
        "count": (count := random.randint(250, 500)),
        "description": f"Spend {count} Pokécoins on the market",
    },
    lambda: {
        "event": "market_sell",
        "count": (count := random.randint(250, 500)),
        "description": f"Earn {count} Pokécoins from the market",
    },
]

INVENTORY_DESCRIPTION_COLLAPSED = "Click the expand button to learn more about this holiday's traditions!"
INVENTORY_DESCRIPTION = dedent(
    f"""
    Ofrendas are traditionally decorated with items that represent the deceased loved one and their preferences, as well as the four elements—water, wind, earth, and fire.
    - Water is a symbol of purity and is represented with a full pitcher so spirits may quench their thirst and wash themselves.
    - Wind is represented with colorful hanging paper, called papel picado, symbolizing the journey of the departed soul.
    - Earth is represented by "the crop"—foods such as pan de muerto and other dishes and drinks that the departed loved one enjoyed.
    - Fire is represented with candles, thought to guide the spirit of the departed to the altar honoring them.

    Other items typically include cempasúchiles, or marigolds, which are fragrant flowers thought to guide the visiting spirits; incense, which represents the transition from the corporeal to the spiritual realm; sugar skulls, or calaveras, which symbolize the sweetness in life and in death; and photographs of the departed loved one, and many other items thought to guide them, bring them joy, or bring them rest.
    """
)


class FlavorStrings:
    """Holds various flavor strings."""

    box = FlavorString("Nicho Box", "<:nicho:1297183209817374781>", "Nicho Boxes")
    items = FlavorString("Item", None, "Items", default_plural=True)


QUEST_FLAVOUR = {
    "alebrije": {
        "name": "Alebrije Pyroar",
        "image": "/assets/day_of_the_dead_2024/encounter_pyroar.png",
        "encounter": "You've come across an Alebrije Pyroar!",
        "description": f"The ethereal pokémon accompanies you as you complete your quests, each one rewarding pokécoins. Upon completing all, you'll be rewarded a {FlavorStrings.box:!e} and an item to decorate your ofrendas.\n\nYou may only have one pokémon accompanying you at a time. Once you've completed its quests, it will depart to allow you a new encounter.",
    },
    "pidgey": {
        "name": "Papel Picado Pidgey",
        "image": "/assets/day_of_the_dead_2024/encounter_pidgey.png",
        "encounter": "You've come across an Papel Picado Pidgey!",
        "description": f"The joyful little bird accompanies you as you complete your quests, each one rewarding pokécoins. Upon completing all, you'll be rewarded a {FlavorStrings.box:!e} and an item to decorate your ofrendas.\n\nYou may only have one pokémon accompanying you at a time. Once you've completed its quests, it will fly off to allow you a new encounter.",
    },
}


# region ENUMS
class Item(BaseItemEnum):
    """Enum for all the offering items"""

    CANDLES = 1, "Candle", "<:candle:1297191789488377856>", ["candle", "c"]
    FLOWERS = (
        2,
        "Cempasúchiles",
        "<:flowers:1297191792449425418>",
        ["flowers", "flower", "marigolds", "cempasúchil", "f"],
    )
    PAN_DE_MUERTO = 3, "Pan de muerto", "<:pan_de_muerto:1298716081095053393>", ["bread", "pan", "p"]
    CALAVERA = 4, "Calavera", "<:calavera:1297191946225319948>", ["skull", "candy", "s"]
    DRINKS = 5, "Drink", "<:drink:1297191948926324806>", ["drinks", "d"]


class EventSpecies(Enum):
    """Enum for all event pokemon for this event"""

    PIDGEY = 50192
    LOTAD = 50193, 0.25
    DUSKULL = 50194, 0.25
    YAMASK = 50195, 0.25
    GOTHITELLE = 50196, 0.15
    PYROAR = 50197
    LILLIGANT = 50198, 0.10

    def __init__(self, id: int, weight: Optional[int | float] = None) -> None:
        self.id = id
        self.weight = weight

    def get_species(self, bot: ClusterBot) -> Species:
        return bot.data.species_by_number(self.value)

    def text(self, bot: ClusterBot, *, amount: Optional[int] = None) -> str:
        species = self.get_species(bot)
        return f"""{bot.sprites.get(species)} {f"{amount}x " if amount is not None else ""}{species.name}"""

    @classmethod
    def all_ids(cls) -> List[int]:
        return [species.id for species in cls]

    @classmethod
    def to_weights(cls) -> Dict[int, int | float]:
        return {species.id: species.weight for species in cls if species.weight}


# region VIEWS
class DOTDView(discord.ui.View):
    def __init__(self, ctx: PoketwoContext):
        self.ctx = ctx
        self.cog: DOTD = self.ctx.bot.get_cog("DOTD")
        super().__init__(timeout=120)

    @discord.ui.button(label="Quests", style=discord.ButtonStyle.blurple)
    async def quests(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await self.ctx.invoke(self.cog.quests)

    @discord.ui.button(label="Inventory", style=discord.ButtonStyle.grey)
    async def inventory(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await self.ctx.invoke(self.cog.inventory)

    async def interaction_check(self, interaction):
        if interaction.user.id not in {
            self.ctx.bot.owner_id,
            self.ctx.author.id,
            *self.ctx.bot.owner_ids,
        }:
            await interaction.response.send_message("You can't use this!", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        if self.message:
            for child in self.children:
                child.disabled = True
            await self.message.edit(view=self)


class InformationView(discord.ui.View):
    def __init__(self, ctx: PoketwoContext, embed: discord.Embed):
        self.ctx = ctx
        self.embed = embed
        super().__init__(timeout=120)

    @discord.ui.button(label="Expand Information", style=discord.ButtonStyle.blurple)
    async def info(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.embed.description == INVENTORY_DESCRIPTION_COLLAPSED:
            self.embed.description = INVENTORY_DESCRIPTION
            button.style = discord.ButtonStyle.green
            button.label = "Collapse Information"
        else:
            self.embed.description = INVENTORY_DESCRIPTION_COLLAPSED
            button.style = discord.ButtonStyle.blurple
            button.label = "Expand Information"

        await interaction.response.edit_message(embed=self.embed, view=self)

    async def interaction_check(self, interaction):
        if interaction.user.id not in {
            self.ctx.bot.owner_id,
            self.ctx.author.id,
            *self.ctx.bot.owner_ids,
        }:
            await interaction.response.send_message("You can't use this!", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        if self.message:
            for child in self.children:
                child.disabled = True
            await self.message.edit(view=self)


BOX_REWARDS = [
    Reward(
        item=RewardItem.EVENT_POKEMON,
        chance=40,
        amounts=[1],
        species_ids=EventSpecies.to_weights(),
        shiny_boost=EVENT_SHINY_BOOST,
    ),
    Reward(item=RewardItem.POKECOINS, chance=35, amounts=range(1000, 1501)),
    Reward(item=RewardItem.SHARDS, chance=15, amounts=range(5, 16)),
    Reward(item=RewardItem.POKEMON, chance=9, amounts=[1], shiny_boost=300),
    Reward(item=RewardItem.REDEEM, chance=1, amounts=[1]),
]


# region MAIN COG
class DOTD(commands.Cog):
    """Day of the Dead 2024 event commands."""

    def __init__(self, bot):
        self.bot: ClusterBot = bot

    # region Functions
    def choose_flavour(self):
        chosen_flavour = random.choice(list(QUEST_FLAVOUR.keys()))
        return chosen_flavour

    def make_random_quests(self):
        quests = [
            *[x() for x in random.sample(QUESTS, k=3)],
        ]
        return [{**x, "progress": 0, "complete": False} for x in quests]

    async def get_quests(self, user):
        member = await self.bot.mongo.fetch_member_info(user)
        return member[f"{EVENT_PREFIX}_quests"]

    async def send_chunked_lines(self, user: discord.Member, lines: List[str]):
        max_lines = 10
        for chunk in discord.utils.as_chunks(lines, max_lines):
            with contextlib.suppress(discord.HTTPException):
                await user.send("\n".join(chunk))

    def verify_condition(self, condition, pokemon, to=None):
        if condition is not None:
            species = pokemon.species
            for k, v in condition.items():
                if k == "id" and species.id != v:
                    return False
                elif k == "type" and v not in species.types:
                    return False
                elif k == "region" and v != species.region:
                    return False
                elif k == "to" and to.id != v:
                    return False
                elif k == "gender" and v != pokemon.gender.lower():
                    return False
        return True

    async def check_quests(self, user, context=None):
        member = await self.bot.mongo.fetch_member_info(user)
        quests = member[f"{EVENT_PREFIX}_quests"]
        if quests is None:
            return

        messages = []
        for i, q in enumerate(quests):
            if q["progress"] >= q["count"] and not q.get("complete"):
                member = await self.bot.mongo.db.member.find_one_and_update(
                    {
                        "_id": user.id,
                        f"{EVENT_PREFIX}_quests.{i}.progress": {"$gte": q["count"]},
                        f"{EVENT_PREFIX}_quests.{i}.complete": {"$ne": True},
                    },
                    {"$set": {f"{EVENT_PREFIX}_quests.{i}.complete": True}, "$inc": {"balance": QUEST_PC_REWARD}},
                )
                if member is not None:
                    await self.bot.redis.hdel("db:member", user.id)
                    messages.append(
                        dedent(
                            f"""
                            You have completed the event quest "{q['description']}" and earned **{QUEST_PC_REWARD:,} Pokécoins**!
                            -# Use `@Pokétwo#8236 {self.quests.qualified_name}` to see all your quests.
                            """
                        ).strip("\n")
                    )

        if messages:
            if context:
                for message in messages:
                    await context.send(
                        f"Congratulations {user.mention}! {message}",
                        allowed_mentions=discord.AllowedMentions(users=True)
                        if member.get("catch_mention", True)
                        else discord.AllowedMentions.none(),
                    )
            else:
                await self.send_chunked_lines(user, messages)

            await self.all_quests_complete(user)

    async def all_quests_complete(self, user, context=None):
        member = await self.bot.mongo.fetch_member_info(user)
        quests = member[f"{EVENT_PREFIX}_quests"]
        if not quests:
            return

        if all(q.get("complete") for q in member[f"{EVENT_PREFIX}_quests"]):
            quests_metadata = member[f"{EVENT_PREFIX}_quests_metadata"]
            item = Item[quests_metadata["item"]]
            flavour = QUEST_FLAVOUR[quests_metadata["flavour"]]
            await self.bot.mongo.update_member(
                user,
                {
                    "$unset": {f"{EVENT_PREFIX}_quests": 1},
                    "$inc": {
                        f"{EVENT_PREFIX}_items.{item.name}": 1,
                        f"{EVENT_PREFIX}_boxes": SET_COMPLETION_BOXES,
                    },
                },
            )
            await (context if context else user).send(
                dedent(
                    f"""
                    Congratulations{' ' + user.mention if context else ''}! You've completed all your quests for {flavour['name']} and earned **{SET_COMPLETION_BOXES} {FlavorStrings.box:{'' if SET_COMPLETION_BOXES == 1 else 's'}}** and **1 x {item}**!
                    -# Use `@Pokétwo#8236 {self.open.qualified_name} {self.open.signature}` to open your {FlavorStrings.box:s!e}!
                    -# Use `@Pokétwo#8236 {self.offer.qualified_name} {self.offer.signature}` to decorate your ofrenda with items!
                    """
                )
            )

    async def cog_load(self):
        self.bot.Embed.CUSTOM_COLOR = EMBED_COLOR  # Set custom embed color for this event

    async def cog_unload(self):
        self.bot.Embed.CUSTOM_COLOR = None  # Unset custom embed color

    def get_ofrenda_offerings(self, member) -> List[int]:
        item_ids = [0] * MAX_ITEMS
        for i, item_id in enumerate(member.day_of_the_dead_2024_ofrenda_offerings):
            item_ids[i] = item_id or EMPTY_ITEM_ID
        return item_ids

    def ofrenda_image_url(self, offerings: List[int]) -> str:
        return (
            urljoin(self.bot.config.EXT_SERVER_URL, f"day_of_the_dead_2024/ofrenda")
            + "?"
            + urlencode({"items": ",".join(map(str, offerings))})
        )

    # region main embed
    @checks.has_started()
    @commands.group(
        aliases=("dia-de-muertos", "day-of-the-dead", "ddm", "event", "ev", "ofrenda"),
        invoke_without_command=True,
        case_insensitive=True,
    )
    async def dotd(self, ctx: PoketwoContext):
        """Open Day of the Dead 2024 menu"""

        member = await self.bot.mongo.fetch_member_info(ctx.author)
        member_offerings = self.get_ofrenda_offerings(member)

        embed = self.bot.Embed(
            title=f"Día de Muertos (Day of the Dead)",
            description=dedent(
                f"""
                Welcome to the Día de Muertos (Day of the Dead) celebration, a Mexican tradition to pay respects to friends and family who have passed away.

                Ofrendas are traditional Mexican altars decorated for this celebration to honor deceased loved ones. During this event, you'll encounter alebrijes and pokémon with quests as you catch pokémon. Alebrijes are colorful, whimsical spirit animals believed to connect the living and spirit realms.

                As you complete their quests, you'll be rewarded with pokécoins, {FlavorStrings.box:s!e} and items to decorate your ofrendas with, and as you complete ofrendas, you'll receive more {FlavorStrings.box:sb} that contain various gifts!
                -# Use `{ctx.clean_prefix}{self.quests.qualified_name}` to view your active quests
                """
            ),
        )
        embed.set_image(url=self.ofrenda_image_url(self.get_ofrenda_offerings(member)))

        value = ", ".join([f"{discord.utils.get(Item, id=i):b}" if i else "—" for i in member_offerings])
        embed.add_field(
            name=f"Your Current Ofrenda — #{member.day_of_the_dead_2024_ofrendas_completed + 1}",
            value=dedent(
                f"""
                Items used to decorate your ofrenda so far:
                {value}

                *Complete the ofrenda to earn **{OFRENDA_COMPLETION_BOXES} {FlavorStrings.box:{'' if OFRENDA_COMPLETION_BOXES == 1 else 's'}}!***
                -# Use `{ctx.clean_prefix}{self.inventory.qualified_name}` to view and offer items
                """
            ),
        )

        view = DOTDView(ctx)
        if not member[f"{EVENT_PREFIX}_quests"]:
            view.quests.style = discord.ButtonStyle.gray

        view.message = await ctx.send(embed=embed, view=view)

    @checks.has_started()
    @dotd.command(name="inventory", aliases=("inv", "boxes", "items"))
    async def inventory(self, ctx: PoketwoContext):
        """See how many tickets and boxes you have"""

        member = await self.bot.mongo.fetch_member_info(ctx.author)
        items = member.day_of_the_dead_2024_items
        boxes = member.day_of_the_dead_2024_boxes

        embed = self.bot.Embed(
            title=f"Your Inventory",
            description=INVENTORY_DESCRIPTION_COLLAPSED,
        )
        embed.set_author(name=str(ctx.author), icon_url=ctx.author.display_avatar.url)

        embed.add_field(
            name=f"Offering {FlavorStrings.items}",
            value="\n".join(
                [
                    dedent(
                        """
                        Here are items you can offer and decorate your ofrendas with. As you catch pokémon, you'll encounter alebrijes and pokémon in need of assistance. Complete their quests to earn items, among other rewards!"""
                    ),
                    "\n".join(f"- {item:b}: {items.get(item.name, 0):,}" for item in Item),
                    f"-# Use `{ctx.clean_prefix}{self.offer.qualified_name} {self.offer.signature}` to offer {FlavorStrings.items}",
                    f"-# Use `{ctx.clean_prefix}help {self.offer.qualified_name}` to see aliases of items",
                ]
            ),
            inline=False,
        )
        embed.add_field(
            name=f"{FlavorStrings.box:s} — {boxes:,}",
            value="\n".join(
                [
                    dedent(
                        f"""
                        {FlavorStrings.box:s!e} are gift boxes which contain gifts such as exclusive event pokémon, pokécoins, shards and redeems. Earn more by completing quests and ofrendas using items earned through those quests!"""
                    ),
                    f"-# Use `{ctx.clean_prefix}{self.open.qualified_name} {self.open.signature}` to open your {FlavorStrings.box:s!e}",
                ]
            ),
            inline=False,
        )

        view = InformationView(ctx, embed)
        view.message = await ctx.reply(embed=embed, view=view, mention_author=False)

    @checks.has_started()
    @dotd.command(
        name="offer",
        aliases=("ofrece", "use"),
        help="Pass in the items you want to offer separated by spaces, or leave empty to offer randomly.",
        description="Offer items to decorate your ofrenda\n### Items\n"
        + "\n".join(f"- {item} [{', '.join(item.aliases)}]" for item in Item),
    )
    async def offer(
        self,
        ctx: PoketwoContext,
        *,
        items: GreedyEnumConverter(Item) = None,
    ):
        """Offer items to decorate your ofrenda"""

        member = await self.bot.mongo.fetch_member_info(ctx.author)
        member_items = member.day_of_the_dead_2024_items
        member_offerings = self.get_ofrenda_offerings(member)

        offerings_needed = member_offerings.count(EMPTY_ITEM_ID)

        shuffle = False
        if items:
            items = items[:offerings_needed]
        else:
            flat_items = []
            for item, count in member_items.items():
                flat_items.extend([Item.from_name(item)] * count)

            if len(flat_items) == 0:
                return await ctx.send(f"You don't have enough {str(FlavorStrings.items).lower()}!")

            shuffle = True
            items = random.sample(flat_items, k=min(offerings_needed, len(flat_items)))

        offerings = defaultdict(int)
        for item in items:
            offerings[item] += 1

        not_enough = []
        for item, count in offerings.items():
            if member_items.get(item.name, 0) < count:
                not_enough.append(item)

        if not_enough:
            return await ctx.send(
                f"""You don't have enough {comma_formatted([format(item, "!e") for item in not_enough])}!"""
            )

        final_offerings = member_offerings.copy()
        empty_idxes = [i for i, item_id in enumerate(final_offerings) if item_id == EMPTY_ITEM_ID]
        for item in items:
            idx = random.choice(empty_idxes) if shuffle else empty_idxes[0]
            final_offerings[idx] = item.id
            empty_idxes.remove(idx)

        await self.bot.mongo.update_member(
            ctx.author,
            {
                "$inc": {f"{EVENT_PREFIX}_items.{item.name}": -count for item, count in offerings.items()},
                "$set": {
                    f"{EVENT_PREFIX}_ofrenda_offerings": [item_id for item_id in final_offerings],
                },
            },
        )

        embed = self.bot.Embed(
            title=f"You decorate your ofrenda with...",
            description="\n".join(f"- {count} x {item}" for item, count in offerings.items()),
        )
        embed.set_author(name=str(ctx.author), icon_url=ctx.author.display_avatar.url)
        embed.set_image(url=self.ofrenda_image_url([item_id for item_id in final_offerings]))

        # Check for completion

        member = await self.bot.mongo.fetch_member_info(ctx.author)
        member_offerings = self.get_ofrenda_offerings(member)
        offerings_needed = member_offerings.count(EMPTY_ITEM_ID)
        if not offerings_needed:
            await self.bot.mongo.update_member(
                member,
                {
                    "$set": {f"{EVENT_PREFIX}_ofrenda_offerings": []},
                    "$inc": {
                        f"{EVENT_PREFIX}_ofrendas_completed": 1,
                        f"{EVENT_PREFIX}_boxes": OFRENDA_COMPLETION_BOXES,
                    },
                },
            )

            embed.add_field(
                name=f"You have completed decorating your ofrenda with offerings!",
                value=f"You have received **{OFRENDA_COMPLETION_BOXES} {FlavorStrings.box:{'' if OFRENDA_COMPLETION_BOXES == 1 else 's'}}**!",
                inline=False,
            )

        embed.set_image(url=self.ofrenda_image_url(self.get_ofrenda_offerings(member)))

        await ctx.reply(embed=embed, mention_author=False)

    @checks.has_started()
    @dotd.command(name="open", aliases=("o",))
    async def open(
        self,
        ctx: PoketwoContext,
        qty: Optional[int] = 1,
    ):
        """Open boxes for rewards"""

        if qty <= 0:
            return await ctx.send(f"Nice try...")

        if qty > 15:
            return await ctx.send(f"You can only open up to 15 boxes at once!")

        member = await self.bot.mongo.fetch_member_info(ctx.author)
        boxes = member.day_of_the_dead_2024_boxes

        if qty > boxes:
            return await ctx.send(f"You don't have enough {FlavorStrings.box:s}!")

        await self.bot.mongo.update_member(ctx.author, {"$inc": {f"{EVENT_PREFIX}_boxes": -qty}})

        embed = self.bot.Embed(
            title=f"You open {qty} {FlavorStrings.box:{'' if qty == 1 else 's'}}...",
            description=None,
        )
        embed.set_author(name=str(ctx.author), icon_url=ctx.author.display_avatar.url)

        rewards_text = await give_rewards(self.bot, ctx.author, qty, rewards=BOX_REWARDS)
        embed.description = rewards_text

        await ctx.reply(embed=embed, mention_author=False)

    # region Quests
    @checks.has_started()
    @dotd.command(name="quests", aliases=("quest", "q"))
    async def quests(self, ctx: PoketwoContext):
        """See the active quests"""

        await self.all_quests_complete(ctx.author, ctx)
        member = await self.bot.mongo.fetch_member_info(ctx.author)
        quests = member[f"{EVENT_PREFIX}_quests"]
        if not quests:
            return await ctx.send(
                "You don't have any active quests. Catch wild pokémon to encounter pokémon in need of assistance!"
            )

        quests_metadata = member[f"{EVENT_PREFIX}_quests_metadata"]
        flavour = QUEST_FLAVOUR[quests_metadata["flavour"]]
        item = Item[quests_metadata["item"]]

        description = f"{flavour['description']}\n\n"
        for quest in quests:
            if quest.get("complete"):
                description += f"- ~~{quest['description']} ({quest['progress']}/{quest['count']})~~\n"
            else:
                description += f"- {quest['description']} ({quest['progress']}/{quest['count']})\n"

        embed = self.bot.Embed(
            title=f"{flavour['name']}'s Quests",
            description=dedent(f"""{description}"""),
        )
        embed.add_field(
            name="Rewards",
            value=f"1 x {item} *(Decoration item)*\n{SET_COMPLETION_BOXES} x {FlavorStrings.box:{'' if SET_COMPLETION_BOXES == 1 else 's'}}",
            inline=False,
        )
        embed.set_image(url=self.bot.data.asset(flavour["image"]))
        embed.set_author(name=str(ctx.author), icon_url=ctx.author.display_avatar.url)
        embed.set_footer(
            text=f"If you want, you can cancel your current set of quests using `{ctx.clean_prefix}{self.cancel.qualified_name}`"
        )

        await ctx.reply(embed=embed, mention_author=False)

    @checks.has_started()
    @dotd.command(name="cancel", aliases=("quit", "c", "x"))
    async def cancel(self, ctx: PoketwoContext):
        """Cancel current set of quests"""

        quests = await self.get_quests(ctx.author)
        if not quests:
            return await ctx.send(
                f"You don't have any active quests. Catch wild pokémon to encounter pokémon in need of assistance!"
            )

        result = await ctx.confirm("Are you sure you want to cancel your quests? This action is irreversible.")
        if result is None:
            return await ctx.send("Time's up. Aborted.")
        if result is False:
            return await ctx.send("Aborted.")

        await self.bot.mongo.update_member(ctx.author, {"$set": {f"{EVENT_PREFIX}_quests": []}})
        await ctx.send("Your quests have been removed.")

    async def on_quest_event(
        self,
        user: discord.User,
        event: str,
        to_verify: Optional[list] = None,
        *,
        count: Optional[int] = 1,
        context: Optional[PoketwoContext] = None,
    ):
        quests = await self.get_quests(user)
        if quests is None:
            return

        incs = defaultdict(lambda: 0)
        for i, q in enumerate(quests):
            if q["event"] != event or q.get("complete"):
                continue

            if not to_verify or any(self.verify_condition(q.get("condition"), x) for x in to_verify):
                inc = (
                    min((q["progress"] + count, q["count"])) - q["progress"]
                )  # So that progress doesn't go over the goal
                incs[f"{EVENT_PREFIX}_quests.{i}.progress"] += inc

        if len(incs) > 0:
            await self.bot.mongo.update_member(user, {"$inc": incs})

        await self.check_quests(user, context=context)

    # region on_catch
    @commands.Cog.listener(name="on_catch")
    async def on_catch(self, ctx: PoketwoContext, species: Species, idx: int):
        pokemon = await self.bot.mongo.fetch_pokemon(ctx.author, idx)
        await self.on_quest_event(ctx.author, "catch", [pokemon], context=ctx)

        if random.random() < QUEST_ENCOUNTER_CHANCE:
            quests = await self.get_quests(ctx.author)
            if not quests:
                chosen_flavour = self.choose_flavour()
                chosen_quests = self.make_random_quests()
                chosen_item = random.choice(list(Item))

                flavour = QUEST_FLAVOUR[chosen_flavour]
                embed = self.bot.Embed(
                    title=f"A mysterious pokémon is in need of your assistance!",
                    description=f"{flavour['name']} needs you to complete the following quests, in return for 1 x {chosen_item:b}:\n"
                    + "\n".join([f"- {q['description']}" for q in chosen_quests])
                    + f"\nWill you accept?",
                )
                embed.set_image(url=self.bot.data.asset(flavour["image"]))
                embed.set_footer(text=f"Items are used to decorate ofrendas for various rewards!")

                result = await ctx.confirm(embed=embed, cls=ConfirmationAcceptDeclineView)
                if result is None:
                    return await ctx.send("Time's up. Aborted.")
                if result is False:
                    return await ctx.send("You have declined the quest.")

                await self.bot.mongo.update_member(
                    ctx.author,
                    {
                        "$set": {
                            f"{EVENT_PREFIX}_quests": chosen_quests,
                            f"{EVENT_PREFIX}_quests_metadata": {
                                "flavour": chosen_flavour,
                                "item": chosen_item.name,
                            },
                        },
                    },
                )
                await ctx.send(
                    f"You have accepted {flavour['name']}'s request! Use `{ctx.clean_prefix}{self.quests.qualified_name}` to see your active quests."
                )

    # region on_trade
    @commands.Cog.listener()
    async def on_trade(self, trade):
        a, b = trade["users"]

        for user in (a, b):
            await self.on_quest_event(user, "trade")

    # region on_evolve
    @commands.Cog.listener()
    async def on_mass_evolve(self, user, evolved):
        await self.on_quest_event(user, "evolve", count=len(evolved))

    # region on_release
    @commands.Cog.listener()
    async def on_release(self, user, count):
        await self.on_quest_event(user, "release", count=count)

    # region on_market_buy
    @commands.Cog.listener()
    async def on_market_buy(self, buyer, pokemon):
        price = pokemon["market_data"]["price"]

        # For buyer
        await self.on_quest_event(buyer, "market_buy", count=price)

        # For seller
        seller = await self.bot.fetch_user(pokemon["owner_id"])
        await self.on_quest_event(seller, "market_sell", count=price)

    # region Debug
    @checks.is_developer()
    @dotd.group(name="debug", aliases=("dev",), invoke_without_command=True)
    async def debug(
        self,
        ctx: PoketwoContext,
    ):
        """Dev-only command for debugging purposes"""

        return await ctx.send_help(self.debug)

    @checks.is_developer()
    @debug.command(name="simulate-boxes")
    async def simulate_boxes(
        self,
        ctx: PoketwoContext,
        qty: Optional[int] = 1,
    ):
        """Dev-only command to simulate box openings"""

        embeds = []
        embed = self.bot.Embed(
            title=f"Simulating {qty:,} {FlavorStrings.box:{'' if qty == 1 else 'es'}}...",
            description=None,
        )
        embed.set_author(name=str(ctx.author), icon_url=ctx.author.display_avatar.url)

        rewards_text = simulate_rewards(self.bot, qty, rewards=BOX_REWARDS)
        embed.description = rewards_text
        embeds.append(embed)

        await ctx.reply(embeds=embeds, mention_author=False)

    @checks.is_developer()
    @debug.group(name="give", invoke_without_command=True)
    async def give(
        self,
        ctx: PoketwoContext,
    ):
        """Dev-only command to give stuff for debugging purposes"""

        return await ctx.send_help(self.give)

    @checks.is_developer()
    @give.command(name="items")
    async def give_items(
        self,
        ctx: PoketwoContext,
        user: Optional[discord.Member] = commands.Author,
        qty: Optional[int] = 1,
    ):
        """Dev-only command to give items for debugging purposes"""

        await self.bot.mongo.update_member(user, {"$inc": {f"{EVENT_PREFIX}_items.{item.name}": qty for item in Item}})
        await ctx.send(f"Gave {qty}x {FlavorStrings.items} to **{user}**.")

    @checks.is_developer()
    @give.command(name="boxes", aliases=("box",))
    async def give_boxes(
        self,
        ctx: PoketwoContext,
        user: Optional[discord.Member] = commands.Author,
        qty: Optional[int] = 1,
    ):
        """Dev-only command to give boxes for debugging purposes"""

        await self.bot.mongo.update_member(user, {"$inc": {f"{EVENT_PREFIX}_boxes": qty}})
        await ctx.send(f"Gave {qty}x {FlavorStrings.box} to **{user}**.")


async def setup(bot: commands.Bot):
    await bot.add_cog(DOTD(bot))
