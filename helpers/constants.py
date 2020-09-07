BOXES = {"n": "normal", "g": "great", "u": "ultra", "m": "master"}

NUMBER_REACTIONS = [
    "0️⃣",
    "1️⃣",
    "2️⃣",
    "3️⃣",
    "4️⃣",
    "5️⃣",
    "6️⃣",
    "7️⃣",
    "8️⃣",
    "9️⃣",
    "🔟",
]

LETTER_REACTIONS = [
    "🇦",
    "🇧",
    "🇨",
    "🇩",
    "🇪",
    "🇫",
    "🇬",
    "🇭",
    "🇮",
    "🇯",
    "🇰",
    "🇱",
    "🇲",
    "🇳",
    "🇴",
    "🇵",
    "🇶",
    "🇷",
    "🇸",
    "🇹",
    "🇺",
    "🇻",
    "🇼",
    "🇽",
    "🇾",
    "🇿",
]

REWARDS = [
    {"type": "pp", "value": 200},  # 1
    {"type": "pp", "value": 400},  # 2
    {"type": "pp", "value": 800},  # 3
    {"type": "pp", "value": 1600},  # 4
    {"type": "pokemon", "value": "iv1"},  # 5
    {"type": "pokemon", "value": "iv2"},  # 6
    {"type": "pokemon", "value": "iv3"},  # 7
    {"type": "pokemon", "value": "normal"},  # 8
    {"type": "pokemon", "value": "mythical"},  # 9
    {"type": "pokemon", "value": "legendary"},  # 10
    {"type": "pokemon", "value": "ultra_beast"},  # 11
    {"type": "pokemon", "value": "shiny"},  # 12
    {"type": "redeem", "value": 1},  # 13
]

# fmt: off
REWARD_WEIGHTS = {
    # numbers   1   2   3   4   5   6   7   8   9    10    11    12  13
    "normal": [50, 10,  5,  0,  6,  2,  0, 25,  1,  0.5,  0.5,  0.0,  0],
    "great":  [ 5, 35, 15,  0, 25, 10,  0,  5,  2,  1.0,  1.0,  0.2,  1],
    "ultra":  [ 0, 15, 36,  0, 25, 11,  1,  1,  4,  1.8,  2.0,  0.2,  3],
    "master": [ 0, 0,   0, 35,  0,  0,  0,  0, 20,   20,   20,    1,  4],
}

# fmt: on

TYPES = [
    None,
    "Normal",
    "Fighting",
    "Flying",
    "Poison",
    "Ground",
    "Rock",
    "Bug",
    "Ghost",
    "Steel",
    "Fire",
    "Water",
    "Grass",
    "Electric",
    "Psychic",
    "Ice",
    "Dragon",
    "Dark",
    "Fairy",
    "???",
    "Shadow",
]

DAMAGE_CLASSES = [None, "Status", "Physical", "Special"]

MOVE_AILMENTS = {
    -1: "????",
    0: "none",
    1: "Paralysis",
    2: "Sleep",
    3: "Freeze",
    4: "Burn",
    5: "Poison",
    6: "Confusion",
    7: "Infatuation",
    8: "Trap",
    9: "Nightmare",
    12: "Torment",
    13: "Disable",
    14: "Yawn",
    15: "Heal Block",
    17: "No type immunity",
    18: "Leech Seed",
    19: "Embargo",
    20: "Perish Song",
    21: "Ingrain",
    24: "Silence",
}

