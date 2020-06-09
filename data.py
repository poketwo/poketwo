from cogs.helpers.models import *


def get_pokemon():
    path = Path.cwd() / "data" / "pokemon.csv"

    with open(path) as f:
        reader = csv.DictReader(f)
        species = [None] + list(
            {k: int(v) if v.isdigit() else v for k, v in row.items() if v != ""}
            for row in reader
        )

    pokemon = {}

    for row in species[1:]:
        if "enabled" not in row:
            continue

        evo_from = evo_to = None

        if "evo.from" in row:
            if row["evo.trigger"] == 1 and "evo.level" in row:
                trigger = LevelTrigger(int(row["evo.level"]))
            elif row["evo.trigger"] == 3:
                trigger = ItemTrigger(int(row["evo.item"]))
            else:
                trigger = OtherTrigger()

            evo_from = Evolution.evolve_from(row["evo.from"], trigger)

        if "evo.to" in row:
            evo_to = []

            for s in str(row["evo.to"]).split():
                pto = species[int(s)]

                if pto["evo.trigger"] == 1 and "evo.level" in pto:
                    trigger = LevelTrigger(int(pto["evo.level"]))
                elif pto["evo.trigger"] == 3:
                    trigger = ItemTrigger(int(pto["evo.item"]))
                else:
                    trigger = OtherTrigger()

                evo_to.append(Evolution.evolve_to(int(s), trigger))

        if evo_to and len(evo_to) == 0:
            evo_to = None

        types = []
        if "type.0" in row:
            types.append(row["type.0"])
        if "type.1" in row:
            types.append(row["type.1"])

        names = [
            ("🇯🇵", row["name.ja"]),
            ("🇯🇵", row["name.ja_r"]),
        ]

        if "name.ja_t" in row and row["name.ja_t"] != row["name.ja_r"]:
            names.append(("🇯🇵", row["name.ja_t"]))

        names += [
            ("🇬🇧", row["name.en"]),
            ("🇩🇪", row["name.de"]),
            ("🇫🇷", row["name.fr"]),
        ]

        pokemon[row["id"]] = Species(
            id=row["id"],
            names=names,
            slug=row["slug"],
            base_stats=Stats(
                row["base.hp"],
                row["base.atk"],
                row["base.def"],
                row["base.satk"],
                row["base.sdef"],
                row["base.spd"],
            ),
            types=types,
            height=int(row["height"]) / 10,
            weight=int(row["weight"]) / 10,
            mega_id=row["evo.mega"] if "evo.mega" in row else None,
            mega_x_id=row["evo.mega_x"] if "evo.mega_x" in row else None,
            mega_y_id=row["evo.mega_y"] if "evo.mega_y" in row else None,
            catchable="catchable" in row,
            dex_number=row["dex_number"],
            evolution_from=evo_from,
            evolution_to=evo_to,
            mythical="mythical" in row,
            legendary="legendary" in row,
            ultra_beast="ultra_beast" in row,
            is_form="is_form" in row,
        )

    load_pokemon(pokemon)


def get_items():
    path = Path.cwd() / "data" / "items.csv"

    with open(path) as f:
        reader = csv.DictReader(f)
        data = list(
            {k: int(v) if v.isdigit() else v for k, v in row.items() if v != ""}
            for row in reader
        )

    items = {}

    for row in data:
        items[row["id"]] = Item(
            id=row["id"],
            name=row["name"],
            description=row["description"],
            cost=row["cost"],
            page=row["page"],
            action=row["action"],
            inline=(not "separate" in row),
            emote=row.get("emote", None),
        )

    load_items(items)


def load_data():
    get_pokemon()
    get_items()


# spawns = []
# for i in range(100000):
#     spawns.append(GameData.random_spawn())

# unique = set(spawns)
# freq = [(spawns.count(k), k.id) for k in unique]

# import pprint
# pprint.pprint(sorted(freq))
