import aioredis
from discord.ext import commands


class Redis(commands.Cog):
    """For redis."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.pool = None
        self.ready = False
        self._connect_task = self.bot.loop.create_task(self.connect())

    async def connect(self):
        self.pool = await aioredis.create_redis_pool(**self.bot.config.REDIS_CONF)
        self.ready = True

    async def wait_until_ready(self):
        await self._connect_task


def setup(bot):
    bot.add_cog(Redis(bot))
