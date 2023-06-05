import contextlib
import math
import random
import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from functools import cached_property

import discord
from discord.ext import commands

from helpers.context import ConfirmationYesNoView
from helpers.utils import make_slider

PRIDE_CATEGORIES = ["pride", "nonbinary", "lesbian", "bisexual", "transgender", "gay", "pansexual"]
FLAG_NAMES = {
    "flag_pride": "Pride Flag",
    "flag_nonbinary": "Non-binary Pride Flag",
    "flag_lesbian": "Lesbian Pride Flag",
    "flag_bisexual": "Bisexual Pride Flag",
    "flag_transgender": "Transgender Pride Flag",
    "flag_gay": "Gay Pride Flag",
    "flag_pansexual": "Pansexual Pride Flag",
}

FLAG_SHORTCUTS = {
    "flag_pride": ["", "lgbt", "lgbtq", "rainbow"],
    "flag_nonbinary": ["nonbinary", "non-binary", "non binary", "enby", "nb"],
    "flag_lesbian": ["lesbian", "les"],
    "flag_bisexual": ["bisexual", "bi"],
    "flag_transgender": ["transgender", "trans"],
    "flag_gay": ["gay"],
    "flag_pansexual": ["pansexual", "pan"],
}

FLAG_BY_SHORTCUT = {v: k for k, v in FLAG_SHORTCUTS.items() for v in v}

POKEMON = {
    "pride": [50106, 50112, 50116],
    "nonbinary": [50103, 50105],
    "lesbian": [50108, 50117],
    "bisexual": [50104, 50115],
    "transgender": [50107, 50114],
    "gay": [50111, 50113],
    "pansexual": [50109, 50110],
}


FESTIVAL_PERIOD_START = datetime(2023, 6, 1, 0, 0, 0, tzinfo=timezone.utc)
FESTIVAL_PERIOD_OFFSET = timedelta(hours=7)
FESTIVAL_PERIOD_DURATION = timedelta(hours=4)

BASE_FLAG_DROP_CHANCE = 1 / 70  # * 7 different types
FESTIVAL_MULTIPLIER = 5


def make_catch_type_quest(type):
    return lambda: {
        "event": "catch",
        "count": (count := random.randint(5, 15)),
        "condition": {"type": type},
        "flag_count": random.randint(15, 25),
        "description": f"Catch {count} {type}-type pokémon",
    }


QUESTS = [
    lambda: {
        "event": "market_buy",
        "count": (count := random.randint(5, 10)),
        "flag_count": random.randint(2, 4),
        "description": f"Purchase {count} pokémon from the market",
    },
    lambda: {
        "event": "market_add",
        "count": (count := random.randint(10, 20)),
        "flag_count": random.randint(3, 5),
        "description": f"List {count} pokémon on the market",
    },
    lambda: {
        "event": "battle_start",
        "count": 1,
        "condition": {"type": "Grass"},
        "flag_count": random.randint(3, 8),
        "description": f"Battle using a Grass-type pokémon",
    },
    lambda: {
        "event": "release",
        "count": (count := random.randint(10, 20)),
        "flag_count": random.randint(3, 8),
        "description": f"Release {count} pokémon",
    },
    lambda: {
        "event": "battle_win",
        "count": (count := random.randint(1, 3)),
        "flag_count": random.randint(3, 5),
        "description": f"Win a battle {count} times",
    },
    lambda: {
        "event": "battle_start",
        "count": 1,
        "condition": {"type": "Normal"},
        "flag_count": random.randint(2, 5),
        "description": f"Battle using a Normal-type pokémon",
    },
    lambda: {
        "event": "trade",
        "count": (count := random.randint(3, 6)),
        "flag_count": random.randint(2, 3),
        "description": f"Trade with {count} people",
    },
    lambda: {
        "event": "evolve",
        "count": (count := random.randint(10, 15)),
        "flag_count": random.randint(3, 5),
        "description": f"Evolve {count} pokémon",
    },
]