TYPE_EFFICACY = [
    None,
    [None, 1, 1, 1, 1, 1, 0.5, 1, 0, 0.5, 1, 1, 1, 1, 1, 1, 1, 1, 1],
    [None, 2, 1, 0.5, 0.5, 1, 2, 0.5, 0, 2, 1, 1, 1, 1, 0.5, 2, 1, 2, 0.5],
    [None, 1, 2, 1, 1, 1, 0.5, 2, 1, 0.5, 1, 1, 2, 0.5, 1, 1, 1, 1, 1],
    [None, 1, 1, 1, 0.5, 0.5, 0.5, 1, 0.5, 0, 1, 1, 2, 1, 1, 1, 1, 1, 2],
    [None, 1, 1, 0, 2, 1, 2, 0.5, 1, 2, 2, 1, 0.5, 2, 1, 1, 1, 1, 1],
    [None, 1, 0.5, 2, 1, 0.5, 1, 2, 1, 0.5, 2, 1, 1, 1, 1, 2, 1, 1, 1],
    [None, 1, 0.5, 0.5, 0.5, 1, 1, 1, 0.5, 0.5, 0.5, 1, 2, 1, 2, 1, 1, 2, 0.5],
    [None, 0, 1, 1, 1, 1, 1, 1, 2, 1, 1, 1, 1, 1, 2, 1, 1, 0.5, 1],
    [None, 1, 1, 1, 1, 1, 2, 1, 1, 0.5, 0.5, 0.5, 1, 0.5, 1, 2, 1, 1, 2],
    [None, 1, 1, 1, 1, 1, 0.5, 2, 1, 2, 0.5, 0.5, 2, 1, 1, 2, 0.5, 1, 1],
    [None, 1, 1, 1, 1, 2, 2, 1, 1, 1, 2, 0.5, 0.5, 1, 1, 1, 0.5, 1, 1],
    [None, 1, 1, 0.5, 0.5, 2, 2, 0.5, 1, 0.5, 0.5, 2, 0.5, 1, 1, 1, 0.5, 1, 1],
    [None, 1, 1, 2, 1, 0, 1, 1, 1, 1, 1, 2, 0.5, 0.5, 1, 1, 0.5, 1, 1],
    [None, 1, 2, 1, 2, 1, 1, 1, 1, 0.5, 1, 1, 1, 1, 0.5, 1, 1, 0, 1],
    [None, 1, 1, 2, 1, 2, 1, 1, 1, 0.5, 0.5, 0.5, 2, 1, 1, 0.5, 2, 1, 1],
    [None, 1, 1, 1, 1, 1, 1, 1, 1, 0.5, 1, 1, 1, 1, 1, 1, 2, 1, 0],
    [None, 1, 0.5, 1, 1, 1, 1, 1, 2, 1, 1, 1, 1, 1, 2, 1, 1, 0.5, 0.5],
    [None, 1, 2, 1, 0.5, 1, 1, 1, 1, 0.5, 0.5, 1, 1, 1, 1, 1, 2, 2, 1],
]

MOVE_META_CATEGORIES = [
    "Inflicts damage",
    "No damage; inflicts status ailment",
    "No damage; lowers target's stats or raises user's stats",
    "No damage; heals the user",
    "Inflicts damage; inflicts status ailment",
    "No damage; inflicts status ailment; raises target's stats",
    "Inflicts damage; lowers target's stats",
    "Inflicts damage; raises user's stats",
    "Inflicts damage; absorbs damage done to heal the user",
    "One-hit KO",
    "Effect on the whole field",
    "Effect on one side of the field",
    "Forces target to switch out",
    "Unique effect",
]

STAT_STAGE_MULTIPLIERS = {
    -6: 2 / 8,
    -5: 2 / 7,
    -4: 2 / 6,
    -3: 2 / 5,
    -2: 2 / 4,
    -1: 2 / 3,
    0: 2 / 2,
    1: 3 / 2,
    2: 4 / 2,
    3: 5 / 2,
    4: 6 / 2,
    5: 7 / 2,
    6: 8 / 2,
}

STAT_NAMES = {
    "hp": "HP",
    "atk": "Attack",
    "defn": "Defense",
    "satk": "Sp. Atk",
    "sdef": "Sp. Def",
    "spd": "Speed",
    "evasion": "Evasion",
    "accuracy": "Accuracy",
    "crit": "Critical Hit",
}

MOVE_TARGETS = [
    None,
    "One specific move. How this move is chosen depends upon on the move being used.",
    "One other Pokémon on the field, selected by the trainer. Stolen moves reuse the same target.",
    "The user's ally (if any).",
    "The user's side of the field. Affects the user and its ally (if any).",
    "Either the user or its ally, selected by the trainer.",
    "The opposing side of the field. Affects opposing Pokémon.",
    "The user.",
    "One opposing Pokémon, selected at random.",
    "Every other Pokémon on the field.",
    "One other Pokémon on the field, selected by the trainer.",
    "All opposing Pokémon.",
    "The entire field. Affects all Pokémon.",
    "The user and its allies.",
    "Every Pokémon on the field.",
]

NATURES = [
    "Adamant",
    "Bashful",
    "Bold",
    "Brave",
    "Calm",
    "Careful",
    "Docile",
    "Gentle",
    "Hardy",
    "Hasty",
    "Impish",
    "Jolly",
    "Lax",
    "Lonely",
    "Mild",
    "Modest",
    "Naive",
    "Naughty",
    "Quiet",
    "Quirky",
    "Rash",
    "Relaxed",
    "Sassy",
    "Serious",
    "Timid",
]

STARTER_GENERATION = {
    "Generation I (Kanto)": ("Bulbasaur", "Charmander", "Squirtle"),
    "Generation II (Johto)": ("Chikorita", "Cyndaquil", "Totodile"),
    "Generation III (Hoenn)": ("Treecko", "Torchic", "Mudkip"),
    "Generation IV (Sinnoh)": ("Turtwig", "Chimchar", "Piplup"),
    "Generation V (Unova)": ("Snivy", "Tepig", "Oshawott"),
    "Generation VI (Kalos)": ("Chespin", "Fennekin", "Froakie"),
    "Generation VII (Alola)": ("Rowlet", "Litten", "Popplio"),
}

STARTER_POKEMON = [item.lower() for l in STARTER_GENERATION.values() for item in l]

