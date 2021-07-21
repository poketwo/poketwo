import asyncio
from importlib import reload
import aiohttp

import discord
import uvloop
from aioredis_lock import RedisLock
from discord.ext import commands
from expiringdict import ExpiringDict

import cogs
import helpers

uvloop.install()

DEFAULT_DISABLED_MESSAGE = (
    "The bot's currently disabled. It may be refreshing for some quick updates, or down for another reason. "
    "Try again later and check the #status channel in the official server for more details."
)


async def determine_prefix(bot, message):
    cog = bot.get_cog("Bot")
    return await cog.determine_prefix(message.guild)


def is_enabled(ctx):
    if not ctx.bot.enabled:
        raise commands.CheckFailure(DEFAULT_DISABLED_MESSAGE)
    return True


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

        self.ready = False
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
        self.add_check(is_enabled)

        self.activity = discord.Game("p!help • poketwo.net")
        self.http_session = aiohttp.ClientSession()

        # Run bot

        self.loop.create_task(self.do_startup_tasks())
        self.run(kwargs["token"])

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

    @property
    def enabled(self):
        for cog in self.cogs.values():
            try:
                if not cog.ready:
                    return False
            except AttributeError:
                pass
        return self.ready

    # Other stuff

    async def send_dm(self, user, *args, **kwargs):
        # This code can wait until Messageable + Object comes out.
        # user_data = await self.mongo.fetch_member_info(discord.Object(uid))
        # if (priv := user_data.private_message_id) is None:
        #     priv = await self.http.start_private_message(uid)
        #     priv = int(priv["id"])
        #     self.loop.create_task(
        #         self.mongo.update_member(uid, {"$set": {"private_message_id": priv}})
        #     )

        if not isinstance(user, discord.abc.Snowflake):
            user = discord.Object(user)

        dm = await self.create_dm(user)
        return await dm.send(*args, **kwargs)

    async def do_startup_tasks(self):
        self.log.info(f"Starting with shards {self.shard_ids} and total {self.shard_count}")

        await self.wait_until_ready()
        self.ready = True
        self.log.info(f"Logged in as {self.user}")

    async def on_ready(self):
        self.log.info(f"Ready called.")

    async def on_shard_ready(self, shard_id):
        self.log.info(f"Shard {shard_id} ready")

    async def on_message(self, message: discord.Message):
        message.content = (
            message.content.replace("—", "--").replace("'", "′").replace("‘", "′").replace("’", "′")
        )

        await self.process_commands(message)

    async def before_identify_hook(self, shard_id, *, initial=False):
        async with RedisLock(self.redis, f"identify:{shard_id % 16}", 5, None):
            await asyncio.sleep(5)

    async def close(self):
        self.log.info("shutting down")
        await super().close()

    async def reload_modules(self):
        self.ready = False

        reload(cogs)
        reload(helpers)

        for i in dir(helpers):
            if not i.startswith("_"):
                reload(getattr(helpers, i))

        for i in cogs.default:
            self.reload_extension(f"cogs.{i}")

        await self.do_startup_tasks()
