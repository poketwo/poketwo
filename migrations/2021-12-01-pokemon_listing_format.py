"""
This is a one-shot script used to migrate listings to the global Pokémon collection and reformat existing Pokémon.
1 December 2021
"""

from pymongo import MongoClient

import config

client = MongoClient(config.DATABASE_URI)
db = client[config.DATABASE_NAME]

print("Part 1...")

db.pokemon.update_many({"owned_by": {"$exists": False}}, {"$set": {"owned_by": "user"}})

print("Part 2...")

db.listing.aggregate(
    [
        {
            "$set": {
                "pokemon.market_data._id": "$_id",
                "pokemon.market_data.price": "$price",
                "pokemon.owner_id": "$user_id",
                "pokemon.owned_by": "market",
            }
        },
        {"$replaceRoot": {"newRoot": "$pokemon"}},
        {"$merge": {"into": "pokemon", "on": "_id", "whenMatched": "keepExisting"}},
    ],
    allowDiskUse=True,
)
