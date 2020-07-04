import random
import time
from datetime import datetime, timedelta
from functools import cached_property
from pathlib import Path

import discord
from discord.ext import commands

from .database import Database
from .helpers import checks, models, mongo


def setup(bot: commands.Bot):
    bot.add_cog(Spawning(bot))


class Spawning(commands.Cog):
    """For basic bot operation."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

        if not hasattr(self.bot, "spawns"):
            self.bot.spawns = {}

        self.bot.cooldown_users = {}
        self.bot.cooldown_guilds = {}
        self.bot.redeem = {}

        if not hasattr(self.bot, "guild_counter"):
            self.bot.guild_counter = {}

    @property
    def db(self) -> Database:
        return self.bot.get_cog("Database")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        try:
            await self.handle_message(message)
        except discord.Forbidden:
            pass

    async def handle_message(self, message: discord.Message):
        if message.guild is None:
            return

        if not self.bot.enabled:
            return

        if message.author.bot:
            return

        if self.bot.user in message.mentions:
            prefix = await self.bot.get_cog("Bot").determine_prefix(message)
            if type(prefix) == list:
                prefix = prefix[0]
            await message.channel.send(f"My prefix is `{prefix}` in this server.")

        current = time.time()

        # Spamcheck, every two seconds

        if self.bot.env != "dev":
            if current - self.bot.cooldown_users.get(message.author.id, 0) < 1:
                return

        self.bot.cooldown_users[message.author.id] = current

        # Increase XP on selected pokemon

        member = await self.db.fetch_member_info(message.author)

        if member is not None:
            pokemon = await self.db.fetch_pokemon(message.author, member.selected)

            if pokemon is not None and pokemon.held_item != 13002:

                if pokemon.level < 100 and pokemon.xp <= pokemon.max_xp:
                    xp_inc = random.randint(10, 40)

                    if member.boost_active or message.guild.id == 716390832034414685:
                        xp_inc *= 2

                    await self.db.update_member(
                        message.author,
                        {"$inc": {f"pokemon.{member.selected}.xp": xp_inc},},
                    )

                if pokemon.xp > pokemon.max_xp and pokemon.level < 100:
                    update = {
                        "$set": {
                            f"pokemon.{member.selected}.xp": 0,
                            f"pokemon.{member.selected}.level": pokemon.level + 1,
                        }
                    }
                    embed = discord.Embed()
                    embed.color = 0xF44336
                    embed.title = f"Congratulations {message.author.name}!"

                    name = str(pokemon.species)

                    if pokemon.nickname is not None:
                        name += f' "{pokemon.nickname}"'

                    embed.description = f"Your {name} is now level {pokemon.level + 1}!"

                    if (
                        pokemon.species.level_evolution is not None
                        and pokemon.held_item != 13001
                        and pokemon.level + 1
                        >= pokemon.species.level_evolution.trigger.level
                    ):
                        embed.add_field(
                            name=f"Your {name} is evolving!",
                            value=f"Your {name} has turned into a {pokemon.species.level_evolution.target}!",
                        )
                        update["$set"][
                            f"pokemon.{member.selected}.species_id"
                        ] = pokemon.species.level_evolution.target_id

                        if member.silence and pokemon.level < 99:
                            await message.author.send(embed=embed)

                    else:
                        c = 0
                        for move in pokemon.species.moves:
                            if move.method.level == pokemon.level + 1:
                                embed.add_field(
                                    name=f"New move!",
                                    value=f"Your {name} can now learn {move.move.name}!",
                                )
                                c += 1

                        for i in range(-c % 3):
                            embed.add_field(
                                name="‎", value="‎",
                            )

                    await self.db.update_member(message.author, update)

                    if member.silence and pokemon.level == 99:
                        await message.author.send(embed=embed)

                    if not member.silence:
                        await message.channel.send(embed=embed)

                elif pokemon.level == 100:
                    await self.db.update_member(
                        message.author,
                        {"$set": {f"pokemon.{member.selected}.xp": pokemon.max_xp}},
                    )

        # Increment guild activity counter

        if not message.guild:
            return

        if self.bot.env != "dev":
            if current - self.bot.cooldown_guilds.get(message.guild.id, 0) < 1:
                return

        self.bot.cooldown_guilds[message.guild.id] = current
        self.bot.guild_counter[message.guild.id] = (
            self.bot.guild_counter.get(message.guild.id, 0) + 1
        )

        if self.bot.guild_counter[message.guild.id] >= (
            5 if self.bot.env == "dev" else 15
        ):
            self.bot.guild_counter[message.guild.id] = 0
            guild = await self.db.fetch_guild(message.guild)

            if guild.channel is not None:
                channel = message.guild.get_channel(guild.channel)
            else:
                channel = message.channel

            if message.guild.id == 716390832034414685 and self.bot.env != "dev":
                channel, channel2 = [
                    self.bot.get_channel(x)
                    for x in random.sample(
                        [
                            717095398476480562,
                            720020140401360917,
                            720231680564264971,
                            724762012453961810,
                            724762035094683718,
                            728867911799668747,
                        ],
                        2,
                    )
                ]

                await self.spawn_pokemon(self.bot.get_channel(720944005856100452))

                if channel2.id not in self.bot.redeem or datetime.now() - self.bot.redeem[
                    channel2.id
                ] > timedelta(
                    minutes=1
                ):
                    await self.spawn_pokemon(channel2)

            if channel.id not in self.bot.redeem or datetime.now() - self.bot.redeem[
                channel.id
            ] > timedelta(minutes=1):
                await self.spawn_pokemon(channel)

    async def spawn_pokemon(self, channel, species=None, shiny=None):
        # Get random species and level, add to tracker

        if species is None:
            species = models.GameData.random_spawn()

        level = min(max(int(random.normalvariate(20, 10)), 1), 100)

        inds = [i for i, x in enumerate(species.name) if x.isalpha()]
        blanks = random.sample(inds, len(inds) // 2)

        main = models.GameData.species_by_number(species.dex_number)

        hint = "".join(x if i in blanks else "\_" for i, x in enumerate(main.name))

        self.bot.spawns[channel.id] = (species, level, hint, shiny, [])

        # Fetch image and send embed

        with open(Path.cwd() / "data" / "images" / f"{species.id}.png", "rb") as f:
            image = discord.File(f, filename="pokemon.png")

        embed = discord.Embed()
        embed.color = 0xF44336
        embed.title = f"A wild pokémon has appeared!"
        embed.description = (
            "Guess the pokémon and type `p!catch <pokémon>` to catch it!"
        )
        embed.set_image(url="attachment://pokemon.png")

        await channel.send(file=image, embed=embed)

    @checks.has_started()
    @commands.command()
    async def hint(self, ctx: commands.Context):
        """Get a hint for the wild pokémon."""

        if ctx.channel.id not in self.bot.spawns:
            return

        hint = self.bot.spawns[ctx.channel.id][2]

        await ctx.send(f"The pokémon is {hint}.")

    @checks.has_started()
    @commands.command()
    async def catch(self, ctx: commands.Context, *, guess: str):
        """Catch a wild pokémon."""

        # Retrieve correct species and level from tracker

        if ctx.channel.id not in self.bot.spawns:
            return

        species, level, hint, shiny, users = self.bot.spawns[ctx.channel.id]

        if models.deaccent(guess.lower()) not in species.correct_guesses:
            return await ctx.send("That is the wrong pokémon!")

        # Correct guess, add to database

        if ctx.channel.id == 720944005856100452:
            if ctx.author.id in users:
                return await ctx.send("You have already caught this pokémon!")

            users.append(ctx.author.id)
        else:
            del self.bot.spawns[ctx.channel.id]

        member = await self.db.fetch_member_info(ctx.author)

        if shiny is None:
            shiny = random.randint(1, 4096) == 1

        await self.db.update_member(
            ctx.author,
            {
                "$inc": {"shinies_caught": 1 if shiny else 0},
                "$push": {
                    "pokemon": {
                        "species_id": species.id,
                        "level": level,
                        "xp": 0,
                        "nature": mongo.random_nature(),
                        "iv_hp": mongo.random_iv(),
                        "iv_atk": mongo.random_iv(),
                        "iv_defn": mongo.random_iv(),
                        "iv_satk": mongo.random_iv(),
                        "iv_sdef": mongo.random_iv(),
                        "iv_spd": mongo.random_iv(),
                        "shiny": shiny,
                    }
                },
            },
        )

        message = f"Congratulations {ctx.author.mention}! You caught a level {level} {species}!"

        memberp = await self.db.fetch_pokedex(
            ctx.author, species.dex_number, species.dex_number + 1
        )

        if str(species.dex_number) not in memberp.pokedex:
            message += " Added to Pokédex. You received 35 Pokécoins!"

            await self.db.update_member(
                ctx.author,
                {
                    "$set": {f"pokedex.{species.dex_number}": 1},
                    "$inc": {"balance": 35},
                },
            )

        else:
            inc_bal = 0

            if memberp.pokedex[str(species.dex_number)] + 1 == 10:
                message += f" This is your 10th {species}! You received 350 Pokécoins."
                inc_bal = 350

            elif memberp.pokedex[str(species.dex_number)] + 1 == 100:
                message += (
                    f" This is your 100th {species}! You received 3500 Pokécoins."
                )
                inc_bal = 3500

            elif memberp.pokedex[str(species.dex_number)] + 1 == 1000:
                message += (
                    f" This is your 1000th {species}! You received 35000 Pokécoins."
                )
                inc_bal = 35000

            await self.db.update_member(
                ctx.author,
                {"$inc": {"balance": inc_bal, f"pokedex.{species.dex_number}": 1},},
            )

        if shiny:
            message += "\n\nThese colors seem unusual... ✨"

        await ctx.send(message)

    @commands.command()
    async def silence(self, ctx: commands.Context):
        """Silence level up messages."""

        member = await self.db.fetch_member_info(ctx.author)

        await self.db.update_member(
            ctx.author, {"$set": {"silence": not member.silence}}
        )

        if member.silence:
            await ctx.send(f"Reverting to normal level up behavior.")
        else:
            await ctx.send(
                f"I'll no longer send level up messages. You'll receive a DM when your pokémon evolves or reaches level 100."
            )

    @checks.is_admin()
    @commands.command()
    async def redirect(self, ctx: commands.Context, *, channel: discord.TextChannel):
        """Redirect pokémon catches to one channel."""

        await self.db.update_guild(ctx.guild, {"$set": {"channel": channel.id}})

        await ctx.send(f"Now redirecting all pokémon spawns to {channel.mention}")
