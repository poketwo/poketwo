"""
This is a one-shot script used to backfill moves into all Pokémon with no moves.
9 September 2020
"""
import os
import random
import sys
from multiprocessing import Pool

import config
from pymongo import MongoClient, UpdateOne

sys.path.append(os.getcwd())

import helpers

data = helpers.data.make_data_manager()

client = MongoClient(config.DATABASE_URI)
db = client[config.DATABASE_NAME]


def make_request(i):
    if "species_id" not in i:
        return None
    species = data.species_by_number(i["species_id"])
    moves = [x.move.id for x in species.moves if i["level"] >= x.method.level]
    random.shuffle(moves)
    return UpdateOne({"_id": i["_id"]}, {"$set": {"moves": moves[:4]}})


requests = [0]

if __name__ == "__main__":
    with Pool() as p:
        while len(requests) > 0:
            requests = []
            result = (
                db["pokemon"]
                .find({"$or": [{"moves": {"$exists": False}}, {"moves": []}]})
                .limit(100000)
            )

            requests = [x for x in p.imap(make_request, result, 100) if x is not None]

            print(f"Bulk writing {len(requests)} operations")
            db["pokemon"].bulk_write(requests, ordered=False)
            print(f"Wrote {len(requests)} operations")
