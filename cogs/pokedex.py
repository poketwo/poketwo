from discord.ext import commands
import discord

from .helpers.models import GameData


class Pokedex(commands.Cog):
    """Pokédex-related commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(aliases=["dex"])
    async def pokedex(self, ctx: commands.Context, species: str):
        try:
            species = int(species)
            pokemon = GameData.get_pokemon(species)

            embed = discord.Embed()
            embed.title = f"#{pokemon.id} – {pokemon}"
            embed.description = pokemon.evolution_text
            embed.set_image(url=GameData.get_image_url(species))

            base_stats = (
                f"**HP:** {pokemon.base_stats.hp}",
                f"**Attack:** {pokemon.base_stats.atk}",
                f"**Defense:** {pokemon.base_stats.defn}",
                f"**Sp. Atk:** {pokemon.base_stats.satk}",
                f"**Sp. Def:** {pokemon.base_stats.sdef}",
                f"**Speed:** {pokemon.base_stats.spd}",
            )

            embed.add_field(name="Base Stats", value="\n".join(base_stats))

            await ctx.send(embed=embed)

        except ValueError:
            await ctx.send("no")
