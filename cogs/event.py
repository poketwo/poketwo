from collections import defaultdict
import itertools
from textwrap import dedent

from discord.ext import commands
from discord import Color

from helpers import checks


# For future events, add this cog to cogs/__init__.py and just change these

TITLE = "Catching Fairies 🦋"
DESCRIPTION = dedent(
    f"""
    When Autumn comes and the leaves turn red, yellow and brown, the world looks magical. This is also the time that various fairies are seen, preparing for the Winter to come.
    During this week, you will be able to catch three fairies before they hide until Spring!

    The following Fairy Pokémon have been sighted in the wild:
    - 🌙 **Moon Fairy Mudkip**
    - 🥀 **Flower Fairy Flabébé**
    - 🔥 **Fire Fairy Salandit**

    Happy catching! 🦋
    """
)
COLORS = [0xEED25D, 0x4B4069]


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
        embed.set_image(
            url="https://cdn.discordapp.com/attachments/1122578987919605870/1287367322197295146/IMG_5333.png"
        )
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Event(bot))
