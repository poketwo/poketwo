"""
This is a one-shot script used to add the next_idx field to all members.
4 October 2020
"""

import config
from pymongo import MongoClient

client = MongoClient(config.DATABASE_URI)
db = client[config.DATABASE_NAME]

result = db["pokemon"].aggregate(
    [
        {
            "$group": {
                "_id": "$owner_id",
                "max_idx": {
                    "$max": "$idx",
                },
            }
        },
        {"$set": {"next_idx": {"$add": ["$max_idx", 1]}}},
        {"$unset": "max_idx"},
        {"$match": {"_id": {"$ne": None}}},
        {
            "$merge": {
                "into": "member",
                "on": "_id",
            }
        },
    ],
)

for i in result:
    print(i)