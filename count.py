# Requires the PyMongo package.
# https://api.mongodb.com/python/current

import matplotlib.pyplot as plt
from pymongo import MongoClient

from cogs.helpers.models import GameData
from data import load_data

load_data()

client = MongoClient(
    "mongodb+srv://pokepoke:Cd0KUYyjoS7LDD5h@pokepoke-f9xby.mongodb.net/pokemon?authSource=admin&replicaSet=PokePoke-shard-0&w=majority&readPreference=primary&appname=MongoDB%20Compass&retryWrites=true&ssl=true"
)
result = client["pokemon"]["member"].aggregate(
    [
        # {"$match": {"_id": idd}},
        # {"$unwind": {"path": "$pokemon"}},
        # {"$match": {"pokemon.shiny": True}},
        # {"$group": {"_id": "$_id", "pokemon": {"$addToSet": "$pokemon"},}},
        {"$project": {"dex": {"$objectToArray": "$pokedex"}}},
        {"$project": {"num": {"$sum": "$dex.v"}}},
        {"$sort": {"num": -1}},
        {"$limit": 500},
    ]
)

# for idx, x in enumerate(result):
#     print(idx + 1, x["_id"], x["num"], sep="\t")

# plt.axis("auto")
plt.plot([x["num"] for x in result])
plt.ylabel("# pokemon caught")
# plt.yscale('log')
plt.show()
