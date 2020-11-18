from importlib import reload

from discord.ext import commands

import data


class Data(commands.Cog):
    """For game data."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        reload(data)
        self.instance = data.DataManager()


def setup(bot):
    bot.add_cog(Data(bot))
