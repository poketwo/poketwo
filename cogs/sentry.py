import sentry_sdk
from discord.ext import commands


class Sentry(commands.Cog):
    """For sentry."""

    def __init__(self, bot):
        self.bot = bot
        sentry_sdk.init(bot.config.SENTRY_URL, traces_sample_rate=1.0)
    
    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        sentry_sdk.capture_exception(error)

    @commands.Cog.listener()
    async def on_error(self, error):
        sentry_sdk.capture_exception(error)


def setup(bot):
    bot.add_cog(Sentry(bot))
