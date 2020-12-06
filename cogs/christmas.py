from discord.ext import commands
from helpers import checks


class Christmas(commands.Cog):
    """For the Christmas event"""

    def __init__(self, bot):
        self.bot = bot

    @checks.has_started()
    @commands.command()
    async def event(self, ctx):
        """Christmas Event"""
        embed = self.bot.Embed(color=0x9CCFFF)
        embed.title = f"12 Days of Christmas"
        embed.description = (
            "This event is coming soon."
        )
        await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(Christmas(bot))
