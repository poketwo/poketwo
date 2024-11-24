from collections import defaultdict
import itertools
from textwrap import dedent

from discord.ext import commands
from discord import Color

from helpers import checks


# For future events, add this cog to cogs/__init__.py and just change these

TITLE = "Sweater Weather ☕"
DESCRIPTION = dedent(
    f"""
    The days are getting colder, rain is falling and winter is coming. For a week, you are able to catch three Pokémon looking for warmth and comfort during these colder times.

    The following Pokémon will be catchable for a week:
    - Sweater Teddiursa
    - Leafy Baltoy
    - Cosy Perrserker

    Happy catching! ☕
    """
)
IMAGE_URL = ""
COLORS = [0xA7573C, 0x69763A, 0x323D55]


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

        if IMAGE_URL:
            embed.set_image(
                url=IMAGE_URL,
            )
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Event(bot))
