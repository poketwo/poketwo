import logging
import sys

from discord.ext import commands

EXCLUDE = {
    "func",
    "sinfo",
    "getMessage",
    "args",
    "asctime",
    "created",
    "exc_info",
    "filename",
    "funcName",
    "levelno",
    "lineno",
    "message",
    "module",
    "msecs",
    "msg",
    "pathname",
    "process",
    "processName",
    "relativeCreated",
    "stack_info",
    "thread",
    "threadName",
    "extra",
}


class LogfmtFormatter(logging.Formatter):
    def format(self, record):
        attrs = {"message": record.getMessage()}
        attrs.update(
            {k: getattr(record, k) for k in dir(record) if not (k in EXCLUDE or k.startswith("_"))}
        )
        attrs.update(getattr(record, "extra", None) or {})
        return " ".join(
            '{}="{}"'.format(k, str(v).replace('"', '\\"')) if " " in str(v) else f"{k}={v}"
            for k, v in attrs.items()
            if v is not None
        )


class ClusterFilter(logging.Filter):
    def __init__(self, cluster):
        self.cluster = cluster

    def filter(self, record):
        record.cluster = self.cluster
        return True


formatter = LogfmtFormatter()


class Logging(commands.Cog):
    """For logging."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(formatter)

        log_filter = ClusterFilter(bot.cluster_name)

        dlog = logging.getLogger("discord")
        dlog.handlers = [handler]
        dlog.addFilter(log_filter)
        dlog.setLevel(logging.INFO)

        self.log = logging.getLogger("poketwo")
        self.log.handlers = [handler]
        self.log.addFilter(log_filter)
        self.log.setLevel(logging.INFO)


def setup(bot):
    bot.add_cog(Logging(bot))
