import discord
import pymongo
from discord.ext import commands


class Database(commands.Cog):
    """For database operations."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def fetch_member_info(self, member: discord.Member):
        return await self.bot.mongo.Member.find_one(
            {"id": member.id}, {"pokemon": 0, "pokedex": 0}
        )

    async def fetch_pokedex(self, member: discord.Member, start: int, end: int):

        filter_obj = {}

        for i in range(start, end):
            filter_obj[f"pokedex.{i}"] = 1

        return await self.bot.mongo.Member.find_one({"id": member.id}, filter_obj)

    async def fetch_market_list(self, skip: int, limit: int, aggregations=[]):
        return await self.bot.mongo.db.listing.aggregate(
            [*aggregations, {"$skip": skip}, {"$limit": limit}], allowDiskUse=True
        ).to_list(None)

    async def fetch_market_count(self, aggregations=[]):

        result = await self.bot.mongo.db.listing.aggregate(
            [*aggregations, {"$count": "num_matches"}], allowDiskUse=True
        ).to_list(None)

        if len(result) == 0:
            return 0

        return result[0]["num_matches"]

    async def fetch_pokemon_list(
        self, member: discord.Member, skip: int, limit: int, aggregations=[]
    ):

        return await self.bot.mongo.db.member.aggregate(
            [
                {"$match": {"_id": member.id}},
                {
                    "$lookup": {
                        "from": "pokemon",
                        "localField": "_id",
                        "foreignField": "owner_id",
                        "as": "pokemon",
                    }
                },
                {"$unwind": "$pokemon"},
                {
                    "$sort": {
                        "pokemon.timestamp": 1,
                        "pokemon._id": 1,
                    }
                },
                {"$group": {"_id": "$_id", "pokemon": {"$push": "$pokemon"}}},
                {"$unwind": {"path": "$pokemon", "includeArrayIndex": "idx"}},
                *aggregations,
                {"$skip": skip},
                {"$limit": limit},
            ],
            allowDiskUse=True,
        ).to_list(None)

    async def fetch_pokemon_count(self, member: discord.Member, aggregations=[]):

        result = await self.bot.mongo.db.member.aggregate(
            [
                {"$match": {"_id": member.id}},
                {
                    "$lookup": {
                        "from": "pokemon",
                        "localField": "_id",
                        "foreignField": "owner_id",
                        "as": "pokemon",
                    }
                },
                {"$unwind": "$pokemon"},
                {
                    "$sort": {
                        "pokemon.timestamp": 1,
                        "pokemon._id": 1,
                    }
                },
                *aggregations,
                {"$count": "num_matches"},
            ],
            allowDiskUse=True,
        ).to_list(None)

        if len(result) == 0:
            return 0

        return result[0]["num_matches"]

    async def fetch_pokedex_count(self, member: discord.Member, aggregations=[]):

        result = await self.bot.mongo.db.member.aggregate(
            [
                {"$match": {"_id": member.id}},
                {"$project": {"pokedex": {"$objectToArray": "$pokedex"}}},
                {"$unwind": {"path": "$pokedex"}},
                {"$replaceRoot": {"newRoot": "$pokedex"}},
                *aggregations,
                {"$group": {"_id": "count", "result": {"$sum": 1}}},
            ],
            allowDiskUse=True,
        ).to_list(None)

        if len(result) == 0:
            return 0

        return result[0]["result"]

    async def fetch_pokedex_sum(self, member: discord.Member, aggregations=[]):

        result = await self.bot.mongo.db.member.aggregate(
            [
                {"$match": {"_id": member.id}},
                {"$project": {"pokedex": {"$objectToArray": "$pokedex"}}},
                {"$unwind": {"path": "$pokedex"}},
                {"$replaceRoot": {"newRoot": "$pokedex"}},
                *aggregations,
                {"$group": {"_id": "sum", "result": {"$sum": "$v"}}},
            ],
            allowDiskUse=True,
        ).to_list(None)

        if len(result) == 0:
            return 0

        return result[0]["result"]

    async def update_member(self, member, update):
        if hasattr(member, "id"):
            member = member.id
        return await self.bot.mongo.db.member.update_one({"_id": member}, update)

    async def update_pokemon(self, pokemon, update):
        if hasattr(pokemon, "id"):
            pokemon = pokemon.id
        if hasattr(pokemon, "_id"):
            pokemon = pokemon._id
        if isinstance(pokemon, dict) and "_id" in pokemon:
            pokemon = pokemon["_id"]
        return await self.bot.mongo.db.pokemon.update_one({"_id": pokemon}, update)

    async def fetch_pokemon(self, member: discord.Member, idx: int):

        result = await self.bot.mongo.db.member.aggregate(
            [
                {"$match": {"_id": member.id}},
                {
                    "$lookup": {
                        "from": "pokemon",
                        "localField": "_id",
                        "foreignField": "owner_id",
                        "as": "pokemon",
                    }
                },
                {"$unwind": "$pokemon"},
                {
                    "$sort": {
                        "pokemon.timestamp": 1,
                        "pokemon._id": 1,
                    }
                },
                {"$skip": idx},
                {"$limit": 1},
            ],
            allowDiskUse=True,
        ).to_list(None)

        if len(result) == 0 or "pokemon" not in result[0]:
            return None

        return self.bot.mongo.Pokemon.build_from_mongo(result[0]["pokemon"])

    async def fetch_guild(self, guild: discord.Guild):
        guild = await self.bot.mongo.Guild.find_one({"id": guild.id})
        if guild is None:
            guild = self.bot.mongo.Guild(id=guild.id)
            await guild.commit()
        return guild

    async def update_guild(self, guild: discord.Guild, update):
        return await self.bot.mongo.db.guild.update_one(
            {"_id": guild.id}, update, upsert=True
        )


def setup(bot: commands.Bot):
    bot.add_cog(Database(bot))
