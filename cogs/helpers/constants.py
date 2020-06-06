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
    "number": lambda p: p.number,
    "iv": lambda p: -p.iv_percentage,
    "level": lambda p: -p.level,
    "abc": lambda p: p.species.name,
    "pokedex": lambda p: p.species.dex_number,
}

FILTER_BY_NUMERICAL = {
    "iv": lambda p: p.iv_percentage * 100,
    "hp": lambda p: p.hp,
    "atk": lambda p: p.atk,
    "def": lambda p: p.defn,
    "spatk": lambda p: p.satk,
    "spdef": lambda p: p.sdef,
    "spd": lambda p: p.spd,
    "hpiv": lambda p: p.iv_hp,
    "atkiv": lambda p: p.iv_atk,
    "defiv": lambda p: p.iv_defn,
    "spatkiv": lambda p: p.iv_satk,
    "spdefiv": lambda p: p.iv_sdef,
    "spdiv": lambda p: p.iv_spd,
}
