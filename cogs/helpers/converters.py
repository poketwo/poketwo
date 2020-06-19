from discord.ext import commands


class PokemonConversionError(commands.CommandError):
    pass


class Pokemon(commands.Converter):
    def __init__(self, accept_blank=True):
        self.accept_blank = accept_blank

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
        elif self.accept_blank:
            raise PokemonConversionError(
                f"Please either enter nothing for your selected pokémon, a number for a specific pokémon, or `latest` for your latest pokémon."
            )
        else:
            raise PokemonConversionError(
                f"Please either enter a number for a specific pokémon, or `latest` for your latest pokémon."
            )

        count = await db.fetch_pokemon_count(ctx.author)
        number = number % count

        return await db.fetch_pokemon(ctx.author, number), number
