# Requires the PyMongo package.
# https://api.mongodb.com/python/current

from pymongo import MongoClient

from cogs.helpers.models import GameData
from data import load_data

load_data()


while True:
    idd = int(input("> "))

    client = MongoClient(
        "mongodb+srv://pokepoke:Cd0KUYyjoS7LDD5h@pokepoke-f9xby.mongodb.net/pokemon?authSource=admin&replicaSet=PokePoke-shard-0&w=majority&readPreference=primary&appname=MongoDB%20Compass&retryWrites=true&ssl=true"
    )
    result = client["pokemon"]["member"].aggregate(
        [
            {"$match": {"_id": idd}},
            {"$unwind": {"path": "$pokemon", "includeArrayIndex": "idx"}},
            {"$match": {"pokemon.shiny": True}},
        ]
    )

    for x in result:
        print(
            GameData.species_by_number(x["pokemon"]["species_id"]),
            x["pokemon"],
            x["idx"],
        )
