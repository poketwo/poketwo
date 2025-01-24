from collections import defaultdict
import itertools
from textwrap import dedent

from discord.ext import commands
from discord import Color

from helpers import checks


# For future events, add this cog to cogs/__init__.py and just change these

TITLE = "Lunar New Year 🏮"
DESCRIPTION = dedent(
    f"""
    It is the Lunar New Year, and some Pokémon have joined the festive celebrations for 2025, the Year of the Wood Snake, and the mark of new beginnings!

    The following Pokémon will be catchable for a week:
    - Wooden Serperior
    - Paper Lantern Lampent
    - Dragon Dancer Litleo

    Happy Lunar New Year, and happy catching! 🧧
    """
)
EMBED_IMAGE_URL = "https://cdn.discordapp.com/attachments/1122578987919605870/1332491925097283624/Lunar_2025_server_banner.png?ex=6795734f&is=679421cf&hm=4dec5f9e1959bbd7d3b0b627c1228ea1884cfdc81a465a8b7a3f8d318913b09b&"
COLORS = [0xDB662D, 0xF2A32D]


class Event(commands.Cog):
    """Cog for simple events that don't have special mechanics and don't need a dedicated cog"""

    def __init__(self, bot):
        self.bot = bot
        self.colors = defaultdict(lambda: itertools.cycle(COLORS))

    @checks.has_started()
    @commands.command(aliases=("ev",))
    async def event(self, ctx):
        """Command to show any currently running event, if any."""

        embed = self.bot.Embed(
            title=TITLE,
            description=DESCRIPTION,
            color=next(self.colors[ctx.author.id]),
        )

        if EMBED_IMAGE_URL:
            embed.set_image(
                url=EMBED_IMAGE_URL,
            )
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Event(bot))
