# Requires the PyMongo package.
# https://api.mongodb.com/python/current

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
        {"$limit": 20},
    ]
)

for x in result:
    print(x["_id"], x["num"])
