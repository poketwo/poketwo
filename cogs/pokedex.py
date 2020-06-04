import discord
from discord.ext import commands

from .helpers.models import GameData, SpeciesNotFoundError


class Pokedex(commands.Cog):
    """Pokédex-related commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @property
    def db(self):
        return self.bot.get_cog("Database")

    def balance(self, member: discord.Member):
        return self.db.fetch_member(member).balance

    def add_balance(self, member: discord.Member, amount: int):
        self.db.update_member(member, inc__balance=amount)

    def remove_balance(self, member: discord.Member, amount: int):
        self.db.update_member(member, dec__balance=amount)

    @commands.command(aliases=["balance"])
    async def bal(self, ctx: commands.Context):
        await ctx.send(f"You have {self.balance(ctx.author)} credits.")

    @commands.command(aliases=["dex"])
    async def pokedex(self, ctx: commands.Context, *, search_or_page: str = None):
        """View your pokédex, or search for a pokémon species."""

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

            member = self.db.fetch_member(ctx.author)
            embed.description = (
                f"You've caught {len(member.pokedex)} out of 809 pokémon!"
            )

            for p in range(pgstart + 1, pgend + 1):
                species = GameData.species_by_number(p)
                text = "Not caught yet! ❌"
                if str(p) in member.pokedex:
                    text = f"{member.pokedex[str(p)]} caught! ✅"
                embed.add_field(name=f"{species.name} #{species.id}", value=text)

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
