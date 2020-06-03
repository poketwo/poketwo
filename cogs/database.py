import datetime

import discord
import mongoengine
from discord.ext import commands

from .helpers import mongo


class Database(commands.Cog):
    """For database operations."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def fetch_member(self, member: discord.Member) -> mongo.Member:
        return mongo.Member.objects.get(id=member.id)

    def fetch_guild(self, guild: discord.Guild) -> mongo.Guild:
        try:
            return mongo.Guild.objects.get(id=guild.id)
        except mongoengine.DoesNotExist:
            return mongo.Guild.objects.create(id=guild.id)

    def update_member(self, member: discord.Member, **kwargs):
        mongo.Member.objects(id=member.id).update_one(**kwargs)
