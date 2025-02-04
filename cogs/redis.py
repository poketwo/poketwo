import aioredis
from discord.ext import commands, tasks


class Redis(commands.Cog):
    """For redis."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.pool = None
        self._connect_task = self.bot.loop.create_task(self.connect())
        self.attempt_reconnect.start()

    async def connect(self):
        self.pool = await aioredis.create_redis_pool(**self.bot.config.REDIS_CONF)

    @tasks.loop(seconds=0.1, reconnect=True)
    async def attempt_reconnect(self):
        if self.pool:
            return

        await self.connect()

    @attempt_reconnect.before_loop
    async def before_attempt_reconnect(self):
        await self.bot.wait_until_ready()

    async def close(self):
        self.pool.close()
        await self.pool.wait_closed()

    async def wait_until_ready(self):
        await self._connect_task

    def cog_unload(self):
        self.attempt_reconnect.cancel()
        self.bot.loop.create_task(self.close())


async def setup(bot: commands.Bot):
    await bot.add_cog(Redis(bot))
