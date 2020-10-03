"""
This is a one-shot script used to add timestamp fields to all pokemon.
17 September 2020
"""

import os

import config
from pymongo import MongoClient

client = MongoClient(config.DATABASE_URI)
db = client[config.DATABASE_NAME]

db["member"].aggregate(
    [
        {
            "$lookup": {
                "from": "pokemon",
                "localField": "_id",
                "foreignField": "owner_id",
                "as": "pokemon",
            }
        },
        {"$set": {"next_idx": {"$add": [{"$max": "$pokemon.idx"}, 1]}}},
        {"$unwind": "$pokemon"},
        {"$match": {"$expr": {"selected": "$pokemon.idx"}}},
        {"$group": {"_id": "$_id", "doc": {"$first": "$$ROOT"}}},
        {"$replaceRoot": {"newRoot": "$doc"}},
        {"$set": {"selected_id": "$pokemon._id"}},
        {"$unset": "pokemon"},
        {"$out": "new_member"},
    ],
)
