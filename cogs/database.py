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

    async def fetch_member_info(self, member: discord.Member) -> mongo.Member:
        return await mongo.Member.find_one(
            {"id": member.id}, {"pokemon": 0, "pokedex": 0}
        )

    async def update_member(self, member: discord.Member, update):
        return await mongo.db.member.update_one({"_id": member.id}, update)

    async def fetch_pokemon(self, member: discord.Member, number: int):
        return await mongo.Member.find_one(
            {"_id": member.id, "pokemon.number": number},
            projection={"pokemon": {"$elemMatch": {"number": number}}},
        )

    async def update_pokemon(self, member: discord.Member, number: int, update):
        return await mongo.db.member.update_one(
            {"_id": member.id, "pokemon.number": number}, update
        )

    async def fetch_guild(self, guild: discord.Guild) -> mongo.Guild:
        guild = await mongo.Guild.find_one({"id": guild.id})
        if guild is None:
            guild = mongo.Guild(id=guild.id)
            await guild.commit()
        return guild

    async def update_guild(self, guild: discord.Guild, update):
        return await mongo.db.guild.update_one({"_id": guild.id}, update)
