import discord
from discord.ext import commands

from .helpers.models import GameData, SpeciesNotFoundError


class Pokedex(commands.Cog):
    """Pokédex-related commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(aliases=["dex"])
    async def pokedex(self, ctx: commands.Context, *, search: str):
        try:
            try:
                search = int(search)
                species = GameData.species_by_number(search)
            except ValueError:
                species = GameData.species_by_name(search)
        except SpeciesNotFoundError:
            return await ctx.send(f"Could not find a pokemon matching `{search}`.")

        embed = discord.Embed()
        embed.color = 0xF44336
        embed.title = f"#{species.id} — {species}"
        embed.description = species.evolution_text
        embed.set_image(url=GameData.get_image_url(species.id))

        base_stats = (
            f"**HP:** {species.base_stats.hp}",
            f"**Attack:** {species.base_stats.atk}",
            f"**Defense:** {species.base_stats.defn}",
            f"**Sp. Atk:** {species.base_stats.satk}",
            f"**Sp. Def:** {species.base_stats.sdef}",
            f"**Speed:** {species.base_stats.spd}",
        )

        embed.add_field(name="Base Stats", value="\n".join(base_stats))

        await ctx.send(embed=embed)
