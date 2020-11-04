import logging

from discord.ext import commands

formatter = logging.Formatter("%(asctime)s:%(levelname)s:%(name)s: %(message)s")


class Logging(commands.Cog):
    """For logging."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

        self.log = logging.getLogger(f"Cluster#{self.bot.cluster_name}")
        handler = logging.FileHandler(f"logs/commands-{self.bot.cluster_name}.log")
        handler.setFormatter(formatter)
        self.log.handlers = [handler]

        dlog = logging.getLogger("discord")
        dhandler = logging.FileHandler(f"logs/discord-{self.bot.cluster_name}.log")
        dhandler.setFormatter(formatter)
        dlog.handlers = [dhandler]

        self.log.setLevel(logging.DEBUG)
        dlog.setLevel(logging.INFO)


def setup(bot):
    bot.add_cog(Logging(bot))
