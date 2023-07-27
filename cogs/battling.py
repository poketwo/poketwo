import asyncio
import math
import pickle
import typing
from datetime import datetime
from enum import Enum
from urllib.parse import urlencode, urljoin

import discord
from discord.ext import commands, tasks

import data.constants
from data import models
from helpers import checks, constants, converters, pagination


def in_battle(bool=True):
    async def predicate(ctx):
        if bool is (ctx.author in ctx.bot.battles):
            return True
        raise commands.CheckFailure(ctx._("not-in-battle" if bool else "already-in-battle"))

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

        # TODO: We should be accessing ctx._ here instead of bot._

        for idx, x in enumerate(self.selected.moves):
            actions[constants.NUMBER_REACTIONS[idx + 1]] = {
                "type": "move",
                "value": x,
                "text": self.bot._("action-move", move=self.bot.data.move_by_number(x).name),
                "command": self.bot.data.move_by_number(x).name,
            }

        for idx, pokemon in enumerate(self.pokemon):
            if pokemon != self.selected and pokemon.hp > 0:
                actions[constants.LETTER_REACTIONS[idx]] = {
                    "type": "switch",
                    "value": idx,
                    "text": ctx._("action-switch", species=pokemon.species, ivPercentage=pokemon.iv_percentage),
                    "command": f"switch {idx + 1}",
                }

        actions["⏹️"] = {
            "type": "flee",
            "text": self.bot._("action-flee"),
            "command": "flee",
        }
        actions["⏭️"] = {
            "type": "pass",
            "text": self.bot._("action-pass"),
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

        await self.user.send(self.bot._("selected-action", jumpUrl=message.jump_url, action=action["text"]))

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
        embed = ctx.localized_embed("battle-selection-embed")
        embed.color = constants.PINK

        for trainer in self.trainers:
            if len(trainer.pokemon) > 0:
                embed.add_field(
                    name=ctx._("battle-selection-party-field-name", trainer=trainer.user),
                    value="\n".join(
                        ctx._(
                            "battle-selection-party-line", ivPercentage=x.iv_percentage, species=x.species, index=x.idx
                        )
                        for x in trainer.pokemon
                    ),
                )
            else:
                embed.add_field(name=ctx._("battle-selection-party-field-name"), value="None")

        await ctx.send(embed=embed)

    async def send_ready(self):
        embed = self.ctx.localized_embed("battle-ready-embed")

        for trainer in self.trainers:
            embed.add_field(
                name=self.ctx._("battle-selection-party-field-name", trainer=trainer.user),
                value="\n".join(
                    self.ctx._(
                        "battle-selection-party-line", ivPercentage=x.iv_percentage, species=x.species, index=x.idx
                    )
                    for x in trainer.pokemon
                ),
            )

        await self.channel.send(embed=embed)

    def end(self):
        self.stage = Stage.END
        del self.manager[self.trainers[0].user]

    async def run_step(self, message):
        if self.stage != Stage.PROGRESS:
            return

        actions = await asyncio.gather(self.trainers[0].get_action(message), self.trainers[1].get_action(message))

        if actions[0]["type"] == "pass" and actions[1]["type"] == "pass":
            self.passed_turns += 1

        if self.passed_turns >= 3:
            await self.channel.send(self.ctx._("trainers-repeatedly-passing"))
            self.end()
            return

        iterl = list(zip(actions, self.trainers, reversed(self.trainers)))

        for action, trainer, opponent in iterl:
            action["priority"] = get_priority(action, trainer.selected)

        embed = self.bot.Embed(
            title=self.ctx._(
                "battle-between",
                firstTrainer=self.trainers[0].user.display_name,
                secondTrainer=self.trainers[1].user.display_name,
            )
        )
        embed.set_footer(text=ctx._("next-round-begins-in", seconds=5))

        for trainer in self.trainers:
            if "Burn" in trainer.selected.ailments:
                trainer.selected.hp -= 1 / 16 * trainer.selected.max_hp
            if "Poison" in trainer.selected.ailments:
                trainer.selected.hp -= 1 / 8 * trainer.selected.max_hp

        for action, trainer, opponent in sorted(iterl, key=lambda x: x[0]["priority"], reverse=True):
            title = None
            text = None

            if action["type"] == "flee":
                # battle's over
                await self.channel.send(
                    self.ctx._("opponent-has-fled", opponent=opponent.user.mention, fleeingTrainer=trainer.user.mention)
                )
                self.bot.dispatch("battle_win", self, opponent.user)
                self.end()
                return

            elif action["type"] == "switch":
                trainer.selected_idx = action["value"]
                title = self.ctx._("switched-pokemon-title", trainer=trainer.user.display_name)
                text = self.ctx._("switched-pokemon-text", pokemon=trainer.selected.species)

            elif action["type"] == "move":

                # calculate damage amount

                move = action["value"]

                result = move.calculate_turn(trainer.selected, opponent.selected)

                title = self.ctx._("trainer-used-move", move=move.name, pokemon=trainer.selected.species)
                text = "\n".join([self.ctx._("dealt-damage", damage=result.damage, move=move.name)] + result.messages)

                if result.success:
                    opponent.selected.hp -= result.damage
                    trainer.selected.hp += result.healing
                    trainer.selected.hp = min(trainer.selected.hp, trainer.selected.max_hp)

                    if result.healing > 0:
                        text += "\n" + self.ctx._(
                            "restored-hp", pokemon=trainer.selected.species, healed=result.healing
                        )
                    elif result.healing < 0:
                        text += "\n" + self.ctx._(
                            "took-damage", pokemon=trainer.selected.species, damage=-result.healing
                        )

                    if result.ailment:
                        text += "\n" + ctx._("ailment-inflicted", ailment=result.ailment)
                        opponent.selected.ailments.add(result.ailment)

                    for change in result.stat_changes:
                        if move.target_id == 7:
                            target = trainer.selected
                            if change.change < 0:
                                text += "\n" + self.ctx._(
                                    "lowered-user-stat", stat=constants.STAT_NAMES[change.stat], change=-change.change
                                )
                            else:
                                text += "\n" + self.ctx._(
                                    "raised-user-stat", change=change.change, stat=constants.STAT_NAMES[change.stat]
                                )

                        else:
                            target = opponent.selected
                            if change.change < 0:
                                text += "\n" + self.ctx._(
                                    "lowered-opponent-stat",
                                    change=-change.change,
                                    stat=constants.STAT_NAMES[change.stat],
                                )
                            else:
                                text += "\n" + self.ctx._(
                                    "raised-opponent-stat", change=change.change, stat=constants.STAT_NAMES[change.stat]
                                )

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
                title = title or self.ctx._("fainted")
                text = (text or "") + self.ctx._("pokemon-has-fainted", pokemon=opponent.selected.species)

                try:
                    opponent.selected_idx = next(idx for idx, x in enumerate(opponent.pokemon) if x.hp > 0)
                except StopIteration:
                    # battle's over
                    self.end()
                    opponent.selected_idx = -1
                    self.bot.dispatch("battle_win", self, trainer.user)
                    await self.channel.send(ctx._("won-battle", victor=trainer.user.mention))
                    return

                embed.add_field(name=title, value=text, inline=False)
                break

            if title is not None:
                embed.add_field(name=title, value=text, inline=False)

        await self.channel.send(embed=embed)

    async def send_battle(self):
        embed = self.bot.Embed(
            title=self.bot._(
                "battle-between",
                firstTrainer=self.trainers[0].user.display_name,
                secondTrainer=self.trainers[1].user.display_name,
            ),
        )

        if self.stage == Stage.PROGRESS:
            embed.description = self.ctx._("battle-dm-cta")
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
            if hasattr(self.bot.config, "EXT_SERVER_URL"):
                url = urljoin(
                    self.bot.config.EXT_SERVER_URL,
                    f"battle/{t0.selected.species.id}/{t1.selected.species.id}?{urlencode(image_query, True)}",
                )
                embed.set_image(url=url)
        else:
            embed.description = self.ctx._("battle-ended")

        for trainer in self.trainers:
            embed.add_field(
                name=trainer.user.display_name,
                value="\n".join(
                    self.ctx._(
                        "trainer-pokemon-line-selected" if trainer.selected == x else "trainer-pokemon-line",
                        pokemon=x.species,
                        hp=x.hp,
                        maxHp=x.max_hp,
                    )
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
        species = self.bot.data.species_by_number(species_id)

        embed = self.bot.Embed(title=self.bot._("move-request-cta", pokemon=species))

        embed.description = "\n".join(
            self.bot._(
                "move-action-request-line", action=k, description=v["text"], command=f"battle move {v['command']}"
            )
            for k, v in actions.items()
        )
        msg = await self.bot.send_dm(user_id, embed=embed)

        async def add_reactions():
            for k in actions:
                await msg.add_reaction(k)

        self.bot.loop.create_task(add_reactions())

        def check(payload):
            return payload.message_id == msg.id and payload.user_id == user_id and payload.emoji.name in actions

        async def listen_for_reactions():
            try:
                payload = await self.bot.wait_for("raw_reaction_add", timeout=35, check=check)
                action = actions[payload.emoji.name]
                self.bot.dispatch("battle_move", user_id, action["command"])
            except asyncio.TimeoutError:
                pass

        self.bot.loop.create_task(listen_for_reactions())

        try:
            while True:
                _, move_name = await self.bot.wait_for("battle_move", timeout=35, check=lambda u, m: u == user_id)
                try:
                    action = next(x for x in actions.values() if x["command"].lower() == move_name.lower())
                except StopIteration:
                    await self.bot.send_dm(user_id, self.bot._("move-request-invalid-move"))
                else:
                    break
        except asyncio.TimeoutError:
            action = {"type": "pass", "text": self.bot._("action-pass-text")}

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
            return await ctx.send(ctx._("nice-try"))
        if user in self.bot.battles:
            return await ctx.send(ctx._("user-already-in-battle", user=user))

        member = await ctx.bot.mongo.Member.find_one({"id": user.id}, {"suspended": 1, "suspension_reason": 1})

        if member is None:
            return await ctx.send(ctx._("user-hasnt-started"))

        if member.suspended or datetime.utcnow() < member.suspended_until:
            return await ctx.send(ctx._("user-is-suspended", user=user))

        # Challenge to battle

        message = await ctx.send(ctx._("challenging", user=user.mention))
        await message.add_reaction("✅")

        def check(payload):
            return payload.message_id == message.id and payload.user_id == user.id and payload.emoji.name == "✅"

        try:
            await self.bot.wait_for("raw_reaction_add", timeout=30, check=check)
        except asyncio.TimeoutError:
            await message.add_reaction("❌")
            await ctx.send(ctx._("challenge-timed-out"))
            return

        # Accepted, continue

        if ctx.author in self.bot.battles:
            return await ctx.send(ctx._("challenging-already-battling"))

        if user in self.bot.battles:
            return await ctx.send(ctx._("cannot-challenge-while-battling"))

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
                await ctx.send(ctx._("already-enough-pokemon", index=pokemon.idx))
                return

            for x in trainer.pokemon:
                if x.id == pokemon.id:
                    await ctx.send(ctx._("pokemon-already-in-party", index=pokemon.idx))
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
            return await ctx.send(ctx._("unknown-pokemon"))

        embed = ctx.localized_embed(
            "moves-embed",
            field_ordering=["available", "current"],
            field_values={
                "available": "\n".join(x.move.name for x in pokemon.species.moves if pokemon.level >= x.method.level),
                "current": None
                if len(pokemon.moves) == 0
                else "\n".join(self.bot.data.move_by_number(x).name for x in pokemon.moves),
            },
            level=pokemon.level,
            pokemon=pokemon.species,
        )
        embed.color = constants.PINK

        await ctx.send(embed=embed)

    @checks.has_started()
    @commands.command()
    async def learn(self, ctx, *, search: str):
        """Learn moves for your pokémon to use in battle."""

        move = self.bot.data.move_by_name(search)

        if move is None:
            return await ctx.send(ctx._("unknown-move"))

        member = await self.bot.mongo.fetch_member_info(ctx.author)
        pokemon = await self.bot.mongo.fetch_pokemon(ctx.author, member.selected_id)
        if pokemon is None:
            return await ctx.send(ctx._("pokemon-must-be-selected"))

        if move.id in pokemon.moves:
            return await ctx.send(ctx._("already-learned-move"))

        try:
            pokemon_move = next(x for x in pokemon.species.moves if x.move_id == move.id)
        except StopIteration:
            pokemon_move = None

        if pokemon_move is None or pokemon_move.method.level > pokemon.level:
            return await ctx.send(ctx._("cannot-learn-move"))

        update = {}

        if len(pokemon.moves) >= 4:
            result = await ctx.select(
                ctx._("knows-too-many-moves"),
                options=[discord.SelectOption(label=self.bot.data.move_by_number(x).name) for x in set(pokemon.moves)],
            )
            if result is None:
                return await ctx.send(ctx._("times-up"))

            rep_move = self.bot.data.move_by_name(result[0])
            idx = pokemon.moves.index(rep_move.id)
            update["$set"] = {f"moves.{idx}": move.id}

        else:
            update["$push"] = {f"moves": move.id}

        await self.bot.mongo.update_pokemon(pokemon, update)
        await ctx.send(ctx._("learned-move", move=move.name))

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
            raise commands.BadArgument(ctx._("invalid-pokemon-search-moveset"))

        async def get_page(source, menu, pidx):
            pgstart = pidx * 20
            pgend = min(pgstart + 20, len(species.moves))

            # Send embed

            embed = ctx.localized_embed(pokemon=species, start=pgstart + 1, end=pgend, totalMoves=len(species.moves))
            embed.color = constants.PINK

            for move in species.moves[pgstart:pgend]:
                embed.add_field(name=move.move.name, value=move.text)

            for i in range(-pgend % 3):
                embed.add_field(name="‎", value="‎")

            return embed

        pages = pagination.ContinuablePages(pagination.FunctionPageSource(math.ceil(len(species.moves) / 20), get_page))
        self.bot.menus[ctx.author.id] = pages
        await pages.start(ctx)

    @commands.command(aliases=("mi",))
    async def moveinfo(self, ctx, *, search: str):
        """View information about a certain move."""

        move = self.bot.data.move_by_name(search)

        if move is None:
            return await ctx.send(ctx._("unknown-move"))

        embed = ctx.localized_embed(
            "moveinfo-embed",
            field_ordering=["target", "power", "accuracy", "pp", "priority", "type", "class"],
            block_fields=["target"],
            field_values={
                name: value if (value := getattr(move, name)) is not None else "—"
                for name in ("power", "accuracy", "pp", "priority", "type")
            },
            title=move.name,
            description=move.description,
            target=move.target_text,
            damageClass=move.damage_class,
        )
        embed.color = constants.PINK

        await ctx.send(embed=embed)

    @in_battle(True)
    @battle.command(aliases=("x",))
    async def cancel(self, ctx):
        """Cancel a battle."""

        self.bot.battles[ctx.author].end()
        await ctx.send(ctx._("battle-canceled"))

    def cog_unload(self):
        if self.bot.cluster_idx == 0:
            self.process_move_requests.cancel()


async def setup(bot: commands.Bot):
    await bot.add_cog(Battling(bot))
