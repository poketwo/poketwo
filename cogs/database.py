import datetime

import discord
from discord.ext import commands

from .helpers import mongo


class Database(commands.Cog):
    """For database operations."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def fetch_member(self, member: discord.Member) -> mongo.Member:
        return await mongo.Member.find_one({"id": member.id})

    async def fetch_guild(self, guild: discord.Guild) -> mongo.Guild:
        guild = await mongo.Guild.find_one({"id": guild.id})
        if guild is None:
            guild = mongo.Guild(id=guild.id)
            await guild.commit()
        return guild
