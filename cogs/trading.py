import asyncio
from csv import field_size_limit
import math
import random
from datetime import datetime, timedelta
from itertools import zip_longest

import discord
from discord.ext import commands, tasks

from data.models import deaccent
from helpers import checks, constants, flags, pagination


def chunks(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i : i + n]


class Trading(commands.Cog):
    """For trading."""

    def __init__(self, bot):
        self.bot = bot
        if not hasattr(self.bot, "trades"):
            self.bot.loop.create_task(self.clear_trades())
        self.process_cancel_trades.start()

    @tasks.loop(seconds=0.1)
    async def process_cancel_trades(self):
        with await self.bot.redis as r:
            req = await r.blpop(f"cancel_trade:{self.bot.cluster_idx}")
            await self.end_trade(int(req[1]))

    @process_cancel_trades.before_loop
    async def before_process_cancel_trades(self):
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_message(self, message):
        if (
            message.author.bot
            and message.author != self.bot.user
            and deaccent(message.author.display_name) == "Poketwo"
            and len(message.embeds) > 0
            and "Trade between" in message.embeds[0].title
        ):
            try:
                await message.delete()
            except discord.HTTPException:
                await message.channel.send(self.bot._("scam-identified"))
            else:
                await message.channel.send(self.bot._("scam-identified-and-deleted"))

    async def clear_trades(self):
        await self.bot.get_cog("Redis").wait_until_ready()
        await self.bot.wait_until_ready()

        todel = []
        async for key, val in self.bot.redis.ihscan("trade"):
            if int(val) == self.bot.cluster_idx:
                todel.append(key)
        if len(todel) > 0:
            await self.bot.redis.hdel("trade", *todel)

        self.bot.trades = {}

    def is_in_trade(self, user):
        return self.bot.redis.hexists("trade", user.id)

    async def end_trade(self, user_id):
        cluster_id = int(await self.bot.redis.hget("trade", user_id))
        if cluster_id == self.bot.cluster_idx:
            if user_id in self.bot.trades:
                a, b = self.bot.trades[user_id]["users"]
                self.bot.dispatch("trade", self.bot.trades[user_id])
                await self.bot.redis.hdel("trade", a.id, b.id)
                del self.bot.trades[a.id]
                del self.bot.trades[b.id]
            else:
                await self.bot.redis.hdel("trade", user_id)
            return True
        else:
            await self.bot.redis.rpush(f"cancel_trade:{cluster_id}", user_id)
            return False

    async def send_trade(self, ctx, user: discord.Member):
        # TODO this code is pretty shit. although it does work

        trade = self.bot.trades[user.id]
        a, b = trade["users"]

        done = False

        if trade[a.id] and trade[b.id] and not trade["executing"]:
            done = True
            trade["executing"] = True

        num_pages = max(math.ceil(len(x) / 20) for x in trade["pokemon"].values())

        if done:
            execmsg = await ctx.send(ctx._("executing-trade"))

        users = {k: [("p", x) for x in v] for k, v in trade["pokemon"].items()}
        for x in users:
            if trade["redeems"][x] > 0:
                users[x].insert(0, ("r", trade["redeems"][x]))
            if trade["pokecoins"][x] > 0:
                users[x].insert(0, ("c", trade["pokecoins"][x]))

        embed_pages = list(zip_longest(*[list(chunks(x, 20)) for x in users.values()]))

        if len(embed_pages) == 0:
            embed_pages = [[[], []]]

        async def get_page(source, menu, pidx):
            embed = self.bot.Embed(title=ctx._("trade-between", a=a.display_name, b=b.display_name))

            if done:
                embed.title = ctx._("trade-completed", a=a.display_name, b=b.display_name)

            for mem, page in zip((a, b), embed_pages[pidx]):
                try:
                    maxn = max(x.idx for t, x in page or [] if t == "p")
                except ValueError:
                    maxn = 0

                def padn(idx, n):
                    return " " * (len(str(n)) - len(str(idx))) + str(idx)

                def txt(p):
                    return ctx._(
                        "trade-page-line-shiny" if p.shiny else "trade-page-line",
                        index=padn(p.idx, maxn),
                        species=p.species,
                        level=p.level,
                        ivPercentage=p.iv_percentage,
                    )

                val = "\n".join(
                    ctx._("trade-pokecoins", coins=x) if t == "c" else f"{x:,} redeems" if t == "r" else txt(x)
                    for t, x in page or []
                )

                if val == "":
                    if len(users[mem.id]) == 0:
                        val = ctx._("trade-none")
                    else:
                        val = ctx._("trade-none-on-this-page")

                sign = "🟢" if trade[mem.id] else "🔴"

                embed.add_field(name=f"{sign} {mem.display_name}", value=val[:1024])

            embed.set_footer(text=ctx._("trade-footer", numPages=num_pages, page=pidx + 1))

            return embed

        # Check if done

        embeds = []

        if done:
            try:
                bothsides = list(enumerate(trade["pokemon"].items()))

                for u in trade["users"]:
                    member = await self.bot.mongo.fetch_member_info(u)
                    if member.balance < trade["pokecoins"][u.id]:
                        await ctx.send(ctx._("trade-needs-pokecoins"))
                        await self.end_trade(a.id)
                        return
                    if member.redeems < trade["redeems"][u.id]:
                        await ctx.send(ctx._("trade-needs-redeems"))
                        await self.end_trade(a.id)
                        return

                for idx, (i, side) in bothsides:
                    _, (oi, _) = bothsides[(idx + 1) % 2]

                    mem = ctx.guild.get_member(i) or await ctx.guild.fetch_member(i)
                    omem = ctx.guild.get_member(oi) or await ctx.guild.fetch_member(oi)

                    if trade["pokecoins"][i] > 0:
                        res = await self.bot.mongo.db.member.find_one_and_update(
                            {"_id": mem.id}, {"$inc": {"balance": -trade["pokecoins"][i]}}
                        )
                        await self.bot.redis.hdel("db:member", mem.id)
                        if res["balance"] >= trade["pokecoins"][i]:
                            await self.bot.mongo.update_member(omem, {"$inc": {"balance": trade["pokecoins"][i]}})
                        else:
                            await self.bot.mongo.update_member(mem, {"$inc": {"balance": trade["pokecoins"][i]}})
                            return await ctx.send(ctx._("trade-needs-pokecoins"))

                    if trade["redeems"][i] > 0:
                        res = await self.bot.mongo.db.member.find_one_and_update(
                            {"_id": mem.id}, {"$inc": {"redeems": -trade["redeems"][i]}}
                        )
                        await self.bot.redis.hdel("db:member", mem.id)
                        if res["redeems"] >= trade["redeems"][i]:
                            await self.bot.mongo.update_member(omem, {"$inc": {"redeems": trade["redeems"][i]}})
                        else:
                            await self.bot.mongo.update_member(mem, {"$inc": {"redeems": trade["redeems"][i]}})
                            return await ctx.send(ctx._("trade-needs-redeems"))

                for idx, (i, side) in bothsides:
                    _, (oi, _) = bothsides[(idx + 1) % 2]

                    mem = ctx.guild.get_member(i) or await ctx.guild.fetch_member(i)
                    omem = ctx.guild.get_member(oi) or await ctx.guild.fetch_member(oi)

                    idxs = set()

                    num_pokes = len(list(x for x in side if type(x) != int))
                    idx = await self.bot.mongo.fetch_next_idx(omem, num_pokes)

                    for x in side:
                        pokemon = x

                        if pokemon.idx in idxs:
                            continue

                        idxs.add(pokemon.idx)

                        update = {
                            "$set": {
                                "owner_id": omem.id,
                                "idx": idx,
                            }
                        }
                        idx += 1

                        if pokemon.held_item != 13001:
                            evos = [
                                evo
                                for evo in pokemon.species.trade_evolutions
                                if (evo.trigger.item is None or evo.trigger.item.id == pokemon.held_item)
                            ]

                            if len(evos) > 0:
                                evo = random.choice(evos)

                                evo_embed = self.bot.Embed(title=ctx._("congratulations", name=omem.display_name))

                                name = str(pokemon.species)

                                if pokemon.nickname is not None:
                                    name += f' "{pokemon.nickname}"'

                                evo_embed.add_field(
                                    name=ctx._("pokemon-evolving", pokemon=name),
                                    value=ctx._("pokemon-turned-into", old=name, new=evo.target),
                                )

                                self.bot.dispatch("evolve", mem, pokemon, evo.target)
                                self.bot.dispatch("evolve", omem, pokemon, evo.target)

                                update["$set"]["species_id"] = evo.target.id

                                embeds.append(evo_embed)

                        await self.bot.mongo.update_pokemon(
                            pokemon,
                            update,
                        )

            except:
                await self.end_trade(a.id)
                raise

            try:
                await execmsg.delete()
            except:
                pass

            try:
                await self.bot.mongo.db.logs.insert_one(
                    {
                        "event": "trade",
                        "users": [a.id, b.id],
                        "pokemon": {
                            str(a.id): [x.id for x in trade["pokemon"][a.id]],
                            str(b.id): [x.id for x in trade["pokemon"][b.id]],
                        },
                        "pokecoins": {
                            str(a.id): trade["pokecoins"][a.id],
                            str(b.id): trade["pokecoins"][b.id],
                        },
                        "redeems": {
                            str(a.id): trade["redeems"][a.id],
                            str(b.id): trade["redeems"][b.id],
                        },
                    }
                )
            except:
                pass

            await self.end_trade(a.id)

        # Send msg

        pages = pagination.ContinuablePages(pagination.FunctionPageSource(num_pages, get_page))
        self.bot.menus[a.id] = pages
        self.bot.menus[b.id] = pages
        if menu := trade.get("menu"):
            menu.stop()
            await menu.message.delete()
        await pages.start(ctx)
        trade["menu"] = pages

        for evo_embed in embeds:
            await ctx.send(embed=evo_embed)

    @checks.has_started()
    @commands.guild_only()
    @commands.group(aliases=("t",), invoke_without_command=True, case_insensitive=True)
    async def trade(self, ctx, *, user: discord.Member):
        """Trade pokémon with another trainer."""

        if user == ctx.author:
            return await ctx.send(ctx._("nice-try"))

        if await self.is_in_trade(ctx.author):
            return await ctx.send(ctx._("already-in-a-trade"))

        if await self.is_in_trade(user):
            return await ctx.send(ctx._("user-already-in-a-trade", user=user))

        member = await ctx.bot.mongo.Member.find_one({"id": user.id}, {"suspended": 1, "suspension_reason": 1})

        if member is None:
            return await ctx.send(ctx._("user-hasnt-started"))

        if member.suspended or datetime.utcnow() < member.suspended_until:
            return await ctx.send(ctx._("user-is-suspended", user=user))

        message = await ctx.send(ctx._("requesting-a-trade", mention=user.mention))
        await message.add_reaction("✅")

        def check(reaction, u):
            return reaction.message.id == message.id and u == user and str(reaction.emoji) == "✅"

        try:
            await self.bot.wait_for("reaction_add", timeout=30, check=check)
        except asyncio.TimeoutError:
            await message.add_reaction("❌")
            return await ctx.send(ctx._("trade-request-timed-out"))

        if await self.is_in_trade(ctx.author):
            return await ctx.send(ctx._("user-who-sent-request-is-already-trading"))

        if await self.is_in_trade(user):
            return await ctx.send(ctx._("cannot-accept-trade-while-trading"))

        trade = {
            "pokemon": {ctx.author.id: [], user.id: []},
            "redeems": {ctx.author.id: 0, user.id: 0},
            "pokecoins": {ctx.author.id: 0, user.id: 0},
            "users": [ctx.author, user],
            ctx.author.id: False,
            user.id: False,
            "channel": ctx.channel,
            "executing": False,
            "last_updated": datetime.utcnow(),
        }
        self.bot.trades[ctx.author.id] = trade
        self.bot.trades[user.id] = trade
        await self.bot.redis.hset("trade", ctx.author.id, self.bot.cluster_idx)
        await self.bot.redis.hset("trade", user.id, self.bot.cluster_idx)
        await self.send_trade(ctx, ctx.author)

    @commands.guild_only()
    @trade.command(aliases=("x",))
    async def cancel(self, ctx):
        """Cancel a trade."""

        if not await self.is_in_trade(ctx.author):
            return await ctx.send(ctx._("not-in-trade"))

        try:
            if self.bot.trades[ctx.author.id]["executing"]:
                return await ctx.send(ctx._("trade-loading"))
        except KeyError:
            pass

        if await self.end_trade(ctx.author.id):
            await ctx.send(ctx._("trade-has-been-canceled"))
        else:
            await ctx.send(ctx._("attempting-to-cancel-trade"))

    @checks.has_started()
    @commands.guild_only()
    @trade.command(aliases=("c",))
    async def confirm(self, ctx):
        """Confirm a trade."""

        if not await self.is_in_trade(ctx.author):
            return await ctx.send(ctx._("not-in-trade"))

        if self.bot.trades[ctx.author.id]["executing"]:
            return await ctx.send(ctx._("trade-loading"))

        last_updated = self.bot.trades[ctx.author.id]["last_updated"]
        if datetime.utcnow() - last_updated < timedelta(seconds=3):
            return await ctx.reply(ctx._("trade-was-recently-modified"))

        self.bot.trades[ctx.author.id][ctx.author.id] = not self.bot.trades[ctx.author.id][ctx.author.id]

        await self.send_trade(ctx, ctx.author)

    @checks.has_started()
    @commands.max_concurrency(1, commands.BucketType.member)
    @commands.guild_only()
    @trade.group(aliases=("a",), invoke_without_command=True, case_insensitive=True)
    async def add(self, ctx, *args):
        """Add pokémon to a trade."""

        if not await self.is_in_trade(ctx.author):
            return await ctx.send(ctx._("not-in-trade"))

        if ctx.channel.id != self.bot.trades[ctx.author.id]["channel"].id:
            return await ctx.send(ctx._("same-channel-to-add"))

        if self.bot.trades[ctx.author.id]["executing"]:
            return await ctx.send(ctx._("trade-loading"))

        if len(args) == 0:
            return

        if len(args) <= 2 and args[-1].lower().endswith(("pp", "pc")):
            return await ctx.send(ctx._("add-command-for-pokemon-only"))

        else:
            updated = False
            lines = []

            for what in args:
                if what.isdigit():
                    skip = False

                    if not 1 <= int(what) <= 2**31 - 1:
                        lines.append(ctx._("trade-add-firm-refusal", thing=what))
                        continue

                    for x in self.bot.trades[ctx.author.id]["pokemon"][ctx.author.id]:
                        if x.idx == int(what):
                            lines.append(ctx._("trade-add-pokemon-already-in-trade", thing=what))
                            skip = True
                            break

                    if skip:
                        continue

                    number = int(what)
                    member = await self.bot.mongo.fetch_member_info(ctx.author)
                    pokemon = await self.bot.mongo.fetch_pokemon(ctx.author, number)

                    if pokemon is None:
                        lines.append(ctx._("trade-unknown-pokemon", thing=what))
                        continue

                    if member.selected_id == pokemon.id:
                        lines.append(ctx._("trade-add-cannot-trade-selected-pokemon", thing=what))
                        continue

                    if pokemon.favorite:
                        lines.append(ctx._("trade-add-cannot-trade-favorited-pokemon", thing=what))
                        continue

                    self.bot.trades[ctx.author.id]["pokemon"][ctx.author.id].append(pokemon)
                    updated = True
                else:
                    lines.append(ctx._("trade-add-invalid-item-to-add", thing=what))
                    continue

            if len(lines) > 0:
                await ctx.send("\n".join(lines)[:2048])

            if not updated:
                return

        for k in self.bot.trades[ctx.author.id]:
            if type(k) == int:
                self.bot.trades[ctx.author.id][k] = False

        self.bot.trades[ctx.author.id]["last_updated"] = datetime.utcnow()
        await self.send_trade(ctx, ctx.author)

    @checks.has_started()
    @commands.max_concurrency(1, commands.BucketType.member)
    @commands.guild_only()
    @add.command(name="pokecoins", aliases=("pc", "pokecoin"))
    async def add_pokecoins(self, ctx, *, amt: int):
        """Add Pokécoin(s) to a trade."""

        if not await self.is_in_trade(ctx.author):
            return await ctx.send(ctx._("not-in-trade"))

        if ctx.channel.id != self.bot.trades[ctx.author.id]["channel"].id:
            return await ctx.send(ctx._("same-channel-to-add"))

        if self.bot.trades[ctx.author.id]["executing"]:
            return await ctx.send(ctx._("trade-loading"))

        if amt < 0:
            return await ctx.send(ctx._("amount-must-be-positive"))

        member = await self.bot.mongo.fetch_member_info(ctx.author)
        if self.bot.trades[ctx.author.id]["pokecoins"][ctx.author.id] + amt > member.balance:
            return await ctx.send(ctx._("not-enough-coins"))

        self.bot.trades[ctx.author.id]["pokecoins"][ctx.author.id] += amt

        for k in self.bot.trades[ctx.author.id]:
            if type(k) == int:
                self.bot.trades[ctx.author.id][k] = False

        await self.send_trade(ctx, ctx.author)

    @checks.has_started()
    @commands.max_concurrency(1, commands.BucketType.member)
    @commands.guild_only()
    @add.command(name="redeems", aliases=("redeem", "r"))
    async def add_redeems(self, ctx, *, amt: int):
        """Add redeem(s) to a trade."""

        if not await self.is_in_trade(ctx.author):
            return await ctx.send(ctx._("not-in-trade"))

        if ctx.channel.id != self.bot.trades[ctx.author.id]["channel"].id:
            return await ctx.send(ctx._("same-channel-to-add"))

        if self.bot.trades[ctx.author.id]["executing"]:
            return await ctx.send(ctx._("trade-loading"))

        if amt < 0:
            return await ctx.send(ctx._("amount-must-be-positive"))

        member = await self.bot.mongo.fetch_member_info(ctx.author)
        if self.bot.trades[ctx.author.id]["redeems"][ctx.author.id] + amt > member.redeems:
            return await ctx.send(ctx._("not-enough-redeems"))

        self.bot.trades[ctx.author.id]["redeems"][ctx.author.id] += amt

        for k in self.bot.trades[ctx.author.id]:
            if type(k) == int:
                self.bot.trades[ctx.author.id][k] = False

        await self.send_trade(ctx, ctx.author)

    @checks.has_started()
    @commands.max_concurrency(1, commands.BucketType.member)
    @commands.guild_only()
    @trade.group(aliases=("r",), invoke_without_command=True, case_insensitive=True)
    async def remove(self, ctx, *args):
        """Remove pokémon from a trade."""

        # TODO this shares a lot of code with the add command

        if not await self.is_in_trade(ctx.author):
            return await ctx.send(ctx._("not-in-trade"))

        if ctx.channel.id != self.bot.trades[ctx.author.id]["channel"].id:
            return await ctx.send(ctx._("same-channel-to-remove"))

        if self.bot.trades[ctx.author.id]["executing"]:
            return await ctx.send(ctx._("trade-loading"))

        if len(args) == 0:
            return

        trade = self.bot.trades[ctx.author.id]

        if len(args) <= 2 and args[-1].lower().endswith(("pp", "pc")):
            return await ctx.send(ctx._("remove-command-for-pokemon-only"))
        else:
            updated = False
            for what in args:
                if what.isdigit():
                    for idx, x in enumerate(trade["pokemon"][ctx.author.id]):
                        if x.idx == int(what):
                            del trade["pokemon"][ctx.author.id][idx]
                            updated = True
                            break
                    else:
                        await ctx.send(ctx._("trade-unknown-item", thing=what))
                else:
                    await ctx.send(ctx._("trade-remove-invalid-item", thing=what))
                    continue

            if not updated:
                return

        for k in self.bot.trades[ctx.author.id]:
            if type(k) == int:
                self.bot.trades[ctx.author.id][k] = False

        await self.send_trade(ctx, ctx.author)

    @checks.has_started()
    @commands.max_concurrency(1, commands.BucketType.member)
    @commands.guild_only()
    @remove.command(name="pokecoins", aliases=("pc", "pokecoin"))
    async def remove_pokecoins(self, ctx, *, amt: int):
        """Remove Pokécoin(s) from a trade."""

        if not await self.is_in_trade(ctx.author):
            return await ctx.send(ctx._("not-in-trade"))

        if ctx.channel.id != self.bot.trades[ctx.author.id]["channel"].id:
            return await ctx.send(ctx._("same-channel-to-remove"))

        if self.bot.trades[ctx.author.id]["executing"]:
            return await ctx.send(ctx._("trade-loading"))

        if amt < 0:
            return await ctx.send(ctx._("amount-must-be-positive"))

        if self.bot.trades[ctx.author.id]["pokecoins"][ctx.author.id] - amt < 0:
            return await ctx.send(ctx._("not-that-many-pokecoins"))

        self.bot.trades[ctx.author.id]["pokecoins"][ctx.author.id] -= amt

        for k in self.bot.trades[ctx.author.id]:
            if type(k) == int:
                self.bot.trades[ctx.author.id][k] = False

        await self.send_trade(ctx, ctx.author)

    @checks.has_started()
    @commands.max_concurrency(1, commands.BucketType.member)
    @commands.guild_only()
    @remove.command(name="redeems", aliases=("redeem", "r"))
    async def remove_redeems(self, ctx, *, amt: int):
        """Remove redeem(s) from a trade."""

        if not await self.is_in_trade(ctx.author):
            return await ctx.send(ctx._("not-in-trade"))

        if ctx.channel.id != self.bot.trades[ctx.author.id]["channel"].id:
            return await ctx.send(ctx._("same-channel-to-add"))

        if self.bot.trades[ctx.author.id]["executing"]:
            return await ctx.send(ctx._("trade-loading"))

        if amt < 0:
            return await ctx.send(ctx._("amount-must-be-positive"))

        if self.bot.trades[ctx.author.id]["redeems"][ctx.author.id] - amt < 0:
            return await ctx.send(ctx._("not-that-many-redeems"))

        self.bot.trades[ctx.author.id]["redeems"][ctx.author.id] -= amt

        for k in self.bot.trades[ctx.author.id]:
            if type(k) == int:
                self.bot.trades[ctx.author.id][k] = False

        await self.send_trade(ctx, ctx.author)

    # Filter
    @flags.add_flag("page", nargs="?", type=int, default=1)
    @flags.add_flag("--shiny", action="store_true")
    @flags.add_flag("--alolan", action="store_true")
    @flags.add_flag("--galarian", action="store_true")
    @flags.add_flag("--hisuian", action="store_true")
    @flags.add_flag("--mythical", action="store_true")
    @flags.add_flag("--legendary", action="store_true")
    @flags.add_flag("--ub", action="store_true")
    @flags.add_flag("--event", action="store_true")
    @flags.add_flag("--mega", action="store_true")
    @flags.add_flag("--embedcolor", "--ec", action="store_true")
    @flags.add_flag("--name", "--n", nargs="+", action="append")
    @flags.add_flag("--nickname", nargs="*", action="append")
    @flags.add_flag("--type", "--t", type=str, action="append")
    @flags.add_flag("--region", "--r", type=str, action="append")

    # IV
    @flags.add_flag("--level", nargs="+", action="append")
    @flags.add_flag("--hpiv", nargs="+", action="append")
    @flags.add_flag("--atkiv", nargs="+", action="append")
    @flags.add_flag("--defiv", nargs="+", action="append")
    @flags.add_flag("--spatkiv", nargs="+", action="append")
    @flags.add_flag("--spdefiv", nargs="+", action="append")
    @flags.add_flag("--spdiv", nargs="+", action="append")
    @flags.add_flag("--iv", nargs="+", action="append")

    # Duplicate IV's
    @flags.add_flag("--triple", "--three", type=int)
    @flags.add_flag("--quadruple", "--four", "--quadra", "--quad", "--tetra", type=int)
    @flags.add_flag("--pentuple", "--quintuple", "--penta", "--pent", "--five", type=int)
    @flags.add_flag("--hextuple", "--sextuple", "--hexa", "--hex", "--six", type=int)

    # Skip/limit
    @flags.add_flag("--skip", type=int)
    @flags.add_flag("--limit", type=int)

    # Trade add all
    @checks.has_started()
    @commands.guild_only()
    @commands.max_concurrency(1, commands.BucketType.member)
    @commands.cooldown(1, 5, commands.BucketType.user)
    @trade.command(aliases=("aa",), cls=flags.FlagCommand)
    async def addall(self, ctx, **flags):
        """Add multiple pokémon to a trade."""

        if not await self.is_in_trade(ctx.author):
            return await ctx.send(ctx._("not-in-trade"))

        if ctx.channel.id != self.bot.trades[ctx.author.id]["channel"].id:
            return await ctx.send(ctx._("same-channel-to-add"))

        if self.bot.trades[ctx.author.id]["executing"]:
            return await ctx.send(ctx._("trade-loading"))

        member = await self.bot.mongo.fetch_member_info(ctx.author)

        aggregations = await self.bot.get_cog("Pokemon").create_filter(flags, ctx, order_by=member.order_by)

        if aggregations is None:
            return

        aggregations.extend(
            [
                {"$match": {"_id": {"$not": {"$eq": member.selected_id}}}},
                {"$match": {"favorite": {"$not": {"$eq": True}}}},
            ]
        )

        num = await self.bot.mongo.fetch_pokemon_count(ctx.author, aggregations=aggregations)

        if num == 0:
            return await ctx.send(ctx._("found-no-pokemon-matching-excluding-favorited-and-selected"))

        # confirm

        trade_size = len(self.bot.trades[ctx.author.id]["pokemon"][ctx.author.id])

        if 3000 - trade_size < 0:
            return await ctx.send(ctx._("too-many-pokemon-in-trade"))

        if trade_size + num > 3000:
            return await ctx.send(ctx._("too-many-pokemon-in-trade-use-limit-flag", limit=3000 - trade_size))

        result = await ctx.confirm(ctx._("trade-add-all-confirmation", number=num))
        if result is None:
            return await ctx.send(ctx._("times-up"))
        if result is False:
            return await ctx.send(ctx._("aborted"))

        # confirmed, add all

        await ctx.send(ctx._("trade-add-all-in-progress", number=num))

        pokemon = self.bot.mongo.fetch_pokemon_list(ctx.author, aggregations)

        self.bot.trades[ctx.author.id]["pokemon"][ctx.author.id].extend(
            [
                x
                async for x in pokemon
                if all(
                    (type(i) == int or x.idx != i.idx for i in self.bot.trades[ctx.author.id]["pokemon"][ctx.author.id])
                )
            ]
        )

        for k in self.bot.trades[ctx.author.id]:
            if type(k) == int:
                self.bot.trades[ctx.author.id][k] = False

        await self.send_trade(ctx, ctx.author)

    @checks.has_started()
    @commands.guild_only()
    @trade.command(aliases=("i",))
    async def info(self, ctx, *, number: int):
        """View a pokémon from the trade."""

        if not await self.is_in_trade(ctx.author):
            return await ctx.send(ctx._("not-in-trade"))

        other_id = next(x for x in self.bot.trades[ctx.author.id] if type(x) == int and x != ctx.author.id)
        other = ctx.guild.get_member(other_id) or await ctx.guild.fetch_member(other_id)

        try:
            pokemon = next(
                x for x in self.bot.trades[ctx.author.id]["pokemon"][other_id] if type(x) != int and x.idx == number
            )
        except StopIteration:
            return await ctx.send(ctx._("couldnt-find-pokemon-in-trade"))

        field_values = {}
        if pokemon.held_item:
            item = self.bot.data.item_by_number(pokemon.held_item)
            emote = ""
            if item.emote is not None:
                emote = getattr(self.bot.sprites, item.emote) + " "
            field_values = {"held-item": f"{emote}{item.name}"}

        embed = ctx.localized_embed(
            "trade-info-embed",
            field_ordering=["details", "stats", "held-item"],
            block_fields=["details", "stats"],
            field_values=field_values,
            droppable_fields=["held-item"],
            pokemon=f"{pokemon:ln}",
            xp=pokemon.xp,
            maxXp=pokemon.max_xp,
            nature=pokemon.nature,
            hp=pokemon.hp,
            ivHp=pokemon.iv_hp,
            atk=pokemon.atk,
            ivAtk=pokemon.iv_atk,
            defn=pokemon.defn,
            ivDefn=pokemon.iv_defn,
            satk=pokemon.satk,
            ivSatk=pokemon.iv_satk,
            sdef=pokemon.sdef,
            ivSdef=pokemon.iv_sdef,
            spd=pokemon.spd,
            ivSpd=pokemon.iv_spd,
            ivPercentage=pokemon.iv_percentage * 100,
            number=number,
            tradingPartner=other.display_name,
        )
        embed.color = constants.PINK

        if pokemon.shiny:
            embed.set_image(url=pokemon.species.shiny_image_url)
        else:
            embed.set_image(url=pokemon.species.image_url)

        embed.set_thumbnail(url=other.display_avatar.url)

        await ctx.send(embed=embed)

    def cog_unload(self):
        self.process_cancel_trades.cancel()


async def setup(bot: commands.Bot):
    await bot.add_cog(Trading(bot))
