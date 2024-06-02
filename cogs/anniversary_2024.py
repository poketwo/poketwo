from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from functools import cached_property
import random
import operator
from textwrap import dedent
from typing import Any, Dict, List, Optional, Tuple, TypeAlias

import discord
from discord.ext import commands
from discord.utils import get, find, format_dt

from cogs.mongo import Member
from data.models import Species
from data.utils import comma_formatted
from helpers import checks
from helpers import converters
from helpers.context import PoketwoContext
from helpers.converters import ItemAndQuantityConverter
from helpers.utils import FlavorString
from lib.box_rewards import Rarity, Reward, RewardItem, give_rewards


# BASE CLASSES


class StatusEmoji:
    pending = "<:gray:1243289159993524385>"
    in_stock = "<:yellow:1243289168445051091>"
    completed = "<:green:1243289163130867752>"


@dataclass
class BaseDifficulty:
    name: str
    ingredient_count: int
    max_stack: int
    interval: timedelta


@dataclass
class BaseIngredient:
    name: str
    emoji: str
    amount: int


@dataclass
class BaseRecipe:
    name: str
    emoji: str
    ingredients: Dict[Ingredient, int]
    connected_pokemon: Optional[AnniversaryPokemon | None] = None


@dataclass
class Progress:
    """Progress of an ingredient of an order"""

    count: int
    goal: int

    @property
    def remaining(self) -> int:
        return self.goal - self.count

    @property
    def completed(self) -> bool:
        return self.remaining == 0


@dataclass
class Order:
    """Instance of a recipe"""

    customer_name: str
    dish_name: str
    progress: Dict[str, int]  # e.g. {"FISH": 3}

    def __post_init__(self):
        self.recipe = Recipe[self.dish_name]

    def __eq__(self, other: Order) -> bool:
        return self.dish_name == (other and other.dish_name)

    @property
    def progress_dict(self) -> Dict[str, Progress]:
        """Returns a dict like {ingredient: (progress, goal)}"""

        return {
            Ingredient[ingredient_name]: Progress(progress, self.recipe.ingredients[Ingredient[ingredient_name]])
            for ingredient_name, progress in self.progress.items()
        }

    @property
    def difficulty(self) -> Difficulty:
        return self.recipe.difficulty

    @property
    def completed(self) -> bool:
        return all((progress.remaining <= 0 for progress in self.progress_dict.values()))

    def progress_text(self, *, compact: Optional[bool] = False, inventory: Optional[Dict[str, int]] = None) -> str:
        if compact:
            separator = ", "
            emoji_spec = "!e"
        else:
            separator = "\n"
            emoji_spec = ""

        progresses = []
        for ingredient, progress in self.progress_dict.items():
            if compact:
                prefix = ""
            else:
                if progress.completed:
                    status = StatusEmoji.completed
                else:
                    status = StatusEmoji.pending
                    if inventory is not None and inventory.get(ingredient.name):
                        status = StatusEmoji.in_stock

                prefix = f"{status} "

            progresses.append(f"{prefix}{ingredient:{emoji_spec}} ({progress.count}/{progress.goal})")

        return separator.join(progresses)

    def title(self) -> str:
        flavor = random.choice(TITLE_FLAVORS)
        return f"{self.customer_name} {flavor}:\n{self.recipe:b}"

    def text(self, *, inventory: Dict[str, int]) -> str:
        return f"{self.title()}\n{self.progress_text(inventory=inventory)}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "customer_name": self.customer_name,
            "dish_name": self.dish_name,
            "progress": self.progress,
        }


@dataclass
class OrderPeriod:
    from_dt: datetime
    interval: timedelta
    value: int
    elapsed: timedelta

    @property
    def next_in(self) -> timedelta:
        return self.interval - self.elapsed

    @property
    def next_at(self) -> datetime:
        return self.from_dt + self.next_in


# region ENUMS


class FlavorStrings:
    """Holds various flavor strings."""

    poke2cafe = FlavorString("Poké2Café")

    pokecoins = FlavorString("Pokécoins", "<:pokecoins:1185296751012356126>")
    event_pokemon = FlavorString("Event Pokémon")
    shards = FlavorString("Shards", "<:shards:1185296789918728263>")
    redeem = FlavorString("Redeem")
    mythical = FlavorString("Mythical Pokémon", "<:present_red:1185312798343962794>")
    ub = FlavorString("Ultra Beast", "<:present_yellow:1185312800596308048>")
    legendary = FlavorString("Legendary Pokémon", "<:present_purple:1185312796854980719>")


class AnniversaryPokemon(Enum):
    """Enum for all event pokemon for this event"""

    #! Change non_exclusives index if more exclusives are added
    VULPIX = 50168
    DOUBLADE = 50173

    # Connected Recipe Pokemon
    TANGELA = 50169
    GULPIN = 50170
    SPHEAL = 50171
    CLAMPERL = 50172
    GOOMY = 50174
    APPLIN = 50175
    FALINKS = 50176
    BELLIBOLT = 50177

    @classmethod
    def non_exclusives(cls) -> List[AnniversaryPokemon]:
        return [pokemon for pokemon in list(cls)[2:]]

    def get_species(self, bot) -> Species:
        return bot.data.species_by_number(self.value)


class Difficulty(Enum):
    """Enum for recipe difficulties based on total number of ingredients"""

    EASY = BaseDifficulty(name="Easy", ingredient_count=3, max_stack=20, interval=timedelta(minutes=30))
    HARD = BaseDifficulty(name="Hard", ingredient_count=5, max_stack=10, interval=timedelta(hours=1))

    def __init__(self, base_difficulty: BaseDifficulty) -> None:
        self.id = self.name.lower()
        self.qualified_name = base_difficulty.name
        self.ingredient_count = base_difficulty.ingredient_count
        self.max_stack = base_difficulty.max_stack
        self.interval = base_difficulty.interval

    def __str__(self) -> str:
        return self.qualified_name

    def get_period(self, dt: Optional[datetime] = None) -> OrderPeriod:
        dt = dt or datetime.now()
        period, elapsed = divmod(dt - ORDERS_START, self.interval)
        return OrderPeriod(from_dt=dt, interval=self.interval, value=period, elapsed=elapsed)

    @classmethod
    def from_name(cls, name: str) -> Difficulty:
        for difficulty in cls:
            if name.lower() in (difficulty.name.lower(), difficulty.qualified_name.lower()):
                return difficulty
        else:
            raise ValueError("Invalid difficulty name provided")

    @classmethod
    def from_ingredient_count(self, ingredient_count: int) -> Difficulty:
        return get(list(Difficulty), ingredient_count=ingredient_count)


