import asyncio
from importlib import reload

import aiohttp
import discord
import uvloop
from aioredis_lock import LockTimeoutError, RedisLock
from discord.ext import commands
from expiringdict import ExpiringDict

import cogs
import helpers

uvloop.install()

DEFAULT_DISABLED_MESSAGE = (
    "The bot's currently disabled. It may be refreshing for some quick updates, or down for another reason. "
    "Try again later and check the #status channel in the official server for more details."
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
}


async def determine_prefix(bot, message):
    cog = bot.get_cog("Bot")
    return await cog.determine_prefix(message.guild)


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

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        super().__init__(**kwargs, loop=loop, command_prefix=determine_prefix)

        # Load extensions

        self.load_extension("jishaku")
        for i in cogs.default:
            self.load_extension(f"cogs.{i}")

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

        self.activity = discord.Game("p!help • poketwo.net")
        self.http_session = aiohttp.ClientSession()

        # Run bot

        self.loop.create_task(self.do_startup_tasks())
        self.run(kwargs["token"])

    async def get_context(self, message, *, cls=helpers.context.PoketwoContext):
        return await super().get_context(message, cls=cls)

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

    @property
    def log(self):
        return self.get_cog("Logging").log

    # Other stuff

    async def send_dm(self, user, *args, **kwargs):
        if not isinstance(user, discord.abc.Snowflake):
            user = discord.Object(user)

        dm = await self.create_dm(user)
        return await dm.send(*args, **kwargs)

    async def do_startup_tasks(self):
        self.log.info(f"Starting with shards {self.shard_ids} and total {self.shard_count}")
        await self.wait_until_ready()
        self.log.info(f"Logged in as {self.user}")

    async def on_ready(self):
        self.log.info(f"Ready called.")

    async def on_shard_ready(self, shard_id):
        self.log.info(f"Shard {shard_id} ready")

    async def on_message(self, message: discord.Message):
        if message.guild and message.guild.me is None:
            message.guild._members[self.bot.user.id] = await message.guild.fetch_member(self.bot.user.id)
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
        self.log.info("shutting down")
        await super().close()

    async def reload_modules(self):
        reload(cogs)
        reload(helpers)

        for i in dir(helpers):
            if not i.startswith("_"):
                reload(getattr(helpers, i))

        for i in cogs.default:
            self.reload_extension(f"cogs.{i}")

        await self.do_startup_tasks()
