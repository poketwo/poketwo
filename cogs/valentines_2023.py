import random
from datetime import datetime
from urllib.parse import urlencode, urljoin

import discord
from discord.ext import commands

from cogs import mongo
from helpers import checks
from helpers.context import ConfirmationYesNoView, SelectView
from helpers.converters import FetchUserConverter
from helpers.utils import write_fp

JOIN_DATE = datetime(2023, 2, 11)


class SelectImageView(SelectView):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.curr = 0
        self.remove_item(self.select)

    def build_embed(self):
        option = self.select.options[self.curr]
        embed = self.message.embeds[0]
        embed.description = option.label
        embed.set_image(url=f"https://assets.poketwo.net/valentines_2023/{option.value}")
        return embed

    @discord.ui.button(emoji="\N{BLACK LEFT-POINTING TRIANGLE}\ufe0f")
    async def previous(self, interaction, button):
        self.curr -= 1
        self.curr %= len(self.select.options)
        await interaction.response.edit_message(embed=self.build_embed())

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.success)
    async def confirm(self, interaction, button):
        await interaction.response.defer()
        if self.message:
            await self.message.edit(view=None)
        self.result = [self.select.options[self.curr].value]
        self.stop()
        if self.delete_after:
            await self.message.delete()

    @discord.ui.button(emoji="\N{BLACK RIGHT-POINTING TRIANGLE}\ufe0f")
    async def next(self, interaction, button):
        self.curr += 1
        self.curr %= len(self.select.options)
        await interaction.response.edit_message(embed=self.build_embed())


class Valentines(commands.Cog):
    """Valentine's Day 2023 commands."""

    def __init__(self, bot):
        self.bot = bot

    @commands.group(aliases=("event", "valentines"), invoke_without_command=True)
    async def valentine(self, ctx):
        """View Valentine's Day 2023 event info."""

        author_data = await self.bot.mongo.fetch_member_info(ctx.author)
        species = self.bot.data.species_by_number(50089)
        embed = discord.Embed(
            title="Valentine's Day 2023 \N{HEART WITH RIBBON}",
            description="Cupid time is almost here, but wait...? He forgot his bow and arrow! Decidueye is taking his place in the Pokétwo world, celebrating Valentine's and spreading love!",
            color=0xFF6F77,
        )
        embed.set_thumbnail(url=species.image_url)
        embed.add_field(
            name="Cupid Decidueye Gifts",
            value=f"`{ctx.clean_prefix}valentine gift <ID/@User> <message>`\n"
            f"• You may purchase up to 5 gifts (remaining: {5 - author_data.valentines_purchased_2023}).\n"
            "• Each gift comes with a **customizable Valentine's Day card!**\n"
            "• The first gift costs 5,000 Pokécoins.\n"
            "• Additional gifts cost 10,000 Pokécoins each.\n",
            inline=False,
        )
        embed.add_field(
            name="Requirements",
            value="Trainers (both gifters and receivers) must have started Pokétwo prior to February 11, 2023 to participate.",
            inline=False,
        )
        await ctx.send(embed=embed)

    async def generate_pokemon(self, user, nickname):
        user_data = await self.bot.mongo.fetch_member_info(user)

        species = self.bot.data.species_by_number(50089)
        shiny = user_data.determine_shiny(species)
        level = min(max(int(random.normalvariate(20, 10)), 1), 100)
        ivs = [mongo.random_iv() for i in range(6)]

        return self.bot.mongo.Pokemon.build_from_mongo(
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
                "nickname": nickname,
            }
        )

    @checks.has_started()
    @valentine.command()
    async def gift(self, ctx, user: FetchUserConverter, *, message):
        """Send a Valentine's Day Card + Cupid Decidueye Gift to someone!"""

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
        if author_data.valentines_purchased_2023 >= 5:
            return await ctx.send("You have already purchased the maximum number of gifts!")

        price = 5000 if author_data.valentines_purchased_2023 == 0 else 10000
        if author_data.balance < price:
            return await ctx.send("You don't have enough Pokécoins for that!")

        query = {"to": f"To: {user}", "message": message}

        # Select Background

        embed = discord.Embed(title="Select a Card Background", description="Background 1", color=0xFF6F77)
        embed.set_author(icon_url=ctx.author.display_avatar.url, name=str(ctx.author))
        embed.set_image(url=f"https://assets.poketwo.net/valentines_2023/bg1.png")
        options = [discord.SelectOption(label=f"Background {i}", value=f"bg{i}.png") for i in range(1, 6)]
        result = await ctx.select(embed=embed, options=options, cls=SelectImageView, delete_after=True)
        if result is None:
            return await ctx.send("Time's up. Aborted.")

        query["bg"] = result[0]

        # Select Border

        embed = discord.Embed(title="Select a Card Overlay", description="Overlay 1", color=0xFF6F77)
        embed.set_author(icon_url=ctx.author.display_avatar.url, name=str(ctx.author))
        embed.set_image(url=f"https://assets.poketwo.net/valentines_2023/border1.png")
        options = [discord.SelectOption(label=f"Overlay {i}", value=f"border{i}.png") for i in range(1, 6)]
        result = await ctx.select(embed=embed, options=options, cls=SelectImageView, delete_after=True)
        if result is None:
            return await ctx.send("Time's up. Aborted.")

        query["border"] = result[0]

        # Anonymous?

        result = await ctx.confirm(
            f"{ctx.author.mention} Would you like this card to be anonymous?",
            cls=ConfirmationYesNoView,
            delete_after=True,
        )
        if result is None:
            return await ctx.send("Time's up. Aborted.")

        query["from"] = "From: Anonymous" if result else f"From: {ctx.author}"

        # Generate & Confirm

        url = urljoin(self.bot.config.SERVER_URL, f"valentines_day_2023?{urlencode(query)}")
        async with self.bot.http_session.get(url) as resp:
            if resp.status == 200:
                arr = await self.bot.loop.run_in_executor(None, write_fp, await resp.read())
                image = discord.File(arr, filename="card.png")
            else:
                return await ctx.send("Something went wrong while generating your card. Please try again later.")

        embed = discord.Embed(
            title="Your Valentine's Card",
            description=f"Are you sure you would like to send this card to **{user}** for for **{price:,} Pokécoins**?",
            color=0xFF6F77,
        )
        embed.set_author(icon_url=ctx.author.display_avatar.url, name=str(ctx.author))
        embed.set_image(url="attachment://card.png")

        result = await ctx.confirm(file=image, embed=embed, delete_after=True)
        if result is None:
            return await ctx.send("Time's up. Aborted.")

        # Send

        author_data = await self.bot.mongo.fetch_member_info(ctx.author)
        if author_data.balance < price:
            return await ctx.send("You don't have enough Pokécoins for that!")

        await self.bot.mongo.update_member(ctx.author, {"$inc": {"balance": -price, "valentines_purchased_2023": 1}})

        pokemon = await self.generate_pokemon(user, query["from"])

        embed = discord.Embed(
            title="You have received a Valentine's Day Card!",
            description=f"It came with a **{pokemon}**!",
            color=0xFF6F77,
        )
        embed.set_image(url="attachment://card.png")
        image.reset()

        try:
            await user.send(file=image, embed=embed)
        except discord.HTTPException:
            return await ctx.send("I could not send your card to that user! The user might have their DMs off.")

        await self.bot.mongo.db.pokemon.insert_one(pokemon.to_mongo())
        await ctx.send("Your gift has been sent.")


async def setup(bot: commands.Bot):
    await bot.add_cog(Valentines(bot))