class Ingredient(Enum):
    """Enum for all ingredients. A specific one should be used and accessed using Ingredient[name]"""

    FISH = BaseIngredient(name="Fish", emoji="🐟", amount=2)
    VEGETABLES = BaseIngredient(name="Vegetables", emoji="🥕", amount=1)
    CHOCOLATE = BaseIngredient(name="Chocolate", emoji="🍫", amount=1)
    CHEESE = BaseIngredient(name="Cheese", emoji="🧀", amount=3)
    MILK = BaseIngredient(name="Milk", emoji="🥛", amount=1)
    SALT = BaseIngredient(name="Salt", emoji="🧂", amount=3)
    FRUIT = BaseIngredient(name="Fruit", emoji="🍎", amount=1)
    WATER = BaseIngredient(name="Water", emoji="💧", amount=1)
    CREAM = BaseIngredient(name="Cream", emoji="<:cream:1242180486768496764>", amount=1)
    SUGAR = BaseIngredient(name="Sugar", emoji="<:sugar:1242180512324390942>", amount=1)
    EGG = BaseIngredient(name="Egg", emoji="🥚", amount=1)
    HERBS = BaseIngredient(name="Herbs", emoji="🌿", amount=1)
    RICE = BaseIngredient(name="Rice", emoji="🍚", amount=2)
    FLOUR = BaseIngredient(name="Flour", emoji="🌾", amount=1)
    BUTTER = BaseIngredient(name="Butter", emoji="🧈", amount=4)

    def __init__(self, base_ingredient: BaseIngredient) -> None:
        self.qualified_name = base_ingredient.name
        self.emoji = base_ingredient.emoji
        self.amount = base_ingredient.amount

    def __format__(self, format_spec: str) -> str:
        val = self.qualified_name
        emoji = self.emoji

        # Whether to not show emoji
        if "!e" not in format_spec and emoji is not None:
            val = f"{emoji} {val}"

        # Whether to bold
        if "b" in format_spec:
            val = f"**{val}**"

        return val

    def __str__(self) -> str:
        return f"{self}"

    @classmethod
    def dict(cls) -> Dict[str, Ingredient]:
        ingredients_dict = {}
        for ingredient in cls:
            ingredients_dict[ingredient.name.lower()] = ingredient
            ingredients_dict[ingredient.qualified_name.lower()] = ingredient

        return ingredients_dict


