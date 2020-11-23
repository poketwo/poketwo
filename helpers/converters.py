from datetime import timedelta

import discord
from discord.ext import commands
from durations_nlp import Duration

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

        member = await ctx.bot.mongo.fetch_member_info(ctx.author)

        if arg == "" and self.accept_blank:
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
