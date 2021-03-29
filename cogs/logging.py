from pathlib import Path
import logging
import sys

from discord.ext import commands

formatter = logging.Formatter("%(asctime)s:%(levelname)s:%(name)s: %(message)s")


class Logging(commands.Cog):
    """For logging."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(formatter)

        self.log = logging.getLogger(f"Cluster#{self.bot.cluster_name}")
        self.log.handlers = [handler]
        self.log.setLevel(logging.INFO)

        dlog = logging.getLogger("discord")
        dlog.handlers = [handler]
        dlog.setLevel(logging.INFO)


def setup(bot):
    bot.add_cog(Logging(bot))
