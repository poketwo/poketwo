"""
This is a one-shot script used to add timestamp fields to all pokemon.
17 September 2020
"""

import os

import config
from pymongo import MongoClient

client = MongoClient(config.DATABASE_URI)
db = client[config.DATABASE_NAME]

result = db["pokemon"].aggregate(
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
                "ids": {
                    "$push": "$_id",
                },
            }
        },
        {
            "$unwind": {
                "path": "$ids",
                "includeArrayIndex": "idx",
            }
        },
        {"$project": {"_id": "$ids", "idx": "$idx"}},
        {"$out": "new_pokemon"},
    ],
    allowDiskUse=True,
)

for i in result:
    print(i)
