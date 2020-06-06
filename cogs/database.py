import datetime

import discord
import mongoengine
from discord.ext import commands

from .helpers import mongo


class Database(commands.Cog):
    """For database operations."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def fetch_member(
        self, member: discord.Member, pokemon=False, pokedex=False
    ) -> mongo.Member:
        obj = mongo.Member.objects

        if not pokemon:
            obj = obj.exclude("pokemon")

        if not pokedex:
            obj = obj.exclude("pokedex")

        return obj.get(id=member.id)

    def fetch_pokemon(self, member: discord.Member, number: int):
        return (
            mongo.Member.objects.fields(pokemon={"$elemMatch": {"number": number}})
            .get(id=member.id)
            .pokemon[0]
        )

    # def update_pokemon(self, member: discord.Member, number: int, **kwargs):
    #     updates = [(k.split("__"), v) for k, v in kwargs.items()]
    #     updates = {f"{k[0]}__pokemon__S__{k[1]}": v for k, v in updates}
    #     print(updates)
    #     return (
    #         mongo.Member.objects(id=member.id)
    #         .fields(pokemon={"$elemMatch": {"number": number}})
    #         .update_one(**updates)
    #     )

    def fetch_guild(self, guild: discord.Guild) -> mongo.Guild:
        try:
            return mongo.Guild.objects.get(id=guild.id)
        except mongoengine.DoesNotExist:
            return mongo.Guild.objects.create(id=guild.id)

    def update_member(self, member: discord.Member, **kwargs):
        mongo.Member.objects(id=member.id).update_one(**kwargs)
