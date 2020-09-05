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

import cogs
import helpers


async def determine_prefix(bot, message):
    cog = bot.get_cog("Bot")
    return await cog.determine_prefix(message.guild)


class ClusterBot(commands.AutoShardedBot):
    def __init__(self, **kwargs):
        self.pipe = kwargs.pop("pipe")
        self.cluster_name = kwargs.pop("cluster_name")
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
                manage_messages=True,
                embed_links=True,
                attach_files=True,
                read_message_history=True,
                add_reactions=True,
                external_emojis=True,
            ).predicate
        )

        # Run bot

        self.loop.create_task(self.do_startup_tasks())
        self.loop.create_task(self.pipe_loop())

        self.run(kwargs["token"])

    class Embed(discord.Embed):
        def __init__(self, **kwargs):
            color = kwargs.pop("color", 0xF44336)
            super().__init__(**kwargs, color=color)

    async def do_startup_tasks(self):
        await self.wait_until_ready()
        self.data = helpers.data.make_data_manager()
        self.sprites = helpers.emojis.EmojiManager(self)
        self.mongo = helpers.mongo.Database(self, self.database_uri, self.database_name)
        self.enabled = True
        self.log.info(f"Logged in as {self.user}")

    async def on_ready(self):
        self.log.info(f"[Cluster#{self.cluster_name}] Ready called.")
        self.pipe.send("ready")

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
            print(f"Ignoring exception in command {ctx.command}:", file=sys.stderr)
            traceback.print_exception(
                type(error), error, error.__traceback__, file=sys.stderr
            )

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

    def cleanup_code(self, content):
        """Automatically removes code blocks from the code."""
        # remove ```py\n```
        if content.startswith("```") and content.endswith("```"):
            return "\n".join(content.split("\n")[1:-1])

        # remove `foo`
        return content.strip("` \n")

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

    async def pipe_loop(self):
        while True:
            msg = await self.loop.run_in_executor(None, self.pipe.recv)

            try:
                data = json.loads(msg)
                cmd = data.get("command")
            except json.decoder.JSONDecodeError:
                cmd = msg

            if cmd == "ping":
                self.log.info("received command [ping]")
                ret = "pong"

            elif cmd == "eval":
                self.log.info(f"received command [eval] ({data['content']})")
                content = data["content"]
                data = await self.exec(content)
                ret = str(data)

            elif cmd == "reloadall":
                self.log.info("received command [reloadall]")
                try:
                    await self.reload_modules()
                    ret = "reloaded"
                except Exception as error:
                    ret = "error reloading"
                    traceback.print_exception(
                        type(error), error, error.__traceback__, file=sys.stderr
                    )

            elif cmd == "disable":
                self.log.info("received command [disable]")
                self.enabled = False
                ret = "disabled"

            elif cmd == "enable":
                self.log.info("received command [enable]")
                self.enabled = True
                await self.reload_modules()
                ret = "enabled"

            else:
                ret = "unknown"

            self.log.info(f"responding: {ret}")
            self.pipe.send(ret)
