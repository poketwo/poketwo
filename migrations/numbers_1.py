import os

from pymongo import DeleteMany, InsertOne, MongoClient, ReplaceOne, UpdateOne

db = MongoClient(os.getenv("DATABASE_URI"))[os.getenv("DATABASE_NAME")]

updates = []

c = 0

for x in db.member.find():
    agg = db.member.aggregate(
        [
            {"$match": {"_id": x["_id"]}},
            {"$unwind": {"path": "$pokemon", "includeArrayIndex": "idx"}},
            {"$match": {"pokemon.number": x["selected"]}},
        ]
    )
    try:
        selected = list(agg)[0]["idx"]
    except IndexError:
        selected = 0

    updates.append(UpdateOne({"_id": x["_id"]}, {"$set": {"selected": selected}}))

    c += 1

db.member.bulk_write(updates)
print("Done")
