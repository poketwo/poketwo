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

        await ctx.send(ctx._("no-event-active"))


async def setup(bot: commands.Bot):
    await bot.add_cog(NoEvent(bot))
