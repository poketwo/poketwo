"""
This is a one-shot script used to migrate all Pokémon from array fields to a global collection.
6 September 2020
"""

from pymongo import MongoClient
import os


client = MongoClient(os.getenv("DATABASE_URI"))
db = client[os.getenv("DATABASE_NAME")]

result = db["member"].aggregate(
    [
        {"$match": {"suspended": {"$ne": True}}},
        {"$unwind": {"path": "$pokemon", "includeArrayIndex": "idx"}},
        {"$addFields": {"pokemon.owner_id": "$_id"}},
        {"$replaceRoot": {"newRoot": "$pokemon"}},
        {"$out": "pokemon"},
    ],
    allowDiskUse=True,
)