QUESTS += [
    make_catch_type_quest("Normal"),
    make_catch_type_quest("Flying"),
    make_catch_type_quest("Poison"),
    make_catch_type_quest("Bug"),
    make_catch_type_quest("Ghost"),
    make_catch_type_quest("Fire"),
    make_catch_type_quest("Water"),
    make_catch_type_quest("Grass"),
    make_catch_type_quest("Electric"),
    make_catch_type_quest("Psychic"),
]


class Pride(commands.Cog):
    """Pride Month 2023 commands."""

    def __init__(self, bot):
        self.bot = bot
        for p in self.base_pokemon:
            sp = self.bot.data.species_by_number(p)
            sp.abundance *= 5

    def cog_unload(self):
        for p in self.base_pokemon:
            sp = self.bot.data.species_by_number(p)
            sp.abundance //= 5

    @cached_property
    def event_pokemon(self):
        return {p: k for k, v in POKEMON.items() for p in v}

    @cached_property
    def base_pokemon(self):
        base = {self.bot.data.species_by_number(k).dex_number: k for k in self.event_pokemon}
        base[655] = 50107
        return base

    def get_festival_status(self, dt=None):
        if dt is None:
            dt = datetime.now(timezone.utc)
        if dt < FESTIVAL_PERIOD_START:
            return ["next", 0, FESTIVAL_PERIOD_START, FESTIVAL_PERIOD_START + FESTIVAL_PERIOD_DURATION]
        period, elapsed = divmod(dt - FESTIVAL_PERIOD_START, FESTIVAL_PERIOD_OFFSET)
        if elapsed < FESTIVAL_PERIOD_DURATION:
            return [
                "current",
                period,
                FESTIVAL_PERIOD_START + period * FESTIVAL_PERIOD_OFFSET,
                FESTIVAL_PERIOD_START + period * FESTIVAL_PERIOD_OFFSET + FESTIVAL_PERIOD_DURATION,
            ]
        else:
            return [
                "next",
                period + 1,
                FESTIVAL_PERIOD_START + (period + 1) * FESTIVAL_PERIOD_OFFSET,
                FESTIVAL_PERIOD_START + (period + 1) * FESTIVAL_PERIOD_OFFSET + FESTIVAL_PERIOD_DURATION,
            ]

    def get_festival_category(self, dt=None):
        match self.get_festival_status(dt):
            case "current", period, _, _:
                return PRIDE_CATEGORIES[period % len(PRIDE_CATEGORIES)]

    async def fetch_pride_buddy(self, member: discord.Member):
        member_info = await self.bot.mongo.fetch_member_info(member)
        if member_info.pride_2023_buddy is None:
            return None
        return await self.bot.mongo.fetch_pokemon(member, member_info.pride_2023_buddy)

    async def fetch_quests(self, member: discord.Member):
        match self.get_festival_status():
            case "current", period, _, _:
                member_info = await self.bot.mongo.fetch_member_info(member)
                quests = member_info.pride_2023_quests.get(str(period))
                if not quests:
                    quests = [{**q(), "_id": str(uuid.uuid4()), "progress": 0} for q in random.sample(QUESTS, 5)]
                    await self.bot.mongo.update_member(member, {"$set": {f"pride_2023_quests.{period}": quests}})
                return quests

    @commands.Cog.listener(name="on_catch")
    async def process_flag_drops(self, ctx, species, _id):
        drops = defaultdict(int)

        for cat in PRIDE_CATEGORIES:
            chance = BASE_FLAG_DROP_CHANCE
            if self.get_festival_category() == cat:
                chance *= FESTIVAL_MULTIPLIER

            if random.random() < chance:
                drops[f"flag_{cat}"] += 1

        if drops:
            drop_msg = ", ".join(f"{v}× {self.bot.sprites[k]} {FLAG_NAMES[k]}" for k, v in drops.items())
            await self.bot.mongo.update_member(ctx.author, {"$inc": {f"pride_2023_{k}": v for k, v in drops.items()}})
            await ctx.send(f"The Pokémon dropped {drop_msg}! Use `{ctx.clean_prefix}pride` to view more info.")

    @commands.Cog.listener(name="on_catch")
    async def process_befriend(self, ctx, species, pokemon_id):
        if species.id not in self.base_pokemon:
            return
        member = await self.bot.mongo.fetch_member_info(ctx.author)
        if species.id == 493 and not all(member.pride_2023_categories.get(x) for x in PRIDE_CATEGORIES):
            return
        pride_species = self.base_pokemon[species.id]
        pride_species = self.bot.data.species_by_number(pride_species)

        if await self.fetch_pride_buddy(ctx.author):
            return

        embed = self.bot.Embed(
            title=f"Set `{species:lp}` as Pride Buddy?",
            description=f"You can offer flags to your Pride Buddy to increase its pride level and receive Pokécoins. Once {species}'s pride level is high enough, it will transform into {pride_species}!\n\nUse `@Pokétwo pride` to view more info.",
        )
        embed.set_image(url=pride_species.image_url)

        if await ctx.confirm(embed=embed, cls=ConfirmationYesNoView):
            await self.bot.mongo.update_member(
                ctx.author, {"$set": {"pride_2023_buddy": pokemon_id, "pride_2023_buddy_progress": 0}}
            )
            await ctx.send(f"{species} has been set as your Pride Buddy! Use `@Pokétwo pride buddy` to view more info.")
        else:
            await ctx.send(f"{species} was not set as your Pride Buddy.")

        if species.id == 493:
            await self.bot.mongo.update_member(ctx.author, {"$unset": {f"pride_2023_categories": True}})

    @commands.group(invoke_without_command=True, case_insensitive=True, aliases=("event",))
    async def pride(self, ctx):
        """Pride Month 2023 event commands."""

        embed = self.bot.Embed(
            title="Pride Month 2023",
            description="It's Pride Month, and Pokémon are celebrating too! Certain Pokémon have even been spotted in special pride forms. Participate in this festival for the chance to obtain limited-time Pride Pokémon, all while supporting the LGBTQ+ community!\n\nPokétwo is donating 80% of all revenue collected during this Pride Month to [The Trevor Project](https://www.thetrevorproject.org/), a US-based suicide prevention organization for young LGBTQ people.",
        )

        member = await self.bot.mongo.fetch_member_info(ctx.author)
        inventory = {f"flag_{cat}": member[f"pride_2023_flag_{cat}"] for cat in PRIDE_CATEGORIES}
        inventory_text = [
            "Look out for flag drops from catching Pokémon. During festival hours, flags will drop more frequently! You can also obtain flags from completing event quests.",
        ]
        inventory_text += [f"{v}× {self.bot.sprites[k]} {FLAG_NAMES[k]}" for k, v in inventory.items()]

        if buddy := await self.fetch_pride_buddy(ctx.author):
            pride_species = self.bot.data.species_by_number(self.base_pokemon[buddy.species_id])
            embed.add_field(
                name=f"Pride Buddy: {buddy:li} — {member.pride_2023_buddy_progress}%",
                value=f"Offer flags to {buddy.species} to increase its pride level and receive Pokécoins. Once its pride level is high enough, it will transform into {pride_species}!\nUse `@Pokétwo pride buddy` for more details.",
            )
            embed.set_thumbnail(url=buddy.species.image_url)
        else:
            embed.add_field(
                name="Pride Buddy",
                value="When catching Pokémon, you'll have the chance to set certain Pokémon as your Pride Buddy! Offer flags to your Pride Buddy to increase its pride level and receive Pokécoins. Once its pride level is high enough, it will transform into a special Pride Pokémon!",
                inline=False,
            )

        embed.add_field(name="Flag Inventory", value="\n".join(inventory_text), inline=False)

        quests = await self.fetch_quests(ctx.author)
        if quests:
            flag = f"flag_{self.get_festival_category()}"
            text = [
                "Complete event quests to earn more flags!",
                "You will receive a new set of quests every festival period.",
            ]
            text += [
                f"{x['flag_count']}× {self.bot.sprites[flag]}: {x['description']} ({x['progress']}/{x['count']})"
                for x in quests
            ]
            embed.add_field(name="Event Quests", value="\n".join(text), inline=False)

        status, period, start, end = self.get_festival_status()
        flag = f"flag_{PRIDE_CATEGORIES[period % len(PRIDE_CATEGORIES)]}"
        festival_text = [
            "The festival will run from **June 1st** to **June 30th**.",
            "Every 7 hours, there will be a 4-hour festival period featuring a specific pride flag.",
            f"{status.title()} Period: {discord.utils.format_dt(start, 'f')} to {discord.utils.format_dt(end, 'f')}",
            f"{status.title()} Featured Flag: {self.bot.sprites[flag]} {FLAG_NAMES[flag]}",
        ]

        embed.add_field(name="Festival Schedule", value="\n".join(festival_text), inline=False)

        await ctx.send(embed=embed)

    @pride.command()
    async def buddy(self, ctx):
        """View your Pride Buddy."""

        member = await self.bot.mongo.fetch_member_info(ctx.author)
        buddy = await self.fetch_pride_buddy(ctx.author)
        if buddy is None:
            return await ctx.send("You don't have a Pride Buddy set. Try catching some Pokémon!")

        pride_species = self.bot.data.species_by_number(self.base_pokemon[buddy.species_id])
        preferred_flag = f"flag_{self.event_pokemon[pride_species.id]}"

        embed = self.bot.Embed(
            title=f"Pride Buddy: {buddy:l}",
            description=f"Use `@Pokétwo pride offer <flag> <qty>` to offer flags to {buddy.species} to increase its pride level and receive Pokécoins. Once its pride level is high enough, it will transform into {pride_species}!\n",
        )
        embed.set_image(url=buddy.species.image_url)
        embed.add_field(
            name="Preferred Flag",
            value=f"{self.bot.sprites[preferred_flag]} {FLAG_NAMES[preferred_flag]}",
            inline=False,
        ),
        embed.add_field(
            name="Pride Level",
            value=f"{make_slider(self.bot, member.pride_2023_buddy_progress / 100)} {member.pride_2023_buddy_progress}%",
            inline=False,
        )
        await ctx.send(embed=embed)

    def calculate_probability(self, start, inc):
        if start + inc >= 100:
            return 1
        a = start / 100
        b = (start + inc) / 100
        return (b**4 - a**4) / (1 - a**4)

    @pride.command()
    async def offer(self, ctx, flag, qty: int = 1):
        """Offer flags to your Pride Buddy."""

        try:
            flag = FLAG_BY_SHORTCUT[flag.casefold().replace("flag", "").replace("pride", "").strip()]
        except KeyError:
            return await ctx.send(f"Invalid flag. Valid flags are: {', '.join(FLAG_NAMES.values())}")

        member = await self.bot.mongo.fetch_member_info(ctx.author)
        buddy = await self.fetch_pride_buddy(ctx.author)
        if buddy is None:
            await ctx.send("You don't have a Pride Buddy set. Try catching some Pokémon!")
            return
        pride_species = self.bot.data.species_by_number(self.base_pokemon[buddy.species_id])

        if member[f"pride_2023_{flag}"] < qty:
            return await ctx.send(
                f"You don't have enough {FLAG_NAMES[flag]}s to offer. Try catching some more Pokémon, or completing event quests!"
            )

        if flag.removeprefix("flag_") == self.event_pokemon[pride_species.id]:
            qty = min(qty, 50 - member.pride_2023_buddy_progress // 2)
            limit = 2 * qty
        else:
            qty = min(qty, 100 - member.pride_2023_buddy_progress)
            limit = qty

        success = random.random() < self.calculate_probability(member.pride_2023_buddy_progress, limit)
        pc = round(random.normalvariate(600 * limit, 200 * math.sqrt(limit)))

        if success:
            await self.bot.mongo.update_member(
                ctx.author,
                {
                    "$inc": {f"pride_2023_{flag}": -qty, "balance": pc},
                    "$set": {
                        "pride_2023_buddy": None,
                        "pride_2023_buddy_progress": 0,
                        f"pride_2023_categories.{self.event_pokemon[pride_species.id]}": True,
                    },
                },
            )
            await self.bot.mongo.update_pokemon(buddy, {"$set": {"species_id": pride_species.id}})
            embed = self.bot.Embed(
                title=f"Your {buddy.species} is transforming!",
                description=f"{buddy.species} (No. {buddy.idx}) transformed into {pride_species}!",
            )
            embed.set_image(url=pride_species.image_url)
            await ctx.send(
                f"You offered {qty} {FLAG_NAMES[flag]} to {buddy.species}. You received {pc} Pokécoins!", embed=embed
            )
        else:
            await self.bot.mongo.update_member(
                ctx.author,
                {"$inc": {f"pride_2023_{flag}": -qty, "pride_2023_buddy_progress": limit, "balance": pc}},
            )
            await ctx.send(
                f"You offered {qty} {FLAG_NAMES[flag]} to {buddy.species}! {buddy.species}'s Pride Level is now at {member.pride_2023_buddy_progress + limit}%. You received {pc} Pokécoins!"
            )

    def verify_condition(self, condition, species, to=None):
        if condition is not None:
            for k, v in condition.items():
                if k == "id" and species.id not in v:
                    return False
                elif k == "type" and v not in species.types:
                    return False
                elif k == "region" and v != species.region:
                    return False
                elif k == "to" and to.id != v:
                    return False
        return True

    async def on_quest_event(self, user, event, to_verify, *, count=1):
        _, period, *_ = self.get_festival_status()
        quests = await self.fetch_quests(user)
        if not quests:
            return

        for q in quests:
            if q["event"] != event:
                continue

            if len(to_verify) == 0 or any(self.verify_condition(q.get("condition"), x) for x in to_verify):
                self.bot.mongo.db.member.update_one(
                    {"_id": user.id, f"pride_2023_quests.{period}._id": q["_id"]},
                    {"$inc": {f"pride_2023_quests.{period}.$.progress": count}},
                )

        await self.bot.redis.hdel("db:member", user.id)
        await self.check_quests(user)

    async def check_quests(self, user):
        _, period, *_ = self.get_festival_status()
        quests = await self.fetch_quests(user)
        if not quests:
            return

        inc = 0

        for q in quests:
            if q["progress"] >= q["count"]:
                inc += q["flag_count"]
                await self.bot.mongo.update_member(user, {"$pull": {f"pride_2023_quests.{period}": {"_id": q["_id"]}}})

        flag = f"flag_{self.get_festival_category()}"
        await self.bot.mongo.update_member(user, {"$inc": {f"pride_2023_{flag}": inc}})

        if inc > 0:
            with contextlib.suppress(discord.HTTPException):
                msg = f"You completed a quest! You received {inc}× {self.bot.sprites[flag]} {FLAG_NAMES[flag]}!"
                await user.send(msg)

    @commands.Cog.listener()
    async def on_catch(self, ctx, species, id):
        await self.on_quest_event(ctx.author, "catch", [species])

    @commands.Cog.listener()
    async def on_market_buy(self, user, pokemon):
        await self.on_quest_event(user, "market_buy", [self.bot.data.species_by_number(pokemon["species_id"])])

    @commands.Cog.listener()
    async def on_market_add(self, user, pokemon):
        await self.on_quest_event(user, "market_add", [self.bot.data.species_by_number(pokemon["species_id"])])

    @commands.Cog.listener()
    async def on_trade(self, trade):
        a, b = trade["users"]
        await self.on_quest_event(a, "trade", [])
        await self.on_quest_event(b, "trade", [])

    @commands.Cog.listener()
    async def on_battle_start(self, ba):
        await self.on_quest_event(ba.trainers[0].user, "battle_start", [x.species for x in ba.trainers[0].pokemon])
        await self.on_quest_event(ba.trainers[1].user, "battle_start", [x.species for x in ba.trainers[1].pokemon])

    @commands.Cog.listener()
    async def on_battle_win(self, _battle, winner):
        await self.on_quest_event(winner, "battle_win", [])

    @commands.Cog.listener()
    async def on_evolve(self, user, pokemon, evo):
        await self.on_quest_event(user, "evolve", [])

    @commands.Cog.listener()
    async def on_release(self, user, count):
        await self.on_quest_event(user, "release", [], count=count)


async def setup(bot: commands.Bot):
    await bot.add_cog(Pride(bot))
