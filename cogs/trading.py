import asyncio
from functools import cached_property

import discord
from discord.ext import commands, flags

from .database import Database
from .helpers import checks, mongo
from .helpers.models import *


class Trading(commands.Cog):
    """For trading."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.users = {}

    @property
    def db(self) -> Database:
        return self.bot.get_cog("Database")

    async def send_trade(self, ctx: commands.Context, user: discord.Member):
        trade = self.users[f"{ctx.guild.id}-{user.id}"]
        a, b = trade["items"].keys()

        done = False

        if trade[a] and trade[b]:
            done = True
            del self.users[f"{ctx.guild.id}-{a}"]
            del self.users[f"{ctx.guild.id}-{b}"]

        a = ctx.guild.get_member(a)
        b = ctx.guild.get_member(b)

        embed = discord.Embed()
        embed.color = 0xF44336
        embed.title = f"Trade between {a.display_name} and {b.display_name}."

        if done:
            embed.title = (
                f"✅ Completed trade between {a.display_name} and {b.display_name}."
            )

        embed.description = "Type **p!trade add <number>** to add a pokémon, **p!trade add <number> pp** to add Poképoints, or **p!trade confirm** to confirm."

        for i, side in trade["items"].items():
            mem = ctx.guild.get_member(i)

            if mem is None:
                return await ctx.send(
                    "The trade has been canceled because a user has left the server."
                )

            if i == "prev":
                continue

            val = "\n".join(
                f"{x} Poképoints" if type(x) == int else f"Level {x.level} {x.species}"
                for x in side
            )

            sign = "🟢" if trade[i] else "🔴"

            embed.add_field(
                name=f"{sign} {mem.display_name}", value="None" if val == "" else val,
            )

        if "prev" in trade:
            await trade["prev"].delete()

        # Check if done

        if done:
            bothsides = list(enumerate(trade["items"].items()))
            for idx, tup in bothsides:
                i, side = tup

                oidx, otup = bothsides[(idx + 1) % 2]
                oi, oside = otup

                mem = ctx.guild.get_member(i)
                omem = ctx.guild.get_member(oi)

                print(i, oi)

                for x in side:
                    if type(x) == int:
                        await self.db.update_member(mem, {"$inc": {"balance": -x}})
                        await self.db.update_member(omem, {"$inc": {"balance": x}})
                    else:
                        omember = await self.db.fetch_member_info(omem)

                        await self.db.update_member(
                            mem, {"$pull": {"pokemon": {"number": x.number}}}
                        )

                        await self.db.update_member(
                            omem,
                            {
                                "$inc": {"next_id": 1},
                                "$push": {
                                    "pokemon": {
                                        "number": omember.next_id,
                                        "species_id": x.species.id,
                                        "level": x.level,
                                        "xp": x.xp,
                                        "owner_id": omem.id,
                                        "nature": x.nature,
                                        "iv_hp": x.iv_hp,
                                        "iv_atk": x.iv_atk,
                                        "iv_defn": x.iv_defn,
                                        "iv_satk": x.iv_satk,
                                        "iv_sdef": x.iv_sdef,
                                        "iv_spd": x.iv_spd,
                                    }
                                },
                            },
                        )

        # Send msg

        msg = await ctx.send(embed=embed)
        trade["prev"] = msg

    @checks.has_started()
    @commands.group(aliases=["t"], invoke_without_command=True)
    async def trade(self, ctx: commands.Context, *, user: discord.Member):
        if user == ctx.author:
            return await ctx.send("Nice try...")

        if ctx.author.id in self.users:
            return await ctx.send("You are already in a trade!")

        if user.id in self.users:
            return await ctx.send(f"**{user}** is already in a trade!")

        member = await mongo.Member.find_one({"id": user.id})

        if member is None:
            return await ctx.send("That user hasn't picked a starter pokémon yet!")

        message = await ctx.send(
            f"Requesting a trade with {user.mention}. Click the checkmark to accept!"
        )
        await message.add_reaction("✅")

        def check(reaction, u):
            return u == user and str(reaction.emoji) == "✅"

        try:
            await self.bot.wait_for("reaction_add", timeout=30, check=check)
        except asyncio.TimeoutError:
            await message.add_reaction("❌")
            await ctx.send("The request to trade has timed out.")
        else:
            trade = {
                "items": {ctx.author.id: [], user.id: []},
                ctx.author.id: False,
                user.id: False,
            }
            self.users[f"{ctx.guild.id}-{ctx.author.id}"] = trade
            self.users[f"{ctx.guild.id}-{user.id}"] = trade

            await self.send_trade(ctx, ctx.author)

    @checks.has_started()
    @trade.command()
    async def cancel(self, ctx: commands.Context):
        if f"{ctx.guild.id}-{ctx.author.id}" not in self.users:
            return await ctx.send("You're not in a trade!")

        a, b = self.users[f"{ctx.guild.id}-{ctx.author.id}"]["items"].keys()
        del self.users[f"{ctx.guild.id}-{a}"]
        del self.users[f"{ctx.guild.id}-{b}"]

        await ctx.send("The trade has been canceled.")

    @checks.has_started()
    @trade.command()
    async def confirm(self, ctx: commands.Context):
        if f"{ctx.guild.id}-{ctx.author.id}" not in self.users:
            return await ctx.send("You're not in a trade!")

        self.users[f"{ctx.guild.id}-{ctx.author.id}"][ctx.author.id] = not self.users[
            f"{ctx.guild.id}-{ctx.author.id}"
        ][ctx.author.id]

        await self.send_trade(ctx, ctx.author)

    @checks.has_started()
    @trade.command()
    async def add(self, ctx: commands.Context, *, what: str):
        if f"{ctx.guild.id}-{ctx.author.id}" not in self.users:
            return await ctx.send("You're not in a trade!")

        if what.isdigit():
            t = await self.db.fetch_pokemon(ctx.author, int(what))

            if t is None:
                return await ctx.send("Couldn't find a pokémon with that number!")

            self.users[f"{ctx.guild.id}-{ctx.author.id}"]["items"][
                ctx.author.id
            ].append(t.pokemon[0])

        elif what.lower().endswith("pp"):
            num = what.replace("pp", "").strip()

            if num.isdigit():
                current = sum(
                    x
                    for x in self.users[f"{ctx.guild.id}-{ctx.author.id}"]["items"][
                        ctx.author.id
                    ]
                    if type(x) == int
                )

                member = await self.db.fetch_member_info(ctx.author)

                if current + int(num) > member.balance:
                    return await ctx.send("You don't have enough Poképoints for that!")

                self.users[f"{ctx.guild.id}-{ctx.author.id}"]["items"][
                    ctx.author.id
                ].append(int(num))

            else:
                return await ctx.send("That's not a valid item to add to the trade!")

        else:
            return await ctx.send("That's not a valid item to add to the trade!")

        await self.send_trade(ctx, ctx.author)
