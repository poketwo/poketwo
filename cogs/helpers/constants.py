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

HELP = {
    "0": {
        "title": "Pokétwo Help",
        "description": "Use `p!help <page>` to view different pages of the help command.",
        "fields": {
            "Page 1": "Getting Started",
            "Page 2": "Main Commands",
            "Page 3": "Shop & Trading",
            "Page 4": "Settings",
            "Page 5": "Miscellaneous",
        },
    },
    "1": {
        "title": "Help · Getting Started",
        "description": "Here are some basic tips to get you started with Pokétwo!",
        "fields": {
            "What is Pokétwo?": "Pokétwo is a Pokémon-oriented Discord bot that lets you collect pokémon! You can catch pokémon in the wild, level your pokémon, compete with your friends, and more.",
            "Getting Started": "To get started, type **p!start**! I'll show you a list of starter pokémon you can choose from. After you make your decision, start your journey by typing **p!pick <pokémon>**.",
            "Catching Pokémon": "Pokémon will spawn randomly in servers based on chat activity. When a pokémon pops up, you'll have to guess which pokémon it is based on the picture and type **p!catch <pokémon>** to catch it! If you're successful, I will let you know.",
            "Viewing Pokémon": "To view all the pokémon you've caught, type **p!pokemon**! Every pokémon you catch is assigned a number specific to you, which is used to identify the pokémon. You can also type **p!info** to view your selected pokémon, **p!info <number>**, or **p!info latest**.",
            "Selecting Pokémon": "You can select one pokémon at a time to level up, evolve, and do other actions with. Every time you talk, your selected pokémon will gain XP, and if it has enough, it will level up! Change your selected pokémon with **p!select <number>**.",
        },
    },
    "2": {
        "title": "Help · Main Commands",
        "description": "Here are Pokétwo's main commands.",
        "fields": {
            "p!pokemon": "View a list of your pokémon. This command has many options.",
            "p!order": "Change the order pokémon are listed.",
            "p!pokedex": "View your pokédex, or view the pokédex entry for a specific species.",
            "p!info": "View a specific pokémon.",
            "p!select": "Change your selected pokémon.",
            "p!nickname": "Set a nickname for your pokémon.",
            "p!favorite": "Mark a pokémon as favorite.",
            "p!catch": "Catch a pokémon in the wild.",
            "p!hint": "Get a hint for a pokémon in the wild.",
        },
    },
    "3": {
        "title": "Help · Shop & Trading",
        "description": "Here are shop- and trading-related commands!",
        "fields": {
            "p!shop": "View the Pokétwo shop.",
            "p!buy": "Buy an item from the shop.",
            "p!balance": "View your current balance in credits.",
            "p!trade": "*Coming soon*",
        },
    },
    "4": {
        "title": "Help · Settings",
        "description": "Here are some settings you can change for the bot.",
        "fields": {
            "p!prefix": "Set the server-wide prefix for the bot. You can always ping me to remember the current prefix.",
            "p!redirect": "Redirect server-wide pokémon spawns to a specific channel.",
            "p!silence": "Silence your own level up messages.",
        },
    },
    "5": {
        "title": "Help · Miscellaneous",
        "description": "These are some commands that don't fit into the other categories.",
        "fields": {
            "p!help": "View this menu.",
            "p!invite": "Invite the bot to a server or join the Pokétwo Official Server.",
            "p!redeem": "Use a redeem to receive a pokémon of your choice.",
            "p!ping": "Measure the bot's latency.",
            "p!stats": "View some interesting statistics about the bot.",
        },
    },
}
