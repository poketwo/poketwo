"""
This is a one-shot script used to add timestamp fields to all pokemon.
17 September 2020
"""

import os

import config
from pymongo import MongoClient

client = MongoClient(config.DATABASE_URI)
db = client[config.DATABASE_NAME]

db["pokemon"].aggregate(
    [
        {
            "$sort": {
                "timestamp": 1,
                "_id": 1,
            }
        },
        {
            "$group": {
                "_id": "$owner_id",
                "pokemon": {
                    "$push": "$$ROOT",
                },
            }
        },
        {
            "$unwind": {
                "path": "$pokemon",
                "includeArrayIndex": "pokemon.idx",
            }
        },
        {
            "$replaceRoot": {
                "newRoot": "$pokemon",
            }
        },
        {"$out": "new_pokemon"},
    ]
)