class Recipe(Enum):
    """Enum for all recipes. A specific one should be used and accessed using Recipe[name]"""

    VEGETABLE_SOUP = BaseRecipe(
        name="Vegetable Soup",
        emoji="🍲",
        ingredients={Ingredient.VEGETABLES: 3, Ingredient.WATER: 1, Ingredient.HERBS: 1},
    )
    PANCAKES = BaseRecipe(
        name="Pancakes", emoji="🥞", ingredients={Ingredient.FLOUR: 2, Ingredient.MILK: 1, Ingredient.EGG: 2}
    )
    FRUIT_SMOOTHIE = BaseRecipe(
        name="Fruit Smoothie", emoji="🍹", ingredients={Ingredient.FRUIT: 2, Ingredient.MILK: 1, Ingredient.WATER: 2}
    )
    CREAMY_TOMATO_SOUP = BaseRecipe(
        name="Creamy Tomato Soup",
        emoji="<:tomato_soup:1242180506049843211>",
        ingredients={Ingredient.CREAM: 3, Ingredient.VEGETABLES: 1, Ingredient.SALT: 1},
    )
    HERB_ROASTED_FISH = BaseRecipe(
        name="Herb Roasted Fish",
        emoji="🐟",
        ingredients={Ingredient.HERBS: 3, Ingredient.FISH: 1, Ingredient.SALT: 1},
    )
    MARGHERITA_PIZZA = BaseRecipe(
        name="Margherita Pizza",
        emoji="🍕",
        ingredients={Ingredient.FLOUR: 2, Ingredient.CHEESE: 2, Ingredient.HERBS: 1},
    )
    RASPBERRY_CHEESECAKE = BaseRecipe(
        name="Raspberry Cheesecake",
        emoji="<:raspberry_cheesecake:1242180498390913024>",
        ingredients={Ingredient.CHEESE: 2, Ingredient.FLOUR: 2, Ingredient.FRUIT: 1},
    )
    PASTA_BOLOGNESE = BaseRecipe(
        name="Pasta Bolognese",
        emoji="🍝",
        ingredients={Ingredient.FLOUR: 2, Ingredient.WATER: 2, Ingredient.SALT: 1},
        connected_pokemon=AnniversaryPokemon.TANGELA,
    )
    CREME_BRULEE = BaseRecipe(
        name="Crème Brûlée",
        emoji="🍮",
        ingredients={Ingredient.EGG: 1, Ingredient.SUGAR: 3, Ingredient.CREAM: 1},
        connected_pokemon=AnniversaryPokemon.GOOMY,
    )
    ONIGIRI = BaseRecipe(
        name="Onigiri",
        emoji="🍙",
        ingredients={Ingredient.WATER: 1, Ingredient.VEGETABLES: 1, Ingredient.RICE: 3},
        connected_pokemon=AnniversaryPokemon.BELLIBOLT,
    )
    FILLED_EGG = BaseRecipe(
        name="Filled Eggs",
        emoji="<:filledeggs:1242180502169976982>",
        ingredients={Ingredient.EGG: 3, Ingredient.HERBS: 1, Ingredient.SALT: 1},
    )
    SALAD = BaseRecipe(
        name="Salad", emoji="🥗", ingredients={Ingredient.VEGETABLES: 2, Ingredient.HERBS: 2, Ingredient.FRUIT: 1}
    )
    ICE_CREAM = BaseRecipe(
        name="Ice Cream",
        emoji="🍨",
        ingredients={Ingredient.MILK: 2, Ingredient.CREAM: 2, Ingredient.CHOCOLATE: 1},
        connected_pokemon=AnniversaryPokemon.SPHEAL,
    )
    DANGO = BaseRecipe(
        name="Dango",
        emoji="🍡",
        ingredients={Ingredient.FLOUR: 1, Ingredient.WATER: 2, Ingredient.FRUIT: 2},
        connected_pokemon=AnniversaryPokemon.FALINKS,
    )
    FRIED_FOODS = BaseRecipe(
        name="Fried Fish", emoji="🍤", ingredients={Ingredient.BUTTER: 2, Ingredient.FISH: 2, Ingredient.HERBS: 1}
    )
    STRAWBERRY_SHORTCAKE = BaseRecipe(
        name="Strawberry Shortcake",
        emoji="🍰",
        ingredients={
            Ingredient.FRUIT: 3,
            Ingredient.MILK: 2,
            Ingredient.FLOUR: 1,
            Ingredient.SUGAR: 2,
            Ingredient.EGG: 1,
        },
        connected_pokemon=AnniversaryPokemon.APPLIN,
    )
    CHOCOLATE_CHIP_COOKIES = BaseRecipe(
        name="Chocolate Chip Cookies",
        emoji="🍪",
        ingredients={
            Ingredient.FLOUR: 1,
            Ingredient.BUTTER: 1,
            Ingredient.MILK: 2,
            Ingredient.SUGAR: 2,
            Ingredient.CHOCOLATE: 3,
        },
    )
    MACARONS = BaseRecipe(
        name="Macarons",
        emoji="<:macarons:1243080663553540177>",
        ingredients={
            Ingredient.FLOUR: 2,
            Ingredient.SUGAR: 1,
            Ingredient.FRUIT: 4,
            Ingredient.CHOCOLATE: 1,
            Ingredient.CREAM: 1,
        },
        connected_pokemon=AnniversaryPokemon.CLAMPERL,
    )
    CINNAMON_ROLL = BaseRecipe(
        name="Cinnamon Roll",
        emoji="<:cinnamon_roll:1242180494683148420>",
        ingredients={
            Ingredient.FLOUR: 1,
            Ingredient.EGG: 1,
            Ingredient.SUGAR: 4,
            Ingredient.MILK: 1,
            Ingredient.CHOCOLATE: 2,
        },
    )
    SUSHI = BaseRecipe(
        name="Sushi",
        emoji="🍣",
        ingredients={
            Ingredient.WATER: 1,
            Ingredient.VEGETABLES: 2,
            Ingredient.HERBS: 1,
            Ingredient.FISH: 2,
            Ingredient.RICE: 3,
        },
        connected_pokemon=AnniversaryPokemon.GULPIN,
    )

    def __init__(self, base_recipe: BaseRecipe) -> None:
        self.qualified_name = base_recipe.name
        self.emoji = base_recipe.emoji
        self.ingredients = dict(sorted(base_recipe.ingredients.items(), key=lambda i: i[0].name))
        self.connected_pokemon = base_recipe.connected_pokemon

    def __format__(self, format_spec: str) -> str:
        val = self.qualified_name
        emoji = self.emoji

        # Whether to not show emoji
        if "!e" not in format_spec and emoji is not None:
            val = f"{emoji} {val}"

        # Whether to bold
        if "b" in format_spec:
            val = f"**{val}**"

        # Whether to show difficulty
        if "d" in format_spec:
            val += f" (**{self.difficulty}**)"

        return val

    def __str__(self) -> str:
        return f"{self}"

    @classmethod
    def dict(cls) -> Dict[str, Recipe]:
        recipes_dict = {}
        for recipe in cls:
            recipes_dict[recipe.name.lower()] = recipe
            recipes_dict[recipe.qualified_name.lower()] = recipe

        return recipes_dict

    @property
    def difficulty(self) -> Difficulty:
        return Difficulty.from_ingredient_count(len(self.ingredients))

    @property
    def rewards(self) -> List[Reward]:
        event_species_ids = (
            [self.connected_pokemon.value]
            if self.connected_pokemon
            else [pokemon.value for pokemon in AnniversaryPokemon.non_exclusives()]
        )
        return ORDER_REWARDS[self.difficulty](event_species_ids)

    @classmethod
    def difficulty_categories(cls) -> Dict[Difficulty, List[Recipe]]:
        difficulties = set([recipe.difficulty for recipe in cls])
        return {
            difficulty: [recipe for recipe in cls if recipe.difficulty == difficulty] for difficulty in difficulties
        }

    def new_order(self, customer_name: str) -> Order:
        return Order(
            customer_name=customer_name,
            dish_name=self.name,
            progress={ingredient.name: 0 for ingredient in self.ingredients},
        )

    def ingredients_text(self, *, compact: Optional[bool] = False) -> str:
        separator = ", " if compact else "\n"
        prefix = "" if compact else "- "
        emoji_spec = "!e" if compact else ""

        return separator.join(
            [f"{prefix}{goal}x {ingredient:{emoji_spec}}" for ingredient, goal in self.ingredients.items()]
        )


# region CONSTANTS
ANNIVERSARY_PREFIX = "anniversary_2024"
EMBED_COLOR = 0xF4D790

TITLE_FLAVORS = ["is craving some", "would like one serving of", "ordered one serving of"]

