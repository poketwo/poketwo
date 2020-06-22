import asyncio
from functools import cached_property

import discord
from discord.ext import commands, flags

from .database import Database
from .helpers import checks, mongo


def setup(bot: commands.Bot):
    bot.add_cog(Trading(bot))


class Trading(commands.Cog):
    """For trading."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.bot.trades = {}

    @property
    def db(self) -> Database:
        return self.bot.get_cog("Database")

    async def send_trade(self, ctx: commands.Context, user: discord.Member):
        trade = self.bot.trades[user.id]
        a, b = trade["items"].keys()

        done = False

        if trade[a] and trade[b]:
            done = True
            del self.bot.trades[a]
            del self.bot.trades[b]

        a = ctx.guild.get_member(a)
        b = ctx.guild.get_member(b)

        embed = discord.Embed()
        embed.color = 0xF44336
        embed.title = f"Trade between {a.display_name} and {b.display_name}."

        if done:
            embed.title = (
                f"✅ Completed trade between {a.display_name} and {b.display_name}."
            )

        embed.set_footer(
            text="Type `p!trade add <number>` to add a pokémon, `p!trade add <number> pc` to add Pokécoins, `p!trade confirm` to confirm, or `p!trade cancel` to cancel."
        )

        for i, side in trade["items"].items():
            mem = ctx.guild.get_member(i)

            if mem is None:
                return await ctx.send(
                    "The trade has been canceled because a user has left the server."
                )

            val = "\n".join(
                f"{x} Pokécoins"
                if type(x) == int
                else f"Level {x[0].level} {x[0].species} ({x[1] + 1})"
                for x in side
            )

            sign = "🟢" if trade[i] else "🔴"

            embed.add_field(
                name=f"{sign} {mem.display_name}", value="None" if val == "" else val,
            )

        if "prev" in trade:
            try:
                await trade["prev"].delete()
            except:
                pass

        # Check if done

        embeds = []

        if done:
            bothsides = list(enumerate(trade["items"].items()))
            for idx, tup in bothsides:
                i, side = tup

                oidx, otup = bothsides[(idx + 1) % 2]
                oi, oside = otup

                mem = ctx.guild.get_member(i)
                omem = ctx.guild.get_member(oi)

                dec = 0

                member = await self.db.fetch_member_info(mem)
                omember = await self.db.fetch_member_info(omem)

                for x in side:
                    if type(x) == int:
                        await self.db.update_member(mem, {"$inc": {"balance": -x}})
                        await self.db.update_member(omem, {"$inc": {"balance": x}})
                    else:

                        pokemon, idx = x

                        if idx < member.selected:
                            dec += 1

                        if (
                            evo := pokemon.species.trade_evolution
                        ) and pokemon.held_item != 13001:
                            if (
                                evo.trigger.item is None
                                or evo.trigger.item.id == pokemon.held_item
                            ):
                                evo_embed = discord.Embed()
                                evo_embed.color = 0xF44336
                                evo_embed.title = f"Congratulations {omem.name}!"

                                name = str(pokemon.species)

                                if pokemon.nickname is not None:
                                    name += f' "{pokemon.nickname}"'

                                evo_embed.add_field(
                                    name=f"The {name} is evolving!",
                                    value=f"The {name} has turned into a {evo.target}!",
                                )

                                pokemon.species_id = evo.target.id

                                embeds.append(evo_embed)

                        await self.db.update_member(
                            mem, {"$unset": {f"pokemon.{idx}": 1}}
                        )

                        await self.db.update_member(
                            omem,
                            {
                                "$push": {
                                    "pokemon": {
                                        "species_id": pokemon.species.id,
                                        "level": pokemon.level,
                                        "xp": pokemon.xp,
                                        "nature": pokemon.nature,
                                        "iv_hp": pokemon.iv_hp,
                                        "iv_atk": pokemon.iv_atk,
                                        "iv_defn": pokemon.iv_defn,
                                        "iv_satk": pokemon.iv_satk,
                                        "iv_sdef": pokemon.iv_sdef,
                                        "iv_spd": pokemon.iv_spd,
                                        "shiny": pokemon.shiny,
                                        "held_item": pokemon.held_item,
                                    }
                                },
                            },
                        )

                await self.db.update_member(
                    mem, {"$inc": {f"selected": -dec}, "$pull": {"pokemon": None}},
                )

        # Send msg

        msg = await ctx.send(embed=embed)

        for evo_embed in embeds:
            await ctx.send(embed=evo_embed)

        trade["prev"] = msg

    @checks.has_started()
    @commands.group(aliases=["t"], invoke_without_command=True)
    async def trade(self, ctx: commands.Context, *, user: discord.Member):
        if user == ctx.author:
            return await ctx.send("Nice try...")

        if ctx.author.id in self.bot.trades:
            return await ctx.send("You are already in a trade!")

        if user.id in self.bot.trades:
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
            if ctx.author.id in self.bot.trades:
                return await ctx.send(
                    "Sorry, the user who sent the request is already in another trade."
                )

            if user.id in self.bot.trades:
                return await ctx.send(
                    "Sorry, you can't accept a trade while you're already in one!"
                )

            trade = {
                "items": {ctx.author.id: [], user.id: []},
                ctx.author.id: False,
                user.id: False,
            }
            self.bot.trades[ctx.author.id] = trade
            self.bot.trades[user.id] = trade

            await self.send_trade(ctx, ctx.author)

    @checks.has_started()
    @trade.command(aliases=["x"])
    async def cancel(self, ctx: commands.Context):
        if ctx.author.id not in self.bot.trades:
            return await ctx.send("You're not in a trade!")

        a, b = self.bot.trades[ctx.author.id]["items"].keys()
        del self.bot.trades[a]
        del self.bot.trades[b]

        await ctx.send("The trade has been canceled.")

    @checks.has_started()
    @trade.command(aliases=["c"])
    async def confirm(self, ctx: commands.Context):
        if ctx.author.id not in self.bot.trades:
            return await ctx.send("You're not in a trade!")

        self.bot.trades[ctx.author.id][ctx.author.id] = not self.bot.trades[
            ctx.author.id
        ][ctx.author.id]

        await self.send_trade(ctx, ctx.author)

    @checks.has_started()
    @trade.command(aliases=["a"])
    async def add(self, ctx: commands.Context, *args):
        if ctx.author.id not in self.bot.trades:
            return await ctx.send("You're not in a trade!")

        if len(args) <= 2 and (
            args[-1].lower().endswith("pp") or args[-1].lower().endswith("pc")
        ):

            what = args[0].replace("pp", "").replace("pc", "").strip()

            if what.isdigit():
                current = sum(
                    x
                    for x in self.bot.trades[ctx.author.id]["items"][ctx.author.id]
                    if type(x) == int
                )

                member = await self.db.fetch_member_info(ctx.author)

                if current + int(what) > member.balance:
                    return await ctx.send("You don't have enough Pokécoins for that!")

                self.bot.trades[ctx.author.id]["items"][ctx.author.id].append(int(what))

            else:
                return await ctx.send("That's not a valid item to add to the trade!")

        else:

            updated = False

            for what in args:

                if what.isdigit():

                    skip = False

                    if not 1 <= int(what) <= 2 ** 31 - 1:
                        await ctx.send(f"{what}: NO")
                        continue

                    for x in self.bot.trades[ctx.author.id]["items"][ctx.author.id]:
                        if type(x) == int:
                            continue

                        if x[1] + 1 == int(what):
                            await ctx.send(
                                f"{what}: This item is already in the trade!"
                            )
                            skip = True
                            break

                    if skip:
                        continue

                    number = int(what) - 1

                    member = await self.db.fetch_member_info(ctx.author)
                    pokemon = await self.db.fetch_pokemon(ctx.author, number)

                    if pokemon is None:
                        await ctx.send(f"{what}: Couldn't find that pokémon!")
                        continue

                    if member.selected == number:
                        await ctx.send(
                            f"{what}: You can't trade your selected pokémon!"
                        )
                        continue

                    if pokemon.favorite:
                        await ctx.send(f"{what}: You can't trade favorited pokémon!")
                        continue

                    self.bot.trades[ctx.author.id]["items"][ctx.author.id].append(
                        (pokemon, number)
                    )

                    updated = True

                else:
                    await ctx.send(
                        f"{what}: That's not a valid item to add to the trade!"
                    )
                    continue

            if not updated:
                return

        for k in self.bot.trades[ctx.author.id]:
            if type(k) == int:
                self.bot.trades[ctx.author.id][k] = False

        await self.send_trade(ctx, ctx.author)

    @checks.has_started()
    @trade.command(aliases=["r"])
    async def remove(self, ctx: commands.Context, *args):
        if ctx.author.id not in self.bot.trades:
            return await ctx.send("You're not in a trade!")

        trade = self.bot.trades[ctx.author.id]

        if len(args) <= 2 and (
            args[-1].lower().endswith("pp") or args[-1].lower().endswith("pc")
        ):

            what = args[0].replace("pp", "").replace("pc", "").strip()

            if what.isdigit():

                for idx, x in enumerate(trade["items"][ctx.author.id]):
                    if type(x) != int:
                        continue

                    if x == int(what):
                        del trade["items"][ctx.author.id][idx]
                        break
                else:
                    return await ctx.send("Couldn't find that item!")

            else:
                return await ctx.send(
                    "That's not a valid item to remove from the trade!"
                )

        else:

            updated = False

            for what in args:

                if what.isdigit():

                    for idx, x in enumerate(trade["items"][ctx.author.id]):
                        if type(x) == int:
                            continue

                        if x[1] + 1 == int(what):
                            del trade["items"][ctx.author.id][idx]
                            updated = True
                            break
                    else:
                        await ctx.send(f"{what}: Couldn't find that item!")

                else:
                    await ctx.send(
                        f"{what}: That's not a valid item to remove from the trade!"
                    )
                    continue

            if not updated:
                return

        for k in self.bot.trades[ctx.author.id]:
            if type(k) == int:
                self.bot.trades[ctx.author.id][k] = False

        await self.send_trade(ctx, ctx.author)
