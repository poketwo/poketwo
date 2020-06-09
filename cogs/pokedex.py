import discord
from discord.ext import commands

from .helpers.models import GameData, SpeciesNotFoundError
from .helpers import checks


class Pokedex(commands.Cog):
    """Pokédex-related commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @property
    def db(self):
        return self.bot.get_cog("Database")

    @checks.has_started()
    @commands.command(aliases=["dex"])
    async def pokedex(self, ctx: commands.Context, *, search_or_page: str = None):
        """View your pokédex, or search for a pokémon species."""

        member = await self.db.fetch_member(ctx.author)

        if search_or_page is None:
            search_or_page = "1"

        if search_or_page.isdigit():
            pgstart = (int(search_or_page) - 1) * 20

            if pgstart >= 809 or pgstart < 0:
                return await ctx.send("There are no pokémon on this page.")

            pgend = min(int(search_or_page) * 20, 809)

            # Send embed

            embed = discord.Embed()
            embed.color = 0xF44336
            embed.title = f"Your pokédex"
            embed.set_footer(text=f"Showing {pgstart + 1}–{pgend} out of 809.")

            embed.description = (
                f"You've caught {len(member.pokedex)} out of 809 pokémon!"
            )

            for p in range(pgstart + 1, pgend + 1):
                species = GameData.species_by_number(p)
                text = "Not caught yet! ❌"
                if str(species.dex_number) in member.pokedex:
                    text = f"{member.pokedex[str(species.dex_number)]} caught! ✅"
                embed.add_field(name=f"{species.name} #{species.id}", value=text)

            embed.add_field(name="‎", value="‎")

            await ctx.send(embed=embed)

        else:
            try:
                species = GameData.species_by_name(search_or_page)
            except SpeciesNotFoundError:
                return await ctx.send(
                    f"Could not find a pokemon matching `{search_or_page}`."
                )

            embed = discord.Embed()
            embed.color = 0xF44336
            embed.title = f"#{species.dex_number} — {species}"
            embed.description = species.evolution_text
            embed.set_image(url=species.image_url)

            base_stats = (
                f"**HP:** {species.base_stats.hp}",
                f"**Attack:** {species.base_stats.atk}",
                f"**Defense:** {species.base_stats.defn}",
                f"**Sp. Atk:** {species.base_stats.satk}",
                f"**Sp. Def:** {species.base_stats.sdef}",
                f"**Speed:** {species.base_stats.spd}",
            )

            embed.add_field(
                name="Names",
                value="\n".join(f"{x} {y}" for x, y in species.names),
                inline=False,
            )
            embed.add_field(name="Base Stats", value="\n".join(base_stats))
            embed.add_field(
                name="Appearance",
                value=f"Height: {species.height} m\nWeight: {species.weight} kg",
            )
            embed.add_field(name="Types", value="\n".join(species.types))

            text = "You haven't caught this pokémon yet!"
            if str(species.dex_number) in member.pokedex:
                text = f"You've caught {member.pokedex[str(species.dex_number)]} of this pokémon!"

            embed.set_footer(text=text)

            await ctx.send(embed=embed)
