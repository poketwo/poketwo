"""
This is a one-shot script used to add timestamp fields to all pokemon.
17 September 2020
"""

import config
from pymongo import MongoClient

client = MongoClient(config.DATABASE_URI)
db = client[config.DATABASE_NAME]

result = db["pokemon"].update_many(
    {"timestamp": {"$exists": False}}, [{"$set": {"timestamp": {"$toDate": "$_id"}}}]
)
result = db["listing"].update_many(
    {"pokemon.timestamp": {"$exists": False}},
    [{"$set": {"pokemon.timestamp": {"$toDate": "$pokemon._id"}}}],
)