SORTING_FUNCTIONS = {
    "number": "$idx",
    "iv": {
        "$divide": [
            {
                "$add": [
                    "$pokemon.iv_hp",
                    "$pokemon.iv_atk",
                    "$pokemon.iv_defn",
                    "$pokemon.iv_satk",
                    "$pokemon.iv_sdef",
                    "$pokemon.iv_spd",
                ]
            },
            1.86,
        ]
    },
    "level": "$pokemon.level",
    "pokedex": "$pokemon.species_id",
    "price": "$price",
}

FILTER_BY_NUMERICAL = {
    "iv": {
        "$divide": [
            {
                "$add": [
                    "$pokemon.iv_hp",
                    "$pokemon.iv_atk",
                    "$pokemon.iv_defn",
                    "$pokemon.iv_satk",
                    "$pokemon.iv_sdef",
                    "$pokemon.iv_spd",
                ]
            },
            1.86,
        ]
    },
    "level": "$pokemon.level",
    "hpiv": "$pokemon.iv_hp",
    "atkiv": "$pokemon.iv_atk",
    "defiv": "$pokemon.iv_defn",
    "spatkiv": "$pokemon.iv_satk",
    "spdefiv": "$pokemon.iv_sdef",
    "spdiv": "$pokemon.iv_spd",
}

NATURE_MULTIPLIERS = {
    "Hardy": {"hp": 1, "atk": 1, "defn": 1, "satk": 1, "sdef": 1, "spd": 1,},
    "Lonely": {"hp": 1, "atk": 1.1, "defn": 0.9, "satk": 1, "sdef": 1, "spd": 1,},
    "Brave": {"hp": 1, "atk": 1.1, "defn": 1, "satk": 1, "sdef": 1, "spd": 0.9,},
    "Adamant": {"hp": 1, "atk": 1.1, "defn": 1, "satk": 0.9, "sdef": 1, "spd": 1,},
    "Naughty": {"hp": 1, "atk": 1.1, "defn": 1, "satk": 1, "sdef": 0.9, "spd": 1,},
    "Bold": {"hp": 1, "atk": 0.9, "defn": 1.1, "satk": 1, "sdef": 1, "spd": 1,},
    "Docile": {"hp": 1, "atk": 1, "defn": 1, "satk": 1, "sdef": 1, "spd": 1,},
    "Relaxed": {"hp": 1, "atk": 1, "defn": 1.1, "satk": 1, "sdef": 1, "spd": 0.9,},
    "Impish": {"hp": 1, "atk": 1, "defn": 1.1, "satk": 0.9, "sdef": 1, "spd": 1,},
    "Lax": {"hp": 1, "atk": 1, "defn": 1.1, "satk": 1, "sdef": 0.9, "spd": 1,},
    "Timid": {"hp": 1, "atk": 0.9, "defn": 1, "satk": 1, "sdef": 1, "spd": 1.1,},
    "Hasty": {"hp": 1, "atk": 1, "defn": 0.9, "satk": 1, "sdef": 1, "spd": 1.1,},
    "Serious": {"hp": 1, "atk": 1, "defn": 1, "satk": 1, "sdef": 1, "spd": 1,},
    "Jolly": {"hp": 1, "atk": 1, "defn": 1, "satk": 0.9, "sdef": 1, "spd": 1.1,},
    "Naive": {"hp": 1, "atk": 1, "defn": 1, "satk": 1, "sdef": 0.9, "spd": 1.1,},
    "Modest": {"hp": 1, "atk": 0.9, "defn": 1, "satk": 1.1, "sdef": 1, "spd": 1,},
    "Mild": {"hp": 1, "atk": 1, "defn": 0.9, "satk": 1.1, "sdef": 1, "spd": 1,},
    "Quiet": {"hp": 1, "atk": 1, "defn": 1, "satk": 1.1, "sdef": 1, "spd": 0.9,},
    "Bashful": {"hp": 1, "atk": 1, "defn": 1, "satk": 1, "sdef": 1, "spd": 1,},
    "Rash": {"hp": 1, "atk": 1, "defn": 1, "satk": 1.1, "sdef": 0.9, "spd": 1,},
    "Calm": {"hp": 1, "atk": 0.9, "defn": 1, "satk": 1, "sdef": 1.1, "spd": 1,},
    "Gentle": {"hp": 1, "atk": 1, "defn": 0.9, "satk": 1, "sdef": 1.1, "spd": 1,},
    "Sassy": {"hp": 1, "atk": 1, "defn": 1, "satk": 1, "sdef": 1.1, "spd": 0.9,},
    "Careful": {"hp": 1, "atk": 1, "defn": 1, "satk": 0.9, "sdef": 1.1, "spd": 1,},
    "Quirky": {"hp": 1, "atk": 1, "defn": 1, "satk": 1, "sdef": 1, "spd": 1,},
}
