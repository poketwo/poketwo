from datetime import timedelta

from discord.ext import commands
from durations_nlp import Duration


class PokemonConversionError(commands.ConversionError):
    pass


class Pokemon(commands.Converter):
    def __init__(self, accept_blank=True, raise_errors=True):
        self.accept_blank = accept_blank
        self.raise_errors = raise_errors

    async def convert(self, ctx, arg):
        arg = arg.strip()

        db = ctx.bot.get_cog("Database")

        member = await db.fetch_member_info(ctx.author)

        if arg == "" and self.accept_blank:
            number = member.selected_id
        elif arg.isdigit() and arg != "0":
            number = int(arg)
        elif arg.lower() in ["latest", "l", "0"]:
            number = -1
        elif not self.raise_errors:
            return None
        elif self.accept_blank:
            raise PokemonConversionError(
                self,
                original=ValueError(
                    "Please either enter nothing for your selected pokémon, a number for a specific pokémon, or `latest` for your latest pokémon."
                ),
            )
        else:
            raise PokemonConversionError(
                self,
                original=ValueError(
                    "Please either enter a number for a specific pokémon, or `latest` for your latest pokémon."
                ),
            )

        return await db.fetch_pokemon(ctx.author, number)


class TimeDelta(commands.Converter):
    async def convert(self, ctx, arg):
        duration = Duration(arg)
        return timedelta(seconds=duration.to_seconds())
