from __future__ import annotations

import contextlib
from dataclasses import dataclass
from enum import Enum
import itertools
import math
from collections import defaultdict
from datetime import datetime
from functools import cache, cached_property
from operator import itemgetter
import textwrap
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

import discord
import pymongo
from discord.errors import DiscordException
from discord.ext import commands
from pymongo import UpdateOne

from cogs.mongo import Member
from data.constants import GENDER_TYPES
from data.models import Species
from data.utils import comma_formatted
from helpers import checks, constants, converters, flags, genders, pagination
from helpers.context import PoketwoContext

if TYPE_CHECKING:
    from bot import ClusterBot


def isfloat(x):
    try:
        float(x)
    except ValueError:
        return False
    else:
        return True


POKEDEX_REWARD_SHINY_BOOST = 15


class PokedexRewardItem(Enum):
    ORIGINAL_MAGEARNA = 10147, Species

    def __init__(self, _id: int, reward_type: Species) -> None:
        self.id = _id
        self.type = reward_type

    def emoji(self, bot: ClusterBot) -> str:
        match self.type:
            case Species:
                species = bot.data.species_by_number(self.id)
                return bot.sprites.get(species)

    def name(self, bot: ClusterBot) -> str:
        match self.type:
            case Species:
                species = bot.data.species_by_number(self.id)
                return species.name


@dataclass
class PokedexReward:
    item: PokedexRewardItem
    amount: int

    def text(self, bot: ClusterBot) -> str:
        emoji = self.item.emoji(bot)
        text = self.item.name(bot)

        return f"{self.amount}x {emoji} {text}"


class PokedexMilestone(Enum):
    #! DO NOT RENAME THESE ENUMS (the title strings are fine to change), THEY ARE USED TO KEEP TRACK OF CLAIMED MILESTONES!
    GEN_1_TO_7 = "Gen I-VII", (1, 809), PokedexReward(PokedexRewardItem.ORIGINAL_MAGEARNA, 1)
    GEN_8 = "Gen VIII Expansion", (810, 898), PokedexReward(PokedexRewardItem.ORIGINAL_MAGEARNA, 1)
    HISUI = "Hisui Expansion", (899, 905), PokedexReward(PokedexRewardItem.ORIGINAL_MAGEARNA, 1)
    GEN_9 = "Gen IX Expansion", (906, 1010), PokedexReward(PokedexRewardItem.ORIGINAL_MAGEARNA, 1)
    DLC_1 = "Teal Mask Expansion", (1011, 1017), PokedexReward(PokedexRewardItem.ORIGINAL_MAGEARNA, 1)
    DLC_2 = "Indigo Disk Expansion", (1018, 1025), PokedexReward(PokedexRewardItem.ORIGINAL_MAGEARNA, 1)

    def __init__(self, title: str, from_to: Tuple[int, int], reward: PokedexReward):
        self.title = title
        self.from_id, self.to_id = from_to
        self.reward = reward

        self.entries = list(range(self.from_id, self.to_id + 1))

    @property
    def total_entries(self) -> int:
        return len(self.entries)

    @classmethod
    def all(cls) -> List[PokedexMilestone]:
        return list(sorted(list(cls), key=lambda m: m.from_id))

    @classmethod
    def get_user_milestones(cls, bot: ClusterBot, member: Member) -> List[Milestone]:
        """Get all of a user's milestones"""

        milestones = []
        unlocked = True  # First one will always be unlocked
        for milestone in cls.all():
            m = Milestone(milestone, bot, member, unlocked)
            unlocked = m.completed  # And then if this milestone isn't complete yet, next ones should not be unlocked
            milestones.append(m)

        return milestones

    @classmethod
    async def fetch_user_milestones(cls, bot: ClusterBot, user: discord.Member) -> List[Milestone]:
        """Fetch all of a user's milestones"""

        total_count = bot.data.total_pokedex_count
        pokedex_member = await bot.mongo.fetch_pokedex(user, 0, total_count + 1)

        milestones = [milestone for milestone in cls.get_user_milestones(bot, pokedex_member)]
        return milestones

    @classmethod
    async def fetch_unclaimed(cls, bot: ClusterBot, user: discord.Member) -> List[Milestone]:
        """Fetch all of a user's unclaimed milestones"""

        milestones = await cls.fetch_user_milestones(bot, user)

        unclaimed = [milestone for milestone in milestones if milestone.unclaimed]
        return unclaimed


@dataclass
class Milestone:
    meta: PokedexMilestone
    bot: ClusterBot
    member: Member
    unlocked: bool

    def __hash__(self) -> int:
        return hash(self.meta)

    def total_completed(self) -> int:
        pokedex = self.member.pokedex
        return sum([bool(pokedex.get(str(species_id), 0)) for species_id in self.meta.entries])

    @property
    def completed(self) -> bool:
        completed = self.total_completed() == self.meta.total_entries
        return self.unlocked and completed

    @property
    def claimed(self) -> bool:
        claimed = bool(self.member.claimed_pokedex_rewards.get(self.meta.name))
        return self.completed and claimed

    @property
    def unclaimed(self) -> bool:
        return self.completed and not self.claimed

    @property
    def unnotified(self) -> bool:
        notified = bool(self.member.notified_milestones.get(self.meta.name))
        return self.unclaimed and not notified

    def reward(self) -> Species:
        reward = self.meta.reward
        match reward.item.type:
            case Species:
                return self.bot.data.species_by_number(reward.item.id)

    def status_emoji(self, *, return_gray: Optional[bool] = True) -> str:
        if not self.unlocked:
            return self.bot.sprites.locked

        if self.completed:
            if self.claimed:
                return self.bot.sprites.check
            else:
                return self.bot.sprites.quest_trophy
        else:
            return self.bot.sprites.gray if return_gray else ""

    def reward_text(self) -> str:
        return self.meta.reward.text(self.bot)

    def text(self) -> str:
        completed = self.total_completed()
        status_emoji = self.status_emoji()

        meta = self.meta
        progress = f"`{completed}/{meta.total_entries}`" if self.unlocked else "Locked"
        reward_text = f"> **Reward**: {self.reward_text()}" if not self.claimed else f""
        return textwrap.dedent(
            f"""
            **• {status_emoji} {meta.title}** (#{meta.from_id}-#{meta.to_id}) ― {progress}
            {reward_text}
            """
        ).strip("\n")


