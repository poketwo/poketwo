import asyncio
import random
from datetime import datetime, timedelta

import discord
from discord.ext import commands
from helpers import checks, constants, converters, models, mongo

from .database import Database


class Halloween(commands.Cog):
    """Halloween event commands."""

    def __init__(self, bot):
        self.bot = bot

    @property
    def db(self) -> Database:
        return self.bot.get_cog("Database")

    @checks.has_started()
    @commands.command(aliases=["event"])
    async def halloween(self, ctx: commands.Context):
        """View halloween event information."""

        member = await self.db.fetch_member_info(ctx.author)

        embed = self.bot.Embed()
        embed.title = f"Spooktober Event"
        embed.description = "It's spooky season! Join us this month to earn special rewards, including exclusive event pokémon!"
        embed.set_thumbnail(url="https://i.imgur.com/3YB6ldP.png")
        embed.add_field(
            name=f"{self.bot.sprites.candy_halloween} Candies — {member.halloween_tickets}",
            value=(
                # f"**Your Candies:** {member.halloween_tickets}\n"
                "Earn candy by voting and completing tasks, and exchange them for rewards on Halloween!\n"
            ),
            inline=False,
        )
        embed.add_field(
            name=f"{self.bot.sprites.quest_trophy} Quests",
            value=f"Check back soon for some special quests!",
            inline=False,
        )
        await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(Halloween(bot))
