import random
from datetime import datetime

import discord
from discord.ext import commands
from helpers import checks

from cogs import mongo

JOIN_DATE = datetime(2022, 1, 14)


class Valentines(commands.Cog):
    """Valentines event commands."""

    def __init__(self, bot):
        self.bot = bot

    @commands.group(aliases=("event", "valentines"), invoke_without_command=True)
    async def valentine(self, ctx):
        author_data = await self.bot.mongo.fetch_member_info(ctx.author)
        species = self.bot.data.species_by_number(50058)
        embed = discord.Embed(
            title="Valentine's Day 2022 \N{HEART WITH RIBBON}",
            description="It's that time of year again. Purchase a Valentine's Nidoran for that special someone, or simply a friend!",
            color=0xFF6F77,
        )
        embed.set_thumbnail(url=species.image_url)
        embed.add_field(
            name="Nidoran Gifts",
            value=f"`{ctx.prefix}valentine gift <@user> [message]`\n"
            f"• You may purchase up to 5 gifts (remaining: {5 - author_data.valentines_purchased}).\n"
            "• The first gift costs 5,000 Pokécoins.\n"
            "• Additional gifts cost 10,000 Pokécoins each.\n",
            inline=False,
        )
        embed.add_field(
            name="Requirements",
            value="Trainers (both gifters and receivers) must have started Pokétwo prior to January 14, 2022 to participate.",
            inline=False,
        )
        await ctx.send(embed=embed)

    @checks.has_started()
    @valentine.command(rest_is_raw=True)
    async def gift(self, ctx, user: discord.Member, *, message):
        if user == ctx.author:
            return await ctx.send("You cannot gift yourself!")

        author_data = await self.bot.mongo.fetch_member_info(ctx.author)
        user_data = await self.bot.mongo.fetch_member_info(user)

        # Checks

        if user_data is None:
            return await ctx.send("That user has not picked a starter Pokémon!")

        if author_data.joined_at is not None and author_data.joined_at >= JOIN_DATE:
            return await ctx.send("Your account is not old enough to participate in this event.")
        if user_data.joined_at is not None and user_data.joined_at > JOIN_DATE:
            return await ctx.send("That account is not old enough to participate in this event.")
        if author_data.valentines_purchased >= 5:
            return await ctx.send("You have already purchased the maximum number of gifts!")

        price = 5000 if author_data.valentines_purchased == 0 else 10000
        if author_data.balance < price:
            return await ctx.send("You don't have enough Pokécoins for that!")

        # Confirm

        if not await ctx.confirm(
            f"Are you sure you would like to gift {user.mention} a **Valentine's Nidoran** for **{price:,} Pokécoins**?"
        ):
            return await ctx.send("Aborted.")

        # Go

        species = self.bot.data.species_by_number(50058)
        shiny = user_data.determine_shiny(species)
        level = min(max(int(random.normalvariate(20, 10)), 1), 100)

        ivs = [mongo.random_iv() for i in range(6)]

        author_data = await self.bot.mongo.fetch_member_info(ctx.author)
        if author_data.balance < price:
            return await ctx.send("You don't have enough Pokécoins for that!")
        if author_data.valentines_purchased >= 5:
            return await ctx.send("You have already purchased the maximum number of gifts!")
        await self.bot.mongo.update_member(ctx.author, {"$inc": {"balance": -price, "valentines_purchased": 1}})

        await self.bot.mongo.db.pokemon.insert_one(
            {
                "owner_id": user.id,
                "owned_by": "user",
                "species_id": species.id,
                "level": level,
                "xp": 0,
                "nature": mongo.random_nature(),
                "iv_hp": ivs[0],
                "iv_atk": ivs[1],
                "iv_defn": ivs[2],
                "iv_satk": ivs[3],
                "iv_sdef": ivs[4],
                "iv_spd": ivs[5],
                "iv_total": sum(ivs),
                "moves": [],
                "shiny": shiny,
                "idx": await self.bot.mongo.fetch_next_idx(user),
                "nickname": f"Gift from {ctx.author}",
            }
        )

        embed = discord.Embed(
            title="Valentine's Day Card \N{HEART WITH RIBBON}",
            description=message.strip() or "Happy Valentine's Day!",
            color=0xFF6F77,
        )
        embed.set_author(name=ctx.author, icon_url=ctx.author.display_avatar.url)
        embed.set_image(url=species.image_url)
        embed.set_footer(text="You have received a Valentine's Nidoran.")
        await user.send(embed=embed)

        await ctx.send("Your gift has been sent.")


async def setup(bot: commands.Bot):
    await bot.add_cog(Valentines(bot))
