from urllib.parse import urljoin
import pickle
import asyncio
import math
import typing
from enum import Enum
from urllib.parse import urlencode

import data.constants
import discord
from data import models
from discord.ext import commands, tasks

from helpers import checks, constants, converters, pagination


def in_battle(bool=True):
    async def predicate(ctx):
        if bool is (ctx.author in ctx.bot.battles):
            return True
        raise commands.CheckFailure(f"You're {'not' if bool else 'already'} in a battle!")

    return commands.check(predicate)


def get_priority(action, selected):
    if action["type"] == "move":
        s = selected.spd
        if "Paralysis" in selected.ailments:
            s *= 0.5
        return (
            action["value"].priority * 1e20
            + selected.spd * data.constants.STAT_STAGE_MULTIPLIERS[selected.stages.spd]
        )

    return 1e99


class Stage(Enum):
    SELECT = 1
    PROGRESS = 2
    END = 3


class Trainer:
    def __init__(self, user: discord.Member, bot):
        self.user = user
        self.pokemon = []
        self.selected_idx = 0
        self.done = False
        self.bot = bot

    @property
    def selected(self):
        if self.selected_idx == -1:
            return None
        return self.pokemon[self.selected_idx]

    async def get_action(self, message):

        actions = {}

        for idx, x in enumerate(self.selected.moves):
            actions[constants.NUMBER_REACTIONS[idx + 1]] = {
                "type": "move",
                "value": x,
                "text": f"Use {self.bot.data.move_by_number(x).name}",
                "command": self.bot.data.move_by_number(x).name,
            }

        for idx, pokemon in enumerate(self.pokemon):
            if pokemon != self.selected and pokemon.hp > 0:
                actions[constants.LETTER_REACTIONS[idx]] = {
                    "type": "switch",
                    "value": idx,
                    "text": f"Switch to {pokemon.iv_percentage:.2%} {pokemon.species}",
                    "command": f"switch {idx + 1}",
                }

        actions["⏹️"] = {
            "type": "flee",
            "text": "Flee from the battle",
            "command": "flee",
        }
        actions["⏭️"] = {
            "type": "pass",
            "text": "Pass this turn and do nothing.",
            "command": "Pass",
        }

        # Send request

        await self.bot.redis.rpush(
            "move_request",
            pickle.dumps(
                {
                    "cluster_idx": self.bot.cluster_idx,
                    "user_id": self.user.id,
                    "species_id": self.selected.species.id,
                    "actions": actions,
                }
            ),
        )

        uid, action = await self.bot.wait_for("move_decide", check=lambda u, a: u == self.user.id)

        await self.user.send(
            f"You selected **{action['text']}**.\n\n**Back to battle:** {message.jump_url}"
        )

        if action["type"] == "move":
            action["value"] = self.bot.data.move_by_number(action["value"])

        return action


