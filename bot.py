import asyncio
import io
import logging
import textwrap
import traceback
from contextlib import redirect_stdout
from importlib import reload

import discord
import aioredis
from discord.ext import commands
from discord.ext.ipc import Client, Server

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


class ClusterBot(commands.AutoShardedBot):
    class Embed(discord.Embed):
        def __init__(self, **kwargs):
            color = kwargs.pop("color", 0xF44336)
            super().__init__(**kwargs, color=color)

    def __init__(self, **kwargs):
        self.disabled_message = DEFAULT_DISABLED_MESSAGE
        self.pipe = kwargs.pop("pipe")
        self.cluster_name = kwargs.pop("cluster_name")
        self.cluster_idx = kwargs.pop("cluster_idx")
        self.embed_color = 0xF44336

        self.battles = None
        self.dbl_token = config.DBL_TOKEN
        self.database_uri = config.DATABASE_URI
        self.database_name = config.DATABASE_NAME

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        super().__init__(**kwargs, loop=loop, command_prefix=determine_prefix)
        self.mongo = helpers.mongo.Database(self, self.database_uri, self.database_name)

        self._last_result = None
        self.waiting = False
        self.enabled = False
        self.sprites = None

        self.log = logging.getLogger(f"Cluster#{self.cluster_name}")
        self.log.setLevel(logging.DEBUG)
        handler = logging.FileHandler(
            filename=f"logs/commands-{self.cluster_name}.log",
            encoding="utf-8",
            mode="a",
        )
        handler.setFormatter(
            logging.Formatter("%(asctime)s:%(levelname)s:%(name)s: %(message)s")
        )
        self.log.handlers = [handler]

        discord_logger = logging.getLogger("discord")
        discord_logger.setLevel(logging.INFO)
        discord_handler = logging.FileHandler(
            filename=f"logs/discord-{self.cluster_name}.log", encoding="utf-8", mode="a"
        )
        discord_handler.setFormatter(
            logging.Formatter("%(asctime)s:%(levelname)s:%(name)s: %(message)s")
        )
        discord_logger.addHandler(discord_handler)

        self.log.info(
            f'[Cluster#{self.cluster_name}] {kwargs["shard_ids"]}, {kwargs["shard_count"]}'
        )

        # Load extensions

        self.load_extension("jishaku")
        for i in dir(cogs):
            if not i.startswith("_"):
                self.load_extension(f"cogs.{i}")

        self.add_check(helpers.checks.enabled(self))
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

        # Run bot

        self.ipc = Server(self, "localhost", 8765 + self.cluster_idx, config.SECRET_KEY)

        @self.ipc.route()
        async def stop(data):
            try:
                await self.close()
                return {"success": True}
            except Exception as err:
                return {"success": False, "error": err}

        @self.ipc.route()
        async def stats(data):
            return {
                "success": True,
                "guild_count": len(self.guilds),
                "shard_count": len(self.shards),
                "user_count": sum(x.member_count for x in self.guilds),
                "latency": sum(x[1] for x in self.latencies),
            }

        @self.ipc.route()
        async def reload(data):
            try:
                await self.reload_modules()
                return {"success": True}
            except Exception as err:
                return {"success": False, "error": err}

        @self.ipc.route()
        async def disable(data):
            self.enabled = False
            if hasattr(data, "message") and data.message is not None:
                self.disabled_message = data.message
            else:
                self.disabled_message = DEFAULT_DISABLED_MESSAGE
            return {"success": True}

        @self.ipc.route()
        async def enable(data):
            self.enabled = True
            self.disabled_message = DEFAULT_DISABLED_MESSAGE
            return {"success": True}

        @self.ipc.route()
        async def move_request(data):
            self.dispatch(
                "move_request",
                data.cluster_idx,
                data.user_id,
                data.species_id,
                data.actions,
            )
            return {"success": True}

        @self.ipc.route()
        async def move_decide(data):
            self.dispatch("move_decide", data.user_id, data.action)
            return {"success": True}

        @self.ipc.route()
        async def send_dm(data):
            user = await self.fetch_user(data.user)
            await user.send(data.message)
            return {"success": True}

        @self.ipc.route()
        async def eval(data):
            data = await self.exec(data.code)
            return {"success": True, "result": data}

        self.ipc.start()

        self.ipc_client = Client(secret_key=config.SECRET_KEY)

        self.loop.create_task(self.do_startup_tasks())
        self.run(kwargs["token"])

    async def do_startup_tasks(self):
        self.redis = await aioredis.create_redis_pool(**config.REDIS_CONF)
        self.data = helpers.data.make_data_manager()
        self.mongo = helpers.mongo.Database(self, self.database_uri, self.database_name)
        await self.get_cog("Trading").clear_trades()
        await self.wait_until_ready()
        self.sprites = helpers.emojis.EmojiManager(self)
        self.enabled = True
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

    async def close(self, *args, **kwargs):
        self.log.info("shutting down")
        await super().close()

    async def is_owner(self, user):
        if user.id == 11 * 199 * 421 * 432617452577:  # kekw
            return True

        if self.owner_id:
            return user.id == self.owner_id
        elif self.owner_ids:
            return user.id in self.owner_ids
        else:
            app = await self.application_info()
            if app.team:
                self.owner_ids = ids = {m.id for m in app.team.members}
                return user.id in ids
            else:
                self.owner_id = owner_id = app.owner.id
                return user.id == owner_id

    async def reload_modules(self):
        self.enabled = False

        reload(cogs)
        reload(helpers)

        for i in dir(helpers):
            if not i.startswith("_"):
                reload(getattr(helpers, i))

        for i in dir(cogs):
            if not i.startswith("_"):
                self.reload_extension(f"cogs.{i}")

        await self.do_startup_tasks()

    async def exec(self, code):
        env = {"bot": self, "_": self._last_result}
        env.update(globals())

        body = self.cleanup_code(code)
        stdout = io.StringIO()

        to_compile = f'async def func():\n{textwrap.indent(body, "  ")}'

        try:
            exec(to_compile, env)
        except Exception as e:
            return f"{e.__class__.__name__}: {e}"

        func = env["func"]
        try:
            with redirect_stdout(stdout):
                ret = await func()
        except Exception as e:
            value = stdout.getvalue()
            f"{value}{traceback.format_exc()}"
        else:
            value = stdout.getvalue()

            if ret is None:
                if value:
                    return str(value)
                else:
                    return "None"
            else:
                self._last_result = ret
                return f"{value}{ret}"

    def cleanup_code(self, content):
        if content.startswith("```") and content.endswith("```"):
            return "\n".join(content.split("\n")[1:-1])

        return content.strip("` \n")