INGREDIENT_DROP_CHANCE = 0.50
EVENT_SHINY_BOOST = 5
DONATION_REWARDS = [
    Reward(item=RewardItem.POKECOINS, chance=0.47, amounts=range(1000, 2001)),
    Reward(
        item=RewardItem.EVENT_POKEMON,
        chance=0.28,
        amounts=[1],
        species_ids=[pokemon.value for pokemon in AnniversaryPokemon.non_exclusives()],
        shiny_boost=EVENT_SHINY_BOOST,
    ),
    Reward(item=RewardItem.SHARDS, chance=0.16, amounts=range(10, 21)),
    Reward(item=RewardItem.RARE_POKEMON, chance=0.06, amounts=[1], rarity=Rarity.ANY),
    Reward(item=RewardItem.REDEEM, chance=0.02, amounts=[1]),
    Reward(item=RewardItem.POKEMON, chance=0.01, amounts=[1], shiny_boost=4096),
]

ORDER_REWARDS = {
    Difficulty.EASY: lambda event_species_ids: [
        Reward(
            item=RewardItem.EVENT_POKEMON,
            chance=0.40,
            amounts=[1],
            species_ids=event_species_ids,
            shiny_boost=EVENT_SHINY_BOOST,
        ),
        Reward(item=RewardItem.POKECOINS, chance=0.30, amounts=range(2000, 3001)),
        Reward(item=RewardItem.SHARDS, chance=0.16, amounts=range(10, 21)),
        Reward(item=RewardItem.RARE_POKEMON, chance=0.10, amounts=[1], rarity=Rarity.ANY),
        Reward(item=RewardItem.REDEEM, chance=0.03, amounts=[1]),
        Reward(item=RewardItem.POKEMON, chance=0.01, amounts=[1], shiny_boost=4096),
    ],
    Difficulty.HARD: lambda event_species_ids: [
        Reward(
            item=RewardItem.EVENT_POKEMON,
            chance=0.40,
            amounts=[1],
            species_ids=event_species_ids,
            shiny_boost=EVENT_SHINY_BOOST,
        ),
        Reward(item=RewardItem.POKECOINS, chance=0.30, amounts=range(4000, 5001)),
        Reward(item=RewardItem.SHARDS, chance=0.16, amounts=range(25, 31)),
        Reward(item=RewardItem.RARE_POKEMON, chance=0.09, amounts=[1], rarity=Rarity.ANY),
        Reward(item=RewardItem.REDEEM, chance=0.03, amounts=range(1, 3)),
        Reward(item=RewardItem.POKEMON, chance=0.02, amounts=[1], shiny_boost=4096),
    ],
}

ORDER_MILESTONES = {
    Difficulty.EASY: (20, AnniversaryPokemon.DOUBLADE),
    Difficulty.HARD: (10, AnniversaryPokemon.VULPIX),
}
DONATION_MILESTONES = {5: AnniversaryPokemon.DOUBLADE, 10: AnniversaryPokemon.VULPIX}

ORDERS_START = datetime(2024, 5, 24, 0, 0, 0)


# region Anniversary View
class AnniversaryView(discord.ui.View):
    def __init__(self, ctx: PoketwoContext):
        self.ctx = ctx
        self.cog: Anniversary = self.ctx.bot.get_cog("Anniversary")
        super().__init__(timeout=120)

    @discord.ui.button(label="Ingredients Inventory", style=discord.ButtonStyle.blurple, row=2)
    async def inventory(self, interaction: discord.Interaction, button: discord.Button):
        await interaction.response.defer()
        await self.ctx.invoke(self.cog.event_inventory)

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


# region Select
class RecipeSelect(discord.ui.Select):
    def __init__(self, ctx: PoketwoContext, difficulty: Difficulty, recipeList: List, *args, **kwargs):
        self.ctx = ctx
        self.difficulty = difficulty
        self.recipeList = recipeList
        self.cog: Anniversary = self.ctx.bot.get_cog("Anniversary")

        placeholder = f"Accept {'an' if difficulty == Difficulty.EASY else 'a'} {difficulty.id} order"
        options = []
        for r in self.recipeList:
            recipe = Recipe[r["name"]]  # Assuming recipe is a dictionary
            connected_pokemon = recipe.connected_pokemon
            emoji = "🌟" if connected_pokemon else ""
            options.append(
                discord.SelectOption(
                    label=f"{recipe:!e} {emoji}",
                    value=f"{recipe.name}",
                    description=recipe.ingredients_text(compact=True),
                    emoji=recipe.emoji,
                )
            )

        super().__init__(options=options, placeholder=placeholder, *args, **kwargs)

    async def callback(self, interaction):
        selected_recipe = self.values[0]
        await self.cog.choose_recipe(ctx=self.ctx, recipe_name=selected_recipe)

        member = await self.ctx.bot.mongo.fetch_member_info(interaction.user)
        embed = self.view.cog.make_embed(self.ctx, member)

        # Remove select menu
        self.view.remove_item(self)
        await interaction.response.edit_message(embed=embed, view=self.view)


# region MAIN COG


def get_clock_emoji(remaining: timedelta, maximum: timedelta) -> str:
    """Progress bar but clock emojis"""

    CLOCK_EMOJIS = ["🕐", "🕑", "🕒", "🕓", "🕔", "🕕", "🕖", "🕗", "🕘", "🕙", "🕚", "🕛"]

    seconds = remaining.total_seconds()
    max_seconds = maximum.total_seconds()
    elapsed_seconds = max_seconds - seconds

    scale = elapsed_seconds / max_seconds
    clock_idx = max(int(scale * len(CLOCK_EMOJIS)), 1) - 1
    clock = CLOCK_EMOJIS[clock_idx]
    return clock


valid_ingredients = comma_formatted([f"{ingredient:b!e}" for ingredient in Ingredient])

IngredientAndQtyConverter: TypeAlias = ItemAndQuantityConverter(Ingredient.dict(), valid_ingredients)  # type: ignore


class IngredientConverter(commands.Converter):
    async def convert(self, ctx: PoketwoContext, argument: str) -> Ingredient:
        try:
            ingredient = Ingredient.dict()[argument.casefold().strip()]
        except KeyError:
            raise ValueError(f"Invalid ingredient. Valid ingredients are: {valid_ingredients}")

        return ingredient