class Pokemon(commands.Cog):
    """Pokémon-related commands."""

    def __init__(self, bot):
        self.bot: ClusterBot = bot

    @checks.has_started()
    @commands.command(aliases=("renumber",))
    async def reindex(self, ctx):
        """Re-number all pokémon in your collection."""

        await ctx.send("Reindexing all your pokémon... please don't do anything else during this time.")

        num = await self.bot.mongo.fetch_pokemon_count(ctx.author)
        await self.bot.mongo.reset_idx(ctx.author, value=num + 1)
        mons = self.bot.mongo.db.pokemon.find({"owner_id": ctx.author.id, "owned_by": "user"}).sort("idx")

        ops = []

        idx = 1
        async for pokemon in mons:
            ops.append(UpdateOne({"_id": pokemon["_id"]}, {"$set": {"idx": idx}}))
            idx += 1

            if len(ops) >= 1000:
                await self.bot.mongo.db.pokemon.bulk_write(ops)
                ops = []

        await self.bot.mongo.db.pokemon.bulk_write(ops)
        await ctx.reply("Successfully reindexed all your pokémon!")

    @checks.has_started()
    @commands.command(aliases=("nick",))
    async def nickname(
        self,
        ctx: commands.Context,
        pokemon: Optional[converters.PokemonConverter] = False,
        *nickname,
    ):
        """Change the nickname for your pokémon."""

        if pokemon is False:
            pokemon = await converters.PokemonConverter().convert(ctx, "")

        if pokemon is None:
            return await ctx.send("Couldn't find that pokémon!")

        nickname = " ".join(nickname)

        if len(nickname) > 100:
            return await ctx.send("That nickname is too long.")

        if constants.URL_REGEX.search(nickname):
            return await ctx.send("That nickname contains URL(s).")

        if nickname == "reset":
            nickname = None

        await self.bot.mongo.update_pokemon(
            pokemon,
            {"$set": {f"nickname": nickname}},
        )

        if nickname is None:
            await ctx.send(f"Removed nickname for your **{pokemon:Dx}**.")
        else:
            await ctx.send(f"Changed nickname to `{nickname}` for your **{pokemon:Dx}**.")

    # Nickname
    @flags.add_flag("newname", nargs="+")

    # Filter
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
    @flags.add_flag("--favorite", action="store_true")
    @flags.add_flag("--embedcolor", "--ec", action="store_true")
    @flags.add_flag("--name", "--n", nargs="+", action="append")
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

    # Rename all
    @checks.has_started()
    @commands.max_concurrency(1, commands.BucketType.user)
    @commands.cooldown(1, 5, commands.BucketType.user)
    @flags.command(aliases=("na",))
    async def nickall(self, ctx, **flags):
        """Mass nickname pokémon from your collection."""

        mention_author = flags.get("mention")

        nicknameall = " ".join(flags["newname"])

        member = await self.bot.mongo.fetch_member_info(ctx.author)
        aggregations = await self.create_filter(flags, ctx, order_by=member.order_by)

        if aggregations is None:
            return

        # check nick length
        if len(nicknameall) > 100:
            return await ctx.send("That nickname is too long.")

        if constants.URL_REGEX.search(nicknameall):
            return await ctx.send("That nickname contains URL(s).")

        # check nick reset
        if nicknameall == "reset":
            nicknameall = None

        # check pokemon num
        num = await self.bot.mongo.fetch_pokemon_count(ctx.author, aggregations=aggregations)

        if num == 0:
            return await ctx.reply("Found no pokémon matching this search.", mention_author=mention_author)

        # confirm
        if nicknameall is None:
            message = f"Are you sure you want to **remove** nickname for {num:,} pokémon?"
        else:
            message = f"Are you sure you want to rename {num:,} pokémon to `{nicknameall}`?"

        result = await ctx.confirm(message + await self.valuable_pokemon_details(ctx, aggregations))
        if result is None:
            return await ctx.send("Time's up. Aborted.")
        if result is False:
            return await ctx.send("Aborted.")

        # confirmed, nickname all
        await ctx.send(f"Renaming {num:,} pokémon, this might take a while...")

        pokemon = self.bot.mongo.fetch_pokemon_list(ctx.author, aggregations)

        await self.bot.mongo.db.pokemon.update_many(
            {"_id": {"$in": [x.id async for x in pokemon]}},
            {"$set": {"nickname": nicknameall}},
        )

        if nicknameall is None:
            await ctx.reply(f"Removed nickname for {num:,} pokémon.", mention_author=mention_author)
        else:
            await ctx.reply(f"Changed nickname to `{nicknameall}` for {num:,} pokémon.", mention_author=mention_author)

    @checks.has_started()
    @checks.is_not_in_trade()
    @commands.command(
        aliases=(
            "favourite",
            "fav",
        ),
        rest_is_raw=True,
    )
    async def favorite(self, ctx, *, args: converters.GreedyPokemonConverter):
        """Mark a pokémon as a favorite."""

        messages = []
        fav_ids = []
        async with ctx.typing():
            for pokemon in args:
                if pokemon.favorite:
                    messages.append(
                        f"- Your **{pokemon:Dnx}** is already favorited. To unfavorite a pokemon, please use `{ctx.clean_prefix}unfavorite`."
                    )
                else:
                    fav_ids.append(pokemon.id)
                    messages.append(f"- Favorited your **{pokemon:Dnx}**.")

            m = await self.bot.mongo.db.pokemon.update_many({"_id": {"$in": fav_ids}}, {"$set": {"favorite": True}})
            longmsg = "\n".join(messages)
            for chunk in discord.utils.as_chunks(longmsg, 2000):
                await ctx.send("".join(chunk))

    @checks.has_started()
    @commands.command(
        aliases=(
            "unfavourite",
            "unfav",
        ),
        rest_is_raw=True,
    )
    async def unfavorite(self, ctx, *, args: converters.GreedyPokemonConverter):
        """Unfavorite a selected pokemon."""

        messages = []
        unfav_ids = []
        async with ctx.typing():
            for pokemon in args:
                if pokemon.favorite:
                    unfav_ids.append(pokemon.id)
                messages.append(f"- Unfavorited your **{pokemon:Dnx}**.")

            m = await self.bot.mongo.db.pokemon.update_many({"_id": {"$in": unfav_ids}}, {"$set": {"favorite": False}})
            longmsg = "\n".join(messages)
            for chunk in discord.utils.as_chunks(longmsg, 2000):
                await ctx.send("".join(chunk))

    # Filter
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

    # Rename all
    @checks.has_started()
    @checks.is_not_in_trade()
    @commands.max_concurrency(1, commands.BucketType.user)
    @flags.command(
        aliases=(
            "favouriteall",
            "favall",
            "fa",
        )
    )
    async def favoriteall(self, ctx, **flags):
        """Mass favorite selected pokemon."""

        mention_author = flags.get("mention")

        member = await self.bot.mongo.fetch_member_info(ctx.author)
        aggregations = await self.create_filter(flags, ctx, order_by=member.order_by)

        if aggregations is None:
            return

        # Check pokemon and unfavorited pokemon num
        num = await self.bot.mongo.fetch_pokemon_count(ctx.author, aggregations=aggregations)

        aggregations.append({"$match": {"favorite": {"$ne": True}}})
        unfavnum = await self.bot.mongo.fetch_pokemon_count(ctx.author, aggregations=aggregations)

        if num == 0:
            return await ctx.reply("Found no pokémon matching this search.", mention_author=mention_author)
        elif unfavnum == 0:
            return await ctx.reply(
                f"Found no unfavorited pokémon within this selection.\nTo mass unfavorite a pokemon, please use `{ctx.clean_prefix}unfavoriteall`.",
                mention_author=mention_author,
            )

        # Fetch pokemon list
        pokemon = self.bot.mongo.fetch_pokemon_list(ctx.author, aggregations)

        # confirm

        result = await ctx.confirm(
            f"Are you sure you want to **favorite** your {unfavnum:,} pokémon?"
            + await self.valuable_pokemon_details(ctx, aggregations)
        )
        if result is None:
            return await ctx.send("Time's up. Aborted.")
        if result is False:
            return await ctx.send("Aborted.")

        await self.bot.mongo.db.pokemon.update_many(
            {"_id": {"$in": [x.id async for x in pokemon]}},
            {"$set": {"favorite": True}},
        )

        await ctx.reply(
            f"Favorited your {unfavnum:,} unfavorited pokemon.\nAll {num:,} selected pokemon are now favorited.",
            mention_author=mention_author,
        )

    # Filter
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
    @flags.add_flag("--favorite", action="store_true")
    @flags.add_flag("--embedcolor", "--ec", action="store_true")
    @flags.add_flag("--name", "--n", nargs="+", action="append")
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

    # Rename all
    @checks.has_started()
    @commands.max_concurrency(1, commands.BucketType.user)
    @flags.command(
        aliases=(
            "unfavouriteall",
            "unfavall",
            "ufa",
        )
    )
    async def unfavoriteall(self, ctx, **flags):
        """Mass unfavorite selected pokemon."""

        mention_author = flags.get("mention")

        member = await self.bot.mongo.fetch_member_info(ctx.author)
        aggregations = await self.create_filter(flags, ctx, order_by=member.order_by)

        if aggregations is None:
            return

        # Check pokemon and unfavorited pokemon num
        num = await self.bot.mongo.fetch_pokemon_count(ctx.author, aggregations=aggregations)

        aggregations.append({"$match": {"favorite": True}})
        favnum = await self.bot.mongo.fetch_pokemon_count(ctx.author, aggregations=aggregations)

        if num == 0:
            return await ctx.send("Found no pokémon matching this search.")
        elif favnum == 0:
            return await ctx.send("Found no favorited pokémon within this selection.")

        # Fetch pokemon list
        pokemon = self.bot.mongo.fetch_pokemon_list(ctx.author, aggregations)

        # confirm

        result = await ctx.confirm(
            f"Are you sure you want to **unfavorite** your {favnum:,} pokémon?"
            + await self.valuable_pokemon_details(ctx, aggregations)
        )
        if result is None:
            return await ctx.send("Time's up. Aborted.")
        if result is False:
            return await ctx.send("Aborted.")

        await self.bot.mongo.db.pokemon.update_many(
            {"_id": {"$in": [x.id async for x in pokemon]}},
            {"$set": {"favorite": False}},
        )

        await ctx.reply(
            f"Unfavorited your {favnum:,} favorited pokemon.\nAll {num:,} selected pokemon are now unfavorited.",
            mention_author=mention_author,
        )

    @checks.has_started()
    @commands.cooldown(3, 5, commands.BucketType.user)
    @commands.command(aliases=("i",), rest_is_raw=True)
    async def info(self, ctx, *, pokemon: converters.PokemonConverter):
        """View a specific pokémon from your collection."""

        if pokemon is None:
            return await ctx.send("Couldn't find that pokémon!")

        ## Hacky way using 0=first, 1=prev, 2=curr, 3=next, 4=last page LOL

        async def get_page(source, menu, pidx):
            nonlocal pokemon

            menu.current_page = 2

            agg = None

            if pidx == 4:
                agg = [{"$sort": {"idx": -1}}]
            elif pidx == 3:
                agg = [{"$match": {"idx": {"$gt": pokemon.idx}}}]
            elif pidx == 1:
                agg = [
                    {"$match": {"idx": {"$lt": pokemon.idx}}},
                    {"$sort": {"idx": -1}},
                ]
            elif pidx == 0:
                agg = []

            if agg is not None:
                it = self.bot.mongo.fetch_pokemon_list(ctx.author, agg)
                async for x in it:
                    pokemon = x
                    break

            embed = self.bot.Embed(color=pokemon.color or 0x9CCFFF, title=f"{pokemon:lnf}")

            image = pokemon.image_url
            embed.set_image(url=image)

            embed.set_thumbnail(url=ctx.author.display_avatar.url)

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

            embed.set_footer(text=f"Displaying pokémon {pokemon.idx}.\nID: {pokemon.id}")

            return embed

        pages = pagination.ContinuablePages(pagination.FunctionPageSource(5, get_page), allow_go=False)
        pages.current_page = 2
        ctx.bot.menus[ctx.author.id] = pages
        await pages.start(ctx)

    @checks.has_started()
    @checks.is_not_in_trade()
    @commands.command(aliases=("s",), rest_is_raw=True)
    async def select(self, ctx, *, pokemon: converters.PokemonConverter(accept_blank=False)):  # type: ignore
        """Select a specific pokémon from your collection."""

        if pokemon is None:
            return await ctx.send("Couldn't find that pokémon!")

        member = await self.bot.mongo.fetch_member_info(ctx.author)
        previous_id = member.selected_id

        if pokemon.id == previous_id:
            return await ctx.send("That Pokémon is already selected.")

        await self.bot.mongo.update_member(ctx.author, {"$set": {f"selected_id": pokemon.id}})

        text = f"You selected your **{pokemon:Dx}**"

        previous = await self.bot.mongo.fetch_pokemon(ctx.author, previous_id)
        if previous:
            text += f" (from {previous:x})"

        await ctx.send(f"{text}.")

    @checks.has_started()
    @commands.command(aliases=("or",))
    async def order(self, ctx, *, sort: str = ""):
        """Change how your pokémon are ordered."""

        sort = sort.lower()

        if sort not in [a + b for a in ("number", "iv", "level", "pokedex") for b in ("+", "-", "")]:
            return await ctx.send(
                "Please specify either `iv`, `iv+`, `iv-`, `level`, `level+`, `level-`, `number`, `number+`, `number-`, `pokedex`, `pokedex+` or `pokedex-`"
            )

        await self.bot.mongo.update_member(
            ctx.author,
            {"$set": {f"order_by": sort}},
        )

        await ctx.send(f"Now ordering pokemon by `{sort}`.")

    def parse_numerical_flag(self, text):
        if not (1 <= len(text) <= 2):
            return None

        ops = text

        if len(text) == 1 and isfloat(text[0]):
            ops = ["=", text[0]]

        elif len(text) == 1 and not isfloat(text[0][0]):
            ops = [text[0][0], text[0][1:]]

        if ops[0] not in ("<", "=", ">") or not isfloat(ops[1]):
            return None

        return ops

    @cache
    def gender_filter(self, gender_field, gender):
        gender = gender.casefold()

        if gender.title() not in GENDER_TYPES.values():
            return {"$match": {"gender": gender.title()}}

        defaults = self.bot.data.list_default_gender(gender)

        if gender == "unknown":
            return {"$match": {"species_id": {"$in": defaults}}}

        op = "$lt" if gender == "male" else "$gte"
        by_gender_ratio = defaultdict(list)

        for k, v in self.bot.data.pokemon.items():
            if v.gender_rate == -1:
                continue
            if k in genders.MALE_OVERRIDES:
                by_gender_ratio[100, 0].append(k)
            else:
                by_gender_ratio[tuple(v.gender_ratios)].append(k)

        cases = [
            {
                gender_field: {"$exists": False},
                "species_id": {"$in": v},
                "$expr": {
                    op: [
                        # times 1000 because mongodb has milliseconds not seconds
                        {"$mod": [{"$toLong": {"$toDate": "$_id"}}, int(k[0] * 10 + k[1] * 10) * 1000]},
                        int(k[0] * 10) * 1000,
                    ]
                },
            }
            for k, v in by_gender_ratio.items()
        ]

        return {"$match": {"$or": [{"species_id": {"$in": defaults}}, {gender_field: gender.title()}, *cases]}}

    async def create_filter(self, flags, ctx, order_by=None, map_field=lambda x: x):
        aggregations = []

        if "mine" in flags and flags["mine"]:
            aggregations.append({"$match": {map_field("owner_id"): ctx.author.id}})

        if "bids" in flags and flags["bids"]:
            aggregations.append({"$match": {"auction_data.bidder_id": ctx.author.id}})

        rarity = []
        for x in ("mythical", "legendary", "ub"):
            if x in flags and flags[x] or flags.get("rare"):
                rarity += getattr(self.bot.data, f"list_{x}")
        if rarity:
            aggregations.append({"$match": {map_field("species_id"): {"$in": rarity}}})

        regionals = []
        for x in ("alolan", "galarian", "hisuian", "paldean"):
            if x in flags and flags[x] or flags.get("regional"):
                regionals += getattr(self.bot.data, f"list_{x}")
        if regionals:
            aggregations.append({"$match": {map_field("species_id"): {"$in": regionals}}})

        if "paradox" in flags and flags["paradox"]:
            aggregations.append({"$match": {map_field("species_id"): {"$in": self.bot.data.list_paradox}}})

        for x in ("mega", "event", "gmax"):
            if x in flags and flags[x]:
                aggregations.append({"$match": {map_field("species_id"): {"$in": getattr(self.bot.data, f"list_{x}")}}})

        if "type" in flags and flags["type"]:
            all_species = [i for x in flags["type"] for i in self.bot.data.list_type(x)]
            aggregations.append({"$match": {map_field("species_id"): {"$in": all_species}}})

        if "region" in flags and flags["region"]:
            all_species = [i for x in flags["region"] for i in self.bot.data.list_region(x)]
            aggregations.append({"$match": {map_field("species_id"): {"$in": all_species}}})

        if "favorite" in flags and flags["favorite"]:
            aggregations.append({"$match": {map_field("favorite"): True}})

        if "shiny" in flags and flags["shiny"]:
            aggregations.append({"$match": {map_field("shiny"): True}})

        if "name" in flags and flags["name"] is not None:
            all_species = [i for x in flags["name"] for i in self.bot.data.find_all_matches(" ".join(x))]

            aggregations.append({"$match": {map_field("species_id"): {"$in": all_species}}})

        if "move" in flags and flags["move"] is not None:
            move_ids = [m.id for x in flags["move"] if (m := self.bot.data.move_by_name(" ".join(x))) is not None]

            aggregations.append({"$match": {map_field("moves"): {"$all": move_ids}}})

        if "learns" in flags and flags["learns"] is not None:
            all_species = [sid for x in flags["learns"] for sid in self.bot.data.list_move(" ".join(x))]

            aggregations.append({"$match": {map_field("species_id"): {"$in": all_species}}})

        if "nickname" in flags and flags["nickname"] is not None:
            aggregations.append(
                {
                    "$match": {
                        map_field("nickname"): {
                            "$regex": "(" + ")|(".join(" ".join(x) for x in flags["nickname"]) + ")",
                            "$options": "i",
                        }
                    }
                }
            )

        if "embedcolor" in flags and flags["embedcolor"]:
            aggregations.append({"$match": {map_field("has_color"): True}})

        if "ends" in flags and flags["ends"] is not None:
            aggregations.append({"$match": {"auction_data.ends": {"$lt": datetime.utcnow() + flags["ends"]}}})

        # Numerical flags

        for flag, expr in constants.FILTER_BY_NUMERICAL.items():
            if flag in flags:
                for text in flags[flag] or []:
                    ops = self.parse_numerical_flag(text)

                    if ops is None:
                        raise commands.BadArgument(f"Couldn't parse `--{flag} {' '.join(text)}`")

                    ops[1] = float(ops[1])

                    if flag == "iv":
                        ops[1] = float(ops[1]) * 186 / 100

                    if ops[0] == "<":
                        aggregations.append(
                            {"$match": {map_field(expr): {"$lt": math.ceil(ops[1])}}},
                        )
                    elif ops[0] == "=":
                        aggregations.append(
                            {"$match": {map_field(expr): {"$eq": round(ops[1])}}},
                        )
                    elif ops[0] == ">":
                        aggregations.append(
                            {"$match": {map_field(expr): {"$gt": math.floor(ops[1])}}},
                        )

        for flag, amt in constants.FILTER_BY_DUPLICATES.items():
            if flag in flags and flags[flag] is not None:
                iv = int(flags[flag])

                # Processing combinations
                combinations = [
                    {map_field(field): iv for field in combo}
                    for combo in itertools.combinations(constants.IV_FIELDS, amt)
                ]
                aggregations.append({"$match": {"$or": combinations}})

        if order_by is not None:
            s = order_by[-1]
            if order_by[-1] in "+-":
                order_by, asc = order_by[:-1], 1 if s == "+" else -1
            else:
                asc = -1 if order_by in constants.DEFAULT_DESCENDING else 1

            aggregations.append({"$sort": {map_field(constants.SORTING_FUNCTIONS[order_by]): asc}})

        # put gender after sorting
        if "gender" in flags and flags["gender"]:
            aggregations.append(self.gender_filter(map_field("gender"), flags["gender"][0]))

        if "skip" in flags and flags["skip"] is not None:
            aggregations.append({"$skip": flags["skip"]})

        if "limit" in flags and flags["limit"] is not None:
            aggregations.append({"$limit": flags["limit"]})

        return aggregations

    async def valuable_pokemon_details(
        self,
        ctx: PoketwoContext,
        aggregations: Optional[list] = None,
        *,
        header: Optional[str] = "This includes",
    ) -> str:
        """Function to get a string with list of valuable pokémon of the user included in the provided aggregation.
        This shows the user valuable pokémon that are included in their provided flags for -all commands."""

        aggregations = aggregations or []

        rares_filter = aggregations + await self.create_filter({"mythical": True, "legendary": True, "ub": True}, ctx)
        regionals_filter = aggregations + await self.create_filter(
            {"alolan": True, "galarian": True, "hisuian": True, "paldean": True}, ctx
        )
        event_filter = aggregations + await self.create_filter({"event": True}, ctx)
        shiny_filter = aggregations + await self.create_filter({"shiny": True}, ctx)
        gmax_filter = aggregations + await self.create_filter({"gmax": True}, ctx)

        HIGHEST_IV_THRESHOLD = 90
        highest_iv_filter = aggregations + await self.create_filter({"iv": [[f">{HIGHEST_IV_THRESHOLD}"]]}, ctx)

        HIGH_IV_THRESHOLD = 80
        high_iv_filter = aggregations + await self.create_filter({"iv": [[f">{HIGH_IV_THRESHOLD}"], [f"<{HIGHEST_IV_THRESHOLD}"]]}, ctx)

        LOW_IV_THRESHOLD = 10
        low_iv_filter = aggregations + await self.create_filter({"iv": [[f"<{LOW_IV_THRESHOLD}"]]}, ctx)

        filters = {
            "✨ Shiny Pokémon": shiny_filter,
            f"{self.bot.sprites.gmax} Gigantamax Pokémon": gmax_filter,
            "Event Pokémon": event_filter,
            "Rare Pokémon (Legendaries, Mythicals and Ultra Beasts)": rares_filter,
            "Regional Form Pokémon (Alolans, Galarians, Hisuians and Paldeans)": regionals_filter,
            f"Pokémon with **IV > {HIGHEST_IV_THRESHOLD}%**": highest_iv_filter,
            f"Pokémon with **IV > {HIGH_IV_THRESHOLD}%**, **< {HIGHEST_IV_THRESHOLD}%**": high_iv_filter,
            f"Pokémon with **IV < {LOW_IV_THRESHOLD}%**": low_iv_filter,
        }

        counts = {
            msg: count
            for msg, filter in filters.items()
            if (count := await self.bot.mongo.fetch_pokemon_count(ctx.author, filter))
        }
        if counts:
            return f"\n### {header}:\n" + "\n".join([f"- **{count:,}** {msg}" for msg, count in counts.items()])
        else:
            return ""

    @checks.has_started()
    @checks.is_not_in_trade()
    @commands.max_concurrency(1, commands.BucketType.user)
    @commands.command(aliases=("r",))
    async def release(self, ctx, *, args: converters.GreedyPokemonConverter(include_none=True)):  # type: ignore
        """Release pokémon from your collection for 2pc each."""

        member = await self.bot.mongo.fetch_member_info(ctx.author)

        release = []
        failed_msgs = []
        for pokemon in args:
            if pokemon is None:
                continue

            if member.selected_id == pokemon.id:
                failed_msgs.append(f"- **{pokemon:Dnx}**: You can't release your selected pokémon!")
                continue

            if pokemon.favorite:
                failed_msgs.append(f"- **{pokemon:Dnx}**: You can't release favorited pokémon!")
                continue

            release.append(pokemon)

        if failed_msgs:
            await ctx.send(
                "\n".join([*failed_msgs, f"Couldn't find/release {len(args)-len(release)} pokémon in this selection!"])
            )

        # Confirmation msg

        if len(release) == 0:
            return

        pc = len(release) * 2

        if len(release) == 1:
            message = f"Are you sure you want to **release** your **{release[0]:Dx}** for {pc:,} pc?"
        else:
            message = f"Are you sure you want to release the following pokémon for {pc:,} pc?\n\n" + "\n".join(
                f"- **{x:Dnx}**" for x in release
            )

        result = await ctx.confirm(message)
        if result is None:
            return await ctx.send("Time's up. Aborted.")
        if result is False:
            return await ctx.send("Aborted.")

        if await self.bot.get_cog("Trading").is_in_trade(ctx.author):
            return await ctx.send("You can't do that in a trade!")

        # confirmed, release

        result = await self.bot.mongo.db.pokemon.update_many(
            {"owner_id": ctx.author.id, "_id": {"$in": [p.id for p in release]}},
            {"$set": {"owned_by": "released"}},
        )
        pc = result.modified_count * 2
        await self.bot.mongo.update_member(
            ctx.author,
            {
                "$inc": {"balance": pc},
            },
        )
        await ctx.send(f"You released {result.modified_count:,} pokémon. You received {pc:,} Pokécoins!")
        self.bot.dispatch("release", ctx.author, result.modified_count)

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

    # Release all
    @checks.has_started()
    @checks.is_not_in_trade()
    @commands.max_concurrency(1, commands.BucketType.user)
    @commands.cooldown(1, 5, commands.BucketType.user)
    @flags.command(aliases=("ra",))
    async def releaseall(self, ctx, **flags):
        """Mass release pokémon from your collection for 2 pc each."""

        mention_author = flags.get("mention")

        member = await self.bot.mongo.fetch_member_info(ctx.author)
        aggregations = await self.create_filter(flags, ctx, order_by=member.order_by)

        if aggregations is None:
            return

        member = await self.bot.mongo.fetch_member_info(ctx.author)

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

        result = await ctx.confirm(
            f"Are you sure you want to release **{num:,} pokémon** for {num*2:,} pc? Favorited and selected pokémon won't be removed."
            + await self.valuable_pokemon_details(ctx, aggregations)
        )
        if result is None:
            return await ctx.send("Time's up. Aborted.")
        if result is False:
            return await ctx.send("Aborted.")

        if await self.bot.get_cog("Trading").is_in_trade(ctx.author):
            return await ctx.send("You can't do that in a trade!")

        # confirmed, release all

        num = await self.bot.mongo.fetch_pokemon_count(ctx.author, aggregations=aggregations)

        await ctx.send(f"Releasing {num:,} pokémon, this might take a while...")

        pokemon = self.bot.mongo.fetch_pokemon_list(ctx.author, aggregations)

        result = await self.bot.mongo.db.pokemon.update_many(
            {"owner_id": ctx.author.id, "_id": {"$in": [x.id async for x in pokemon]}},
            {"$set": {"owned_by": "released"}},
        )

        await self.bot.mongo.update_member(
            ctx.author,
            {
                "$inc": {"balance": 2 * result.modified_count},
            },
        )

        await ctx.reply(
            f"You have released {result.modified_count:,} pokémon. You received {2*result.modified_count:,} Pokécoins!",
            mention_author=mention_author,
        )
        self.bot.dispatch("release", ctx.author, result.modified_count)

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
    @flags.add_flag("--favorite", action="store_true")
    @flags.add_flag("--embedcolor", "--ec", action="store_true")
    @flags.add_flag("--name", "--n", nargs="+", action="append")
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

    # Pokemon
    @checks.has_started()
    @commands.cooldown(1, 5, commands.BucketType.user)
    @flags.command(aliases=("p",))
    async def pokemon(self, ctx, **flags):
        """View or filter the pokémon in your collection."""

        mention_author = flags.get("mention")

        if flags["page"] < 1:
            return await ctx.send("Page must be positive!")

        member = await self.bot.mongo.fetch_member_info(ctx.author)

        aggregations = await self.create_filter(flags, ctx, order_by=member.order_by)
        if aggregations is None:
            return

        # Filter pokemon

        def padn(p, n):
            return " " * (len(str(n)) - len(str(p.idx))) + str(p.idx)

        def prepare_page(menu, items):
            menu.maxn = max(x.idx for x in items)

        def format_item(menu, p):
            return f"`{padn(p, menu.maxn)}`　**{p:nifg}**　•　Lvl. {p.level}　•　{p.iv_total / 186:.2%}"

        try:
            count = await self.bot.mongo.fetch_pokemon_count(
                ctx.author, aggregations, max_time_ms=5000 if flags["gender"] else None
            )
        except pymongo.errors.ExecutionTimeout:
            count = None
        pokemon = self.bot.mongo.fetch_pokemon_list(ctx.author, aggregations)

        pages = pagination.ContinuablePages(
            pagination.AsyncListPageSource(
                pokemon,
                title="Your pokémon",
                prepare_page=prepare_page,
                format_item=format_item,
                per_page=20,
                count=count,
            ),
            mention_author=mention_author,
        )
        pages.current_page = flags["page"] - 1
        self.bot.menus[ctx.author.id] = pages

        try:
            await pages.start(ctx)
        except IndexError:
            await ctx.reply("No pokémon found.", mention_author=mention_author)

    @commands.Cog.listener("on_catch")
    async def notify_milestone(self, ctx: PoketwoContext, species: Species, _id):
        milestones = await PokedexMilestone.fetch_user_milestones(self.bot, ctx.author)
        unnotified = [milestone for milestone in milestones if milestone.unnotified]
        if not unnotified:
            return

        num = len(unnotified)
        s = "" if num == 1 else "s"
        message = f"Congratulations, you have completed {'a' if num == 1 else num} pokédex milestone{s}! Use `{ctx.clean_prefix}{self.pokedex.qualified_name}` to view them and claim your rewards!"

        await self.bot.mongo.update_member(
            ctx.author, {"$set": {f"notified_milestones.{milestone.meta.name}": True for milestone in unnotified}}
        )
        return await ctx.reply(message)

    @flags.add_flag("page", nargs="*", type=str, default="1")
    @flags.add_flag("--caught", action="store_true")
    @flags.add_flag("--uncaught", action="store_true")
    @flags.add_flag("--legendary", action="store_true")
    @flags.add_flag("--mythical", action="store_true")
    @flags.add_flag("--ub", action="store_true")
    @flags.add_flag("--rare", action="store_true")
    @flags.add_flag("--paradox", action="store_true")
    @flags.add_flag("--orderd", action="store_true")
    @flags.add_flag("--ordera", action="store_true")
    @flags.add_flag("--type", "--t", type=str)
    @flags.add_flag("--region", "--r", type=str)
    @flags.add_flag("--learns", nargs="*", action="append")
    @checks.has_started()
    @commands.group(aliases=("d", "dex"), invoke_without_command=True, cls=flags.FlagGroup)
    async def pokedex(self, ctx, **flags):
        """View your pokédex, or search for a pokémon species."""

        search_or_page = " ".join(flags["page"])

        if flags["orderd"] and flags["ordera"]:
            return await ctx.send("You can use either --orderd or --ordera, but not both.")

        if flags["caught"] and flags["uncaught"]:
            return await ctx.send("You can use either --caught or --uncaught, but not both.")

        if search_or_page is None:
            search_or_page = "1"

        total_count = self.bot.data.total_pokedex_count
        if search_or_page.isdigit():
            pgstart = (int(search_or_page) - 1) * 20

            if pgstart >= total_count or pgstart < 0:
                return await ctx.send("There are no pokémon on this page.")

            do_emojis = ctx.guild is None or ctx.channel.permissions_for(ctx.guild.me).external_emojis

            member = await self.bot.mongo.fetch_pokedex(ctx.author, 0, total_count + 1)
            milestones = PokedexMilestone.get_user_milestones(self.bot, member)
            pokedex = member.pokedex.copy()
            completed = len(pokedex)

            if not flags["uncaught"] and not flags["caught"]:
                for i in range(1, total_count + 1):
                    if str(i) not in pokedex:
                        pokedex[str(i)] = 0
            elif flags["uncaught"]:
                for i in range(1, total_count + 1):
                    if str(i) not in pokedex:
                        pokedex[str(i)] = 0
                    else:
                        del pokedex[str(i)]

            rarities = [
                s
                for rarity in ("mythical", "legendary", "ub")
                for s in getattr(self.bot.data, f"list_{rarity}")
                if flags[rarity] or flags.get("rare")
            ]

            def include(key):
                if rarities and key not in rarities:
                    return False
                if flags["paradox"] and key not in self.bot.data.list_paradox:
                    return False
                if flags["type"] and key not in self.bot.data.list_type(flags["type"]):
                    return False
                if flags["region"] and key not in self.bot.data.list_region(flags["region"]):
                    return False
                if flags["learns"] and key not in [
                    i for x in flags["learns"] for i in self.bot.data.list_move(" ".join(x))
                ]:
                    return False

                return True

            pokedex = {int(k): v for k, v in pokedex.items() if include(int(k))}

            if flags["ordera"]:
                pokedex = sorted(pokedex.items(), key=itemgetter(1))
            elif flags["orderd"]:
                pokedex = sorted(pokedex.items(), key=itemgetter(1), reverse=True)
            else:
                pokedex = sorted(pokedex.items(), key=itemgetter(0))

            async def get_page(source, menu, pidx):
                pgstart = pidx * 20
                pgend = min(pgstart + 20, len(pokedex))

                # Send embed

                any_unclaimed = False
                milestones_text = []
                for milestone in milestones:
                    if milestone.unclaimed:
                        any_unclaimed = True

                    milestones_text.append(milestone.text())

                embed = self.bot.Embed(
                    title=f"Your pokédex",
                    description=textwrap.dedent(
                        f"""
                        You've caught {completed:,} out of {total_count:,} pokémon!
                        ### Pokédex Entry Milestones
                        """
                    )
                    + "\n".join(milestones_text)
                    + (
                        f"\n\u200c\n> You have unclaimed rewards. Use `{ctx.clean_prefix}{self.claim.qualified_name}` to claim them!"
                        if any_unclaimed
                        else ""
                    ),
                )

                embed.set_footer(text=f"Showing {pgstart + 1}–{pgend} out of {len(pokedex)}.")

                for k, v in pokedex[pgstart:pgend]:
                    species = self.bot.data.species_by_number(k)

                    if do_emojis:
                        text = f"{self.bot.sprites.cross} Not caught yet!"
                    else:
                        text = "Not caught yet!"

                    if v > 0:
                        if do_emojis:
                            text = f"{self.bot.sprites.check} {v} caught!"
                        else:
                            text = f"{v} caught!"

                    if do_emojis:
                        emoji = self.bot.sprites.get(species) + " "
                    else:
                        emoji = ""

                    embed.add_field(name=f"{emoji}{species.name} #{species.id}", value=text)

                if pgend != total_count:
                    embed.add_field(name="‎", value="‎")

                return embed

            pages = pagination.ContinuablePages(pagination.FunctionPageSource(math.ceil(len(pokedex) / 20), get_page))
            pages.current_page = int(search_or_page) - 1
            self.bot.menus[ctx.author.id] = pages
            await pages.start(ctx)

        else:
            shiny = False
            searched_gender = None

            if search_or_page[0] in "Nn#" and search_or_page[1:].isdigit():
                species_id = int(search_or_page[1:])
                species = self.bot.data.species_by_number(species_id)
                if species is None:
                    return await ctx.send(f"Could not find a pokémon with id `{species_id}`.")

            else:
                # Parse search string
                search_parts = search_or_page.lower().split()

                # Check if shiny is queried
                if search_parts[0] == "shiny":
                    shiny = True
                    search_parts.pop(0)

                # Check if a specific gender is queried
                first_part = search_parts[0].capitalize()
                if first_part in GENDER_TYPES.values() and first_part != "Unknown":
                    searched_gender = first_part
                    search_parts.pop(0)

                search = " ".join(search_parts)
                species = self.bot.data.species_by_name(search)
                if species is None:
                    return await ctx.send(f"Could not find a pokémon matching `{search_or_page}`.")

            gender_unknown = species.gender_rate == -1
            if gender_unknown and searched_gender is not None:
                return await ctx.send(f"Invalid gender provided for that pokémon.")
            elif gender_unknown:
                gender = "Unknown"
            elif species.has_gender_differences:
                # Specified gender if any, otherwise default to "Male"
                # TODO: It doesn't make sense to default to Male because of pokemon
                # TODO: whose default is Female, such as Nidoran-F. In the future
                # TODO: we should rely on `species.default_gender`, but not possible
                # TODO: at this point with how little time we have.
                gender = searched_gender or "Male"
            else:
                gender = None

            member = await self.bot.mongo.fetch_pokedex(ctx.author, 0, total_count + 1)

            # Adds the correct button settings to the embed
            view = pagination.DexView(ctx, species=species, member=member, is_shiny=shiny, gender=gender)
            await ctx.send(embed=view.get_embed(), view=view)

    @checks.has_started()
    @pokedex.command(name="claim")
    async def claim(self, ctx: PoketwoContext):
        """Claim completed pokédex milestone rewards."""

        member = await self.bot.mongo.fetch_member_info(ctx.author)
        unclaimed_milestones = await PokedexMilestone.fetch_unclaimed(self.bot, ctx.author)
        if not unclaimed_milestones:
            return await ctx.reply(
                f"You have no unclaimed pokédex milestone rewards that are unlocked at the moment!",
                mention_author=False,
            )

        rewards = {}
        inserts = []
        for milestone in unclaimed_milestones:
            reward = milestone.reward()
            amount = milestone.meta.reward.amount
            match reward:
                case Species:
                    pokemon_texts = []
                    for i in range(amount):
                        pokemon = await self.bot.mongo.make_pokemon(
                            member, reward, shiny_boost=POKEDEX_REWARD_SHINY_BOOST
                        )
                        pokemon_obj = self.bot.mongo.Pokemon.build_from_mongo(pokemon)
                        inserts.append(pokemon)
                        pokemon_texts.append(f"**{pokemon_obj:i}**")

                    rewards[milestone] = comma_formatted(pokemon_texts)

        if inserts:
            await self.bot.mongo.db.pokemon.insert_many(inserts)

        await self.bot.mongo.update_member(
            member, {"$set": {f"claimed_pokedex_rewards.{m.meta.name}": True for m in rewards}}
        )

        num = len(unclaimed_milestones)
        s = "" if num == 1 else "s"
        embed = self.bot.Embed(
            title=f"Congratulations, you have completed {'a' if num == 1 else num} pokédex milestone{s}! 🎉"
        )
        embed.set_author(name=str(ctx.author), icon_url=ctx.author.display_avatar.url)

        for milestone, reward_text in rewards.items():
            embed.add_field(
                name=f"{milestone.meta.title}",
                value=f"You've earned a {reward_text}!",
                inline=False,
            )

        embed.set_footer(
            text=(
                "Thank you for the countless hours you've spent with us 💛\n"
                "Stay tuned for more rewards on your journey to catch em' all!"
            )
        )
        return await ctx.reply(embed=embed)

    @checks.has_started()
    @checks.is_not_in_trade()
    @commands.guild_only()
    @commands.command(rest_is_raw=True)
    async def evolve(self, ctx, *, args: converters.GreedyPokemonConverter):
        """Evolve a pokémon if it has reached the target level."""

        if len(args) == 0:
            return await ctx.send("Couldn't find that pokémon!")

        guild = await self.bot.mongo.fetch_guild(ctx.guild)

        embed = self.bot.Embed(description="", title=f"Congratulations {ctx.author.display_name}!")

        evolved = []

        if len(args) > 30:
            return await ctx.send("You can't evolve more than 30 pokémon at once!")

        failed_msgs = []
        for pokemon in args:
            name = format(pokemon, "Pgnx")

            if (evo := pokemon.get_next_evolution(guild.time)) is None:
                failed_msgs.append(f"- Your **{name}** can't be evolved!")
                continue

            if len(args) < 20:
                embed.add_field(
                    name=f"Your **{name}** is evolving!",
                    value=f"Your **{name}** has turned into a **{evo}**!",
                    inline=True,
                )
            else:
                embed.description += f"\n**Your {name} is evolving!**\nYour **{name}** has turned into a {evo}!"

            if len(args) == 1:
                embed.set_thumbnail(url=evo.get_image_url(pokemon.shiny, pokemon.gender))

            evolved.append((pokemon, evo))

        if failed_msgs:
            await ctx.send("\n".join(failed_msgs))

        if evolved:
            for pokemon, evo in evolved:
                await self.bot.mongo.update_pokemon(
                    pokemon,
                    {"$set": {f"species_id": evo.id}},
                )

                self.bot.dispatch("evolve", ctx.author, pokemon, evo)

            await ctx.send(embed=embed)

    @checks.has_started()
    @checks.is_not_in_trade()
    @commands.command(aliases=("unmega",), rest_is_raw=True)
    async def untransform(self, ctx, *, pokemon: converters.PokemonConverter):
        """Switch a alternative form (e.g. mega) pokémon back to its base / non-mega form."""

        if pokemon is None:
            return await ctx.send("Couldn't find that pokémon!")

        base = self.bot.data.species_by_number(pokemon.species.dex_number)

        is_mega = pokemon.species in (
            base.mega,
            base.mega_x,
            base.mega_y,
        )
        is_item_form = all((pokemon.species.is_form, pokemon.species.form_item is not None, base.form_item is None))
        if not (is_mega or is_item_form):
            return await ctx.send("This pokémon is not an alternative / mega form that can be transformed back!")

        # confirm

        result = await ctx.confirm(
            f"Are you sure you want to switch **{pokemon}** back to a **{base}**?\nThe original price used to transform will not be refunded!"
        )
        if result is None:
            return await ctx.send("Time's up. Aborted.")
        if result is False:
            return await ctx.send("Aborted.")

        await self.bot.mongo.update_pokemon(
            pokemon,
            {"$set": {f"species_id": base.id}},
        )

        embed = self.bot.Embed(title=f"Congratulations {ctx.author.display_name}!")
        embed.add_field(
            name=f"Your {pokemon:n} is changing forms!",
            value=f"Your {pokemon:n} has turned into a {base.name}!",
        )
        embed.set_thumbnail(url=base.get_image_url(pokemon.shiny, pokemon.gender))
        await ctx.send(embed=embed)

    @checks.has_started()
    @commands.command(aliases=("f",))
    async def first(self, ctx):
        if ctx.author.id not in self.bot.menus:
            return await ctx.send("Couldn't find a previous menu to paginate.")

        pages = self.bot.menus[ctx.author.id]
        with contextlib.suppress(TypeError, DiscordException):
            await pages.message.clear_reactions()
        await pages.continue_at(ctx, 0)

    @checks.has_started()
    @commands.command(aliases=("n", "forward"))
    async def next(self, ctx):
        if ctx.author.id not in self.bot.menus:
            return await ctx.send("Couldn't find a previous menu to paginate.")

        pages = self.bot.menus[ctx.author.id]
        with contextlib.suppress(AttributeError, TypeError, DiscordException):
            await pages.message.clear_reactions()
        await pages.continue_at(ctx, pages.current_page + 1)

    @checks.has_started()
    @commands.command(aliases=("prev", "back", "b"))
    async def previous(self, ctx):
        if ctx.author.id not in self.bot.menus:
            return await ctx.send("Couldn't find a previous menu to paginate.")

        pages = self.bot.menus[ctx.author.id]
        if pages.current_page == 0 and not pages.allow_last:
            return await ctx.send(
                f"Sorry, market does not support going to last page. Try sorting in the reverse direction instead. For example, use `{ctx.clean_prefix}market search --order price` to sort by price."
            )
        with contextlib.suppress(AttributeError, TypeError, DiscordException):
            await pages.message.clear_reactions()
        await pages.continue_at(ctx, pages.current_page - 1)

    @checks.has_started()
    @commands.command(aliases=("l",))
    async def last(self, ctx):
        if ctx.author.id not in self.bot.menus:
            return await ctx.send("Couldn't find a previous menu to paginate.")

        pages = self.bot.menus[ctx.author.id]
        if not pages.allow_last:
            return await ctx.send(
                f"Sorry, market does not support this command. Try sorting in the reverse direction instead. For example, use `{ctx.clean_prefix}market search --order price` to sort by price."
            )
        with contextlib.suppress(AttributeError, TypeError, DiscordException):
            await pages.message.clear_reactions()
        await pages.continue_at(ctx, pages._source.get_max_pages() - 1)

    @checks.has_started()
    @commands.command(aliases=("page", "g"))
    async def go(self, ctx, page: int):
        if ctx.author.id not in self.bot.menus:
            return await ctx.send("Couldn't find a previous menu to paginate.")

        pages = self.bot.menus[ctx.author.id]
        if not pages.allow_go:
            return await ctx.send(
                "Sorry, market and info do not support this command. Try further filtering your results instead."
            )
        with contextlib.suppress(AttributeError, TypeError, DiscordException):
            await pages.message.clear_reactions()
        await pages.continue_at(ctx, page - 1)


async def setup(bot: commands.Bot):
    await bot.add_cog(Pokemon(bot))
