import os

from pymongo import DeleteMany, InsertOne, MongoClient, ReplaceOne, UpdateOne

db = MongoClient(os.getenv("DATABASE_URI"))[os.getenv("DATABASE_NAME")]

updates = []

db.member.update_many(
    {}, {"$unset": {"pokemon.$[].owner_id": 1, "pokemon.$[].number": 1}}
)

print("Done")
