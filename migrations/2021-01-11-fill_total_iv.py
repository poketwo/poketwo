"""
This is a one-shot script used to add the iv_total field to all pokemon.
11 January 2020
"""

import config
from pymongo import MongoClient

client = MongoClient(config.DATABASE_URI)
db = client[config.DATABASE_NAME]

db.pokemon.update_many(
    {"iv_total": {"$exists": False}},
    [
        {
            "$set": {
                "iv_total": {
                    "$sum": [
                        "$iv_hp",
                        "$iv_atk",
                        "$iv_defn",
                        "$iv_satk",
                        "$iv_sdef",
                        "$iv_spd",
                    ]
                }
            },
        },
    ],
)

db.listing.update_many(
    {"pokemon.iv_total": {"$exists": False}},
    [
        {
            "$set": {
                "pokemon.iv_total": {
                    "$sum": [
                        "$pokemon.iv_hp",
                        "$pokemon.iv_atk",
                        "$pokemon.iv_defn",
                        "$pokemon.iv_satk",
                        "$pokemon.iv_sdef",
                        "$pokemon.iv_spd",
                    ]
                }
            },
        },
    ],
)


db.auction.update_many(
    {"pokemon.iv_total": {"$exists": False}},
    [
        {
            "$set": {
                "pokemon.iv_total": {
                    "$sum": [
                        "$pokemon.iv_hp",
                        "$pokemon.iv_atk",
                        "$pokemon.iv_defn",
                        "$pokemon.iv_satk",
                        "$pokemon.iv_sdef",
                        "$pokemon.iv_spd",
                    ]
                }
            },
        },
    ],
)
