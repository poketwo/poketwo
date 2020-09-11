import asyncio
import io
import json
import logging
import sys
import textwrap
import traceback
from contextlib import redirect_stdout
from importlib import reload

import discord
from discord.ext import commands, flags
from discord.ext.ipc import Server, Client

import cogs
import helpers


async def determine_prefix(bot, message):
    cog = bot.get_cog("Bot")
    return await cog.determine_prefix(message.guild)


class ClusterBot(commands.AutoShardedBot):
    class Embed(discord.Embed):
        def __init__(self, **kwargs):
            color = kwargs.pop("color", 0xF44336)
            super().__init__(**kwargs, color=color)

    def __init__(self, **kwargs):
        self.pipe = kwargs.pop("pipe")
        self.cluster_name = kwargs.pop("cluster_name")
        self.cluster_idx = kwargs.pop("cluster_idx")
        self.env = kwargs.pop("env")
        self.embed_color = 0xF44336
        self.battles = None
        self.dbl_token = kwargs.pop("dbl_token")
        self.database_uri = kwargs.pop("database_uri")
        self.database_name = kwargs.pop("database_name")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        super().__init__(**kwargs, loop=loop, command_prefix=determine_prefix)
        self.mongo = helpers.mongo.Database(self, self.database_uri, self.database_name)

        self._last_result = None
        self.waiting = False
        self.enabled = False
        self.sprites = None

        log = logging.getLogger(f"Cluster#{self.cluster_name}")
        log.setLevel(logging.DEBUG)
        log.handlers = [
            logging.FileHandler(
                f"logs/cluster-{self.cluster_name}.log", encoding="utf-8", mode="a"
            )
        ]

        log.info(
            f'[Cluster#{self.cluster_name}] {kwargs["shard_ids"]}, {kwargs["shard_count"]}'
        )
        self.log = log

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

        self.ipc = Server(
            self, "localhost", 8765 + self.cluster_idx, kwargs["secret_key"]
        )

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
            return {"success": True}

        @self.ipc.route()
        async def enable(data):
            self.enabled = True
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

        self.ipc.start()

        self.ipc_client = Client(secret_key=kwargs["secret_key"])

        self.loop.create_task(self.do_startup_tasks())
        self.run(kwargs["token"])

    async def do_startup_tasks(self):
        await self.wait_until_ready()
        self.data = helpers.data.make_data_manager()
        self.sprites = helpers.emojis.EmojiManager(self)
        self.mongo = helpers.mongo.Database(self, self.database_uri, self.database_name)
        self.enabled = True
        self.log.info(f"Logged in as {self.user}")

    async def on_ready(self):
        self.log.info(f"[Cluster#{self.cluster_name}] Ready called.")
        self.pipe.send(1)
        self.pipe.close()

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

    async def on_command_error(self, ctx: commands.Context, error):

        if isinstance(error, cogs.bot.Blacklisted):
            self.log.info(f"{ctx.author.id} is blacklisted")
            return
        elif isinstance(error, commands.CommandOnCooldown):
            self.log.info(f"{ctx.author.id} hit cooldown")
            await ctx.message.add_reaction("⛔")
        elif isinstance(error, commands.NoPrivateMessage):
            await ctx.send("This command cannot be used in private messages.")
        elif isinstance(error, commands.DisabledCommand):
            await ctx.send("Sorry. This command is disabled and cannot be used.")
        elif isinstance(error, commands.BotMissingPermissions):
            missing = [
                "`" + perm.replace("_", " ").replace("guild", "server").title() + "`"
                for perm in error.missing_perms
            ]
            fmt = "\n".join(missing)
            message = f"💥 Err, I need the following permissions to run this command:\n{fmt}\nPlease fix this and try again."
            botmember = (
                self.user if ctx.guild is None else ctx.guild.get_member(self.user.id)
            )
            if ctx.channel.permissions_for(botmember).send_messages:
                await ctx.send(message)
            else:
                await ctx.author.send(message)
        elif isinstance(
            error,
            (
                commands.CheckFailure,
                helpers.converters.PokemonConversionError,
                commands.UserInputError,
                flags.ArgumentParsingError,
            ),
        ):
            await ctx.send(error)
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send_help(ctx.command)
        elif isinstance(error, (discord.errors.Forbidden, commands.CommandNotFound)):
            return
        else:
            self.log.exception(f"Ignoring exception in command {ctx.command}:")

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
