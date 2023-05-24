import logging

import aiohttp
import discord
import structlog
import uvloop
from aioredis_lock import LockTimeoutError, RedisLock
from discord.ext import commands
from expiringdict import ExpiringDict
from pythonjsonlogger import jsonlogger

import cogs
import helpers
from helpers import checks

uvloop.install()

DEFAULT_DISABLED_MESSAGE = (
    "The bot's currently disabled. It may be refreshing for some quick updates, or down for another reason. "
    "Try again later and check the #bot-outages channel in the official server for more details."
)

CONCURRENCY_LIMITED_COMMANDS = {
    "auction",
    "market",
    "evolve",
    "favorite",
    "favoriteall",
    "nickall",
    "nickname",
    "reindex",
    "release",
    "releaseall",
    "select",
    "unfavorite",
    "unfavoriteall",
    "unmega",
    "buy",
    "dropitem",
    "embedcolor",
    "moveitem",
    "open",
    "redeemspawn",
    "trade",
    "learn",
    "halloween",
    "valentine",
    "spring",
    "pride",
}


async def determine_prefix(bot, message):
    return [f"<@{bot.user.id}>", f"<@!{bot.user.id}>"]


class ClusterBot(commands.AutoShardedBot):
    class BlueEmbed(discord.Embed):
        def __init__(self, **kwargs):
            color = kwargs.pop("color", helpers.constants.BLUE)
            super().__init__(**kwargs, color=color)

    class Embed(discord.Embed):
        def __init__(self, **kwargs):
            color = kwargs.pop("color", helpers.constants.PINK)
            super().__init__(**kwargs, color=color)

    def __init__(self, **kwargs):
        self.cluster_name = kwargs.pop("cluster_name")
        self.cluster_idx = kwargs.pop("cluster_idx")
        self.config = kwargs.pop("config", None)
        if self.config is None:
            self.config = __import__("config")

        self.menus = ExpiringDict(max_len=300, max_age_seconds=300)

        super().__init__(**kwargs, command_prefix=determine_prefix, strip_after_prefix=True)

        # Load extensions

        self.add_check(
            commands.bot_has_permissions(
                read_messages=True,
                send_messages=True,
                embed_links=True,
                attach_files=True,
                read_message_history=True,
                add_reactions=True,
                external_emojis=True,
            ).predicate
        )

        self.add_check(checks.general_check().predicate)

        self.activity = discord.Game("@Pokétwo help • poketwo.net")

        # Run bot

        self.setup_logging()
        self.run(kwargs["token"], log_handler=None)

    def setup_logging(self):
        self.log: structlog.BoundLogger = structlog.get_logger()

        def add_cluster_name(logger, name, event_dict):
            event_dict["cluster"] = self.cluster_name
            return event_dict

        timestamper = structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S")
        shared_processors = [structlog.stdlib.add_log_level, timestamper, add_cluster_name]

        structlog.configure(
            processors=[
                *shared_processors,
                structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
            ],
            logger_factory=structlog.stdlib.LoggerFactory(),
            cache_logger_on_first_use=True,
        )

        formatter = structlog.stdlib.ProcessorFormatter(
            # These run ONLY on `logging` entries that do NOT originate within
            # structlog.
            foreign_pre_chain=shared_processors,
            # These run on ALL entries after the pre_chain is done.
            processors=[
                # Remove _record & _from_structlog.
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                structlog.dev.ConsoleRenderer() if self.config.DEBUG else structlog.processors.JSONRenderer(),
            ],
        )

        handler = logging.StreamHandler()
        handler.setFormatter(formatter)
        root_logger = logging.getLogger()
        root_logger.addHandler(handler)
        root_logger.setLevel(logging.INFO)

    async def get_context(self, message, *, cls=helpers.context.PoketwoContext):
        return await super().get_context(message, cls=cls)

    async def is_owner(self, user):
        if isinstance(user, discord.Member):
            if any(x.id in (718006431231508481, 930346842586218607) for x in user.roles):
                return True
        return await super().is_owner(user)

    # Easy access to things

    @property
    def mongo(self):
        return self.get_cog("Mongo")

    @property
    def redis(self):
        return self.get_cog("Redis").pool

    @property
    def data(self):
        return self.get_cog("Data").instance

    @property
    def sprites(self):
        return self.get_cog("Sprites")

    # Other stuff

    async def send_dm(self, user, *args, **kwargs):
        if not isinstance(user, discord.abc.Snowflake):
            user = discord.Object(user)

        dm = await self.create_dm(user)
        return await dm.send(*args, **kwargs)

    async def setup_hook(self):
        self.http_session = aiohttp.ClientSession()
        await self.load_extension("jishaku")
        for i in cogs.default:
            await self.load_extension(f"cogs.{i}")
        self.log.info(f"init", shard_ids=self.shard_ids, shard_count=self.shard_count)

    async def on_ready(self):
        self.log.info("ready")

    async def on_shard_ready(self, shard_id):
        self.log.info("shard_ready", shard_id=shard_id)

    async def on_message(self, message: discord.Message):
        message.content = message.content.replace("—", "--").replace("'", "′").replace("‘", "′").replace("’", "′")
        await self.process_commands(message)

    async def invoke(self, ctx):
        if ctx.command is None:
            return

        if not (
            ctx.command.name in CONCURRENCY_LIMITED_COMMANDS
            or (ctx.command.root_parent and ctx.command.root_parent.name in CONCURRENCY_LIMITED_COMMANDS)
        ):
            return await super().invoke(ctx)

        try:
            async with RedisLock(self.redis, f"command:{ctx.author.id}", 60, 1):
                return await super().invoke(ctx)
        except LockTimeoutError:
            await ctx.reply("You are currently running another command. Please wait and try again later.")

    async def close(self):
        self.log.info("close")
        await super().close()
