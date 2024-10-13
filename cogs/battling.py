from __future__ import annotations

import asyncio
import math
import pickle
from datetime import datetime
from enum import Enum
from urllib.parse import urlencode, urljoin
from typing import TYPE_CHECKING, Any, Optional, List, Tuple

import discord
from discord.ext import commands, tasks
from cogs.mongo import Pokemon

import data.constants
from data import models
from helpers import checks, constants, converters, pagination, flags
from helpers.utils import add_moves_field

if TYPE_CHECKING:
    from bot import ClusterBot


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
            action["value"].priority * 1e20 + selected.spd * data.constants.STAT_STAGE_MULTIPLIERS[selected.stages.spd]
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
                    "text": f"Switch to {pokemon:iLpgX}",
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
                    "trainer_data": {"user_id": self.user.id, "pokemon": [p.to_mongo() for p in self.pokemon]},
                    "species_id": self.selected.species.id,
                    "actions": actions,
                }
            ),
        )

        uid, action = await self.bot.wait_for("move_decide", check=lambda u, a: u == self.user.id)

        view = discord.ui.View(timeout=0)
        view.add_item(discord.ui.Button(label="Back to battle", url=message.jump_url))
        await self.user.send(f"You selected **{action['text']}**.", view=view)

        if action["type"] == "move":
            action["value"] = self.bot.data.move_by_number(action["value"])

        return action


def add_selection_field(embed: ClusterBot.Embed, trainer: Trainer, pokemon: List[Pokemon]):
    if len(pokemon) > 0:
        embed.add_field(
            name=f"{trainer.user}'s Party",
            value="\n".join(f"{x:iLpgX}" for x in pokemon),
        )
    else:
        embed.add_field(name=f"{trainer.user}'s Party", value="None")


