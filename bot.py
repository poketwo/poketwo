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
from helpers import constants
from helpers.slash import CommandWithSlashCommand, SlashCommand, SlashContext

uvloop.install()


async def determine_prefix(bot, message):
    cog = bot.get_cog("Bot")
    return await cog.determine_prefix(message.guild)


def is_enabled(ctx):
    if not ctx.bot.enabled:
        raise commands.CheckFailure(constants.DEFAULT_DISABLED_MESSAGE)
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

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        super().__init__(**kwargs, loop=loop, command_prefix=determine_prefix)

        self.ready = False
        self.menus = ExpiringDict(max_len=300, max_age_seconds=300)
        self.slash_commands: dict[str, SlashCommand] = {}
        self.slash_commands_ready = False
        self.activity = discord.Game("p!help • poketwo.net")
        self.http_session = aiohttp.ClientSession()

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
        self.run(kwargs["token"])

    # Slash

    def add_command(self, command):
        super().add_command(command)
        if isinstance(command, CommandWithSlashCommand):
            self.slash_commands[command.slash_command.name] = command.slash_command

    def remove_command(self, name):
        command = super().remove_command(name)
        if isinstance(command, CommandWithSlashCommand):
            del self.slash_commands[command.slash_command.name]
        return command

    async def get_slash_commands(self):
        if self.config.SLASH_GUILD_ID is None:
            return await self.http.get_global_commands(self.application_id)
        return await self.http.get_guild_commands(self.application_id, self.config.SLASH_GUILD_ID)

    async def bulk_upsert_slash_commands(self, payload):
        if self.config.SLASH_GUILD_ID is None:
            return await self.http.bulk_upsert_global_commands(self.application_id, payload)
        return await self.http.bulk_upsert_guild_commands(
            self.application_id, self.config.SLASH_GUILD_ID, payload
        )

    async def process_slash_commands(self, interaction: discord.Interaction):
        if interaction.type is not discord.InteractionType.application_command:
            return
        if interaction.data is None:
            return
        try:
            slash_cmd = self.slash_commands[interaction.data["name"]]
        except KeyError:
            return

        ctx = SlashContext.build_from_interaction(self, interaction, slash_cmd)
        await slash_cmd(ctx)

    async def on_connect(self):
        if self.slash_commands_ready:
            return
        # prev_cmds = await self.get_slash_commands()
        cmds = [x.to_json() for x in self.slash_commands.values()]
        await self.bulk_upsert_slash_commands(cmds)
        self.slash_commands_ready = True

    async def on_interaction(self, interaction):
        await self.process_slash_commands(interaction)

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

    async def on_ready(self):
        await self.wait_until_ready()
        self.ready = True

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
