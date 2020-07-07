import asyncio
import math
import random
from functools import cached_property

import discord
from discord.ext import commands, flags

from .database import Database
from helpers import checks, constants, converters, models, mongo, pagination


def setup(bot: commands.Bot):
    bot.add_cog(Battling(bot))


class Battling(commands.Cog):
    """For battling."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

        if not hasattr(self.bot, "battles"):
            self.bot.battles = {}

    @property
    def db(self) -> Database:
        return self.bot.get_cog("Database")

    async def send_move(self, battle, user: discord.Member):
        a, b = battle["users"]
        a = battle["guild"].get_member(a)
        b = battle["guild"].get_member(b)
        other = b if user == a else a

        selected, _ = battle["game"][user.id][battle["selected"][user.id]]
        other_pokemon = battle["game"][other.id][battle["selected"][other.id]]

        cembed = discord.Embed()
        cembed.color = 0xF44336
        cembed.title = f"What should {selected.species} do?"

        actions = {}

        for idx, x in enumerate(selected.moves):
            actions[constants.NUMBER_REACTIONS[idx + 1]] = {
                "type": "move",
                "value": models.GameData.move_by_number(x),
                "text": f"Use {models.GameData.move_by_number(x).name}",
            }

        for i in range(3):
            if i != battle["selected"][user.id] and battle["game"][user.id][i][1] != 0:
                actions[constants.LETTER_REACTIONS[i]] = {
                    "type": "switch",
                    "value": i,
                    "text": f"Switch to {battle['game'][user.id][i][0].iv_percentage:.2%} {battle['game'][user.id][i][0].species}",
                }

        actions["⏹️"] = {"type": "flee", "text": "Flee from the battle"}
        actions["⏭️"] = {"type": "pass", "text": "Pass this turn and do nothing."}

        # Send embed

        cembed.description = "\n".join(f"{k} {v['text']}" for k, v in actions.items())

        msg = await user.send(embed=cembed)

        async def add_reactions():
            for k in actions:
                await msg.add_reaction(k)

        asyncio.create_task(add_reactions())

        def check(reaction, u):
            return (
                reaction.message.id == msg.id
                and u == user
                and reaction.emoji in actions
            )

        try:
            reaction, _ = await self.bot.wait_for(
                "reaction_add", timeout=30, check=check
            )
            action = actions[reaction.emoji]

        except asyncio.TimeoutError:
            action = {"type": "pass", "text": "nothing. Passing turn..."}

        battle["actions"][user.id] = action

        await user.send(f"You selected **{action['text']}**.")

        await asyncio.sleep(random.random() * 5)
        if battle["actions"][other.id] is not None:
            await self.run_step(battle)

    async def run_step(self, battle):
        a, b = battle["users"]
        a = battle["guild"].get_member(a)
        b = battle["guild"].get_member(b)

        def get_priority(action, selected):
            if action["type"] == "move":
                return action["value"].priority * 1e20 + selected.spd

            return 1e99

        priority = {
            x.id: get_priority(
                battle["actions"][x.id],
                battle["game"][x.id][battle["selected"][x.id]][0],
            )
            for x in (a, b)
        }

        embed = discord.Embed()
        embed.color = 0xF44336
        embed.title = f"Battle between {a.display_name} and {b.display_name}."
        embed.description = "The next round will begin in 5 seconds."

        for x in sorted((a, b), key=lambda x: priority[x.id], reverse=True):
            o = b if x == a else a

            selected, _ = battle["game"][x.id][battle["selected"][x.id]]
            other_pokemon = battle["game"][o.id][battle["selected"][o.id]]

            action = battle["actions"][x.id]

            if action["type"] == "flee":
                # battle's over
                await battle["channel"].send(
                    f"{x.mention} has fled the battle! {o.mention} has won."
                )
                del self.bot.battles[x.id]
                del self.bot.battles[o.id]
                return

            elif action["type"] == "switch":

                battle["selected"][x.id] = action["value"]
                selected, _ = battle["game"][x.id][battle["selected"][x.id]]

                title = f"{x.display_name} switched pokémon!"
                text = f"{selected.species} is now on the field!"

                embed.add_field(name=title, value=text, inline=False)

            elif action["type"] == "move":
                move = action["value"]
                success = True

                if move.damage_class_id == 1 or move.power is None:
                    damage = 0
                else:
                    if move.damage_class_id == 2:
                        atk = selected.atk
                        defn = other_pokemon[0].defn
                    else:
                        atk = selected.satk
                        defn = other_pokemon[0].sdef

                    damage = int(
                        (2 * selected.level / 5 + 2) * move.power * atk / defn / 50 + 2
                    )

                    success = random.randint(0, 99) <= move.accuracy

                    if success:
                        other_pokemon[1] -= damage

                title = f"{selected.species} used {move.name}!"
                text = f"{move.name} dealt {damage} damage!"

                if not success:
                    text = "Missed!"

                if other_pokemon[1] <= 0:
                    other_pokemon[1] = 0

                    text += f" {other_pokemon[0].species} has fainted."

                    idx = battle["selected"][o.id]
                    idx = (idx + 1) % 3

                    if battle["game"][o.id][idx][1] == 0:
                        idx = (idx + 1) % 3

                    if battle["game"][o.id][idx][1] == 0:
                        # battle's over
                        battle["stage"] = "end"
                        battle["selected"][o.id] = -1
                        await self.send_battle(x)
                        await battle["channel"].send(
                            f"Battle's over lol {x.mention} won xd hahahahaha gggggg"
                        )
                        del self.bot.battles[x.id]
                        del self.bot.battles[o.id]
                        return

                    battle["selected"][o.id] = idx

                    embed.add_field(name=title, value=text, inline=False)

                    break

                embed.add_field(name=title, value=text, inline=False)

        await battle["channel"].send(embed=embed)

        battle["actions"] = {a.id: None, b.id: None}

        await asyncio.sleep(5)
        await self.send_battle(a)

    async def send_battle(self, user: discord.Member):
        battle = self.bot.battles[user.id]
        a, b = battle["users"]
        start = False

        a = battle["guild"].get_member(a)
        b = battle["guild"].get_member(b)

        embed = discord.Embed()
        embed.color = 0xF44336
        embed.title = f"Battle between {a.display_name} and {b.display_name}."

        if battle["stage"] == "selection":
            start = (
                len(battle["pokemon"][a.id]) == 3 and len(battle["pokemon"][b.id]) == 3
            )

            embed.description = "💥 Preparing for battle! Choose your party in DMs!"

            for i in (a, b):
                if not start and "prev" in battle and i.id != user.id:
                    continue

                o = b if i == a else a

                cembed = discord.Embed()
                cembed.color = 0xF44336
                cembed.title = (
                    "Choose your party"
                    if len(battle["pokemon"][i.id]) < 3
                    else "Waiting for opponent..."
                )
                cembed.description = "Choose **3** pokémon to fight in the battle. The battle will begin once both trainers have chosen their party."
                cembed.add_field(
                    name="Your Party",
                    value="\n".join(
                        f"{x.iv_percentage:.2%} IV {x.species} ({idx + 1})"
                        for x, idx in battle["pokemon"][i.id]
                    )
                    if len(battle["pokemon"][i.id]) > 0
                    else "None",
                )

                if not start:
                    cembed.add_field(name="Opponent's Party", value="???\n???\n???")
                else:
                    cembed.title = "💥 Ready to battle!"
                    cembed.description = "The battle will begin in 5 seconds."
                    cembed.add_field(
                        name="Opponent's Party",
                        value="\n".join(
                            f"{x.species}" for x, _ in battle["pokemon"][o.id]
                        ),
                    )

                cembed.set_footer(
                    text="Use `p!battle add <pokemon>` in this DM to add a pokémon to the party!"
                )
                await i.send(embed=cembed)

        if start:
            await asyncio.sleep(5)

            battle["stage"] = "progress"
            battle["game"] = {
                a.id: [[x, x.hp] for x, _ in battle["pokemon"][a.id]],
                b.id: [[x, x.hp] for x, _ in battle["pokemon"][b.id]],
            }
            battle["selected"] = {a.id: 0, b.id: 0}
            battle["actions"] = {a.id: None, b.id: None}

        if battle["stage"] in ["progress", "end"]:
            if battle["stage"] == "progress":
                embed.description = "Choose your moves in DMs. After both players have chosen, the move will be executed."
            else:
                embed.description = "The battle has ended."

            for i in (a, b):
                embed.add_field(
                    name=i.display_name,
                    value="\n".join(
                        f"**{x.species}** • {hp}/{x.hp} HP"
                        if battle["selected"][i.id] == idx
                        else f"{x.species} • {hp}/{x.hp} HP"
                        for idx, (x, hp) in enumerate(battle["game"][i.id])
                    ),
                )

                if battle["stage"] == "progress":
                    asyncio.create_task(self.send_move(battle, i))

        # Send msg

        if battle["stage"] == "selection" and "prev" in battle:
            return

        msg = await battle["channel"].send(embed=embed)
        battle["prev"] = msg

    @checks.has_started()
    @commands.group(aliases=["b"], invoke_without_command=True)
    async def battle(self, ctx: commands.Context, *, user: discord.Member):
        """Battle another trainer with your pokémon!"""

        # Base cases

        if user == ctx.author:
            return await ctx.send("Nice try...")

        if ctx.author.id in self.bot.battles:
            return await ctx.send("You are already in a battle!")

        if user.id in self.bot.battles:
            return await ctx.send(f"**{user}** is already in a battle!")

        member = await mongo.Member.find_one({"id": user.id})

        if member is None:
            return await ctx.send("That user hasn't picked a starter pokémon yet!")

        # CONFIRM BETA

        confirm = await ctx.send(
            "This is a beta version of battling, so you will not receive any rewards. "
            "Many features are not fully implemented yet. Press 🆗 to continue."
        )
        await confirm.add_reaction("🆗")

        def ccheck(reaction, u):
            return u == ctx.author and str(reaction.emoji) == "🆗"

        try:
            await self.bot.wait_for("reaction_add", timeout=30, check=ccheck)
        except asyncio.TimeoutError:
            await message.add_reaction("❌")
            await ctx.send("The confirmation has timed out.")
            return

        # Challenge to battle

        message = await ctx.send(
            f"Challenging {user.mention} to a battle. Click the checkmark to accept!"
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
            await ctx.send("The challenge has timed out.")
            return

        # Accepted, continue

        if ctx.author.id in self.bot.battles:
            return await ctx.send(
                "Sorry, the user who sent the challenge is already in another battle."
            )

        if user.id in self.bot.battles:
            return await ctx.send(
                "Sorry, you can't accept a challenge while you're already in a battle!"
            )

        battle = {
            "pokemon": {ctx.author.id: [], user.id: []},
            "stage": "selection",
            "users": [ctx.author.id, user.id],
            "guild": ctx.guild,
            "channel": ctx.channel,
            ctx.author.id: False,
            user.id: False,
        }
        self.bot.battles[ctx.author.id] = battle
        self.bot.battles[user.id] = battle

        await self.send_battle(ctx.author)

    @checks.has_started()
    @battle.command(aliases=["a"])
    async def add(self, ctx: commands.Context, *args):
        """Add a pokémon to a battle."""

        if ctx.author.id not in self.bot.battles:
            return await ctx.send("You're not in a battle!")

        updated = False

        for what in args:
            if what.isdigit():

                skip = False

                if not 1 <= int(what) <= 2 ** 31 - 1:
                    await ctx.send(f"{what}: NO")
                    continue

                elif (
                    len(self.bot.battles[ctx.author.id]["pokemon"][ctx.author.id]) >= 3
                ):
                    await ctx.send(
                        f"{what}: There are already enough pokémon in the party!"
                    )
                    skip = True

                else:
                    for x in self.bot.battles[ctx.author.id]["pokemon"][ctx.author.id]:
                        if x[1] + 1 == int(what):
                            await ctx.send(
                                f"{what}: This pokémon is already in the party!"
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

                self.bot.battles[ctx.author.id]["pokemon"][ctx.author.id].append(
                    (pokemon, number)
                )

                updated = True

            else:
                await ctx.send(
                    f"{what}: That's not a valid pokémon to add to the party!"
                )
                continue

        if not updated:
            return

        await self.send_battle(ctx.author)

    @checks.has_started()
    @commands.command(aliases=["m"], rest_is_raw=True)
    async def moves(self, ctx: commands.Context, *, pokemon: converters.Pokemon):
        """View current and available moves for your pokémon."""

        pokemon, idx = pokemon

        embed = discord.Embed()
        embed.color = 0xF44336
        embed.title = f"Level {pokemon.level} {pokemon.species} — Moves"
        embed.description = "Here are the moves your pokémon can learn right now. View all moves and how to get them using `p!moveset`!"

        embed.add_field(
            name="Available Moves",
            value="\n".join(
                x.move.name
                for x in pokemon.species.moves
                if pokemon.level >= x.method.level
            ),
        )

        embed.add_field(
            name="Current Moves",
            value="No Moves"
            if len(pokemon.moves) == 0
            else "\n".join(
                models.GameData.move_by_number(x).name for x in pokemon.moves
            ),
        )

        await ctx.send(embed=embed)

    @checks.has_started()
    @commands.command(aliases=["l"])
    async def learn(self, ctx: commands.Context, *, search: str):
        """Learn moves for your pokémon to use in battle."""

        move = models.GameData.move_by_name(search)

        if move is None:
            return await ctx.send("Couldn't find that move!")

        member = await self.db.fetch_member_info(ctx.author)
        pokemon = await self.db.fetch_pokemon(ctx.author, member.selected)

        if move.id in pokemon.moves:
            return await ctx.send("Your pokémon has already learned that move!")

        try:
            pokemon_move = next(
                x for x in pokemon.species.moves if x.move_id == move.id
            )
        except StopIteration:
            pokemon_move = None

        if pokemon_move is None or pokemon_move.method.level > pokemon.level:
            return await ctx.send("Your pokémon can't learn that move!")

        update = {}

        if len(pokemon.moves) >= 4:

            await ctx.send(
                "Your pokémon already knows the max number of moves! Please enter the name of a move to replace, or anything else to abort:\n"
                + "\n".join(
                    models.GameData.move_by_number(x).name for x in pokemon.moves
                )
            )

            def check(m):
                return m.channel.id == ctx.channel.id and m.author.id == ctx.author.id

            try:
                msg = await self.bot.wait_for("message", timeout=60, check=check)
            except asyncio.TimeoutError:
                return await ctx.send("Time's up. Aborted.")

            rep_move = models.GameData.move_by_name(msg.content)

            if rep_move is None or rep_move.id not in pokemon.moves:
                return await ctx.send("Aborted.")

            idx = pokemon.moves.index(rep_move.id)

            update["$set"] = {f"pokemon.{member.selected}.moves.{idx}": move.id}

        else:
            update["$push"] = {f"pokemon.{member.selected}.moves": move.id}

        await self.db.update_member(ctx.author, update)

        return await ctx.send("Your pokémon has learned " + move.name + "!")

    @checks.has_started()
    @commands.command(aliases=["ms"], rest_is_raw=True)
    async def moveset(self, ctx: commands.Context, *, search: str):
        """View all moves for your pokémon and how to get them."""

        search = search.strip()

        if len(search) > 0 and search[0] in "Nn#" and search[1:].isdigit():
            species = models.GameData.species_by_number(int(search[1:]))
        else:
            species = models.GameData.species_by_name(search)

            if species is None:
                converter = converters.Pokemon(raise_errors=False)
                pokemon, idx = await converter.convert(ctx, search)
                if pokemon is not None:
                    species = pokemon.species

        if species is None:
            raise converters.PokemonConversionError(
                f"Please either enter the name of a pokémon species, nothing for your selected pokémon, a number for a specific pokémon, `latest` for your latest pokémon."
            )

        async def get_page(pidx, clear):
            pgstart = (pidx) * 20
            pgend = min(pgstart + 20, len(species.moves))

            # Send embed

            embed = discord.Embed()
            embed.color = 0xF44336
            embed.title = f"{species} — Moveset"

            embed.set_footer(
                text=f"Showing {pgstart + 1}–{pgend} out of {len(species.moves)}."
            )

            for move in species.moves[pgstart:pgend]:
                embed.add_field(name=move.move.name, value=move.text)

            for i in range(-pgend % 3):
                embed.add_field(name="‎", value="‎")

            return embed

        paginator = pagination.Paginator(
            get_page, num_pages=math.ceil(len(species.moves) / 20)
        )
        await paginator.send(self.bot, ctx, 0)

    @commands.command(aliases=["mi"])
    async def moveinfo(self, ctx: commands.Context, *, search: str):
        """View information about a certain move."""

        move = models.GameData.move_by_name(search)

        if move is None:
            return await ctx.send("Couldn't find a move with that name!")

        embed = discord.Embed()
        embed.color = 0xF44336
        embed.title = move.name

        embed.description = move.description

        embed.add_field(name="Target", value=move.target_text, inline=False)

        for name, x in (
            ("Power", "power"),
            ("Accuracy", "accuracy"),
            ("PP", "pp"),
            ("Priority", "priority"),
            ("Type", "type"),
        ):
            if (v := getattr(move, x)) is not None:
                embed.add_field(name=name, value=v)
            else:
                embed.add_field(name=name, value="—")

        embed.add_field(name="Class", value=move.damage_class)

        await ctx.send(embed=embed)

    @checks.has_started()
    @battle.command(aliases=["x"])
    async def cancel(self, ctx: commands.Context):
        """Cancel a battle."""

        if ctx.author.id not in self.bot.battles:
            return await ctx.send("You're not in a battle!")

        a, b = self.bot.battles[ctx.author.id]["users"]
        del self.bot.battles[a]
        del self.bot.battles[b]

        await ctx.send("The battle has been canceled.")
