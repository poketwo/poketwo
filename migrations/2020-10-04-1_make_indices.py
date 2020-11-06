"""
This is a one-shot script used to make idx fields for all pokemon into a new collection.
4 October 2020
"""

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
