"""
This is a one-shot script used to migrate all Pokémon from array fields to a global collection.
6 September 2020
"""

import bson
import config
from pymongo import MongoClient

client = MongoClient(config.DATABASE_URI)
db = client[config.DATABASE_NAME]

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
