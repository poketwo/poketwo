import random
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

    @property
    def db(self) -> Database:
        return self.bot.get_cog("Database")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        guild = self.db.fetch_guild(message.guild)
        guild.update(inc__counter=1)

        if guild.counter >= 10:
            guild.update(counter=0)
            await self.spawn_pokemon(await self.bot.get_context(message))

    async def spawn_pokemon(self, ctx: commands.Context):
        species = GameData.species_by_number(random.randint(1, 807))
        level = min(max(int(random.normalvariate(20, 10)), 1), 100)

        with open(Path.cwd() / "data" / "images" / f"{species.id}.png", "rb") as f:
            image = discord.File(f, filename="pokemon.png")

        embed = discord.Embed()
        embed.color = 0xF44336
        embed.title = f"A wild pokémon has appeared!"
        embed.description = (
            "Guess the pokémon and type `p!catch <pokémon>` to catch it!"
        )
        embed.set_image(url="attachment://pokemon.png")

        def check(message):
            return (
                message.channel == ctx.channel
                and message.content.lower() == f"p!catch {species}".lower()
            )

        await ctx.send(file=image, embed=embed)

        member = (await self.bot.wait_for("message", check=check)).author

        member_data = self.db.fetch_member(member)
        next_id = member_data.next_id
        member_data.update(inc__next_id=1)

        member_data.pokemon.create(
            number=member_data.next_id,
            species_id=species.id,
            level=level,
            owner_id=member.id,
        )
        member_data.save()

        await ctx.send(
            f"Congratulations {member.mention}! You caught a level {level} {species}!"
        )

        # TODO: Make sure the member already started
        # TODO: Convert into real command
