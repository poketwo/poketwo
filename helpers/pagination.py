import asyncio

from discord.ext import commands


paginators = {}


class Paginator:
    def __init__(self, get_page, num_pages):
        self.num_pages = num_pages
        self.get_page = get_page
        self.last_page = None

    async def send(self, bot: commands.Bot, ctx: commands.Context, pidx: int):
        async def clear(msg):
            return await ctx.send(msg)

        paginators[ctx.author.id] = self

        self.last_page = pidx

        embed = await self.get_page(pidx, clear)

        message = await ctx.send(embed=embed)

        if self.num_pages > 1:

            await message.add_reaction("⏮️")
            await message.add_reaction("◀")
            await message.add_reaction("▶")
            await message.add_reaction("⏭️")

            try:
                while True:
                    reaction, user = await bot.wait_for(
                        "reaction_add",
                        check=lambda r, u: r.message.id == message.id
                        and u.id == ctx.author.id,
                        timeout=120,
                    )
                    try:
                        await reaction.remove(user)
                    except:
                        pass

                    pidx = {
                        "⏮️": 0,
                        "◀": pidx - 1,
                        "▶": pidx + 1,
                        "⏭️": self.num_pages - 1,
                    }[reaction.emoji] % self.num_pages

                    embed = await self.get_page(pidx, clear)
                    await message.edit(embed=embed)

            except asyncio.TimeoutError:
                await message.add_reaction("❌")
                del paginators[ctx.author.id]
