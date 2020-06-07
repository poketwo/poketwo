from functools import cached_property

import discord
from discord.ext import commands, flags

from .database import Database
from .helpers import checks
from .helpers.models import *


class Trading(commands.Cog):
    """For trading."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.prefixes = {}

    @property
    def db(self) -> Database:
        return self.bot.get_cog("Database")

    @checks.has_started()
    @commands.command()
    async def trade(self, ctx: commands.Context, user: discord.User):
        
