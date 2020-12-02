import asyncio
from importlib import reload

import discord
import uvloop
from discord.ext import commands

import cogs
import config
import helpers

DEFAULT_DISABLED_MESSAGE = (
    "The bot's currently disabled. It may be refreshing for some quick updates, or down for another reason. "
    "Try again later and check the #status channel in the official server for more details."
)


async def determine_prefix(bot, message):
    cog = bot.get_cog("Bot")
    return await cog.determine_prefix(message.guild)


def is_enabled(ctx):
    if not ctx.bot.enabled:
        raise commands.CheckFailure(
            ctx.bot.ipc.disabled_message or DEFAULT_DISABLED_MESSAGE
        )
    return True


class ClusterBot(commands.AutoShardedBot):
    class Embed(discord.Embed):
        def __init__(self, **kwargs):
            color = kwargs.pop("color", 0x9CCFFF)
            super().__init__(**kwargs, color=color)

    def __init__(self, **kwargs):
        self.pipe = kwargs.pop("pipe")
        self.cluster_name = kwargs.pop("cluster_name")
        self.cluster_idx = kwargs.pop("cluster_idx")
        self.config = config
        self.ready = False

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

        # Run bot

        self.log.info(
            f'[Cluster#{self.cluster_name}] {kwargs["shard_ids"]}, {kwargs["shard_count"]}'
        )

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
    def ipc(self):
        return self.get_cog("IPC")

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

    async def do_startup_tasks(self):
        await self.wait_until_ready()
        self.ready = True
        self.log.info(f"Logged in as {self.user}")

    async def on_ready(self):
        self.log.info(f"[Cluster#{self.cluster_name}] Ready called.")
        try:
            self.pipe.send(1)
            self.pipe.close()
        except OSError:
            pass

    async def on_shard_ready(self, shard_id):
        self.log.info(f"[Cluster#{self.cluster_name}] Shard {shard_id} ready")

    async def on_ipc_ready(self):
        self.log.info(f"[Cluster#{self.cluster_name}] IPC ready.")

    async def on_message(self, message: discord.Message):
        message.content = (
            message.content.replace("—", "--")
            .replace("'", "′")
            .replace("‘", "′")
            .replace("’", "′")
        )

        await self.process_commands(message)

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


uvloop.install()
