import discord
from discord.ext import commands

from .helpers.models import GameData, SpeciesNotFoundError
from .helpers import checks
from .helpers.pagination import Paginator
from .helpers.constants import *

from .database import Database


class Pokedex(commands.Cog):
    """Pokédex-related commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @property
    def db(self) -> Database:
        return self.bot.get_cog("Database")

    @checks.has_started()
    @commands.command(aliases=["dex"])
    async def pokedex(self, ctx: commands.Context, *, search_or_page: str = None):
        """View your pokédex, or search for a pokémon species."""

        if search_or_page is None:
            search_or_page = "1"

        if search_or_page.isdigit():
            pgstart = (int(search_or_page) - 1) * 20

            if pgstart >= 809 or pgstart < 0:
                return await ctx.send("There are no pokémon on this page.")

            num = await self.db.fetch_pokedex_count(ctx.author)
            num = num[0]["count"]

            async def get_page(pidx, clear):
                pgstart = (pidx) * 20
                pgend = min(pgstart + 20, 809)

                member = await self.db.fetch_pokedex(ctx.author, pgstart + 1, pgend + 1)

                # Send embed

                embed = discord.Embed()
                embed.color = 0xF44336
                embed.title = f"Your pokédex"
                embed.description = f"You've caught {num} out of 809 pokémon!"
                embed.set_footer(text=f"Showing {pgstart + 1}–{pgend} out of 809.")

                # embed.description = (
                #     f"You've caught {len(member.pokedex)} out of 809 pokémon!"
                # )

                for p in range(pgstart + 1, pgend + 1):
                    species = GameData.species_by_number(p)

                    text = f"{EMOJIS.cross} Not caught yet!"

                    if str(species.dex_number) in member.pokedex:
                        text = f"{EMOJIS.check} {member.pokedex[str(species.dex_number)]} caught!"

                    emoji = str(EMOJIS[p]).replace("pokemon_sprite_", "")

                    embed.add_field(
                        name=f"{emoji} {species.name} #{species.id}", value=text
                    )

                if pgend != 809:
                    embed.add_field(name="‎", value="‎")

                return embed

            paginator = Paginator(get_page, num_pages=41)
            await paginator.send(self.bot, ctx, int(search_or_page) - 1)

        else:
            try:
                species = GameData.species_by_name(search_or_page)
            except SpeciesNotFoundError:
                return await ctx.send(
                    f"Could not find a pokemon matching `{search_or_page}`."
                )

            member = await self.db.fetch_pokedex(
                ctx.author, species.dex_number, species.dex_number + 1
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