class Anniversary(commands.Cog):
    """Anniversary 2024 event commands."""

    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        self.bot.Embed.CUSTOM_COLOR = EMBED_COLOR  # Set custom embed color for this event

    async def cog_unload(self):
        self.bot.Embed.CUSTOM_COLOR = None  # Unset custom embed color

    @cached_property
    def ingredient_weights(self) -> Tuple[List[Ingredient], List[int]]:
        ingredients = defaultdict(int)
        for r in Recipe:
            for i in r.ingredients:
                ingredients[i] += r.ingredients[i]

        return dict(ingredients)

    def weighted_random_ingredient(self) -> Ingredient:
        population, weights = list(self.ingredient_weights.keys()), list(self.ingredient_weights.values())
        ingredient = random.choices(population, weights, k=1)[0]
        return ingredient

    # region On Catch
    @commands.Cog.listener(name="on_catch")
    async def drop_ingredient(self, ctx: PoketwoContext, species: Species, _id: int):
        if random.random() < INGREDIENT_DROP_CHANCE:
            random_ingredient = self.weighted_random_ingredient()
            amount = random_ingredient.amount
            await self.bot.mongo.update_member(
                ctx.author, {"$inc": {f"{ANNIVERSARY_PREFIX}_ingredients.{random_ingredient.name}": amount}}
            )
            await ctx.send(f"You've received a new ingredient: {amount}x {random_ingredient}!")

    @commands.Cog.listener("on_command_completion")
    async def new_orders_notification(self, ctx: PoketwoContext):
        if ctx.command.cog == self:
            return

        member = await self.bot.mongo.fetch_member_info(ctx.author)
        new, first_time = await self.check_new_orders(member)

        if new:
            if first_time:
                embed = self.bot.Embed(
                    title="Happy 4th Anniversary, Pokétwo! 🎂",
                    description=dedent(
                        f"""
                        Happy 4th Anniversary, Pokétwo 🎂! It's {FlavorStrings.poke2cafe}'s grand opening, and customers are pouring in! Cook up and serve dishes to hungry customers and earn various rewards and exclusive Pokémon! 🧑‍🍳
                        - Use `{ctx.clean_prefix}{self.anniversary.qualified_name}` to learn more!"""
                    ),
                )
                return await ctx.reply(embed=embed)
            else:
                if member.anniversary_2024_notify:
                    return await ctx.reply(
                        dedent(
                            f"""
                            You have new {FlavorStrings.poke2cafe} orders available! Use `{ctx.clean_prefix}{self.anniversary.qualified_name}` to view and accept them!

                            You can turn this notification off using `{ctx.clean_prefix}{self.toggle_notification.qualified_name}`."""
                        )
                    )

    def new_customer_name(self) -> str:
        return random.choice(list(self.bot.data.all_pokemon())).name

    async def check_new_orders(self, member: Member) -> Tuple[bool, bool]:
        """Check if member has any new orders. Returns if new orders are available and if it's user's first time."""

        member_orders = member.anniversary_2024_orders

        update = defaultdict(defaultdict)
        new_orders = False
        for difficulty in Difficulty:
            current_period = difficulty.get_period().value
            order_period = member.anniversary_2024_order_periods.get(difficulty.name, 0)
            available_orders = member.anniversary_2024_available_orders.get(difficulty.name, 0)
            completed_orders = member.anniversary_2024_completed_orders.get(difficulty.name, 0)

            order = member_orders.get(difficulty.name)
            if order:
                order = Order(**order)

            is_initial_order = all((not order, completed_orders <= 0, available_orders == 0))
            period_difference = current_period - order_period
            if is_initial_order or period_difference:
                update["$inc"][f"{ANNIVERSARY_PREFIX}_order_periods.{difficulty.name}"] = period_difference

                inc = max(0, period_difference)
                if is_initial_order:  # Free order if first time
                    inc += difficulty.max_stack // 2

                inc = min(difficulty.max_stack, available_orders + inc) - available_orders
                if inc:
                    update["$inc"][f"{ANNIVERSARY_PREFIX}_available_orders.{difficulty.name}"] = inc
                    new_orders = True

        if update:
            await self.bot.mongo.update_member(member, update)

        return new_orders, is_initial_order

    async def get_active_orders(self, member: Member) -> Tuple[Member, List[Order, Order]]:
        """Return member's current incomplete orders"""

        member_orders = member.anniversary_2024_orders

        orders = []
        for difficulty in Difficulty:
            order = member_orders.get(difficulty.name)
            if order:
                order = Order(**order)

            orders.append(order)

        new_orders, _ = await self.check_new_orders(member)
        if new_orders:
            member = await self.bot.mongo.fetch_member_info(member)

        return member, orders

    async def check_completion(self, ctx: PoketwoContext):
        member: Member = await self.bot.mongo.fetch_member_info(ctx.author)
        member, active_orders = await self.get_active_orders(member)

        completed: List[Order] = []
        update = defaultdict(dict)
        for order in active_orders:
            if not order:
                continue

            if order.completed:
                diff = order.difficulty.name
                update["$set"][f"{ANNIVERSARY_PREFIX}_orders.{diff}"] = None
                update["$inc"][f"{ANNIVERSARY_PREFIX}_completed_orders.{diff}"] = 1
                completed.append(order)

        if update:
            await self.bot.mongo.update_member(ctx.author, update)
            member: Member = await self.bot.mongo.fetch_member_info(ctx.author)

            inserts = []
            for order in completed:
                embed = self.bot.Embed(
                    title=f"You've received a reward!",
                    description=None,
                )
                embed.set_author(name=str(ctx.author), icon_url=ctx.author.display_avatar.url)

                rewards_text = await give_rewards(self.bot, ctx.author, rewards=order.recipe.rewards)
                embed.description = rewards_text

                difficulty = order.difficulty
                milestone, reward = ORDER_MILESTONES[order.difficulty]
                total_completed = member.anniversary_2024_completed_orders.get(difficulty.name, 0)
                if total_completed % milestone == 0:
                    species = reward.get_species(self.bot)
                    pokemon = await self.bot.mongo.make_pokemon(member, species, shiny_boost=EVENT_SHINY_BOOST)
                    pokemon_obj = self.bot.mongo.Pokemon.build_from_mongo(pokemon)
                    inserts.append(pokemon)

                    embed.add_field(
                        name=f"This is your {total_completed}th {difficulty} order! You received:",
                        value=f"- {pokemon_obj:liPg}",
                        inline=False,
                    )

                await ctx.reply(
                    f"You've completed the order {order.recipe:b} for {order.customer_name}, good work!",
                    embed=embed,
                )

            if inserts:
                await self.bot.mongo.db.pokemon.insert_many(inserts)

    # region Generate recipe list
    async def generate_recipe_list(self, ctx: PoketwoContext, difficulty):
        guaranteed_list = [recipe for recipe in Recipe if recipe.difficulty == difficulty and recipe.connected_pokemon]
        random_list = [recipe for recipe in Recipe if recipe.difficulty == difficulty and not recipe.connected_pokemon]

        random_guaranteed_recipe = random.choice(guaranteed_list)
        random_normal_recipes = random.sample(random_list, 2)

        generated_recipes = [random_guaranteed_recipe] + random_normal_recipes

        serialized_recipes = [{"name": recipe.name} for recipe in generated_recipes]

        await self.bot.mongo.update_member(
            ctx.author,
            {"$set": {f"{ANNIVERSARY_PREFIX}_order_lists.{difficulty.name}": serialized_recipes}},
        )

        return serialized_recipes

    # region Choose recipe
    async def choose_recipe(self, ctx: PoketwoContext, recipe_name: str) -> Order:
        member = await ctx.bot.mongo.fetch_member_info(ctx.author)
        member, active_orders = await self.get_active_orders(member)

        recipe = Recipe[recipe_name]
        chosen_order = recipe.new_order(self.new_customer_name())

        existing_order = find(lambda o: getattr(o, "difficulty", None) == recipe.difficulty, active_orders)
        if existing_order:
            return await ctx.reply("You already have an order pending.", mention_author=False)

        if member.anniversary_2024_available_orders.get(chosen_order.difficulty.name) <= 0:
            return await ctx.reply("You don't have any queued orders at the moment.", mention_author=False)

        order_dict = chosen_order.to_dict()
        await self.bot.mongo.update_member(
            ctx.author,
            {
                "$set": {
                    f"{ANNIVERSARY_PREFIX}_orders.{chosen_order.difficulty.name}": order_dict,
                    f"{ANNIVERSARY_PREFIX}_order_lists.{chosen_order.difficulty.name}": [],
                },
                "$inc": {f"{ANNIVERSARY_PREFIX}_available_orders.{chosen_order.difficulty.name}": -1},
            },
        )
        return chosen_order

    # region Main command

    def make_embed(self, ctx: PoketwoContext, member: Member) -> discord.Embed:
        active_orders = [
            Order(**order) if (order := member.anniversary_2024_orders.get(difficulty.name)) else None
            for difficulty in Difficulty
        ]
        embed = self.bot.Embed(
            title=f"Welcome to {FlavorStrings.poke2cafe}!",
            description=dedent(
                f"""
                Happy Anni4sary, Pokétwo 🎂! It's {FlavorStrings.poke2cafe}'s grand opening, and customers are pouring in! Cook up and serve dishes to hungry customers and earn various rewards and exclusive Pokémon! 🧑‍🍳

                Ingredients can be obtained through catching wild Pokémon, and are used to fulfil orders. New orders will arrive regularly, and you'll be rewarded as you complete them with special rewards at certain milestones. Good luck!
                - Use `{ctx.clean_prefix}{self.use_ingredient.qualified_name} <ingredient names>...` to progress orders!
                - You can donate excess ingredients for rewards using `{ctx.clean_prefix}{self.donate_ingredients.qualified_name}`, while you wait for new orders!
                """
            ),
        )
        embed.set_author(name=str(ctx.author), icon_url=ctx.author.display_avatar.url)
        footer = []
        for difficulty in Difficulty:
            order = find(lambda o: getattr(o, "difficulty", None) == difficulty, active_orders)
            idx = member.anniversary_2024_completed_orders.get(difficulty.name, 0) + 1
            stacked = member.anniversary_2024_available_orders.get(difficulty.name, 0)

            period = difficulty.get_period()
            clock = get_clock_emoji(period.next_in, difficulty.interval)
            if order:
                value = order.text(inventory=member.anniversary_2024_ingredients)
            else:
                if stacked:
                    value = f"*New orders available, accept one using the select menu!*"
                else:
                    value = f"*No pending orders, good work! Next one {format_dt(period.next_at, 'R')} {clock}*"

            embed.add_field(
                name=f"Pending {difficulty} Order #{idx} — {stacked} queued",
                value=value,
            )

            if stacked < difficulty.max_stack:
                footer.append(f"Next {difficulty.id} order in: {clock} {converters.strfdelta(period.next_in)}")

        embed.set_footer(
            text="   —   ".join(footer) + "\nTip: Orders with 🌟 can reward a specific event pokémon as opposed to a random one!"
        )
        embed.set_image(url=self.bot.data.asset("assets/anniversary_2024/cafe.png"))

        return embed

    @checks.has_started()
    @commands.group(aliases=("anni", "event", "ev"), invoke_without_command=True, case_insensitive=True)
    async def anniversary(self, ctx: PoketwoContext):
        """Open Anniversary 2024's Poké2Cafe menu"""

        member: Member = await self.bot.mongo.fetch_member_info(ctx.author)
        member, active_orders = await self.get_active_orders(member)

        view = AnniversaryView(ctx)
        for difficulty in Difficulty:
            order = find(lambda o: getattr(o, "difficulty", None) == difficulty, active_orders)
            stacked = member.anniversary_2024_available_orders.get(difficulty.name, 0)

            # Generate random recipe list
            order_list = member.anniversary_2024_order_lists.get(difficulty.name)
            if not order_list:
                recipes = await self.generate_recipe_list(ctx, difficulty=difficulty)

            if stacked and not order:
                recipeList = order_list or recipes
                view.add_item(
                    RecipeSelect(
                        ctx,
                        difficulty=difficulty,
                        recipeList=recipeList,
                    )
                )

        embed = self.make_embed(ctx, member)
        view.message = await ctx.reply(embed=embed, view=view, mention_author=False)

    @checks.has_started()
    @anniversary.command(name="togglenotification", aliases=("notify",))
    async def toggle_notification(self, ctx: PoketwoContext):
        """Toggle new order notifications."""

        member = await self.bot.mongo.fetch_member_info(ctx.author)
        notify = member.anniversary_2024_notify

        await self.bot.mongo.update_member(ctx.author, {"$set": {f"{ANNIVERSARY_PREFIX}_notify": not notify}})
        await ctx.reply(f"Turned {'off' if notify else 'on'} notifications for new {FlavorStrings.poke2cafe} orders!")

    # region Inventory
    @checks.has_started()
    @anniversary.command(name="inventory", aliases=("inv", "i"))
    async def event_inventory(self, ctx: PoketwoContext):
        """Show all ingredients and how many in stock."""
        member: Member = await self.bot.mongo.fetch_member_info(ctx.author)
        inventory = member.anniversary_2024_ingredients

        inventory_text = dedent(
            f"""
            You will earn ingredients as you catch pokémon in the wild. Use them to cook dishes and fulfil orders for hungry customers to earn various rewards and pokémon!
            """
        )

        embed = self.bot.Embed(
            title=f"{FlavorStrings.poke2cafe} Ingredients Inventory",
            description=(inventory_text),
        )
        embed.set_author(name=str(ctx.author), icon_url=ctx.author.display_avatar.url)

        quantities = {
            ingredient: str(inventory.get(ingredient.name, 0))
            for ingredient in sorted(Ingredient, key=operator.attrgetter("name"))
        }

        name_pad = len(max(map(operator.attrgetter("name"), quantities.keys()), key=len))
        qty_pad = max(3, len(max(quantities.values(), key=len)))
        embed.add_field(
            name=f"Ingredients",
            value="\n".join(
                [
                    f"{ingredient.emoji} `{ingredient.qualified_name:<{name_pad}}` `{qty:>{qty_pad}}`"
                    for ingredient, qty in quantities.items()
                ]
            )
            + f"\n\n`{ctx.clean_prefix}{self.use_ingredient.qualified_name} {self.use_ingredient.usage}`",
            inline=False,
        )

        donated = member.anniversary_2024_donated
        embed.add_field(
            name="Donate Ingredients ☕",
            value=dedent(
                f"""
                While you are waiting for new orders, you can donate extra ingredients and get some special rewards in exchange, with exclusive pokémon at certain milestones! To do so, you need at least one of every ingredient in your inventory. You have donated a total of **{donated}** time{'' if donated == 1 else 's'} so far!

                `{ctx.clean_prefix}{self.donate_ingredients.qualified_name} [times=1]`
                """
            ),
        )

        await ctx.reply(embed=embed, mention_author=False)

    @checks.has_started()
    @anniversary.command(name="use", usage="<ingredient name> [ingredient name] ...")
    async def use_ingredient(
        self,
        ctx: PoketwoContext,
        ingredients: commands.Greedy[IngredientConverter],
    ):
        """Use ingredients to progress an order. No need to mention the order or the amount, it will automatically use as many as possible on whichever order applicable.
        E.g. `@Pokétwo anniversary use rice vegetables water`"""

        ingredients = list(set(ingredients))
        if not ingredients:
            return await ctx.send(f"Invalid or no ingredients were entered! Valid ingredients are {valid_ingredients}.")

        member: Member = await self.bot.mongo.fetch_member_info(ctx.author)
        member, active_orders = await self.get_active_orders(member)
        inventory = member.anniversary_2024_ingredients

        not_enough = [ingredient for ingredient in ingredients if inventory.get(ingredient.name, 0) <= 0]
        ingredients = [ingredient for ingredient in ingredients if ingredient not in not_enough]
        if not_enough:
            await ctx.send(f"You don't have enough {comma_formatted([f'{ing:b!e}' for ing in not_enough])}.")
            if not ingredients:
                return

        ingredient_orders = [
            order
            for order in active_orders
            if order
            and all([ing in order.recipe.ingredients and order.progress_dict[ing].remaining for ing in ingredients])
        ]
        match len(ingredient_orders):
            case 0:
                return await ctx.send(
                    f"None of your orders currently need {comma_formatted([f'{ing:!e}' for ing in ingredients])}! But you can use "
                    f"`{ctx.clean_prefix}{self.donate_ingredients.qualified_name}` to donate all your ingredients for some rewards."
                )
            case 1:
                order = ingredient_orders[0]
            case 2:
                order_idx = await ctx.select(
                    f"Which order would you like to use your {comma_formatted([f'{ing:b!e}' for ing in ingredients])} on?",
                    options=[
                        discord.SelectOption(
                            label=order.recipe.qualified_name,
                            emoji=order.recipe.emoji,
                            description=order.progress_text(compact=True),
                            value=str(i),
                        )
                        for i, order in enumerate(ingredient_orders)
                    ],
                )
                if not order_idx:
                    return await ctx.send("No order selected.")

                order = ingredient_orders[int(order_idx[0])]

                member: Member = await self.bot.mongo.fetch_member_info(ctx.author)
                member, active_orders = await self.get_active_orders(member)
                inventory = member.anniversary_2024_ingredients

        ingredient_orders = [
            order
            for order in active_orders
            if order
            and all([ing in order.recipe.ingredients and order.progress_dict[ing].remaining for ing in ingredients])
        ]
        for o in ingredient_orders:
            if order == o:
                order = o
                break
        else:
            return await ctx.send("Could not find order.")

        inc = {}
        amounts = {}
        ingredients_text = []
        not_enough = []
        for ing in ingredients:
            in_stock = inventory.get(ing.name, 0)
            progress = order.progress_dict[ing]
            qty = min(in_stock, progress.remaining)

            if qty <= 0:
                not_enough.append(ing)

            amounts[ing] = qty
            inc[f"{ANNIVERSARY_PREFIX}_ingredients.{ing.name}"] = -qty
            inc[f"{ANNIVERSARY_PREFIX}_orders.{order.difficulty.name}.progress.{ing.name}"] = qty

            ingredients_text.append(f"- {qty}x {ing} ({progress.count + qty}/{progress.goal}, {in_stock - qty} in stock)")

        if not_enough:
            return await ctx.send(
                f"You don't have enough {comma_formatted([f'{ing:b!e}' for ing in not_enough])}. Catch wild pokémon to find more!"
            )

        await self.bot.mongo.update_member(
            ctx.author,
            {"$inc": inc},
        )

        ingredients_text = "\n".join(ingredients_text)
        await ctx.send(f"You used the following ingredients on your {order.recipe:b} order!\n{ingredients_text}")
        await self.check_completion(ctx)

    @anniversary.command(name="donate")
    async def donate_ingredients(self, ctx: PoketwoContext, times: Optional[int] = 1):
        """Donate excess ingredients for rewards while waiting for new orders! Requires one of every ingredient."""

        if times <= 0:
            return await ctx.send(f"Nice try...")

        if times > 15:
            return await ctx.send(f"You can only donate a max of 15 times at a time.")

        qty = times
        member: Member = await self.bot.mongo.fetch_member_info(ctx.author)
        inventory = member.anniversary_2024_ingredients

        not_enough = []
        for ingredient in Ingredient:
            count = inventory.get(ingredient.name, 0)
            if count < qty:
                remaining = qty - count
                not_enough.append(f"{remaining}x {ingredient:b!e}")

        s = "" if times == 1 else "s"
        if not_enough:
            return await ctx.send(
                f"You need at least {qty} of every ingredient in your inventory in order to donate {times} time{s}! Currently need {comma_formatted(not_enough)}"
            )

        result = await ctx.confirm(
            f"Are you sure you want to donate **{qty}** of all ingredients in your inventory in exchange for some rewards? These ingredients could still be used in future orders! They will be deducted from your inventory and can't be undone."
        )
        if not result:
            return await ctx.send("Aborted.")

        member: Member = await self.bot.mongo.fetch_member_info(ctx.author)
        inventory = member.anniversary_2024_ingredients

        not_enough = []
        for ingredient in Ingredient:
            count = inventory.get(ingredient.name, 0)
            if count < qty:
                remaining = qty - count
                not_enough.append(f"{remaining}x {ingredient:b!e}")

        s = "" if times == 1 else "s"
        if not_enough:
            return await ctx.send(
                f"You need at least {qty} of every ingredient in your inventory in order to donate {times} time{s}! Currently need {comma_formatted(not_enough)}"
            )

        await self.bot.mongo.update_member(
            ctx.author,
            {
                "$inc": {f"{ANNIVERSARY_PREFIX}_donated": times}
                | {f"{ANNIVERSARY_PREFIX}_ingredients.{ingredient.name}": -qty for ingredient in Ingredient}
            },
        )

        embed = self.bot.Embed(
            title=f"You donate your ingredients **{times}** time{s}...",
            description=None,
        )
        embed.set_author(name=str(ctx.author), icon_url=ctx.author.display_avatar.url)

        rewards_text = await give_rewards(self.bot, ctx.author, qty, rewards=DONATION_REWARDS)
        embed.description = rewards_text

        current_donated = member.anniversary_2024_donated
        total_donated = current_donated + times
        milestone_rewards = defaultdict(list)
        inserts = []
        for i in range(current_donated + 1, total_donated + 1):
            for milestone, reward in DONATION_MILESTONES.items():
                if i % milestone == 0:
                    species = reward.get_species(self.bot)
                    pokemon = await self.bot.mongo.make_pokemon(member, species, shiny_boost=EVENT_SHINY_BOOST)
                    pokemon_obj = self.bot.mongo.Pokemon.build_from_mongo(pokemon)

                    milestone_rewards[i].append(f"- {pokemon_obj:liPg}")
                    inserts.append(pokemon)

        if inserts:
            await self.bot.mongo.db.pokemon.insert_many(inserts)

        for milestone, texts in milestone_rewards.items():
            embed.add_field(
                name=f"You reached {milestone} donations! You received:",
                value="\n".join(texts),
                inline=False,
            )

        await ctx.reply(embed=embed, mention_author=False)

    # region Debug
    @checks.is_developer()
    @anniversary.command(name="give")
    async def give_ingredient(
        self,
        ctx: PoketwoContext,
        user: Optional[discord.Member] = commands.Author,
        *,
        ingredient_and_qty: IngredientAndQtyConverter,
    ):
        """Admin-only command to give ingredients for debugging purposes"""

        ingredient, qty = ingredient_and_qty
        await self.bot.mongo.update_member(user, {"$inc": {f"{ANNIVERSARY_PREFIX}_ingredients.{ingredient.name}": qty}})
        await ctx.send(f"Given {qty}x {ingredient} to **{user}**.")

    @checks.is_developer()
    @anniversary.command(name="reset")
    async def reset_orders(
        self,
        ctx: PoketwoContext,
    ):
        """Admin-only command to refresh orders"""

        update = {"$set": {}}

        for difficulty in Difficulty:
            order = random.choice(Recipe.difficulty_categories()[difficulty]).new_order(self.new_customer_name())
            update["$set"][f"{ANNIVERSARY_PREFIX}_orders.{difficulty.name}"] = order.to_dict()

        await self.bot.mongo.update_member(
            ctx.author,
            update,
        )

        await ctx.send(f"Refreshed your orders.")


async def setup(bot: commands.Bot):
    await bot.add_cog(Anniversary(bot))
