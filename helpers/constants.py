import re

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
    # numbers   1   2   3   4   5   6  7   8   9   10   11   12 13
    "normal": [50, 10,  5,  0,  6,  2, 0, 25,  1, 0.5, 0.5,   0, 0],
    "great":  [ 5, 35, 15,  0, 25, 10, 0,  5,  2,   1,   1, 0.2, 1],
    "ultra":  [ 0, 15, 36,  0, 25, 11, 1,  1,  4,   3,   2, 0.2, 2],
    "master": [ 0,  0,  0, 50,  0,  0, 0,  0, 20,  15,  10,   1, 4],
}

# fmt: on


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
    "Generation VIII (Galar)": ("Grookey", "Scorbunny", "Sobble"),
}

STARTER_POKEMON = [item.lower() for l in STARTER_GENERATION.values() for item in l]

SORTING_FUNCTIONS = {
    "number": "idx",
    "iv": "iv_total",
    "level": "level",
    "pokedex": "species_id",
    "price": "market_data.price",
    "bid": "auction_data.current_bid",
    "ends": "auction_data.ends",
    "id": "_id",
}

DEFAULT_DESCENDING = {"iv", "level"}

FILTER_BY_NUMERICAL = {
    "iv": "iv_total",
    "level": "level",
    "hpiv": "iv_hp",
    "atkiv": "iv_atk",
    "defiv": "iv_defn",
    "spatkiv": "iv_satk",
    "spdefiv": "iv_sdef",
    "spdiv": "iv_spd",
}

FILTER_BY_DUPLICATES = {
    "triple": 3,
    "quadruple": 4,
    "pentuple": 5,
    "hextuple": 6,
}

IV_FIELDS = [
    "iv_hp",
    "iv_atk",
    "iv_defn",
    "iv_satk",
    "iv_sdef",
    "iv_spd",
]

NATURE_MULTIPLIERS = {
    "Hardy": {
        "hp": 1,
        "atk": 1,
        "defn": 1,
        "satk": 1,
        "sdef": 1,
        "spd": 1,
    },
    "Lonely": {
        "hp": 1,
        "atk": 1.1,
        "defn": 0.9,
        "satk": 1,
        "sdef": 1,
        "spd": 1,
    },
    "Brave": {
        "hp": 1,
        "atk": 1.1,
        "defn": 1,
        "satk": 1,
        "sdef": 1,
        "spd": 0.9,
    },
    "Adamant": {
        "hp": 1,
        "atk": 1.1,
        "defn": 1,
        "satk": 0.9,
        "sdef": 1,
        "spd": 1,
    },
    "Naughty": {
        "hp": 1,
        "atk": 1.1,
        "defn": 1,
        "satk": 1,
        "sdef": 0.9,
        "spd": 1,
    },
    "Bold": {
        "hp": 1,
        "atk": 0.9,
        "defn": 1.1,
        "satk": 1,
        "sdef": 1,
        "spd": 1,
    },
    "Docile": {
        "hp": 1,
        "atk": 1,
        "defn": 1,
        "satk": 1,
        "sdef": 1,
        "spd": 1,
    },
    "Relaxed": {
        "hp": 1,
        "atk": 1,
        "defn": 1.1,
        "satk": 1,
        "sdef": 1,
        "spd": 0.9,
    },
    "Impish": {
        "hp": 1,
        "atk": 1,
        "defn": 1.1,
        "satk": 0.9,
        "sdef": 1,
        "spd": 1,
    },
    "Lax": {
        "hp": 1,
        "atk": 1,
        "defn": 1.1,
        "satk": 1,
        "sdef": 0.9,
        "spd": 1,
    },
    "Timid": {
        "hp": 1,
        "atk": 0.9,
        "defn": 1,
        "satk": 1,
        "sdef": 1,
        "spd": 1.1,
    },
    "Hasty": {
        "hp": 1,
        "atk": 1,
        "defn": 0.9,
        "satk": 1,
        "sdef": 1,
        "spd": 1.1,
    },
    "Serious": {
        "hp": 1,
        "atk": 1,
        "defn": 1,
        "satk": 1,
        "sdef": 1,
        "spd": 1,
    },
    "Jolly": {
        "hp": 1,
        "atk": 1,
        "defn": 1,
        "satk": 0.9,
        "sdef": 1,
        "spd": 1.1,
    },
    "Naive": {
        "hp": 1,
        "atk": 1,
        "defn": 1,
        "satk": 1,
        "sdef": 0.9,
        "spd": 1.1,
    },
    "Modest": {
        "hp": 1,
        "atk": 0.9,
        "defn": 1,
        "satk": 1.1,
        "sdef": 1,
        "spd": 1,
    },
    "Mild": {
        "hp": 1,
        "atk": 1,
        "defn": 0.9,
        "satk": 1.1,
        "sdef": 1,
        "spd": 1,
    },
    "Quiet": {
        "hp": 1,
        "atk": 1,
        "defn": 1,
        "satk": 1.1,
        "sdef": 1,
        "spd": 0.9,
    },
    "Bashful": {
        "hp": 1,
        "atk": 1,
        "defn": 1,
        "satk": 1,
        "sdef": 1,
        "spd": 1,
    },
    "Rash": {
        "hp": 1,
        "atk": 1,
        "defn": 1,
        "satk": 1.1,
        "sdef": 0.9,
        "spd": 1,
    },
    "Calm": {
        "hp": 1,
        "atk": 0.9,
        "defn": 1,
        "satk": 1,
        "sdef": 1.1,
        "spd": 1,
    },
    "Gentle": {
        "hp": 1,
        "atk": 1,
        "defn": 0.9,
        "satk": 1,
        "sdef": 1.1,
        "spd": 1,
    },
    "Sassy": {
        "hp": 1,
        "atk": 1,
        "defn": 1,
        "satk": 1,
        "sdef": 1.1,
        "spd": 0.9,
    },
    "Careful": {
        "hp": 1,
        "atk": 1,
        "defn": 1,
        "satk": 0.9,
        "sdef": 1.1,
        "spd": 1,
    },
    "Quirky": {
        "hp": 1,
        "atk": 1,
        "defn": 1,
        "satk": 1,
        "sdef": 1,
        "spd": 1,
    },
}


URL_REGEX = re.compile(r"(([a-z]{3,6}://)|(^|\s))([a-zA-Z0-9\-]+\.)+[a-z]{2,13}[\.\?\=\&\%\/\w\-]*\b([^@]|$)")

PINK = 0xFE9AC9
BLUE = 0x9CCFFF
