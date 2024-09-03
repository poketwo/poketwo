import asyncio
from collections import defaultdict
import math
import random
from datetime import datetime, timedelta
from itertools import zip_longest
from typing import Optional, Tuple

import discord
from discord.ext import commands, tasks

from data.models import deaccent
from helpers import checks, flags, pagination
from helpers.utils import add_moves_field
from helpers.context import ConfirmationButton, ConfirmationView, PoketwoContext


CONFIRM_TIMEOUT = 40


def chunks(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i : i + n]


class TradeConfirmationView(ConfirmationView):
    def __init__(
        self,
        *args,
        **kwargs,
    ) -> None:
        super().__init__(*args, cancel_label="Abort", **kwargs)


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
        await self.bot.get_cog("Redis").wait_until_ready()

    @commands.Cog.listener()
    async def on_message(self, message):
        if (
            message.author.bot
            and message.author.id != 716390085896962058
            and deaccent(message.author.display_name).casefold() == "poketwo"
        ):
            try:
                await message.delete()
            except discord.HTTPException:
                await message.channel.send(
                    "# Fake Bot Warning!\nA message by a bot pretending to be Pokétwo was identified. Unattentive players are scammed using fake bots every day. Please make sure you are trading what you intended to.\n\nPokétwo has left this server for player safety."
                )
            else:
                await message.channel.send(
                    "# Fake Bot Warning!\nA message by a bot pretending to be Pokétwo was identified and deleted for safety. Unattentive players are scammed using fake bots every day. Please make sure you are trading what you intended to.\n\nPokétwo has left this server for player safety."
                )
            await message.guild.leave()

    async def clear_trades(self):
        await self.bot.wait_until_ready()
        await self.bot.get_cog("Redis").wait_until_ready()

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

    def get_embed_builder(self, trade: dict, *, done: bool, confirming: Optional[bool] = False):
        a, b = trade["users"]
        PER_PAGE = 20
        num_pages = max(math.ceil(len(x) / PER_PAGE) for x in trade["pokemon"].values())

        users = {k: [("p", x) for x in v] for k, v in trade["pokemon"].items()}
        for x in users:
            if trade["redeems"][x] > 0:
                users[x].insert(0, ("r", trade["redeems"][x]))
            if trade["pokecoins"][x] > 0:
                users[x].insert(0, ("c", trade["pokecoins"][x]))

        embed_pages = list(zip_longest(*[list(chunks(x, PER_PAGE)) for x in users.values()]))

        if len(embed_pages) == 0:
            embed_pages = [[[], []]]

        async def get_page(source, menu, pidx):
            embed = self.bot.Embed(title=f"Trade between {a.display_name} and {b.display_name}.")
            if confirming:
                embed.set_author(
                    name=f"Are you sure you want to confirm this trade? Please make sure that you are trading what you intended to."
                )

            if done:
                embed.title = f"✅ Completed trade between {a.display_name} and {b.display_name}."

            for mem, page in zip((a, b), embed_pages[pidx]):
                try:
                    maxn = max(x.idx for t, x in page or [] if t == "p")
                except ValueError:
                    maxn = 0

                def padn(idx, n):
                    return " " * (len(str(n)) - len(str(idx))) + str(idx)

                def txt(p):
                    val = f"`{padn(p.idx, maxn)}`　**{p.species}**"
                    if p.shiny:
                        val = f"`{padn(p.idx, maxn)}`　**✨ {p.species}**"
                    val += f"　•　Lvl. {p.level}　•　{p.iv_percentage:.2%}"
                    return val

                val = "\n".join(
                    f"{x:,} Pokécoins" if t == "c" else f"{x:,} redeems" if t == "r" else txt(x) for t, x in page or []
                )

                if val == "":
                    if len(users[mem.id]) == 0:
                        val = "None"
                    else:
                        val = "None on this page"

                sign = "🟢" if trade[mem.id] else "🔴"

                embed.add_field(name=f"{sign} {mem.display_name}", value=val[:1024])

            embed.set_footer(
                text=f"Showing page {pidx + 1} out of {num_pages}.\nReminder: Trading Pokécoins or Pokémon for real-life currencies or items in other bots is prohibited and will result in the suspension of your Pokétwo account!"
            )

            return embed

        return num_pages, get_page

    async def send_trade(self, ctx: PoketwoContext, user: discord.Member, mention_author=False):
        # TODO this code is pretty shit. although it does work

        trade = self.bot.trades[user.id]
        a, b = trade["users"]
        done = False

        if trade[a.id] and trade[b.id] and not trade["executing"]:
            done = True
            trade["executing"] = True

        if done:
            execmsg = await ctx.send("Executing trade...")

        # Check if done

        evolutions = defaultdict(dict)

        if done:
            try:
                bothsides = list(enumerate(trade["pokemon"].items()))

                for u in trade["users"]:
                    member = await self.bot.mongo.fetch_member_info(u)
                    if member.balance < trade["pokecoins"][u.id]:
                        await ctx.send("The trade could not be executed as one user does not have enough Pokécoins.")
                        await self.end_trade(a.id)
                        return
                    if member.redeems < trade["redeems"][u.id]:
                        await ctx.send("The trade could not be executed as one user does not have enough redeems.")
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
                            return await ctx.send(
                                "The trade could not be executed as one user does not have enough pokécoins."
                            )

                    if trade["redeems"][i] > 0:
                        res = await self.bot.mongo.db.member.find_one_and_update(
                            {"_id": mem.id}, {"$inc": {"redeems": -trade["redeems"][i]}}
                        )
                        await self.bot.redis.hdel("db:member", mem.id)
                        if res["redeems"] >= trade["redeems"][i]:
                            await self.bot.mongo.update_member(omem, {"$inc": {"redeems": trade["redeems"][i]}})
                        else:
                            await self.bot.mongo.update_member(mem, {"$inc": {"redeems": trade["redeems"][i]}})
                            return await ctx.send(
                                "The trade could not be executed as one user does not have enough redeems."
                            )

                evolved = []
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

                                self.bot.dispatch("evolve", mem, pokemon, evo.target)
                                self.bot.dispatch("evolve", omem, pokemon, evo.target)
                                evolved.append((pokemon, evo.target))

                                update["$set"]["species_id"] = evo.target.id
                                evolutions[omem][format(pokemon, "Pgnx")] = evo.target

                        await self.bot.mongo.update_pokemon(
                            pokemon,
                            update,
                        )

                self.bot.dispatch("mass_evolve", mem, evolved)
                self.bot.dispatch("mass_evolve", omem, evolved)

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

        num_pages, get_page = self.get_embed_builder(trade, done=done)
        pages = pagination.ContinuablePages(
            pagination.FunctionPageSource(num_pages, get_page), mention_author=mention_author
        )
        self.bot.menus[a.id] = pages
        self.bot.menus[b.id] = pages
        if menu := trade.get("menu"):
            menu.stop()
            await menu.message.delete()
        await pages.start(ctx)
        trade["menu"] = pages

        for member, evos in evolutions.items():
            for chunk in discord.utils.as_chunks(evos.items(), 20):
                evo_embed = self.bot.Embed(title=f"Congratulations {member.display_name}!")
                for pokemon_name, evo in chunk:
                    evo_embed.add_field(
                        name=f"The **{pokemon_name}** is evolving!",
                        value=f"The **{pokemon_name}** has turned into a **{evo}**!",
                        inline=True,
                    )

                await ctx.send(embed=evo_embed)

    @checks.has_started()
    @commands.guild_only()
    @commands.group(aliases=("t",), invoke_without_command=True, case_insensitive=True)
    async def trade(self, ctx: PoketwoContext, *, user: discord.Member):
        """Trade pokémon with another trainer."""

        if user == ctx.author or user.bot:
            return await ctx.send("Nice try...")

        if await self.is_in_trade(ctx.author):
            return await ctx.send("You are already in a trade!")

        if await self.is_in_trade(user):
            return await ctx.send(f"**{user}** is already in a trade!")

        member = await ctx.bot.mongo.fetch_member_info(user)

        if member is None:
            return await ctx.send("That user hasn't picked a starter pokémon yet!")

        if member.suspended or datetime.utcnow() < member.suspended_until:
            return await ctx.send(f"**{user}** is suspended from the bot!")

        result = await ctx.request(
            user, f"Requesting a trade with {user.mention}. Click the accept button to accept!", timeout=30
        )
        if result is None:
            return await ctx.send("The request to trade has timed out.")
        if result is False:
            return await ctx.send("Rejected.")

        if await self.is_in_trade(ctx.author):
            return await ctx.send("Sorry, the user who sent the request is already in another trade.")

        if await self.is_in_trade(user):
            return await ctx.send("Sorry, you can't accept a trade while you're already in one!")

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
    async def cancel(self, ctx: PoketwoContext):
        """Cancel a trade."""

        if not await self.is_in_trade(ctx.author):
            return await ctx.send("You're not in a trade!")

        try:
            if self.bot.trades[ctx.author.id]["executing"]:
                return await ctx.send("The trade is currently loading...")
        except KeyError:
            pass

        if await self.end_trade(ctx.author.id):
            await ctx.send("The trade has been canceled.")
        else:
            await ctx.send("Attempting to cancel trade...")

    @checks.has_started()
    @commands.guild_only()
    @trade.command(aliases=("c",))
    async def confirm(self, ctx: PoketwoContext):
        """Confirm a trade."""

        if not await self.is_in_trade(ctx.author):
            return await ctx.send("You're not in a trade!")

        trade = self.bot.trades[ctx.author.id]

        if trade["executing"]:
            return await ctx.send("The trade is currently loading...")

        before_confirm = datetime.utcnow()
        last_updated = trade["last_updated"]
        if before_confirm - last_updated < timedelta(seconds=3):
            return await ctx.reply("The trade was recently modified. Please wait a few seconds, and then try again.")

        if not trade[ctx.author.id]:  # Show confirmation only when not already confirmed by user
            member = await self.bot.mongo.fetch_member_info(ctx.author)
            done = False

            num_pages, get_page = self.get_embed_builder(trade, done=done, confirming=True)
            source = pagination.FunctionPageSource(num_pages, get_page)
            pages = pagination.ContinuablePages(
                source,
                mention_author=member.confirm_mention,
                timeout=CONFIRM_TIMEOUT,
            )
            delete_after = True
            view = pages.build_view()
            if view:
                # Injecting the confirmation buttons into the paginator's view
                view.result = None
                view.delete_after = delete_after
                view.add_item(ConfirmationButton(label="Confirm", result=True, style=discord.ButtonStyle.green, row=1))
                view.add_item(ConfirmationButton(label="Abort", result=False, style=discord.ButtonStyle.red, row=1))

                await pages.start(ctx)
                view.message = pages.message
                await view.wait()
                result = view.result
            else:
                result = await ctx.confirm(
                    embed=await get_page(source, pages, 0), delete_after=delete_after, cls=TradeConfirmationView
                )

            if result is None:
                if view:
                    await view.message.delete()
                return await ctx.send("Time's up. Aborted.")
            if result is False:
                return await ctx.send("Aborted.")

            if not await self.is_in_trade(ctx.author):
                return await ctx.send("You're not in a trade!")

        if trade != self.bot.trades[ctx.author.id]:
            return await ctx.send("Couldn't find the trade.")

        last_updated = trade["last_updated"]
        if last_updated > before_confirm:
            return await ctx.send("The items in the trade have changed, please try again.")

        if trade["executing"]:
            return await ctx.send("The trade is currently loading...")

        last_updated = trade["last_updated"]
        if datetime.utcnow() - last_updated < timedelta(seconds=3):
            return await ctx.reply("The trade was recently modified. Please wait a few seconds, and then try again.")

        trade[ctx.author.id] = not trade[ctx.author.id]

        await self.send_trade(ctx, ctx.author)

    @checks.has_started()
    @commands.max_concurrency(1, commands.BucketType.member)
    @commands.guild_only()
    @trade.group(aliases=("a",), invoke_without_command=True, case_insensitive=True)
    async def add(self, ctx: PoketwoContext, *args):
        """Add pokémon to a trade."""

        if not await self.is_in_trade(ctx.author):
            return await ctx.send("You're not in a trade!")

        if ctx.channel.id != self.bot.trades[ctx.author.id]["channel"].id:
            return await ctx.send("You must be in the same channel to add items!")

        if self.bot.trades[ctx.author.id]["executing"]:
            return await ctx.send("The trade is currently loading...")

        if len(args) == 0:
            return

        if len(args) <= 2 and args[-1].lower().endswith(("pp", "pc")):
            return await ctx.send(
                f"`{ctx.clean_prefix}trade add <ids>` is now only for adding Pokémon. Please use the new `{ctx.clean_prefix}trade add pc <amount>` instead!"
            )

        else:
            updated = False
            lines = []

            for what in args:
                if what.isdigit():
                    skip = False

                    if not 1 <= int(what) <= 2**31 - 1:
                        lines.append(f"{what}: NO")
                        continue

                    for x in self.bot.trades[ctx.author.id]["pokemon"][ctx.author.id]:
                        if x.idx == int(what):
                            lines.append(f"{what}: This pokémon is already in the trade!")
                            skip = True
                            break

                    if skip:
                        continue

                    number = int(what)
                    member = await self.bot.mongo.fetch_member_info(ctx.author)
                    pokemon = await self.bot.mongo.fetch_pokemon(ctx.author, number)

                    if pokemon is None:
                        lines.append(f"{what}: Couldn't find that pokémon!")
                        continue

                    if member.selected_id == pokemon.id:
                        lines.append(f"{what}: You can't trade your selected pokémon!")
                        continue

                    if pokemon.favorite:
                        lines.append(f"{what}: You can't trade favorited pokémon!")
                        continue

                    self.bot.trades[ctx.author.id]["pokemon"][ctx.author.id].append(pokemon)
                    updated = True
                else:
                    lines.append(f"{what}: That's not a valid item to add to the trade!")
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
    async def add_pokecoins(self, ctx: PoketwoContext, *, amt: int):
        """Add Pokécoin(s) to a trade."""

        if not await self.is_in_trade(ctx.author):
            return await ctx.send("You're not in a trade!")

        if ctx.channel.id != self.bot.trades[ctx.author.id]["channel"].id:
            return await ctx.send("You must be in the same channel to add items!")

        if self.bot.trades[ctx.author.id]["executing"]:
            return await ctx.send("The trade is currently loading...")

        if amt < 0:
            return await ctx.send("The amount must be positive!")

        member = await self.bot.mongo.fetch_member_info(ctx.author)
        if self.bot.trades[ctx.author.id]["pokecoins"][ctx.author.id] + amt > member.balance:
            return await ctx.send("You don't have enough pokécoins for that!")

        self.bot.trades[ctx.author.id]["pokecoins"][ctx.author.id] += amt

        for k in self.bot.trades[ctx.author.id]:
            if type(k) == int:
                self.bot.trades[ctx.author.id][k] = False

        self.bot.trades[ctx.author.id]["last_updated"] = datetime.utcnow()
        await self.send_trade(ctx, ctx.author)

    @checks.has_started()
    @commands.max_concurrency(1, commands.BucketType.member)
    @commands.guild_only()
    @add.command(name="redeems", aliases=("redeem", "r"))
    async def add_redeems(self, ctx: PoketwoContext, *, amt: int):
        """Add redeem(s) to a trade."""

        if not await self.is_in_trade(ctx.author):
            return await ctx.send("You're not in a trade!")

        if ctx.channel.id != self.bot.trades[ctx.author.id]["channel"].id:
            return await ctx.send("You must be in the same channel to add items!")

        if self.bot.trades[ctx.author.id]["executing"]:
            return await ctx.send("The trade is currently loading...")

        if amt < 0:
            return await ctx.send("The amount must be positive!")

        member = await self.bot.mongo.fetch_member_info(ctx.author)
        if self.bot.trades[ctx.author.id]["redeems"][ctx.author.id] + amt > member.redeems:
            return await ctx.send("You don't have enough redeems for that!")

        self.bot.trades[ctx.author.id]["redeems"][ctx.author.id] += amt

        for k in self.bot.trades[ctx.author.id]:
            if type(k) == int:
                self.bot.trades[ctx.author.id][k] = False

        self.bot.trades[ctx.author.id]["last_updated"] = datetime.utcnow()
        await self.send_trade(ctx, ctx.author)

    @checks.has_started()
    @commands.max_concurrency(1, commands.BucketType.member)
    @commands.guild_only()
    @trade.group(aliases=("r",), invoke_without_command=True, case_insensitive=True)
    async def remove(self, ctx: PoketwoContext, *args):
        """Remove pokémon from a trade."""

        # TODO this shares a lot of code with the add command

        if not await self.is_in_trade(ctx.author):
            return await ctx.send("You're not in a trade!")

        if ctx.channel.id != self.bot.trades[ctx.author.id]["channel"].id:
            return await ctx.send("You must be in the same channel to remove items!")

        if self.bot.trades[ctx.author.id]["executing"]:
            return await ctx.send("The trade is currently loading...")

        if len(args) == 0:
            return

        trade = self.bot.trades[ctx.author.id]

        if len(args) <= 2 and args[-1].lower().endswith(("pp", "pc")):
            return await ctx.send(
                f"`{ctx.clean_prefix}trade remove <ids>` is now only for adding Pokémon. Please use the new `{ctx.clean_prefix}trade remove pc <amount>` instead!"
            )
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
                        await ctx.send(f"{what}: Couldn't find that item!")
                else:
                    await ctx.send(f"{what}: That's not a valid item to remove from the trade!")
                    continue

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
    @remove.command(name="pokecoins", aliases=("pc", "pokecoin"))
    async def remove_pokecoins(self, ctx: PoketwoContext, *, amt: int):
        """Remove Pokécoin(s) from a trade."""

        if not await self.is_in_trade(ctx.author):
            return await ctx.send("You're not in a trade!")

        if ctx.channel.id != self.bot.trades[ctx.author.id]["channel"].id:
            return await ctx.send("You must be in the same channel to add items!")

        if self.bot.trades[ctx.author.id]["executing"]:
            return await ctx.send("The trade is currently loading...")

        if amt < 0:
            return await ctx.send("The amount must be positive!")

        if self.bot.trades[ctx.author.id]["pokecoins"][ctx.author.id] - amt < 0:
            return await ctx.send("There aren't that many pokécoins in the trade!")

        self.bot.trades[ctx.author.id]["pokecoins"][ctx.author.id] -= amt

        for k in self.bot.trades[ctx.author.id]:
            if type(k) == int:
                self.bot.trades[ctx.author.id][k] = False

        self.bot.trades[ctx.author.id]["last_updated"] = datetime.utcnow()
        await self.send_trade(ctx, ctx.author)

    @checks.has_started()
    @commands.max_concurrency(1, commands.BucketType.member)
    @commands.guild_only()
    @remove.command(name="redeems", aliases=("redeem", "r"))
    async def remove_redeems(self, ctx: PoketwoContext, *, amt: int):
        """Remove redeem(s) from a trade."""

        if not await self.is_in_trade(ctx.author):
            return await ctx.send("You're not in a trade!")

        if ctx.channel.id != self.bot.trades[ctx.author.id]["channel"].id:
            return await ctx.send("You must be in the same channel to add items!")

        if self.bot.trades[ctx.author.id]["executing"]:
            return await ctx.send("The trade is currently loading...")

        if amt < 0:
            return await ctx.send("The amount must be positive!")

        if self.bot.trades[ctx.author.id]["redeems"][ctx.author.id] - amt < 0:
            return await ctx.send("There aren't that many redeems in the trade!")

        self.bot.trades[ctx.author.id]["redeems"][ctx.author.id] -= amt

        for k in self.bot.trades[ctx.author.id]:
            if type(k) == int:
                self.bot.trades[ctx.author.id][k] = False

        self.bot.trades[ctx.author.id]["last_updated"] = datetime.utcnow()
        await self.send_trade(ctx, ctx.author)

    # Filter
    @flags.add_flag("page", nargs="?", type=int, default=1)
    @flags.add_flag("--shiny", action="store_true")
    @flags.add_flag("--gmax", "--gigantamax", action="store_true")
    @flags.add_flag("--alolan", action="store_true")
    @flags.add_flag("--galarian", action="store_true")
    @flags.add_flag("--hisuian", action="store_true")
    @flags.add_flag("--paldean", action="store_true")
    @flags.add_flag("--regional", action="store_true")
    @flags.add_flag("--paradox", action="store_true")
    @flags.add_flag("--mythical", action="store_true")
    @flags.add_flag("--legendary", action="store_true")
    @flags.add_flag("--ub", action="store_true")
    @flags.add_flag("--rare", action="store_true")
    @flags.add_flag("--event", action="store_true")
    @flags.add_flag("--mega", action="store_true")
    @flags.add_flag("--embedcolor", "--ec", action="store_true")
    @flags.add_flag("--name", "--n", nargs="+", action="append")
    @flags.add_flag("--evolutions", "--evoline", "--evo", nargs="+", action="append")
    @flags.add_flag("--nickname", nargs="*", action="append")
    @flags.add_flag("--type", "--t", type=str, action="append")
    @flags.add_flag("--region", "--r", type=str, action="append")
    @flags.add_flag("--move", nargs="+", action="append")
    @flags.add_flag("--learns", nargs="*", action="append")
    @flags.add_flag("--gender", "--g", type=str, action="append")

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

    # Flag to receive ping on response
    @flags.add_flag("--mention", "--ping", "--p", action="store_true", default=False)

    # Trade add all
    @checks.has_started()
    @commands.guild_only()
    @commands.max_concurrency(1, commands.BucketType.member)
    @commands.cooldown(1, 5, commands.BucketType.user)
    @trade.command(aliases=("aa",), cls=flags.FlagCommand)
    async def addall(self, ctx: PoketwoContext, **flags):
        """Add multiple pokémon to a trade."""

        mention_author = flags.get("mention")

        if not await self.is_in_trade(ctx.author):
            return await ctx.send("You're not in a trade!")

        if ctx.channel.id != self.bot.trades[ctx.author.id]["channel"].id:
            return await ctx.send("You must be in the same channel to add items!")

        if self.bot.trades[ctx.author.id]["executing"]:
            return await ctx.send("The trade is currently loading...")

        member = await self.bot.mongo.fetch_member_info(ctx.author)

        pokemon_cog = self.bot.get_cog("Pokemon")
        aggregations = await pokemon_cog.create_filter(flags, ctx, order_by=member.order_by)

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
            return await ctx.reply(
                "Found no pokémon matching this search (excluding favorited and selected pokémon).",
                mention_author=mention_author,
            )

        # confirm

        trade_size = len(self.bot.trades[ctx.author.id]["pokemon"][ctx.author.id])

        if 3000 - trade_size < 0:
            return await ctx.send(
                f"There are too many pokémon in this trade! Try adding them individually or seperating it into different trades."
            )

        if trade_size + num > 3000:
            return await ctx.send(
                f"There are too many pokémon in this trade! Try adding `--limit {3000 - trade_size}` to the end of your trade."
            )

        result = await ctx.confirm(
            f"Are you sure you want to trade **{num:,} pokémon**? Favorited and selected pokémon won't be added."
            + await pokemon_cog.valuable_pokemon_details(ctx, aggregations)
        )
        if result is None:
            return await ctx.send("Time's up. Aborted.")
        if result is False:
            return await ctx.send("Aborted.")

        # confirmed, add all

        await ctx.send(f"Adding {num:,} pokémon, this might take a while...")

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

        self.bot.trades[ctx.author.id]["last_updated"] = datetime.utcnow()
        await self.send_trade(ctx, ctx.author, mention_author=mention_author)

    @checks.has_started()
    @commands.guild_only()
    @trade.command(aliases=("i",))
    async def info(self, ctx: PoketwoContext, *, number: int):
        """View a pokémon from the trade."""

        if not await self.is_in_trade(ctx.author):
            return await ctx.send("You're not in a trade!")

        other_id = next(x for x in self.bot.trades[ctx.author.id] if type(x) == int and x != ctx.author.id)
        other = ctx.guild.get_member(other_id) or await ctx.guild.fetch_member(other_id)

        try:
            pokemon = next(
                x for x in self.bot.trades[ctx.author.id]["pokemon"][other_id] if type(x) != int and x.idx == number
            )
        except StopIteration:
            return await ctx.send("Couldn't find that pokémon in the trade!")

        embed = self.bot.Embed(title=f"{pokemon:ln}")
        embed.color = pokemon.color or embed.color

        embed.set_image(url=pokemon.image_url)

        embed.set_thumbnail(url=other.display_avatar.url)

        info = (
            f"**XP:** {pokemon.xp}/{pokemon.max_xp}",
            f"**Nature:** {pokemon.nature}",
            f"**Gender:** {pokemon.gender}",
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

        add_moves_field(pokemon.moves, embed, self.bot)

        embed.set_footer(text=f"Displaying pokémon {number} of {other.display_name}.")

        await ctx.send(embed=embed)

    def cog_unload(self):
        self.process_cancel_trades.cancel()


async def setup(bot: commands.Bot):
    await bot.add_cog(Trading(bot))
