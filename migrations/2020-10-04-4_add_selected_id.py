"""
This is a one-shot script used to add the selected_id field to all members.
4 October 2020
"""

import config
from pymongo import MongoClient, UpdateOne

client = MongoClient(config.DATABASE_URI)
db = client[config.DATABASE_NAME]

ops = []

for i in db["member"].find():
    if "selected" not in i:
        continue
    pkmn = db["pokemon"].find_one({"owner_id": i["_id"], "idx": i["selected"]})
    if pkmn is None:
        continue
    ops.append(UpdateOne({"_id": i["_id"]}, {"$set": {"selected_id": pkmn["_id"]}}))

    if len(ops) >= 10000:
        print("Writing " + str(len(ops)))
        db["member"].bulk_write(ops, ordered=False)
        print("Updated " + str(len(ops)))
        ops = []

print("Writing " + str(len(ops)))
db["member"].bulk_write(ops, ordered=False)
print("Updated " + str(len(ops)))
