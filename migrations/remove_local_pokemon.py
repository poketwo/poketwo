from pymongo import MongoClient
import os


client = MongoClient(os.getenv("DATABASE_URI"))
db = client[os.getenv("DATABASE_NAME")]

print(os.getenv("DATABASE_NAME"))
input()

result = db["member"].update_many({}, {"$unset": {"pokemon": 1}})