class Battle:
    def __init__(self, users: List[discord.Member], ctx, manager):
        self.trainers = [Trainer(x, ctx.bot) for x in users]
        self.channel = ctx.channel
        self.stage = Stage.SELECT
        self.passed_turns = 0
        self.ctx = ctx
        self.bot = ctx.bot
        self.manager = manager

    async def send_selection(self, ctx):
        embed = self.bot.Embed(title="Choose your party")
        embed.description = (
            "Choose **3** pokémon to fight in the battle. The battle will begin once both trainers "
            "have chosen their party. "
        )

        for trainer in self.trainers:
            add_selection_field(embed, trainer, trainer.pokemon)

        embed.set_footer(text=f"Use `{ctx.clean_prefix}battle add <pokemon>` to add a pokémon to the party!")

        await ctx.send(embed=embed)

    async def send_ready(self):
        embed = self.bot.Embed(title="💥 Ready to battle!", description="The battle will begin in 5 seconds.")

        for trainer in self.trainers:
            add_selection_field(embed, trainer, trainer.pokemon)

        await self.channel.send(embed=embed)

    def end(self):
        self.stage = Stage.END
        del self.manager[self.trainers[0].user]

    def inc_hp(self, pokemon, value: float):
        pokemon.hp = round(min(max(pokemon.hp + value, 0), pokemon.max_hp), 2)

    async def run_step(self, message):
        if self.stage != Stage.PROGRESS:
            return

        actions = await asyncio.gather(self.trainers[0].get_action(message), self.trainers[1].get_action(message))

        if actions[0]["type"] == "pass" and actions[1]["type"] == "pass":
            self.passed_turns += 1

        if self.passed_turns >= 3:
            await self.channel.send("Both trainers passed three times in a row. I'll end the battle here.")
            self.end()
            return

        iterl = list(zip(actions, self.trainers, reversed(self.trainers)))

        for action, trainer, opponent in iterl:
            action["priority"] = get_priority(action, trainer.selected)

        description = []
        for trainer in self.trainers:
            selected = trainer.selected
            if "Burn" in selected.ailments:
                ailment_damage = round(1 / 16 * selected.max_hp, 2)
                self.inc_hp(selected, -ailment_damage)
                description.append(f"{selected.species} took {ailment_damage} Burn damage.")

            if "Poison" in selected.ailments:
                ailment_damage = round(1 / 8 * selected.max_hp, 2)
                self.inc_hp(selected, -ailment_damage)
                description.append(f"{selected.species} took {ailment_damage} Poison damage.")

        embed = self.bot.Embed(
            title=f"Battle between {self.trainers[0].user.display_name} and {self.trainers[1].user.display_name}.",
            description="\n".join(description),
        )
        embed.set_footer(text="The next round will begin in 5 seconds.")

        winner = None
        for action, trainer, opponent in sorted(iterl, key=lambda x: x[0]["priority"], reverse=True):
            title = None
            text = None

            if action["type"] == "flee":
                # battle's over
                await self.channel.send(f"{trainer.user.mention} has fled the battle! {opponent.user.mention} has won.")
                self.bot.dispatch("battle_win", self, opponent.user)
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
                    self.inc_hp(opponent.selected, -result.damage)
                    self.inc_hp(trainer.selected, result.healing)

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

            text = (text or "") + "\n\n"

            # check if fainted

            break_loop = False
            if opponent.selected.hp <= 0:
                title = title or "Fainted!"
                text += f"{opponent.selected.species} has fainted.\n"

                try:
                    opponent.selected_idx = next(idx for idx, x in enumerate(opponent.pokemon) if x.hp > 0)
                except StopIteration:
                    # battle's over
                    opponent.selected_idx = -1
                    winner = trainer

                break_loop = True

            if trainer.selected.hp <= 0:
                title = title or "Fainted!"
                text += f"{trainer.selected.species} has fainted."

                try:
                    trainer.selected_idx = next(idx for idx, x in enumerate(trainer.pokemon) if x.hp > 0)
                except StopIteration:
                    # battle's over
                    trainer.selected_idx = -1
                    winner = opponent

                break_loop = True

            if title is not None:
                embed.add_field(name=title, value=text, inline=False)

            if break_loop:
                break

        if winner:
            embed.set_footer(text="The battle has ended.")

        await self.channel.send(embed=embed)

        if winner:
            self.end()
            self.bot.dispatch("battle_win", self, winner.user)
            await self.channel.send(f"{winner.user.mention} won the battle!")

    async def send_battle(self):
        embed = self.bot.Embed(
            title=f"Battle between {self.trainers[0].user.display_name} and {self.trainers[1].user.display_name}."
        )

        pkm_format_spec = "iLpg"

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
                "gender0": t0.selected.gender,
                "gender1": t1.selected.gender,
                "ball0": [0 if p.hp == 0 else 1 for p in t0.pokemon],
                "ball1": [0 if p.hp == 0 else 1 for p in t1.pokemon],
                "v": 100,
            }
            if hasattr(self.bot.config, "EXT_SERVER_URL"):
                url = urljoin(
                    self.bot.config.EXT_SERVER_URL,
                    f"battle/{t0.selected.species.id}/{t1.selected.species.id}?{urlencode(image_query, True)}",
                )
                embed.set_image(url=url)
        else:
            embed.description = "The battle has ended."
            pkm_format_spec += "X"

        for trainer in self.trainers:
            embed.add_field(
                name=trainer.user.display_name,
                value="\n".join(
                    f"**{x:{pkm_format_spec}}** • {x.hp}/{x.max_hp} HP"
                    if trainer.selected == x
                    else f"{x:{pkm_format_spec}} • {x.hp}/{x.max_hp} HP"
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


ACTION_TIMEOUT = 35
MOVES_ROW = 0
SWITCH_ROW = 1
FLEE_AND_PASS_ROW = 2


class ActionSelect(discord.ui.Select):
    async def callback(self, interaction):
        await interaction.response.defer()

        value = self.values[0]
        option = discord.utils.get(self.options, value=value)

        option.default = True
        self.view.action = self.view.actions[value]
        self.view.stop()


class ActionButton(discord.ui.Button):
    def __init__(self, action: dict, *args, **kwargs):
        self.action = action
        super().__init__(*args, **kwargs)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()

        self.view.action = self.action
        self.view.stop()


class ActionView(discord.ui.View):
    def __init__(self, bot: ClusterBot, trainer_data: dict, actions: dict):
        self.bot = bot
        self.trainer_data = trainer_data
        self.actions = actions

        self.action = None
        self.message = None
        super().__init__(timeout=ACTION_TIMEOUT)

        self.fill_items()

    def fill_items(self):
        move_options = []
        switch_options = []
        for emoji, action in self.actions.items():
            match action["type"]:
                case "move":
                    move = self.bot.data.move_by_number(action["value"])
                    sprite = self.bot.sprites.get_type_sprite(move.type) or None

                    move_options.append(
                        discord.SelectOption(
                            emoji=sprite,
                            label=move.name,
                            description=move.damage_class,
                            value=emoji,
                        )
                    )
                case "switch":
                    pokemon_idx = action["value"]
                    pokemon_data = self.trainer_data["pokemon"][pokemon_idx]
                    pokemon = self.bot.mongo.Pokemon.build_from_mongo(pokemon_data)
                    switch_options.append(
                        discord.SelectOption(
                            emoji=self.bot.sprites.get(pokemon.species, shiny=pokemon.shiny) or None,
                            label=f"{pokemon:LpX}",
                            description="/".join(pokemon.species.types),
                            value=emoji,
                        )
                    )
                case "flee" | "pass":
                    self.add_item(
                        ActionButton(
                            action,
                            label=action["type"].capitalize(),
                            row=FLEE_AND_PASS_ROW,
                        )
                    )

        none_option = discord.SelectOption(
            label="None",
            value="none",
        )

        self.add_item(
            ActionSelect(
                options=move_options or [none_option],
                placeholder="Use a Move",
                row=MOVES_ROW,
                disabled=len(move_options) == 0,
            )
        )
        self.add_item(
            ActionSelect(
                options=switch_options or [none_option],
                placeholder="Switch Pokémon",
                row=SWITCH_ROW,
                disabled=len(switch_options) == 0,
            )
        )

    async def disable_items(self):
        for item in self.children:
            if getattr(item, "style", None) != discord.ButtonStyle.link:
                item.disabled = True

        if self.message:
            await self.message.edit(view=self)

    async def interaction_check(self, interaction):
        if interaction.user.id not in {
            self.bot.owner_id,
            self.trainer_data["user_id"],
            *self.bot.owner_ids,
        }:
            await interaction.response.send_message("You can't use this!", ephemeral=True)
            return False
        return True


class Battling(commands.Cog):
    """For battling."""

    def __init__(self, bot):
        self.bot: ClusterBot = bot

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
        if not self.bot.redis:
            return

        with await self.bot.redis as r:
            req = await r.blpop("move_request")
            data = pickle.loads(req[1])
            self.bot.dispatch(
                "move_request",
                data["cluster_idx"],
                data["trainer_data"],
                data["species_id"],
                data["actions"],
            )

    @process_move_requests.before_loop
    async def before_process_move_requests(self):
        await self.bot.wait_until_ready()

    @tasks.loop(seconds=0.1)
    async def process_move_decisions(self):
        if not self.bot.redis:
            return

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
    async def on_move_request(self, cluster_idx: int, trainer_data: dict, species_id: int, actions: dict):
        user_id = trainer_data["user_id"]
        species = self.bot.data.species_by_number(species_id)

        embed = self.bot.Embed(title=f"What should {species} do?")

        available_moves = []
        available_pokemon = []

        for e, a in actions.items():
            match a["type"]:
                case "move":
                    move = self.bot.data.move_by_number(a["value"])
                    sprite = f"{self.bot.sprites.get_type_sprite(move.type)} "
                    available_moves.append(f"{sprite}{move.name}".strip())

                case "switch":
                    pokemon_data = trainer_data["pokemon"][a["value"]]
                    pokemon = self.bot.mongo.Pokemon.build_from_mongo(pokemon_data)
                    available_pokemon.append(f"{pokemon:iLpgX}")

        embed.add_field(name="Available Moves", value="\n".join(available_moves) or "None")

        embed.add_field(name="Available Pokémon", value="\n".join(available_pokemon) or "None")

        embed.set_footer(text=f"You can also use `@Pokétwo battle move <move-name> | switch <idx> | flee | pass`")

        view = ActionView(self.bot, trainer_data, actions)
        view.message = await self.bot.send_dm(user_id, embed=embed, view=view)

        async def wait_view():
            await view.wait()
            action = view.action
            if action is not None:
                self.bot.dispatch("battle_move", user_id, action["command"])

        self.bot.loop.create_task(wait_view())

        try:
            while True:
                _, move_name = await self.bot.wait_for(
                    "battle_move", timeout=ACTION_TIMEOUT, check=lambda u, m: u == user_id
                )
                try:
                    action = next(x for x in actions.values() if x["command"].lower() == move_name.lower())
                except StopIteration:
                    await self.bot.send_dm(user_id, "That's not a valid move here!")
                else:
                    break
        except asyncio.TimeoutError:
            action = {"type": "pass", "text": "nothing. Passing turn..."}

        await view.disable_items()

        await self.bot.redis.rpush(
            f"move_decide:{cluster_idx}",
            pickle.dumps({"user_id": user_id, "action": action}),
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

        member = await ctx.bot.mongo.Member.find_one({"id": user.id}, {"suspended": 1, "suspension_reason": 1})

        if member is None:
            return await ctx.send("That user hasn't picked a starter pokémon yet!")

        if member.suspended or datetime.utcnow() < member.suspended_until:
            return await ctx.send(f"**{user}** is suspended from the bot!")

        # Challenge to battle

        result = await ctx.request(
            user, f"Challenging {user.mention} to a battle. Click the accept button to accept!", timeout=30
        )
        if result is None:
            return await ctx.send("The request to battle has timed out.")
        if result is False:
            return await ctx.send("Rejected.")

        # Accepted, continue

        if ctx.author in self.bot.battles:
            return await ctx.send("Sorry, the user who sent the challenge is already in another battle.")

        if user in self.bot.battles:
            return await ctx.send("Sorry, you can't accept a challenge while you're already in a battle!")

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
                await ctx.send(f"Couldn't find that pokémon!")
                continue

            if len(trainer.pokemon) >= 3:
                await ctx.send(f"{pokemon.idx}: There are already enough pokémon in the party!")
                return

            if pokemon in trainer.pokemon:
                await ctx.send(f"{pokemon.idx}: This pokémon is already in the party!")
                continue

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

        self.bot.dispatch("battle_move", ctx.author.id, move)

    @checks.has_started()
    @commands.command(aliases=("mv",), rest_is_raw=True)
    async def moves(self, ctx, *, pokemon: converters.PokemonConverter):
        """View current and available moves for your pokémon."""

        if pokemon is None:
            return await ctx.send("Couldn't find that pokémon!")

        embed = self.bot.Embed(title=f"{pokemon:l} — Moves")
        embed.description = (
            f"Here are the moves your pokémon can learn right now. View all moves and how to get "
            f"them using `{ctx.clean_prefix}moveset`!"
        )

        embed.add_field(
            name="Available Moves",
            value="\n".join(x.move.name for x in pokemon.species.moves if pokemon.level >= x.method.level),
        )

        add_moves_field(pokemon.moves, embed, self.bot)

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
            result = await ctx.select(
                "Your pokémon already knows the max number of moves! Please select a move to replace.",
                options=[discord.SelectOption(label=self.bot.data.move_by_number(x).name) for x in set(pokemon.moves)],
            )
            if result is None:
                return await ctx.send("Time's up. Aborted.")

            rep_move = self.bot.data.move_by_name(result[0])
            idx = pokemon.moves.index(rep_move.id)
            update["$set"] = {f"moves.{idx}": move.id}

        else:
            update["$push"] = {f"moves": move.id}

        await self.bot.mongo.update_pokemon(pokemon, update)
        await ctx.send("Your pokémon has learned " + move.name + "!")

    # Pokemon name
    @flags.add_flag("pokemon_name", nargs="*")

    # Filter
    @flags.add_flag("--type", "--t", type=str)
    @flags.add_flag("--damage-class", "--class", type=str)
    @checks.has_started()
    @flags.command(aliases=("ms",))
    async def moveset(self, ctx, **flags):
        """View all moves for your pokémon and how to get them."""

        search = " ".join(flags["pokemon_name"]).strip()

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

        def include(move):
            if flags["type"] and move.type.lower() != flags["type"].lower():
                return False

            if flags["damage_class"] and move.damage_class.lower() != flags["damage_class"].lower():
                return False

            return True

        moves = [move for move in species.moves if include(move.move)]

        async def get_page(source, menu, pidx):
            pgstart = pidx * 20
            pgend = min(pgstart + 20, len(moves))

            # Send embed

            embed = self.bot.Embed(title=f"{species} — Moveset")

            embed.set_footer(text=f"Showing {pgstart + 1}–{pgend} out of {len(moves)}.")

            for move in moves[pgstart:pgend]:
                type_emoji = self.bot.sprites.get_type_sprite(move.move.type)
                class_emoji = self.bot.sprites[f"class_{move.move.damage_class.lower()}"]
                embed.add_field(name=f"[{type_emoji}/{class_emoji}] {move.move.name}", value=move.text)

            for i in range(-pgend % 3):
                embed.add_field(name="‎", value="‎")

            return embed

        pages = pagination.ContinuablePages(pagination.FunctionPageSource(math.ceil(len(moves) / 20), get_page))
        self.bot.menus[ctx.author.id] = pages
        await pages.start(ctx)

    # Move name
    @flags.add_flag("move_name", nargs="*")

    # Filter
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
    @flags.add_flag("--event", "--ev", action="store_true")
    @flags.add_flag("--mega", action="store_true")
    @flags.add_flag("--name", "--n", nargs="+", action="append")
    @flags.add_flag("--evolutions", "--evoline", "--evo", nargs="+", action="append")
    @flags.add_flag("--type", "--t", type=str, action="append")
    @flags.add_flag("--region", "--r", type=str, action="append")
    @flags.add_flag("--learns", nargs="*", action="append")
    @checks.has_started()
    @flags.command(aliases=("ls",))
    async def learnset(self, ctx, **flags):
        """View all pokémon (including forms) that learn a particular move, or any move if move_name is empty."""

        move_name = " ".join(flags["move_name"])

        if move_name:
            move = self.bot.data.move_by_name(move_name)
            if move is None:
                return await ctx.send("Couldn't find a move with that name!")
        else:
            move = None

        if flags.get("regional"):
            for regional in ("alolan", "galarian", "hisuian", "paldean"):
                flags[regional] = True

        if flags.get("evolutions"):
            if "name" in flags and flags["name"] is None:
                flags["name"] = []

            flags["name"].extend(
                [
                    e.name.split()
                    for x in flags["evolutions"]
                    for i in set(self.bot.data.find_all_matches(" ".join(x)))
                    for e in self.bot.data.species_by_number(i).evolution_line
                ]
            )

        forms = [
            s
            for form in ("alolan", "galarian", "hisuian", "paldean", "mega", "event")
            for s in getattr(self.bot.data, f"list_{form}")
            if flags[form]
        ]

        rarities = [
            s
            for rarity in ("mythical", "legendary", "ub")
            for s in getattr(self.bot.data, f"list_{rarity}")
            if flags[rarity] or flags.get("rare")
        ]

        def include(key):
            if forms and key not in forms:
                return False

            if rarities and key not in rarities:
                return False

            if flags["paradox"] and key not in self.bot.data.list_paradox:
                return False

            if flags["event"] and key not in self.bot.data.list_event:
                return False

            if flags["mega"] and key not in self.bot.data.list_mega:
                return False

            if flags["name"] and key not in [
                i for x in flags["name"] for i in self.bot.data.find_all_matches(" ".join(x))
            ]:
                return False

            if flags["type"] and key not in [i for x in flags["type"] for i in self.bot.data.list_type(x)]:
                return False

            if flags["region"] and key not in [i for x in flags["region"] for i in self.bot.data.list_region(x)]:
                return False

            if flags["learns"] and key not in [
                i for x in flags["learns"] for i in self.bot.data.list_move(" ".join(x))
            ]:
                return False

            return True

        # Get list of (Species, [PokemonMove objects]) tuples of each
        # species that can learn this move (if provided, otherwise any move) and matches the flags.
        pokemon = [
            (
                p := self.bot.data.species_by_number(sid),
                [pm for pm in p.moves if pm.move.name == move.name] if move else None,
            )
            for sid in self.bot.data.list_move(move.name if move else None)
            if include(sid)
        ]

        if not pokemon:
            return await ctx.send("No pokémon found.")

        total_count = len(pokemon)

        async def get_page(source, menu, pidx):
            pgstart = pidx * 20
            pgend = min(pgstart + 20, len(pokemon))

            # Send embed

            embed = self.bot.Embed(title=f"{move.name if move else 'Any move'} — Learnset")

            embed.set_footer(text=f"Showing {pgstart + 1}–{pgend} out of {total_count}.")

            for species, pokemon_moves in pokemon[pgstart:pgend]:
                try:
                    emoji = self.bot.sprites.get(species) + " "
                except KeyError:
                    emoji = ""

                embed.add_field(
                    name=f"{emoji}{species.name} #{species.id}",
                    value=" / ".join(pm.method.text for pm in pokemon_moves) if move else "—",
                )

            for i in range(-pgend % 3):
                embed.add_field(name="‎", value="‎")

            return embed

        pages = pagination.ContinuablePages(pagination.FunctionPageSource(math.ceil(total_count / 20), get_page))
        self.bot.menus[ctx.author.id] = pages
        await pages.start(ctx)

    @commands.command(aliases=("mi",))
    async def moveinfo(self, ctx, *, search: str):
        """View information about a certain move."""

        move = self.bot.data.move_by_name(search)

        if move is None:
            return await ctx.send("Couldn't find a move with that name!")

        embed = self.bot.Embed(title=move.name, description=move.description)
        embed.add_field(name="Target", value=move.target_text, inline=False)

        for name, x in (
            ("Power", "power"),
            ("Accuracy", "accuracy"),
            ("PP", "pp"),
            ("Priority", "priority"),
        ):
            if getattr(move, x) is not None:
                v = getattr(move, x)  # yeah, i had to remove walrus op cuz its just too bad lol
                embed.add_field(name=name, value=v)
            else:
                embed.add_field(name=name, value="—")

        embed.add_field(name="Type", value=f"{self.bot.sprites.get_type_sprite(move.type)} {move.type}")

        class_sprite = self.bot.sprites[f"class_{move.damage_class.lower()}"].replace("_", move.damage_class, 1)
        embed.add_field(name="Class", value=f"{class_sprite} {move.damage_class}")

        await ctx.send(embed=embed)

    @in_battle(True)
    @battle.command(aliases=("x",))
    async def cancel(self, ctx):
        """Cancel a battle."""

        self.bot.battles[ctx.author].end()
        await ctx.send("The battle has been canceled.")

    def cog_unload(self):
        if self.bot.cluster_idx == 0:
            self.process_move_requests.cancel()


async def setup(bot: commands.Bot):
    await bot.add_cog(Battling(bot))
