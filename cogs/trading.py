import asyncio
import math
from datetime import datetime

import discord
from discord.ext import commands, flags

from helpers import checks, pagination

from .database import Database


class Trading(commands.Cog):
    """For trading."""

    def __init__(self, bot):
        self.bot = bot

        if not hasattr(self.bot, "trades"):
            self.bot.trades = {}

    @property
    def db(self) -> Database:
        return self.bot.get_cog("Database")

    async def send_trade(self, ctx: commands.Context, user: discord.Member):
        # TODO this code is pretty shit. although it does work

        trade = self.bot.trades[user.id]
        a, b = trade["items"].keys()

        done = False

        if trade[a] and trade[b] and not trade["executing"]:
            done = True
            trade["executing"] = True

        a = ctx.guild.get_member(a) or await ctx.guild.fetch_member(a)
        b = ctx.guild.get_member(b) or await ctx.guild.fetch_member(b)

        num_pages = max(math.ceil(len(x) / 20) for x in trade["items"].values())

        if done:
            execmsg = await ctx.send("Executing trade...")

        async def get_page(pidx, clear):
            embed = self.bot.Embed()
            embed.title = f"Trade between {a.display_name} and {b.display_name}."

            if done:
                embed.title = (
                    f"✅ Completed trade between {a.display_name} and {b.display_name}."
                )

            embed.set_footer(
                text=f"Type `{ctx.prefix}trade add <number>` to add a pokémon, `{ctx.prefix}trade add <number> pc` to add Pokécoins, `{ctx.prefix}trade confirm` to confirm, or `{ctx.prefix}trade cancel` to cancel."
            )

            for i, fullside in trade["items"].items():
                mem = ctx.guild.get_member(i) or await ctx.guild.fetch_member(i)

                side = fullside[pidx * 20 : (pidx + 1) * 20]

                if mem is None:
                    return await ctx.send("The trade has been canceled.")

                try:
                    maxn = max(x[1] + 1 for x in side if type(x) != int)
                except ValueError:
                    maxn = 0

                def padn(idx, n):
                    return " " * (len(str(n)) - len(str(idx))) + str(idx)

                def txt(x):
                    val = f"`{padn(x[1] + 1, maxn)}`　**{x[0].species}**"
                    if x[0].shiny:
                        val += " ✨"
                    val += f"　•　Lvl. {x[0].level}　•　{x[0].iv_percentage:.2%}"
                    return val

                val = "\n".join(
                    f"{x:,} Pokécoins" if type(x) == int else txt(x) for x in side
                )

                if val == "":
                    if len(fullside) == 0:
                        val = "None"
                    else:
                        val = "None on this page"

                sign = "🟢" if trade[i] else "🔴"

                embed.add_field(name=f"{sign} {mem.display_name}", value=val)

            embed.set_footer(text=f"Showing page {pidx + 1} out of {num_pages}.")

            return embed

        # Check if done

        embeds = []

        if done:
            try:
                bothsides = list(enumerate(trade["items"].items()))
                for idx, tup in bothsides:
                    i, side = tup

                    oidx, otup = bothsides[(idx + 1) % 2]
                    oi, oside = otup

                    mem = ctx.guild.get_member(i) or await ctx.guild.fetch_member(i)
                    omem = ctx.guild.get_member(oi) or await ctx.guild.fetch_member(oi)

                    dec = 0

                    member = await self.db.fetch_member_info(mem)
                    omember = await self.db.fetch_member_info(omem)

                    idxs = set()

                    for x in side:
                        if type(x) == int:
                            await self.db.update_member(mem, {"$inc": {"balance": -x}})
                            await self.db.update_member(omem, {"$inc": {"balance": x}})
                        else:

                            pokemon, idx = x

                            if idx in idxs:
                                continue

                            idxs.add(idx)

                            if idx < member.selected:
                                dec += 1

                            if (
                                pokemon.species.trade_evolution
                            ) and pokemon.held_item != 13001:
                                evo = pokemon.species.trade_evolution
                                if (
                                    evo.trigger.item is None
                                    or evo.trigger.item.id == pokemon.held_item
                                ):
                                    evo_embed = self.bot.Embed()
                                    evo_embed.title = (
                                        f"Congratulations {omem.display_name}!"
                                    )

                                    name = str(pokemon.species)

                                    if pokemon.nickname is not None:
                                        name += f' "{pokemon.nickname}"'

                                    evo_embed.add_field(
                                        name=f"The {name} is evolving!",
                                        value=f"The {name} has turned into a {evo.target}!",
                                    )

                                    pokemon.species_id = evo.target.id

                                    embeds.append(evo_embed)

                            await self.db.update_pokemon(
                                pokemon,
                                {
                                    "$set": {
                                        "owner_id": omem.id,
                                        "timestamp": datetime.now(),
                                    }
                                },
                            )

                    await self.db.update_member(mem, {"$inc": {f"selected": -dec}})
            except:
                del self.bot.trades[a.id]
                del self.bot.trades[b.id]
                raise

            try:
                await execmsg.delete()
            except:
                pass

            del self.bot.trades[a.id]
            del self.bot.trades[b.id]

        # Send msg

        paginator = pagination.Paginator(get_page, num_pages=num_pages)
        self.bot.loop.create_task(paginator.send(self.bot, ctx, 0))

        for evo_embed in embeds:
            await ctx.send(embed=evo_embed)

    @checks.has_started()
    @commands.group(aliases=["t"], invoke_without_command=True)
    async def trade(self, ctx: commands.Context, *, user: discord.Member):
        """Trade pokémon with another trainer."""

        if user == ctx.author:
            return await ctx.send("Nice try...")

        if ctx.author.id in self.bot.trades:
            return await ctx.send("You are already in a trade!")

        if user.id in self.bot.trades:
            return await ctx.send(f"**{user}** is already in a trade!")

        member = await self.bot.mongo.Member.find_one({"id": user.id})

        if member is None:
            return await ctx.send("That user hasn't picked a starter pokémon yet!")

        message = await ctx.send(
            f"Requesting a trade with {user.mention}. Click the checkmark to accept!"
        )
        await message.add_reaction("✅")

        def check(reaction, u):
            return (
                reaction.message.id == message.id
                and u == user
                and str(reaction.emoji) == "✅"
            )

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
                "channel": ctx.channel,
                "executing": False,
            }
            self.bot.trades[ctx.author.id] = trade
            self.bot.trades[user.id] = trade

            await self.send_trade(ctx, ctx.author)

    @checks.has_started()
    @trade.command(aliases=["x"])
    async def cancel(self, ctx: commands.Context):
        """Cancel a trade."""

        if ctx.author.id not in self.bot.trades:
            return await ctx.send("You're not in a trade!")

        if self.bot.trades[ctx.author.id]["executing"]:
            return await ctx.send("The trade is currently loading...")

        a, b = self.bot.trades[ctx.author.id]["items"].keys()
        del self.bot.trades[a]
        del self.bot.trades[b]

        await ctx.send("The trade has been canceled.")

    @checks.has_started()
    @trade.command(aliases=["c"])
    async def confirm(self, ctx: commands.Context):
        """Confirm a trade."""

        if ctx.author.id not in self.bot.trades:
            return await ctx.send("You're not in a trade!")

        if self.bot.trades[ctx.author.id]["executing"]:
            return await ctx.send("The trade is currently loading...")

        self.bot.trades[ctx.author.id][ctx.author.id] = not self.bot.trades[
            ctx.author.id
        ][ctx.author.id]

        await self.send_trade(ctx, ctx.author)

    @checks.has_started()
    @trade.command(aliases=["a"])
    async def add(self, ctx: commands.Context, *args):
        """Add an item to a trade."""

        if ctx.author.id not in self.bot.trades:
            return await ctx.send("You're not in a trade!")

        if ctx.channel.id != self.bot.trades[ctx.author.id]["channel"].id:
            return await ctx.send("You must be in the same channel to add items!")

        if self.bot.trades[ctx.author.id]["executing"]:
            return await ctx.send("The trade is currently loading...")

        if len(args) == 0:
            return

        self.bot.trades[ctx.author.id]["executing"] = True

        if len(args) <= 2 and (
            args[-1].lower().endswith("pp") or args[-1].lower().endswith("pc")
        ):

            what = args[0].replace("pp", "").replace("pc", "").replace(",", "").strip()

            if what.isdigit():
                current = sum(
                    x
                    for x in self.bot.trades[ctx.author.id]["items"][ctx.author.id]
                    if type(x) == int
                )

                member = await self.db.fetch_member_info(ctx.author)

                if current + int(what) > member.balance:
                    self.bot.trades[ctx.author.id]["executing"] = False
                    return await ctx.send("You don't have enough Pokécoins for that!")

                self.bot.trades[ctx.author.id]["items"][ctx.author.id].append(int(what))

            else:
                self.bot.trades[ctx.author.id]["executing"] = False
                return await ctx.send("That's not a valid item to add to the trade!")

        else:

            updated = False

            lines = []

            for what in args:

                if what.isdigit():

                    skip = False

                    if not 1 <= int(what) <= 2 ** 31 - 1:
                        lines.append(f"{what}: NO")
                        continue

                    for x in self.bot.trades[ctx.author.id]["items"][ctx.author.id]:
                        if type(x) == int:
                            continue

                        if x[1] + 1 == int(what):
                            lines.append(f"{what}: This item is already in the trade!")
                            skip = True
                            break

                    if skip:
                        continue

                    number = int(what) - 1

                    member = await self.db.fetch_member_info(ctx.author)
                    pokemon = await self.db.fetch_pokemon(ctx.author, number)

                    if pokemon is None:
                        lines.append(f"{what}: Couldn't find that pokémon!")
                        continue

                    if member.selected == number:
                        lines.append(f"{what}: You can't trade your selected pokémon!")
                        continue

                    if pokemon.favorite:
                        lines.append(f"{what}: You can't trade favorited pokémon!")
                        continue

                    self.bot.trades[ctx.author.id]["items"][ctx.author.id].append(
                        (pokemon, number)
                    )

                    updated = True

                else:
                    lines.append(
                        f"{what}: That's not a valid item to add to the trade!"
                    )
                    continue

            if len(lines) > 0:
                await ctx.send("\n".join(lines)[:2048])

            if not updated:
                self.bot.trades[ctx.author.id]["executing"] = False
                return

        for k in self.bot.trades[ctx.author.id]:
            if type(k) == int:
                self.bot.trades[ctx.author.id][k] = False

        self.bot.trades[ctx.author.id]["executing"] = False
        await self.send_trade(ctx, ctx.author)

    @checks.has_started()
    @trade.command(aliases=["r"])
    async def remove(self, ctx: commands.Context, *args):
        """Remove an item from a trade."""

        # TODO this shares a lot of code with the add command

        if ctx.author.id not in self.bot.trades:
            return await ctx.send("You're not in a trade!")

        if ctx.channel.id != self.bot.trades[ctx.author.id]["channel"].id:
            return await ctx.send("You must be in the same channel to remove items!")

        if self.bot.trades[ctx.author.id]["executing"]:
            return await ctx.send("The trade is currently loading...")

        if len(args) == 0:
            return

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

    # Filter
    @flags.add_flag("page", nargs="?", type=int, default=1)
    @flags.add_flag("--shiny", action="store_true")
    @flags.add_flag("--alolan", action="store_true")
    @flags.add_flag("--mythical", action="store_true")
    @flags.add_flag("--legendary", action="store_true")
    @flags.add_flag("--ub", action="store_true")
    @flags.add_flag("--mega", action="store_true")
    @flags.add_flag("--name", "--n", nargs="+", action="append")
    @flags.add_flag("--nickname", nargs="+", action="append")
    @flags.add_flag("--type", type=str, action="append")
    # IV
    @flags.add_flag("--level", nargs="+", action="append")
    @flags.add_flag("--hpiv", nargs="+", action="append")
    @flags.add_flag("--atkiv", nargs="+", action="append")
    @flags.add_flag("--defiv", nargs="+", action="append")
    @flags.add_flag("--spatkiv", nargs="+", action="append")
    @flags.add_flag("--spdefiv", nargs="+", action="append")
    @flags.add_flag("--spdiv", nargs="+", action="append")
    @flags.add_flag("--iv", nargs="+", action="append")
    # Skip/limit
    @flags.add_flag("--skip", type=int)
    @flags.add_flag("--limit", type=int)
    # Trade add all
    @checks.has_started()
    @trade.command(aliases=["aa"], cls=flags.FlagCommand)
    async def addall(self, ctx: commands.Context, **flags):

        if ctx.author.id not in self.bot.trades:
            return await ctx.send("You're not in a trade!")

        if ctx.channel.id != self.bot.trades[ctx.author.id]["channel"].id:
            return await ctx.send("You must be in the same channel to add items!")

        if self.bot.trades[ctx.author.id]["executing"]:
            return await ctx.send("The trade is currently loading...")

        self.bot.trades[ctx.author.id]["executing"] = True

        member = await self.db.fetch_member_info(ctx.author)

        aggregations = await self.bot.get_cog("Pokemon").create_filter(
            flags, ctx, order_by=member.order_by
        )

        if aggregations is None:
            self.bot.trades[ctx.author.id]["executing"] = False
            return

        aggregations.extend(
            [
                {"$match": {"idx": {"$not": {"$eq": member.selected}}}},
                {"$match": {"pokemon.favorite": {"$not": {"$eq": True}}}},
            ]
        )

        num = await self.db.fetch_pokemon_count(ctx.author, aggregations=aggregations)

        if num == 0:
            self.bot.trades[ctx.author.id]["executing"] = False
            return await ctx.send(
                "Found no pokémon matching this search (excluding favorited and selected pokémon)."
            )

        # confirm

        await ctx.send(
            f"Are you sure you want to trade {num} pokémon? Favorited and selected pokémon won't be added. Type `confirm trade {num}` to confirm."
        )

        def check(m):
            return m.channel.id == ctx.channel.id and m.author.id == ctx.author.id

        try:
            msg = await self.bot.wait_for("message", timeout=30, check=check)

            if msg.content.lower() != f"confirm trade {num}":
                self.bot.trades[ctx.author.id]["executing"] = False
                return await ctx.send("Aborted.")

        except asyncio.TimeoutError:
            self.bot.trades[ctx.author.id]["executing"] = False
            return await ctx.send("Time's up. Aborted.")

        # confirmed, add all

        await ctx.send(f"Adding {num} pokémon, this might take a while...")

        pokemon = await self.db.fetch_pokemon_list(
            ctx.author, 0, num, aggregations=aggregations
        )

        self.bot.trades[ctx.author.id]["items"][ctx.author.id].extend(
            (self.bot.mongo.Pokemon.build_from_mongo(x["pokemon"]), x["idx"])
            for x in pokemon
            if all(
                (
                    type(i) == int or x["idx"] != i[1]
                    for i in self.bot.trades[ctx.author.id]["items"][ctx.author.id]
                )
            )
        )

        for k in self.bot.trades[ctx.author.id]:
            if type(k) == int:
                self.bot.trades[ctx.author.id][k] = False

        self.bot.trades[ctx.author.id]["executing"] = False
        await self.send_trade(ctx, ctx.author)

    @trade.command(aliases=["i"])
    async def info(self, ctx: commands.Context, *, number: int):
        """View a pokémon from the trade."""

        if ctx.author.id not in self.bot.trades:
            return await ctx.send("You're not in a trade!")

        other_id = next(
            x
            for x in self.bot.trades[ctx.author.id]
            if type(x) == int and x != ctx.author.id
        )
        other = ctx.guild.get_member(other_id) or await ctx.guild.fetch_member(other_id)

        try:
            pokemon = next(
                x
                for x in self.bot.trades[ctx.author.id]["items"][other_id]
                if type(x) != int and x[1] == number - 1
            )[0]
        except StopIteration:
            return await ctx.send("Couldn't find that pokémon in the trade!")

        embed = self.bot.Embed()
        embed.title = f"Level {pokemon.level} {pokemon.species}"

        if pokemon.nickname is not None:
            embed.title += f' "{pokemon.nickname}"'

        if pokemon.shiny:
            embed.title += " ✨"
            embed.set_image(url=pokemon.species.shiny_image_url)
        else:
            embed.set_image(url=pokemon.species.image_url)

        embed.set_thumbnail(url=other.avatar_url)

        info = (
            f"**XP:** {pokemon.xp}/{pokemon.max_xp}",
            f"**Nature:** {pokemon.nature}",
        )

        embed.add_field(name="Details", value="\n".join(info), inline=False)

        stats = (
            f"**HP:** {pokemon.hp} – IV: {pokemon.iv_hp}/31",
            f"**Attack:** {pokemon.atk} – IV: {pokemon.iv_atk}/31",
            f"**Defense:** {pokemon.defn} – IV: {pokemon.iv_defn}/31",
            f"**Sp. Atk:** {pokemon.satk} – IV: {pokemon.iv_satk}/31",
            f"**Sp. Def:** {pokemon.sdef} – IV: {pokemon.iv_sdef}/31",
            f"**Speed:** {pokemon.spd} – IV: {pokemon.iv_spd}/31",
            f"**Total IV:** {pokemon.iv_percentage * 100:.2f}%",
        )

        embed.add_field(name="Stats", value="\n".join(stats), inline=False)

        if pokemon.held_item:
            item = self.bot.data.item_by_number(pokemon.held_item)
            emote = ""
            if item.emote is not None:
                emote = getattr(self.bot.sprites, item.emote) + " "
            embed.add_field(name="Held Item", value=f"{emote}{item.name}", inline=False)

        embed.set_footer(text=f"Displaying pokémon {number} of {other.display_name}.")

        await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(Trading(bot))
