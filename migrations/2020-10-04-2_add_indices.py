"""
This is a one-shot script used to merge the idx fields into the pokemon collection.
4 October 2020
"""

import config
from pymongo import MongoClient

client = MongoClient(config.DATABASE_URI)
db = client[config.DATABASE_NAME]

result = db["new_pokemon"].aggregate(
    [
        {
            "$merge": {
                "into": "pokemon",
                "on": "_id",
            }
        },
    ],
    allowDiskUse=True,
)

for i in result:
    print(i)
