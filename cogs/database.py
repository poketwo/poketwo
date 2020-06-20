import datetime

import discord
from discord.ext import commands

from .helpers import mongo, models


def setup(bot: commands.Bot):
    bot.add_cog(Database(bot))


class Database(commands.Cog):
    """For database operations."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command()
    async def profile(self, ctx: commands.Context):

        embed = discord.Embed()
        embed.color = 0xF44336
        embed.title = f"{ctx.author}"

        member = await self.fetch_member_info(ctx.author)

        embed.add_field(
            name="Pokémon Caught", value=await self.fetch_pokemon_count(ctx.author)
        )

        for name, filt in (
            ("Mythicals", models.GameData.list_mythical()),
            ("Legendaries", models.GameData.list_legendary()),
            ("Ultra Beast", models.GameData.list_ub()),
        ):
            embed.add_field(
                name=f"{name} Caught",
                value=await self.fetch_pokemon_count(
                    ctx.author, [{"$match": {"pokemon.species_id": {"$in": filt}}}],
                ),
            )

        embed.add_field(name="Shinies Caught", value=member.shinies_caught)

        await ctx.send(embed=embed)

    async def fetch_member_info(self, member: discord.Member) -> mongo.Member:
        return await mongo.Member.find_one(
            {"id": member.id}, {"pokemon": 0, "pokedex": 0}
        )

    async def fetch_pokedex(
        self, member: discord.Member, start: int, end: int
    ) -> mongo.Member:

        filter_obj = {}

        for i in range(start, end):
            filter_obj[f"pokedex.{i}"] = 1

        return await mongo.Member.find_one({"id": member.id}, filter_obj)

    async def fetch_pokemon_list(
        self, member: discord.Member, skip: int, limit: int, aggregations=[]
    ) -> mongo.Member:

        return await mongo.db.member.aggregate(
            [
                {"$match": {"_id": member.id}},
                {"$unwind": {"path": "$pokemon", "includeArrayIndex": "idx"}},
                *aggregations,
                {"$skip": skip},
                {"$limit": limit},
            ],
            allowDiskUse=True,
        ).to_list(None)

    async def fetch_pokemon_count(
        self, member: discord.Member, aggregations=[]
    ) -> mongo.Member:

        result = await mongo.db.member.aggregate(
            [
                {"$match": {"_id": member.id}},
                {"$unwind": {"path": "$pokemon", "includeArrayIndex": "idx"}},
                *aggregations,
                {"$count": "num_matches"},
            ]
        ).to_list(None)

        if len(result) == 0:
            return 0

        return result[0]["num_matches"]

    async def fetch_pokedex_count(
        self, member: discord.Member, aggregations=[]
    ) -> mongo.Member:

        result = await mongo.db.member.aggregate(
            [
                {"$match": {"_id": member.id}},
                {"$addFields": {"count": {"$size": {"$objectToArray": "$pokedex"}}}},
            ]
        ).to_list(None)

        return result[0]["count"]

    async def update_member(self, member: discord.Member, update):
        return await mongo.db.member.update_one({"_id": member.id}, update)

    async def fetch_pokemon(self, member: discord.Member, idx: int):
        if idx == -1:
            result = await mongo.Member.find_one(
                {"_id": member.id}, projection={"pokemon": {"$slice": -1}},
            )
        else:
            result = await mongo.Member.find_one(
                {"_id": member.id}, projection={"pokemon": {"$slice": [idx, 1]}},
            )

        if len(result.pokemon) == 0:
            return None

        return result.pokemon[0]

    async def fetch_guild(self, guild: discord.Guild) -> mongo.Guild:
        guild = await mongo.Guild.find_one({"id": guild.id})
        if guild is None:
            guild = mongo.Guild(id=guild.id)
            await guild.commit()
        return guild

    async def update_guild(self, guild: discord.Guild, update):
        return await mongo.db.guild.update_one({"_id": guild.id}, update)
