import random
import os

from pymongo import DeleteMany, InsertOne, MongoClient, ReplaceOne, UpdateOne

db = MongoClient(os.getenv("DATABASE_URI"))[os.getenv("DATABASE_NAME")]

results = db.member.aggregate(
    [
        {"$unwind": {"path": "$pokemon", "includeArrayIndex": "idx"}},
        {
            "$match": {
                "pokemon.iv_hp": 1,
                "pokemon.iv_atk": 15,
                "pokemon.iv_defn": 24,
                "pokemon.iv_satk": 4,
                "pokemon.iv_sdef": 7,
                "pokemon.iv_spd": 20,
            }
        },
    ]
)

for x in results:
    print(x)

print("Done")
