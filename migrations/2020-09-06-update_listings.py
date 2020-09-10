"""
This is a one-shot script used to migrate all Pokémon from array fields to a global collection.
6 September 2020
"""
from pymongo import MongoClient
import os
import bson

client = MongoClient(os.getenv("DATABASE_URI"))
db = client[os.getenv("DATABASE_NAME")]

result = db["listing"].update_many(
    {},
    [
        {
            "$set": {
                "pokemon.owner_id": "$user_id",
                "pokemon._id": bson.objectid.ObjectId(),
            }
        },
    ],
)
