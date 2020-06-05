from cogs.helpers.models import *


def get_pokemon():
    path = Path.cwd() / "data" / "pokemon.csv"

    with open(path) as f:
        reader = csv.DictReader(f)
        species = [None] + list(
            {k: int(v) if v.isdigit() else v for k, v in row.items() if v != ""}
            for row in reader
        )

    pokemon = []

    for row in species[1:]:
        evo_from = evo_to = None

        if "evo.to" in row:
            if row["evo.trigger"] == 1 and "evo.level" in row:
                trigger = LevelTrigger(int(row["evo.level"]))
            elif row["evo.trigger"] == 3:
                trigger = ItemTrigger(int(row["evo.item"]))
            else:
                trigger = OtherTrigger

            evo_to = Evolution.evolve_to(row["evo.to"], trigger)

        if "evo.from" in row:
            pfrom = species[row["evo.from"]]

            if pfrom["evo.trigger"] == 1 and "evo.level" in pfrom:
                trigger = LevelTrigger(int(pfrom["evo.level"]))
            elif row["evo.trigger"] == 3:
                trigger = ItemTrigger(int(row["evo.item"]))
            else:
                trigger = OtherTrigger()

            evo_from = Evolution.evolve_from(row["evo.from"], trigger)

        pokemon.append(
            Species(
                id=row["id"],
                names=(
                    ("🇯🇵", row["name.ja"]),
                    ("🇯🇵", row["name.ja_r"]),
                    ("🇬🇧", row["name.en"]),
                    ("🇩🇪", row["name.de"]),
                    ("🇫🇷", row["name.fr"]),
                ),
                slug=row["slug"],
                base_stats=Stats(
                    row["base.hp"],
                    row["base.atk"],
                    row["base.def"],
                    row["base.satk"],
                    row["base.sdef"],
                    row["base.spd"],
                ),
                height=int(row["height"]) / 10,
                weight=int(row["weight"]) / 10,
                evolution_from=evo_from,
                evolution_to=evo_to,
                mythical="mythical" in row,
                legendary="legendary" in row,
                ultra_beast="ultra_beast" in row,
            )
        )

    load_pokemon(pokemon)


def get_items():
    path = Path.cwd() / "data" / "pokemon.csv"

    with open(path) as f:
        reader = csv.DictReader(f)
        data = list(
            {k: int(v) if v.isdigit() else v for k, v in row.items() if v != ""}
            for row in reader
        )

    items = []

    for row in data:
        items.append(Item(id=int(row["id"]), name=row["name"], cost=int(row["cost"])))

    load_items(items)


get_pokemon()
get_items()

# spawns = []
# for i in range(100000):
#     spawns.append(GameData.random_spawn())

# unique = set(spawns)
# freq = [(spawns.count(k), k.id) for k in unique]

# import pprint
# pprint.pprint(sorted(freq))
