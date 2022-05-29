from importlib import reload

from discord.ext import commands

import data


class Data(commands.Cog):
    """For game data."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        reload(data)
        self.instance = data.DataManager(getattr(bot.config, "ASSETS_BASE_URL", None))


async def setup(bot: commands.Bot):
    await bot.add_cog(Data(bot))
