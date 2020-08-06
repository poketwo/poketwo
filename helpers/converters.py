from discord.ext import commands


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
            number = member.selected
        elif arg.isdigit():
            number = int(arg) - 1
        elif arg.lower() == "latest":
            number = -1
        elif not self.raise_errors:
            return None, None
        elif self.accept_blank:
            raise PokemonConversionError(
                f"Please either enter nothing for your selected pokémon, a number for a specific pokémon, or `latest` for your latest pokémon.",
                original=ValueError(),
            )
        else:
            raise PokemonConversionError(
                f"Please either enter a number for a specific pokémon, or `latest` for your latest pokémon.",
                original=ValueError(),
            )

        count = await db.fetch_pokemon_count(ctx.author)

        if number < 0:
            number = number % count

        return await db.fetch_pokemon(ctx.author, number), number
