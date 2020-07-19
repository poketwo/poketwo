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
    {"type": "pp", "value": 200},
    {"type": "pp", "value": 400},
    {"type": "pp", "value": 800},
    {"type": "pokemon", "value": "iv50"},
    {"type": "pokemon", "value": "iv70"},
    {"type": "pokemon", "value": "normal"},
    {"type": "pokemon", "value": "mythical"},
    {"type": "pokemon", "value": "legendary"},
    {"type": "pokemon", "value": "ultra_beast"},
    {"type": "pokemon", "value": "shiny"},
    {"type": "redeem", "value": 1},
]

REWARD_WEIGHTS = {
    "normal": [50, 10, 5, 6, 2, 25, 1, 0.5, 0.5, 0, 0],
    "great": [5, 35, 15, 25, 10, 5, 2, 1, 1, 0, 1],
    "ultra": [0, 14, 35, 24, 10, 5, 4, 2, 2, 1, 3],
}

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
            -1.86,
        ]
    },
    "level": {"$multiply": ["$pokemon.level", -1]},
    "pokedex": "$pokemon.species_id",
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

EMOJI_SERVERS = [
    # Normal
    [
        721451336847065139,
        721451386751156254,
        721451409526227015,
        721451428501127268,
        721451447178231820,
        721451469164773446,
        721451489293500488,
        721451509501395009,
        721451529407823954,
        721451548546301953,
        721451592963981343,
        721451614321246229,
        721451631606235187,
        721451649146683393,
        721451666699845693,
        721451686249496618,
        721451706239418460,
    ],
    # Shiny
    [
        722654879901941801,
        722655445558231081,
        722655648998883328,
        722655852099797053,
        724420332022136892,
        724420365300007033,
        724420399760408656,
        724420923620327514,
        730375897114214501,
        730375941494407169,
        730375972582588416,
        730376004333207614,
    ],
]


class EmojiManager:
    def __init__(self):
        self._emojis = [None]
        self._shiny = [None]
        
        #check if you have access to pokemon sprites
        self.emojiStatus = True

    async def init_emojis(self, bot):
        try: 
            for x in range(809):
                guild = bot.get_guild(EMOJI_SERVERS[0][x // 50])
                emoji = next(i for i in guild.emojis if i.name == f"pokemon_sprite_{x + 1}")

                guild = bot.get_guild(EMOJI_SERVERS[1][(x // 50) % len(EMOJI_SERVERS[1])])
                try:
                    shiny = next(
                        i
                        for i in guild.emojis
                        if i.name == f"pokemon_sprite_{x + 1}"
                        or i.name == f"pokemon_sprite_{x + 1}_shiny"
                    )
                except StopIteration:
                    shiny = emoji

                self._emojis.append(emoji)
                self._shiny.append(shiny)

            gguild = await bot.fetch_guild(725819081835544596)

            self.check = next(filter(lambda x: x.name == "green_tick", gguild.emojis))
            self.cross = next(filter(lambda x: x.name == "red_tick", gguild.emojis))
            self.gray = next(filter(lambda x: x.name == "gray_tick", gguild.emojis))

            self.gift_normal = next(
                filter(lambda x: x.name == "gift_normal", gguild.emojis)
            )
            self.gift_great = next(filter(lambda x: x.name == "gift_great", gguild.emojis))
            self.gift_ultra = next(filter(lambda x: x.name == "gift_ultra", gguild.emojis))
        except:
            print("emojis off")
            self.emojiStatus = False

    def getStatus(self):
        return self.emojiStatus

    def get(self, idx, shiny=False):
        if shiny:
            return self._shiny[idx]
        return self._emojis[idx]


EMOJIS = EmojiManager()
