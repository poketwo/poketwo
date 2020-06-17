import random
import os

from pymongo import DeleteMany, InsertOne, MongoClient, ReplaceOne, UpdateOne

db = MongoClient(os.getenv("DATABASE_URI"))["pokemon"]

results = db.member.aggregate(
    [
        {"$match": {"_id": 415716064060768257}},
        {"$unwind": {"path": "$pokemon", "includeArrayIndex": "idx"}},
        {"$match": {"pokemon.species_id": None}},
    ]
)

for x in results:
    print(x)
    

