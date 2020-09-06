from pymongo import MongoClient
import os


client = MongoClient(os.getenv("DATABASE_URI"))
db = client[os.getenv("DATABASE_NAME")]

result = db["member"].aggregate(
    [
        {"$match": {"suspended": {"$ne": True}}},
        {"$unwind": {"path": "$pokemon", "includeArrayIndex": "idx"}},
        {"$addFields": {"pokemon.owner_id": "$_id"}},
        {"$replaceRoot": {"newRoot": "$pokemon"}},
        {"$out": "pokemon"},
    ],
)

for i in result:
    print(i)
