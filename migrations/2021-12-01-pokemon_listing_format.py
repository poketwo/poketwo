"""
This is a one-shot script used to migrate listings to the global Pokémon collection and reformat existing Pokémon.
1 December 2021
"""

from pymongo import MongoClient

import config

client = MongoClient(config.DATABASE_URI)
db = client[config.DATABASE_NAME]

db.pokemon.update_many({"owned_by": {"$exists": False}}, {"$set": {"owned_by": "user"}})

bulk_inserts = []

for x in db.listing.find({}):
    bulk_inserts.append(
        {
            **x["pokemon"],
            "owner_id": x["user_id"],
            "owned_by": "market",
            "market_data": {"_id": x["_id"], "price": x["price"]},
        }
    )

db.pokemon.insert_many(bulk_inserts, ordered=False)