class Battle:
    def __init__(self, users: typing.List[discord.Member], ctx, manager):
        self.trainers = [Trainer(x, ctx.bot) for x in users]
        self.channel = ctx.channel
        self.stage = Stage.SELECT
        self.passed_turns = 0
        self.ctx = ctx
        self.bot = ctx.bot
        self.manager = manager

    async def send_selection(self, ctx):
        embed = self.bot.Embed(color=0x9CCFFF)
        embed.title = "Choose your party"
        embed.description = (
            "Choose **3** pokémon to fight in the battle. The battle will begin once both trainers "
            "have chosen their party. "
        )

        for trainer in self.trainers:
            if len(trainer.pokemon) > 0:
                embed.add_field(
                    name=f"{trainer.user}'s Party",
                    value="\n".join(
                        f"{x.iv_percentage:.2%} IV {x.species} ({x.idx})" for x in trainer.pokemon
                    ),
                )
            else:
                embed.add_field(name=f"{trainer.user}'s Party", value="None")

        embed.set_footer(
            text=f"Use `{ctx.prefix}battle add <pokemon>` to add a pokémon to the party!"
        )

        await ctx.send(embed=embed)

    async def send_ready(self):
        embed = self.bot.Embed(color=0x9CCFFF)
        embed.title = "💥 Ready to battle!"
        embed.description = "The battle will begin in 5 seconds."

        for trainer in self.trainers:
            embed.add_field(
                name=f"{trainer.user}'s Party",
                value="\n".join(
                    f"{x.iv_percentage:.2%} IV {x.species} ({x.idx + 1})" for x in trainer.pokemon
                ),
            )

        await self.channel.send(embed=embed)

    def end(self):
        self.stage = Stage.END
        del self.manager[self.trainers[0].user]

    async def run_step(self, message):
        if self.stage != Stage.PROGRESS:
            return

        actions = await asyncio.gather(
            self.trainers[0].get_action(message), self.trainers[1].get_action(message)
        )

        if actions[0]["type"] == "pass" and actions[1]["type"] == "pass":
            self.passed_turns += 1

        if self.passed_turns >= 3:
            await self.channel.send(
                "Both trainers passed three times in a row. I'll end the battle here."
            )
            self.end()
            return

        iterl = list(zip(actions, self.trainers, reversed(self.trainers)))

        for action, trainer, opponent in iterl:
            action["priority"] = get_priority(action, trainer.selected)

        embed = self.bot.Embed(color=0x9CCFFF)
        embed.title = f"Battle between {self.trainers[0].user.display_name} and {self.trainers[1].user.display_name}."
        embed.set_footer(text="The next round will begin in 5 seconds.")

        for trainer in self.trainers:
            if "Burn" in trainer.selected.ailments:
                trainer.selected.hp -= 1 / 16 * trainer.selected.max_hp
            if "Poison" in trainer.selected.ailments:
                trainer.selected.hp -= 1 / 8 * trainer.selected.max_hp

        for action, trainer, opponent in sorted(
            iterl, key=lambda x: x[0]["priority"], reverse=True
        ):
            title = None
            text = None

            if action["type"] == "flee":
                # battle's over
                await self.channel.send(
                    f"{trainer.user.mention} has fled the battle! {opponent.user.mention} has won."
                )
                self.end()
                return

            elif action["type"] == "switch":
                trainer.selected_idx = action["value"]
                title = f"{trainer.user.display_name} switched pokémon!"
                text = f"{trainer.selected.species} is now on the field!"

            elif action["type"] == "move":

                # calculate damage amount

                move = action["value"]

                result = move.calculate_turn(trainer.selected, opponent.selected)

                title = f"{trainer.selected.species} used {move.name}!"
                text = "\n".join([f"{move.name} dealt {result.damage} damage!"] + result.messages)

                if result.success:
                    opponent.selected.hp -= result.damage
                    trainer.selected.hp += result.healing
                    trainer.selected.hp = min(trainer.selected.hp, trainer.selected.max_hp)

                    if result.healing > 0:
                        text += f"\n{trainer.selected.species} restored {result.healing} HP."
                    elif result.healing < 0:
                        text += f"\n{trainer.selected.species} took {-result.healing} damage."

                    if result.ailment:
                        text += f"\nIt inflicted {result.ailment}!"
                        opponent.selected.ailments.add(result.ailment)

                    for change in result.stat_changes:
                        if move.target_id == 7:
                            target = trainer.selected
                            if change.change < 0:
                                text += f"\nLowered the user's **{constants.STAT_NAMES[change.stat]}** by {-change.change} stages."
                            else:
                                text += f"\nRaised the user's **{constants.STAT_NAMES[change.stat]}** by {change.change} stages."

                        else:
                            target = opponent.selected
                            if change.change < 0:
                                text += f"\nLowered the opponent's **{constants.STAT_NAMES[change.stat]}** by {-change.change} stages."
                            else:
                                text += f"\nRaised the opponent's **{constants.STAT_NAMES[change.stat]}** by {change.change} stages."

                        setattr(
                            target.stages,
                            change.stat,
                            getattr(target.stages, change.stat) + change.change,
                        )

                else:
                    text = "It missed!"

            # check if fainted

            if opponent.selected.hp <= 0:
                opponent.selected.hp = 0
                title = title or "Fainted!"
                text = (text or "") + f" {opponent.selected.species} has fainted."

                try:
                    opponent.selected_idx = next(
                        idx for idx, x in enumerate(opponent.pokemon) if x.hp > 0
                    )
                except StopIteration:
                    # battle's over
                    self.end()
                    opponent.selected_idx = -1
                    await self.channel.send(f"{trainer.user.mention} won the battle!")
                    return

                embed.add_field(name=title, value=text, inline=False)
                break

            if title is not None:
                embed.add_field(name=title, value=text, inline=False)

        await self.channel.send(embed=embed)

    async def send_battle(self):
        embed = self.bot.Embed(color=0x9CCFFF)
        embed.title = f"Battle between {self.trainers[0].user.display_name} and {self.trainers[1].user.display_name}."

        if self.stage == Stage.PROGRESS:
            embed.description = "Choose your moves in DMs. After both players have chosen, the move will be executed."
            t0 = self.trainers[1]  # switched on purpose because API is like that
            t1 = self.trainers[0]
            image_query = {
                "text0": t0.selected.species.name,
                "text1": t1.selected.species.name,
                "hp0": t0.selected.hp / t0.selected.max_hp,
                "hp1": t1.selected.hp / t1.selected.max_hp,
                "shiny0": 1 if t0.selected.shiny else 0,
                "shiny1": 1 if t1.selected.shiny else 0,
                "ball0": [0 if p.hp == 0 else 1 for p in t0.pokemon],
                "ball1": [0 if p.hp == 0 else 1 for p in t1.pokemon],
                "v": 100,
            }
            if hasattr(self.bot.config, "SERVER_URL"):
                url = urljoin(
                    self.bot.config.SERVER_URL,
                    f"battle/{t0.selected.species.id}/{t1.selected.species.id}?{urlencode(image_query, True)}",
                )
                embed.set_image(url=url)
        else:
            embed.description = "The battle has ended."

        for trainer in self.trainers:
            embed.add_field(
                name=trainer.user.display_name,
                value="\n".join(
                    f"**{x.species}** • {x.hp}/{x.max_hp} HP"
                    if trainer.selected == x
                    else f"{x.species} • {x.hp}/{x.max_hp} HP"
                    for x in trainer.pokemon
                ),
            )

        message = await self.channel.send(embed=embed)
        return message

    async def run_battle(self):
        if self.stage != Stage.SELECT:
            return

        self.bot.dispatch("battle_start", self)
        self.stage = Stage.PROGRESS
        while self.stage != Stage.END:
            await asyncio.sleep(5)
            message = await self.send_battle()
            await self.run_step(message)
        await self.send_battle()


