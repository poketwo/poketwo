from discord.ext import commands
from helpers import checks


class NoEvent(commands.Cog):
    """No event."""

    def __init__(self, bot):
        self.bot = bot

    @checks.has_started()
    @commands.command()
    async def event(self, ctx):
        """No event."""

        await ctx.send("There is no event currently active.")


def setup(bot):
    bot.add_cog(NoEvent(bot))
