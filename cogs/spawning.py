import random
import time
from functools import cached_property
from pathlib import Path

import discord
from discord.ext import commands

from .database import Database
from .helpers import checks
from .helpers.models import GameData


class Spawning(commands.Cog):
    """For basic bot operation."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.pokemon = {}
        self.users = {}
        self.guilds = {}

    @cached_property
    def db(self) -> Database:
        return self.bot.get_cog("Database")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        current = time.time()

        # Spamcheck, every two seconds

        if self.bot.env != "dev":
            if current - self.users.get(message.author.id, 0) < 2:
                return

        self.users[message.author.id] = current

        # Increase XP on selected pokemon

        member = self.db.fetch_member(message.author)
        pokemon = member.selected_pokemon
        pokemon.xp += random.randint(10, 40)
        member.save()

        if pokemon.xp > pokemon.max_xp:
            pokemon.level += 1
            pokemon.xp -= pokemon.max_xp
            member.save()

            embed = discord.Embed()
            embed.color = 0xF44336
            embed.title = f"Congratulations {message.author.name}!"
            embed.description = f"Your {pokemon.species} is now level {pokemon.level}!"

            await message.channel.send(embed=embed)

        # Increment guild activity counter

        self.guilds[message.guild.id] = self.guilds.get(message.guild.id, 0) + 1

        if self.guilds[message.guild.id] >= 5 if self.bot.env == "dev" else 20:
            self.guilds[message.guild.id] = 0

            guild = self.db.fetch_guild(message.guild)

            if guild.channel is not None:
                channel = message.guild.get_channel(guild.channel)
            else:
                channel = message.channel

            await self.spawn_pokemon(channel)

    async def spawn_pokemon(self, channel):
        # Get random species and level, add to tracker

        species = GameData.random_spawn()
        level = min(max(int(random.normalvariate(20, 10)), 1), 100)

        self.pokemon[channel.id] = (species, level)

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
    async def catch(self, ctx: commands.Context, guess: str):
        # Retrieve correct species and level from tracker

        if ctx.channel.id not in self.pokemon:
            return

        species, level = self.pokemon[ctx.channel.id]

        if guess.lower() != species.name.lower():
            return await ctx.send("That is the wrong pokémon!")

        # Correct guess, add to database

        del self.pokemon[ctx.channel.id]

        member_data = self.db.fetch_member(ctx.author)
        next_id = member_data.next_id
        member_data.update(inc__next_id=1)

        member_data.pokemon.create(
            number=member_data.next_id,
            species_id=species.id,
            level=level,
            owner_id=ctx.author.id,
        )
        member_data.save()

        await ctx.send(
            f"Congratulations {ctx.author.mention}! You caught a level {level} {species}!"
        )

    @checks.is_admin()
    @commands.command()
    async def redirect(self, ctx: commands.Context, channel: discord.TextChannel):
        guild = self.db.fetch_guild(ctx.guild)
        guild.update(channel=channel.id)

        await ctx.send(f"Now redirecting all pokémon spawns to {channel.mention}")
