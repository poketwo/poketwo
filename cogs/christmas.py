from discord.ext import commands
from helpers import checks


class Christmas(commands.Cog):
    """For the Christmas event"""

    def __init__(self, bot):
        self.bot = bot

    @checks.has_started()
    @commands.command()
    async def event(self, ctx):
        """Christmas Event"""
        embed = self.bot.Embed(color=0x9CCFFF)
        embed.title = f"12 Days of Christmas"
        embed.description = (
            "It's the holiday season! Some specially dressed pokémon will be visiting "
            "your servers for these twelve days. Keep your eyes peeled for these "
            "event pokémon, as they won't be available for long!"
        )
        embed.add_field(name="Day 1: December 25", value="Festive Sudowoodo")
        embed.add_field(name="Day 2: December 26", value="Festive Pidove")
        embed.add_field(name="Day 3: December 27", value="Festive Torchic")
        embed.add_field(name="Day 4: December 28", value="Festive Murkrow")
        embed.add_field(name="Day 5: December 29", value="Festive Hoopa")
        embed.add_field(name="Day 6: December 30", value="Festive Farfetch'd")
        embed.add_field(name="Day 7: December 31", value="Festive Swanna")
        embed.add_field(name="Day 8: January 1", value="Festive Miltank")
        embed.add_field(name="Day 9: January 2", value="Festive Gardevoir")
        embed.add_field(name="Day 10: January 3", value="Festive Gallade")
        embed.add_field(name="Day 11: January 4", value="Festive Igglybuff")
        embed.add_field(name="Day 12: January 5", value="Festive Cubone")
        await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(Christmas(bot))
