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
        {"$unwind": {"path": "$pokemon"}},
        {
            "$project": {
                "iv": {
                    "$sum": [
                        "$pokemon.iv_atk",
                        "$pokemon.iv_defn",
                        "$pokemon.iv_hp",
                        "$pokemon.iv_satk",
                        "$pokemon.iv_sdef",
                        "$pokemon.iv_spd",
                    ]
                },
                "species": "$pokemon.species_id",
            }
        },
        {"$sort": {"iv": -1}},
        {"$limit": 100},
    ],
    allowDiskUse=True,
)

for x in result:
    # print(x)
    print("{:.02f}%".format(x["iv"] / 186 * 100), GameData.species_by_number(x["species"]))
