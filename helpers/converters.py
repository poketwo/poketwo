from datetime import timedelta
import re
from typing import Dict, Optional

import discord
from discord.ext import commands
from durations_nlp import Duration

from data.utils import comma_formatted, isnumber

from .context import PoketwoContext
from .utils import FakeUser


class FetchUserConverter(commands.Converter):
    async def convert(self, ctx, arg):
        try:
            return await commands.UserConverter().convert(ctx, arg)
        except commands.UserNotFound:
            pass

        try:
            return await ctx.bot.fetch_user(int(arg))
        except (discord.NotFound, discord.HTTPException, ValueError):
            raise commands.UserNotFound(arg)


class MemberOrIdConverter(commands.Converter):
    async def convert(self, ctx, arg):
        try:
            return await commands.MemberConverter().convert(ctx, arg)
        except commands.MemberNotFound:
            pass

        try:
            return FakeUser(int(arg))
        except ValueError:
            raise commands.MemberNotFound(arg)


class PokemonConverter(commands.Converter):
    def __init__(self, accept_blank=True, raise_errors=True):
        self.accept_blank = accept_blank
        self.raise_errors = raise_errors

    async def convert(self, ctx, arg):
        arg = arg.strip()

        if arg == "" and self.accept_blank:
            member = await ctx.bot.mongo.fetch_member_info(ctx.author)
            number = member.selected_id
        elif arg.isdigit() and arg != "0":
            number = int(arg)
        elif arg.lower() in ["latest", "l", "0"]:
            number = -1
        elif not self.raise_errors:
            return None
        elif self.accept_blank:
            raise commands.BadArgument(
                "Please either enter nothing for your selected pokémon, a number for a specific pokémon, or `latest` for your latest pokémon."
            )
        else:
            raise commands.BadArgument(
                "Please either enter a number for a specific pokémon, or `latest` for your latest pokémon."
            )

        return await ctx.bot.mongo.fetch_pokemon(ctx.author, number)


class GreedyPokemonConverter(commands.Converter):
    def __init__(self, *, include_none: Optional[bool] = False):
        self.include_none = include_none

    async def convert(self, ctx: PoketwoContext, argument: str):
        args = []
        for arg in re.split("\s+", argument.strip()):
            arg = arg.strip()
            if arg not in args:
                args.append(arg)

        converter = PokemonConverter()
        pokemon = []
        for arg in args:
            p = await converter.convert(ctx, arg)
            if p is None and not self.include_none:
                continue

            if p is not None and p in pokemon:
                continue

            pokemon.append(p)

        return pokemon


class ItemAndQuantityConverter(commands.Converter):  # TODO: Try validation
    def __init__(self, item_dict: Optional[Dict[str, str]] = None, valid_items_string: Optional[str] = None):
        self.item_dict = item_dict
        self.valid_items_string = valid_items_string

    async def convert(self, ctx: PoketwoContext, item_and_qty: str):
        # Greedily consume the arg until the last one for
        # item and make the last one quantity if it's a digit
        if len(split := item_and_qty.split()) > 1 and isnumber(split[-1]):
            item = " ".join(split[:-1])
            qty = int(split[-1])
        else:
            item = item_and_qty
            qty = 1

        if self.item_dict:
            try:
                item = self.item_dict[item.casefold().strip()]
            except KeyError:
                raise ValueError(
                    f"Invalid item. Valid items are: {self.valid_items_string}"
                )

        return item, qty


def to_timedelta(arg):
    duration = Duration(arg)
    return timedelta(seconds=duration.to_seconds())


class TimeDelta(commands.Converter):
    async def convert(self, ctx, arg):
        return to_timedelta(arg)


PERIODS = (
    ("year", "y", 60 * 60 * 24 * 365),
    ("month", "M", 60 * 60 * 24 * 30),
    ("day", "d", 60 * 60 * 24),
    ("hour", "h", 60 * 60),
    ("minute", "m", 60),
    ("second", "s", 1),
)


def strfdelta(duration, long=False, max_len=None):
    seconds = int(duration.total_seconds())
    strings = []
    for period_name, period_short, period_seconds in PERIODS:
        if seconds >= period_seconds:
            period_value, seconds = divmod(seconds, period_seconds)
            if long:
                has_s = "s" if period_value > 1 else ""
                strings.append(f"{period_value} {period_name}{has_s}")
            else:
                strings.append(f"{period_value}{period_short}")
        if max_len is not None and len(strings) >= max_len:
            break

    if len(strings) == 0:
        strings.append("now")

    return " ".join(strings)


class EnumConverter(commands.Converter):
    """Converter to convert string to an enum from the given enum class. The enum class must have the from_name method implemented."""

    def __init__(self, enum_class):
        self.enum_class = enum_class

    async def convert(self, ctx: PoketwoContext, argument: str):
        return self.enum_class.from_name(argument)


class GreedyEnumConverter(commands.Converter):
    """Greedy converter to convert strings to enum from the given enum class. The enum class must have the from_name method implemented.
    This converter takes into account enums with names with spaces in them, unlike commands.Greedy."""

    def __init__(self, enum_class):
        self.enum_class = enum_class

    async def convert(self, ctx: PoketwoContext, argument: str):
        words = argument.split()

        items = []
        start = 0
        end = 1
        while start < len(words):
            name = " ".join(words[start:end])
            item = self.enum_class.from_name(name, raise_error=False)
            if item:
                items.append(item)
                start = end
                end += 1
            else:
                if end >= len(words):
                    start += 1
                    end = start + 1
                else:
                    end += 1

        if not items:
            raise commands.UserInputError(
                f"Invalid {self.enum_class.__name__}(s). Valid {self.enum_class.__name__}s are: {comma_formatted([f'{e:b!e}' for e in self.enum_class])}"
            )

        return items