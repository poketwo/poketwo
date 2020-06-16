import random
import os

from pymongo import DeleteMany, InsertOne, MongoClient, ReplaceOne, UpdateOne

db = MongoClient(os.getenv("DATABASE_URI"))[os.getenv("DATABASE_NAME")]

sizes = db.member.aggregate([{"$project": {"num_count": {"$size": "$pokemon"}}}])

for x in sizes:
    update = {
        f"pokemon.{idx}.shiny": random.randint(1, 4096) == 1
        for idx in range(x["num_count"])
    }

    if len(update) > 0:
        db.member.update_one({"_id": x["_id"]}, {"$set": update})

    print(x["_id"], len(update))

print("Done")
