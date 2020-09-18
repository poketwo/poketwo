"""
This is a one-shot script used to add timestamp fields to all pokemon.
17 September 2020
"""

from pymongo import MongoClient
import os


client = MongoClient(os.getenv("DATABASE_URI"))
db = client[os.getenv("DATABASE_NAME")]

result = db["pokemon"].update_many({}, [{"$set": {"timestamp": {"$toDate": "$_id"}}}])