class BattleManager:
    def __init__(self):
        self.battles = {}

    def __getitem__(self, user):
        return self.battles[user.id]

    def __contains__(self, user):
        return user.id in self.battles

    def __delitem__(self, user):
        for trainer in self.battles[user.id].trainers:
            del self.battles[trainer.user.id]

    def get_trainer(self, user):
        for trainer in self[user].trainers:
            if trainer.user.id == user.id:
                return trainer

    def get_opponent(self, user):
        for trainer in self[user].trainers:
            if trainer.user.id != user.id:
                return trainer

    def new(self, user1, user2, ctx):
        battle = Battle([user1, user2], ctx, self)
        self.battles[user1.id] = battle
        self.battles[user2.id] = battle
        return battle


class Battling(commands.Cog):
    """For battling."""

    def __init__(self, bot):
        self.bot = bot

        if not hasattr(self.bot, "battles"):
            self.bot.battles = BattleManager()

        self.process_move_decisions.start()
        if self.bot.cluster_idx == 0:
            self.process_move_requests.start()

    def reload_battling(self):
        for battle in self.bot.battles.battles.values():
            battle.stage = Stage.END
        self.bot.battles = BattleManager()

    @tasks.loop(seconds=0.1)
    async def process_move_requests(self):
        with await self.bot.redis as r:
            req = await r.blpop("move_request")
            data = pickle.loads(req[1])
            self.bot.dispatch(
                "move_request",
                data["cluster_idx"],
                data["user_id"],
                data["species_id"],
                data["actions"],
            )

    @process_move_requests.before_loop
    async def before_process_move_requests(self):
        await self.bot.wait_until_ready()

    @tasks.loop(seconds=0.1)
    async def process_move_decisions(self):
        with await self.bot.redis as r:
            req = await r.blpop(f"move_decide:{self.bot.cluster_idx}")
            data = pickle.loads(req[1])
            self.bot.dispatch(
                "move_decide",
                data["user_id"],
                data["action"],
            )

    @process_move_decisions.before_loop
    async def before_process_move_decisions(self):
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_move_request(self, cluster_idx, user_id, species_id, actions):
        user = self.bot.get_user(user_id) or await self.bot.fetch_user(user_id)
        species = self.bot.data.species_by_number(species_id)

        embed = self.bot.Embed(color=0x9CCFFF)
        embed.title = f"What should {species} do?"

        embed.description = "\n".join(
            f"{k} **{v['text']}** • `p!battle move {v['command']}`" for k, v in actions.items()
        )
        msg = await user.send(embed=embed)

        async def add_reactions():
            for k in actions:
                await msg.add_reaction(k)

        self.bot.loop.create_task(add_reactions())

        def check(payload):
            return (
                payload.message_id == msg.id
                and payload.user_id == user.id
                and payload.emoji.name in actions
            )

        async def listen_for_reactions():
            try:
                payload = await self.bot.wait_for("raw_reaction_add", timeout=35, check=check)
                action = actions[payload.emoji.name]
                self.bot.dispatch("battle_move", user, action["command"])
            except asyncio.TimeoutError:
                pass

        self.bot.loop.create_task(listen_for_reactions())

        try:
            while True:
                user, move_name = await self.bot.wait_for(
                    "battle_move", timeout=35, check=lambda u, m: u.id == user.id
                )
                try:
                    action = next(
                        x for x in actions.values() if x["command"].lower() == move_name.lower()
                    )
                except StopIteration:
                    await user.send("That's not a valid move here!")
                else:
                    break
        except asyncio.TimeoutError:
            action = {"type": "pass", "text": "nothing. Passing turn..."}

        await self.bot.redis.rpush(
            f"move_decide:{cluster_idx}",
            pickle.dumps({"user_id": user.id, "action": action}),
        )

    @checks.has_started()
    @in_battle(False)
    @commands.group(aliases=("duel",), invoke_without_command=True, case_insensitive=True)
    async def battle(self, ctx, *, user: discord.Member):
        """Battle another trainer with your pokémon!"""

        # Base cases

        if user == ctx.author:
            return await ctx.send("Nice try...")
        if user in self.bot.battles:
            return await ctx.send(f"**{user}** is already in a battle!")

        member = await self.bot.mongo.Member.find_one({"id": user.id})
        if member is None:
            return await ctx.send("That user hasn't picked a starter pokémon yet!")

        # Challenge to battle

        message = await ctx.send(
            f"Challenging {user.mention} to a battle. Click the checkmark to accept!"
        )
        await message.add_reaction("✅")

        def check(payload):
            return (
                payload.message_id == message.id
                and payload.user_id == user.id
                and payload.emoji.name == "✅"
            )

        try:
            await self.bot.wait_for("raw_reaction_add", timeout=30, check=check)
        except asyncio.TimeoutError:
            await message.add_reaction("❌")
            await ctx.send("The challenge has timed out.")
            return

        # Accepted, continue

        if ctx.author in self.bot.battles:
            return await ctx.send(
                "Sorry, the user who sent the challenge is already in another battle."
            )

        if user in self.bot.battles:
            return await ctx.send(
                "Sorry, you can't accept a challenge while you're already in a battle!"
            )

        battle = self.bot.battles.new(ctx.author, user, ctx)
        await battle.send_selection(ctx)

    @checks.has_started()
    @in_battle(True)
    @battle.command(aliases=("a",))
    async def add(self, ctx, args: commands.Greedy[converters.PokemonConverter]):
        """Add a pokémon to a battle."""

        updated = False

        trainer, opponent = (
            self.bot.battles.get_trainer(ctx.author),
            self.bot.battles.get_opponent(ctx.author),
        )

        for pokemon in args:
            if pokemon is None:
                continue

            if len(trainer.pokemon) >= 3:
                await ctx.send(f"{pokemon.idx}: There are already enough pokémon in the party!")
                return

            for x in trainer.pokemon:
                if x.id == pokemon.id:
                    await ctx.send(f"{pokemon.idx}: This pokémon is already in the party!")
                    return

            pokemon.hp = pokemon.hp
            pokemon.stages = models.StatStages()
            pokemon.ailments = set()
            trainer.pokemon.append(pokemon)

            if len(trainer.pokemon) == 3:
                trainer.done = True

            updated = True

        if not updated:
            return

        if trainer.done and opponent.done:
            await self.bot.battles[ctx.author].send_ready()
            await self.bot.battles[ctx.author].run_battle()
        else:
            await self.bot.battles[ctx.author].send_selection(ctx)

    @checks.has_started()
    @in_battle(True)
    @battle.command(aliases=("m",))
    async def move(self, ctx, *, move):
        """Move in a battle."""

        self.bot.dispatch("battle_move", ctx.author, move)

    @checks.has_started()
    @commands.command(aliases=("mv",), rest_is_raw=True)
    async def moves(self, ctx, *, pokemon: converters.PokemonConverter):
        """View current and available moves for your pokémon."""

        if pokemon is None:
            return await ctx.send("Couldn't find that pokémon!")

        embed = discord.Embed(color=0x9CCFFF)
        embed.title = f"Level {pokemon.level} {pokemon.species} — Moves"
        embed.description = (
            f"Here are the moves your pokémon can learn right now. View all moves and how to get "
            f"them using `{ctx.prefix}moveset`!"
        )

        embed.add_field(
            name="Available Moves",
            value="\n".join(
                x.move.name for x in pokemon.species.moves if pokemon.level >= x.method.level
            ),
        )

        embed.add_field(
            name="Current Moves",
            value="No Moves"
            if len(pokemon.moves) == 0
            else "\n".join(self.bot.data.move_by_number(x).name for x in pokemon.moves),
        )

        await ctx.send(embed=embed)

    @checks.has_started()
    @commands.command()
    async def learn(self, ctx, *, search: str):
        """Learn moves for your pokémon to use in battle."""

        move = self.bot.data.move_by_name(search)

        if move is None:
            return await ctx.send("Couldn't find that move!")

        member = await self.bot.mongo.fetch_member_info(ctx.author)
        pokemon = await self.bot.mongo.fetch_pokemon(ctx.author, member.selected_id)
        if pokemon is None:
            return await ctx.send("You must have a pokémon selected!")

        if move.id in pokemon.moves:
            return await ctx.send("Your pokémon has already learned that move!")

        try:
            pokemon_move = next(x for x in pokemon.species.moves if x.move_id == move.id)
        except StopIteration:
            pokemon_move = None

        if pokemon_move is None or pokemon_move.method.level > pokemon.level:
            return await ctx.send("Your pokémon can't learn that move!")

        update = {}

        if len(pokemon.moves) >= 4:
            await ctx.send(
                "Your pokémon already knows the max number of moves! Please enter the name of a move to replace, "
                "or anything else to abort:\n "
                + "\n".join(self.bot.data.move_by_number(x).name for x in pokemon.moves)
            )

            def check(m):
                return m.channel.id == ctx.channel.id and m.author.id == ctx.author.id

            try:
                msg = await self.bot.wait_for("message", timeout=60, check=check)
            except asyncio.TimeoutError:
                return await ctx.send("Time's up. Aborted.")

            rep_move = self.bot.data.move_by_name(msg.content)
            if rep_move is None or rep_move.id not in pokemon.moves:
                return await ctx.send("Aborted.")

            idx = pokemon.moves.index(rep_move.id)
            update["$set"] = {f"moves.{idx}": move.id}

        else:
            update["$push"] = {f"moves": move.id}

        await self.bot.mongo.update_pokemon(pokemon, update)
        await ctx.send("Your pokémon has learned " + move.name + "!")

    @checks.has_started()
    @commands.command(aliases=("ms",), rest_is_raw=True)
    async def moveset(self, ctx, *, search: str):
        """View all moves for your pokémon and how to get them."""

        search = search.strip()

        if len(search) > 0 and search[0] in "Nn#" and search[1:].isdigit():
            species = self.bot.data.species_by_number(int(search[1:]))
        else:
            species = self.bot.data.species_by_name(search)

            if species is None:
                converter = converters.PokemonConverter(raise_errors=False)
                pokemon = await converter.convert(ctx, search)
                if pokemon is not None:
                    species = pokemon.species

        if species is None:
            raise commands.BadArgument(
                "Please either enter the name of a pokémon species, nothing for your selected pokémon, a number for "
                "a specific pokémon, `latest` for your latest pokémon. ",
            )

        async def get_page(source, menu, pidx):
            pgstart = pidx * 20
            pgend = min(pgstart + 20, len(species.moves))

            # Send embed

            embed = discord.Embed(color=0x9CCFFF)
            embed.title = f"{species} — Moveset"

            embed.set_footer(text=f"Showing {pgstart + 1}–{pgend} out of {len(species.moves)}.")

            for move in species.moves[pgstart:pgend]:
                embed.add_field(name=move.move.name, value=move.text)

            for i in range(-pgend % 3):
                embed.add_field(name="‎", value="‎")

            return embed

        pages = pagination.ContinuablePages(
            pagination.FunctionPageSource(math.ceil(len(species.moves) / 20), get_page)
        )
        self.bot.menus[ctx.author.id] = pages
        await pages.start(ctx)

    @commands.command(aliases=("mi",))
    async def moveinfo(self, ctx, *, search: str):
        """View information about a certain move."""

        move = self.bot.data.move_by_name(search)

        if move is None:
            return await ctx.send("Couldn't find a move with that name!")

        embed = discord.Embed(color=0x9CCFFF)
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
            if getattr(move, x) is not None:
                v = getattr(move, x)  # yeah, i had to remove walrus op cuz its just too bad lol
                embed.add_field(name=name, value=v)
            else:
                embed.add_field(name=name, value="—")

        embed.add_field(name="Class", value=move.damage_class)

        await ctx.send(embed=embed)

    @checks.has_started()
    @in_battle(True)
    @battle.command(aliases=("x",))
    async def cancel(self, ctx):
        """Cancel a battle."""

        self.bot.battles[ctx.author].end()
        await ctx.send("The battle has been canceled.")

    def cog_unload(self):
        if self.bot.cluster_idx == 0:
            self.process_move_requests.cancel()


def setup(bot):
    bot.add_cog(Battling(bot))
