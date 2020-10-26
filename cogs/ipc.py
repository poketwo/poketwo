import io
import textwrap
import traceback
from contextlib import redirect_stdout

from discord.ext import commands
from discord.ext.ipc import Client, Server


class IPC(commands.Cog):
    """For IPC."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._last_result = None
        self.disabled_message = None

        self.server = Server(
            self.bot, "localhost", 8765 + bot.cluster_idx, bot.config.SECRET_KEY
        )

        @self.server.route()
        async def stop(data):
            try:
                await self.bot.close()
                return {"success": True}
            except Exception as err:
                return {"success": False, "error": err}

        @self.server.route()
        async def stats(data):
            return {
                "success": True,
                "guild_count": len(self.bot.guilds),
                "shard_count": len(self.bot.shards),
                "user_count": sum(x.member_count for x in self.bot.guilds),
                "latency": {k: v for k, v in self.bot.latencies},
            }

        @self.server.route()
        async def reload(data):
            try:
                await self.bot.reload_modules()
                return {"success": True}
            except Exception as err:
                return {"success": False, "error": err}

        @self.server.route()
        async def disable(data):
            self.bot.ready = False
            if hasattr(data, "message") and data.message is not None:
                self.disabled_message = data.message
            else:
                self.disabled_message = None
            return {"success": True}

        @self.server.route()
        async def enable(data):
            self.bot.ready = True
            self.disabled_message = None
            return {"success": True}

        @self.server.route()
        async def move_request(data):
            self.bot.dispatch(
                "move_request",
                data.cluster_idx,
                data.user_id,
                data.species_id,
                data.actions,
            )
            return {"success": True}

        @self.server.route()
        async def move_decide(data):
            self.bot.dispatch("move_decide", data.user_id, data.action)
            return {"success": True}

        @self.server.route()
        async def send_dm(data):
            user = await self.bot.fetch_user(data.user)
            await user.send(data.message)
            return {"success": True}

        @self.server.route()
        async def eval(data):
            data = await self.exec(data.code)
            return {"success": True, "result": data}

        bot.loop.create_task(self.server.start())
        self.client = Client(secret_key=bot.config.SECRET_KEY)

    def cleanup_code(self, content):
        if content.startswith("```") and content.endswith("```"):
            return "\n".join(content.split("\n")[1:-1])

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

    def cog_unload(self):
        self.server.close()


def setup(bot):
    bot.add_cog(IPC(bot))
