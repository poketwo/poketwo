from pathlib import Path
import logging
import sys

from discord.ext import commands

formatter = logging.Formatter("%(asctime)s:%(levelname)s:%(name)s: %(message)s")


class Logging(commands.Cog):
    """For logging."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

        Path("logs").mkdir(exist_ok=True)

        self.log = logging.getLogger(f"Cluster#{self.bot.cluster_name}")
        handler = logging.FileHandler(f"logs/commands-{self.bot.cluster_name}.log")
        handler.setFormatter(formatter)
        self.log.handlers = [handler]

        dlog = logging.getLogger("discord")
        dhandler = logging.StreamHandler(sys.stdout)
        dhandler.setFormatter(formatter)
        dlog.handlers = [dhandler]

        httplog = logging.getLogger("discord.http")

        self.log.setLevel(logging.INFO)
        dlog.setLevel(logging.INFO)
        httplog.setLevel(logging.DEBUG)


def setup(bot):
    bot.add_cog(Logging(bot))
