import os

from pymongo import DeleteMany, InsertOne, MongoClient, ReplaceOne, UpdateOne

db = MongoClient(os.getenv("DATABASE_URI"))[os.getenv("DATABASE_NAME")]

updates = []

db.member.update_many({}, {"$unset": {"next_id": 1}})

print("Done")
