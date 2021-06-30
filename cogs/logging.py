import logging
import numbers
import sys
from pathlib import Path

import aiologger
import aiologger.filters
import aiologger.records
from aiologger import Logger
from discord.ext import commands


EXCLUDE = {
    "func",
    "sinfo",
    "getMessage",
    "get_message",
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
        attrs = {"message": (getattr(record, "getMessage", None) or record.get_message)()}
        attrs.update(
            {k: getattr(record, k) for k in dir(record) if not (k in EXCLUDE or k.startswith("_"))}
        )
        attrs.update(getattr(record, "extra", None) or {})
        return " ".join(
            '{}="{}"'.format(k, str(v).replace('"', '\\"')) if " " in str(v) else f"{k}={v}"
            for k, v in attrs.items()
            if v is not None
        )


class ClusterFilter(logging.Filter, aiologger.filters.Filter):
    def __init__(self, cluster):
        self.cluster = cluster

    def filter(self, record):
        record.cluster = self.cluster
        return True


class ExtendedLogger(Logger):
    def _log(
        self,
        level,
        msg,
        args,
        exc_info=None,
        extra=None,
        stack_info=False,
        caller=None,
    ):

        sinfo = None
        if aiologger.logger._srcfile and caller is None:
            try:
                fn, lno, func, sinfo = self.find_caller(stack_info)
            except ValueError:
                fn, lno, func = "(unknown file)", 0, "(unknown function)"
        elif caller:
            fn, lno, func, sinfo = caller
        else:
            fn, lno, func = "(unknown file)", 0, "(unknown function)"
        if exc_info and isinstance(exc_info, BaseException):
            exc_info = (type(exc_info), exc_info, exc_info.__traceback__)

        record = aiologger.records.LogRecord(
            name=self.name,
            level=level,
            pathname=fn,
            lineno=lno,
            msg=msg,
            args=args,
            exc_info=exc_info,
            func=func,
            sinfo=sinfo,
            extra=extra,
        )
        record.extra = extra
        return aiologger.logger.create_task(self.handle(record))


formatter = LogfmtFormatter()


class Logging(commands.Cog):
    """For logging."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(formatter)
        handler.setLevel(logging.INFO)

        log_filter = ClusterFilter(bot.cluster_name)

        dlog = logging.getLogger("discord")
        dlog.handlers = [handler]
        dlog.addFilter(log_filter)

        self.log = ExtendedLogger.with_default_handlers(name="poketwo", formatter=formatter)
        self.log.add_filter(log_filter)


def setup(bot):
    bot.add_cog(Logging(bot))
