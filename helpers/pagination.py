import discord
from discord.ext import commands
import re

paginators = {}


class Paginator:
    def __init__(self, get_page, num_pages):
        self.num_pages = num_pages
        self.get_page = get_page
        self.last_page = 0
        self.message = None
        self.author = None

    async def delete(self):
        try:
            await self.message.delete()
        except:
            pass

    async def end(self):
        try:
            del paginators[self.author.id]
        except:
            pass

    async def send(self, bot, ctx, pidx: int):
        async def clear(msg):
            return await ctx.send(msg)

        self.author = ctx.author
        paginators[self.author.id] = self

        embed = await self.get_page(pidx, clear)

        if not isinstance(embed, discord.Embed):
            return
        
        prefix = re.sub(f"<@!?{ctx.me.id}>", f"@{ctx.me.name}", ctx.prefix)

        try:
            embed.set_footer(
                text=embed.footer.text
                + f"\nUse {prefix}n and {prefix}b to navigate between pages."
            )
        except TypeError:
            embed.set_footer(
                text=f"\nUse {prefix}n and {prefix}b to navigate between pages."
            )
        self.message = await ctx.send(embed=embed)
        self.last_page = pidx

        # if self.num_pages > 1:

        #     await self.message.add_reaction("⏮️")
        #     await self.message.add_reaction("◀")
        #     await self.message.add_reaction("▶")
        #     await self.message.add_reaction("⏭️")
        #     await self.message.add_reaction("🔢")
        #     await self.message.add_reaction("⏹")

        #     try:
        #         while True:
        #             reaction, user = await bot.wait_for(
        #                 "reaction_add",
        #                 check=lambda r, u: r.message.id == self.message.id
        #                 and u.id == self.author.id,
        #                 timeout=120,
        #             )
        #             try:
        #                 await reaction.remove(user)
        #             except:
        #                 pass

        #             if reaction.emoji == "⏹":
        #                 await self.delete()
        #                 await self.end()
        #                 return

        #             elif reaction.emoji == "🔢":
        #                 ask_message = await ctx.send(
        #                     "What page would you like to go to?"
        #                 )
        #                 message = await bot.wait_for(
        #                     "message",
        #                     check=lambda m: m.author == self.author
        #                     and m.channel == ctx.channel,
        #                     timeout=30,
        #                 )
        #                 try:
        #                     pidx = (int(message.content) - 1) % self.num_pages
        #                 except ValueError:
        #                     await ctx.send("That's not a valid page number!")
        #                     continue

        #                 bot.loop.create_task(ask_message.delete())
        #                 bot.loop.create_task(message.delete())

        #             else:
        #                 pidx = {
        #                     "⏮️": 0,
        #                     "◀": pidx - 1,
        #                     "▶": pidx + 1,
        #                     "⏭️": self.num_pages - 1,
        #                 }[reaction.emoji] % self.num_pages

        #             embed = await self.get_page(pidx, clear)
        #             await self.message.edit(embed=embed)

        #     except asyncio.TimeoutError:
        #         await self.message.add_reaction("❌")
        #         try:
        #             del paginators[self.author.id]
        #         except KeyError:
        #             pass
