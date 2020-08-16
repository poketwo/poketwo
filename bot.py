import asyncio
import io
import json
import logging
import os
import sys
import textwrap
import traceback
from contextlib import redirect_stdout
from importlib import reload

import discord
import websockets
from discord.ext import commands, flags

import cogs
import helpers


async def determine_prefix(bot, message):
    cog = bot.get_cog("Bot")
    return await cog.determine_prefix(message.guild)


@commands.is_owner()
@commands.command()
async def ipcsend(ctx: commands.Context, *, command: str):
    ret = {"command": command}
    try:
        await ctx.bot.websocket.send(json.dumps(ret))
    except websockets.ConnectionClosed as exc:
        if exc.code == 1000:
            return
        raise


class ClusterBot(commands.AutoShardedBot):
    def __init__(self, **kwargs):
        self.pipe = kwargs.pop("pipe")
        self.cluster_name = kwargs.pop("cluster_name")
        self.env = kwargs.pop("env")
        loop = asyncio.new_event_loop()

        asyncio.set_event_loop(loop)
        super().__init__(**kwargs, loop=loop, command_prefix=determine_prefix)
        self.mongo = helpers.mongo.Database(
            self, kwargs.pop("database_uri"), kwargs.pop("database_name")
        )

        self.data = helpers.data.make_data_manager()
        self.websocket = None
        self._last_result = None
        self.ws_task = None
        self.responses = asyncio.Queue()
        self.eval_wait = False
        self.enabled = False

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

        self.loop.create_task(self.do_startup_tasks())
        self.loop.create_task(self.ensure_ipc())

        self.add_command(ipcsend)
        self.add_check(helpers.checks.enabled(self))
        self.run(kwargs["token"])

    async def do_startup_tasks(self):
        await self.wait_until_ready()
        await helpers.constants.EMOJIS.init_emojis(self)
        self.enabled = True
        print(f"Logged in as {self.user}")

    async def on_ready(self):
        self.log.info(f"[Cluster#{self.cluster_name}] Ready called.")
        self.pipe.send(1)
        self.pipe.close()

    async def on_shard_ready(self, shard_id):
        self.log.info(f"[Cluster#{self.cluster_name}] Shard {shard_id} ready")

    async def on_message(self, message: discord.Message):
        message.content = (
            message.content.replace("—", "--")
            .replace("'", "′")
            .replace("‘", "′")
            .replace("’", "′")
        )

        await self.process_commands(message)

    async def on_command_error(self, ctx, error):

        if isinstance(error, cogs.bot.Blacklisted):
            logging.info(f"{ctx.author.id} is blacklisted")
            return
        elif isinstance(error, cogs.bot.CommandOnCooldown):
            logging.info(f"{ctx.author.id} hit cooldown")
            await ctx.message.add_reaction("🛑")
        elif isinstance(error, commands.CommandOnCooldown):
            logging.info(f"{ctx.author.id} hit second stage cooldown")
            return
        elif isinstance(error, commands.NoPrivateMessage):
            await ctx.send("This command cannot be used in private messages.")
        elif isinstance(error, commands.DisabledCommand):
            await ctx.send("Sorry. This command is disabled and cannot be used.")
        elif isinstance(error, commands.BotMissingPermissions):
            missing = [
                "`" + perm.replace("_", " ").replace("guild", "server").title() + "`"
                for perm in error.missing_perms
            ]
            if len(missing) > 2:
                fmt = "{}, and {}".format(", ".join(missing[:-1]), missing[-1])
            else:
                fmt = " and ".join(missing)
            message = f"💥 Err, I need the following permissions to run this command:\n{fmt}\nPlease fix this and try again."
            await ctx.send(message)
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
            print(f"Ignoring exception in command {ctx.command}:", file=sys.stderr)
            traceback.print_exception(
                type(error), error, error.__traceback__, file=sys.stderr
            )

    async def close(self, *args, **kwargs):
        self.log.info("shutting down")
        await self.websocket.close()
        await super().close()

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

    async def websocket_loop(self):
        while True:
            try:
                msg = await self.websocket.recv()
            except websockets.ConnectionClosed as exc:
                if exc.code == 1000:
                    return
                raise

            data = json.loads(msg)
            if self.eval_wait and data.get("response"):
                await self.responses.put(data)

            cmd = data.get("command")
            if not cmd:
                continue

            if cmd == "ping":
                self.log.info("received command [ping]")
                ret = {"response": "pong"}
            elif cmd == "reloadall":
                self.log.info("received command [reloadall]")
                try:
                    await self.reload_modules()
                    ret = {"response": "reloaded all"}
                except Exception as error:
                    ret = {"response": "error reloading"}
                    traceback.print_exception(
                        type(error), error, error.__traceback__, file=sys.stderr
                    )
            else:
                ret = {"response": "unknown command"}

            ret["author"] = self.cluster_name
            self.log.info(f"responding: {ret}")
            try:
                await self.websocket.send(json.dumps(ret))
            except websockets.ConnectionClosed as exc:
                if exc.code == 1000:
                    return
                raise

    async def ensure_ipc(self):
        self.websocket = w = await websockets.connect("ws://localhost:42069")
        await w.send(self.cluster_name)
        try:
            await w.recv()
            self.ws_task = self.loop.create_task(self.websocket_loop())
            self.log.info("ws connection succeeded")
        except websockets.ConnectionClosed as exc:
            self.log.warning(f"! couldnt connect to ws: {exc.code} {exc.reason}")
            self.websocket = None
            raise
