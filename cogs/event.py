from collections import defaultdict
import itertools
from textwrap import dedent

from discord.ext import commands
from discord import Color

from helpers import checks


# For future events, add this cog to cogs/__init__.py and just change these

TITLE = "Happy Pride Month! 🏳️‍🌈"
DESCRIPTION = dedent(
    f"""
    Happy pride month! Some Pokémon wanted to express their support by showing all colours of the rainbow! 🌈

    From June 23 to June 30 you can catch the following Pokémon in the wild:
    - Pride Ampharos
    - Rainbow Minior
    - Painted Acorn Skwovet
    - Gradient Chi-Yu

    ❤️🧡💛 Happy Catching 💚💙💜
    """
)
COLORS = [Color.red(), Color.orange(), Color.yellow(), Color.green(), Color.blue(), Color.purple()]


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
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Event(bot))
