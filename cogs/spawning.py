import random
import time
from functools import cached_property
from pathlib import Path

import discord
from discord.ext import commands
from mongoengine import DoesNotExist

from .database import Database
from .helpers import checks
from .helpers.models import GameData, LevelTrigger, deaccent


class Spawning(commands.Cog):
    """For basic bot operation."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.pokemon = {}
        self.users = {}
        self.cooldown = {}
        self.guilds = {}

    @cached_property
    def db(self) -> Database:
        return self.bot.get_cog("Database")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        guild = self.db.fetch_guild(message.guild)

        if self.bot.user in message.mentions:
            await message.channel.send(
                f"My prefix is `{guild.prefix or 'p!'}` in this server."
            )

        current = time.time()

        # Spamcheck, every two seconds

        if self.bot.env != "dev":
            if current - self.users.get(message.author.id, 0) < 2:
                return

        self.users[message.author.id] = current

        # Increase XP on selected pokemon

        try:
            member = self.db.fetch_member(message.author)
            pokemon = member.selected_pokemon

            if pokemon.level < 100 and pokemon.xp <= pokemon.max_xp:
                pokemon.xp += random.randint(10, 40)

                if member.boost_active:
                    pokemon.xp += random.randint(10, 40)

            member.save()

            if pokemon.xp > pokemon.max_xp and pokemon.level < 100:
                pokemon.level += 1
                pokemon.xp -= pokemon.max_xp
                member.save()

                embed = discord.Embed()
                embed.color = 0xF44336
                embed.title = f"Congratulations {message.author.name}!"
                embed.description = (
                    f"Your {pokemon.species} is now level {pokemon.level}!"
                )

                if pokemon.species.primary_evolution is not None:
                    if pokemon.level >= pokemon.species.primary_evolution.trigger.level:
                        embed.add_field(
                            name=f"Your {pokemon.species} is evolving!",
                            value=f"Your {pokemon.species} has turned into a {pokemon.species.primary_evolution.target}!",
                        )
                        pokemon.species_id = pokemon.species.primary_evolution.target_id
                        member.save()

                await message.channel.send(embed=embed)
            elif pokemon.level == 100:
                pokemon.xp = pokemon.max_xp
                member.save()

        except DoesNotExist:
            pass

        # Increment guild activity counter

        if self.bot.env != "dev":
            if current - self.cooldown.get(message.guild.id, 0) < 1:
                return

        self.cooldown[message.guild.id] = current

        self.guilds[message.guild.id] = self.guilds.get(message.guild.id, 0) + 1

        if self.guilds[message.guild.id] >= (5 if self.bot.env == "dev" else 15):
            self.guilds[message.guild.id] = 0

            if guild.channel is not None:
                channel = message.guild.get_channel(guild.channel)
            else:
                channel = message.channel

            await self.spawn_pokemon(channel)

    async def spawn_pokemon(self, channel):
        # Get random species and level, add to tracker

        species = GameData.random_spawn()
        level = min(max(int(random.normalvariate(20, 10)), 1), 100)

        inds = [i for i, x in enumerate(species.name) if x.isalpha()]
        blanks = random.sample(inds, len(inds) // 2)

        hint = "".join([x if i in blanks else "\_" for i, x in enumerate(species.name)])

        self.pokemon[channel.id] = (species, level, hint)

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

        species, level, hint = self.pokemon[ctx.channel.id]
        await ctx.send(f"The pokémon is {hint}.")

    @checks.has_started()
    @commands.command()
    async def catch(self, ctx: commands.Context, *, guess: str):
        """Catch a wild pokémon."""

        # Retrieve correct species and level from tracker

        if ctx.channel.id not in self.pokemon:
            return

        species, level, hint = self.pokemon[ctx.channel.id]

        if deaccent(guess.lower()) not in species.correct_guesses:
            return await ctx.send("That is the wrong pokémon!")

        # Correct guess, add to database

        del self.pokemon[ctx.channel.id]

        member = self.db.fetch_member(ctx.author)
        next_id = member.next_id
        member.update(inc__next_id=1)

        member.pokemon.create(
            number=member.next_id,
            species_id=species.id,
            level=level,
            owner_id=ctx.author.id,
        )

        message = f"Congratulations {ctx.author.mention}! You caught a level {level} {species}!"

        if str(species.id) not in member.pokedex:
            member.pokedex[str(species.id)] = 1
            member.save()

            message += " Added to Pokédex. You received 35 credits!"
            member.update(inc__balance=35)
        else:
            member.pokedex[str(species.id)] += 1
            member.save()

            if member.pokedex[str(species.id)] == 10:
                message += f" This is your 10th {species}! You received 350 credits."
                member.update(inc__balance=350)

            elif member.pokedex[str(species.id)] == 100:
                message += f" This is your 100th {species}! You received 3500 credits."
                member.update(inc__balance=3500)

            elif member.pokedex[str(species.id)] == 1000:
                message += (
                    f" This is your 1000th {species}! You received 35000 credits."
                )
                member.update(inc__balance=35000)

        await ctx.send(message)

    @checks.is_admin()
    @commands.command()
    async def redirect(self, ctx: commands.Context, *, channel: discord.TextChannel):
        """Redirect pokémon catches to one channel."""

        guild = self.db.fetch_guild(ctx.guild)
        guild.update(channel=channel.id)

        await ctx.send(f"Now redirecting all pokémon spawns to {channel.mention}")
