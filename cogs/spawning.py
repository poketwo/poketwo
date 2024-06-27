import random
import textwrap
import time
from collections import defaultdict
from datetime import datetime
from typing import Optional
from urllib.parse import urljoin

import discord
from discord.ext import commands
import humanfriendly

from cogs.mongo import Incense
from data import models
from data.constants import GENDER_IMAGE_SUFFIXES
from helpers import checks, converters
from helpers import genders
from helpers.utils import write_fp


GMAX_CHANCE = 1/100


class Spawning(commands.Cog):
    """For basic bot operation."""

    def __init__(self, bot):
        self.bot = bot

        self.caught_users = defaultdict(list)
        self.bot.cooldown_users = {}
        self.bot.cooldown_guilds = {}

        if not hasattr(self.bot, "guild_counter"):
            self.bot.guild_counter = {}

    async def increase_xp(self, message, member):
        if member is not None:
            silence = member.silence
            if message.guild:
                guild = await self.bot.mongo.fetch_guild(message.guild)
                silence = silence or guild and guild.silence

            pokemon = await self.bot.mongo.fetch_pokemon(message.author, member.selected_id)
            if pokemon is not None and pokemon.held_item != 13002:
                # TODO this stuff here needs to be refactored

                if pokemon.level < 100 and pokemon.xp < pokemon.max_xp:
                    xp_inc = random.randint(10, 40)

                    if member.boost_active or message.guild.id == 716390832034414685:
                        xp_inc *= 2
                    pokemon.xp += xp_inc

                    await self.bot.mongo.update_pokemon(pokemon, {"$inc": {"xp": xp_inc}})

                if pokemon.xp >= pokemon.max_xp and pokemon.level < 100:
                    update = {"$set": {f"xp": 0, f"level": pokemon.level + 1}}
                    embed = self.bot.Embed(title=f"Congratulations {message.author.display_name}!")

                    name = str(pokemon.species)

                    if pokemon.nickname is not None:
                        name += f' "{pokemon.nickname}"'

                    embed.description = f"Your {name} is now level {pokemon.level + 1}!"

                    embed.set_thumbnail(url=pokemon.image_url)

                    pokemon.level += 1
                    guild = await self.bot.mongo.fetch_guild(message.channel.guild)
                    evo = pokemon.get_next_evolution(guild.time)
                    if evo is not None:
                        embed.add_field(
                            name=f"Your {name} is evolving!",
                            value=f"Your {name} has turned into a {evo}!",
                        )

                        embed.set_thumbnail(url=evo.get_image_url(pokemon.shiny, pokemon.gender))

                        update["$set"][f"species_id"] = evo.id

                        self.bot.dispatch("evolve", message.author, pokemon, evo)

                    else:
                        c = 0
                        for move in pokemon.species.moves:
                            if move.method.level == pokemon.level:
                                embed.add_field(
                                    name=f"New move!",
                                    value=f"Your {name} can now learn {move.move.name}!",
                                )
                                c += 1

                        for i in range(-c % 3):
                            embed.add_field(
                                name="‎",
                                value="‎",
                            )

                    await self.bot.mongo.update_pokemon(pokemon, update)

                    if silence and (evo is not None or pokemon.level == 100):
                        await message.author.send(embed=embed)

                    if not silence:
                        permissions = message.channel.permissions_for(message.guild.me)
                        if permissions.send_messages and permissions.attach_files and permissions.embed_links:
                            await message.channel.send(embed=embed)

                elif pokemon.level == 100 and pokemon.xp < pokemon.max_xp:
                    await self.bot.mongo.update_pokemon(pokemon, {"$set": {"xp": pokemon.max_xp}})

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.guild is None:
            return

        ctx = await self.bot.get_context(message)

        if ctx.valid:
            return

        current = time.time()

        # Spamcheck, every one second
        if current - self.bot.cooldown_users.get(message.author.id, 0) < 1.5:
            return

        self.bot.cooldown_users[message.author.id] = current

        member = await self.bot.mongo.fetch_member_info(message.author)
        if member.suspended or datetime.utcnow() < member.suspended_until:
            return

        # Increase XP on selected pokemon

        await self.increase_xp(message, member)

        # Increment guild activity counter

        if not message.guild:
            return

        if current - self.bot.cooldown_guilds.get(message.guild.id, 0) < 1:
            return

        self.bot.cooldown_guilds[message.guild.id] = current
        self.bot.guild_counter[message.guild.id] = self.bot.guild_counter.get(message.guild.id, 0) + 1

        spawn_threshold = 8 if message.guild.id == 716390832034414685 else 24

        if self.bot.guild_counter[message.guild.id] >= spawn_threshold:
            self.bot.guild_counter[message.guild.id] = 0

            guild = await self.bot.mongo.fetch_guild(message.guild)

            if len(guild.channels) > 0:
                channel = message.guild.get_channel_or_thread(random.choice(guild.channels))
            else:
                channel = message.channel

            if channel is None:
                return

            self.bot.loop.create_task(self.spawn_pokemon(channel))

    async def spawn_pokemon(
        self,
        channel: discord.TextChannel | discord.Thread,
        species: Optional[models.Species] = None,
        incense: Optional[Incense] = None,
        redeem: Optional[bool] = False,
    ):
        prev_species = None
        prev_species_id = await self.bot.redis.hget("wild", channel.id)
        if prev_species_id is not None:
            prev_species = self.bot.data.species_by_number(int(prev_species_id))

        if species is None:
            species = self.bot.data.random_spawn()

        if not redeem and await self.bot.redis.get(f"redeem:{channel.id}"):
            return

        self.bot.log.info(
            "pokemon_spawned",
            guild=channel.guild.name,
            guild_id=channel.guild.id,
            channel=channel.name,
            channel_id=channel.id,
            species=species,
            incense=incense,
            redeem=redeem,
        )

        permissions = channel.permissions_for(channel.guild.me)
        if not (permissions.send_messages and permissions.attach_files and permissions.embed_links):
            return False

        # spawn

        guild = await self.bot.mongo.fetch_guild(channel.guild)

        embed = self.bot.Embed()
        if prev_species:
            embed.title = f"Wild {prev_species} fled. A new wild pokémon has appeared!"
        else:
            embed.title = "A wild pokémon has appeared!"

        embed.description = f"Guess the pokémon and type `@{self.bot.user} catch <pokémon>` to catch it!"

        image = None

        gender = genders.generate_gender(species)

        if hasattr(self.bot.config, "SERVER_URL"):
            time = "day" if guild.is_day else "night"
            url = urljoin(self.bot.config.SERVER_URL, f"image")
            params = {
                "species": str(species.id),
                "time": time,
                "gender": gender,
            }
            async with self.bot.http_session.get(url, params=params) as resp:
                if resp.status == 200:
                    arr = await self.bot.loop.run_in_executor(None, write_fp, await resp.read())
                    image = discord.File(arr, filename="pokemon.jpg")
                    embed.set_image(url="attachment://pokemon.jpg")

        if image is None:
            gender_suffix = GENDER_IMAGE_SUFFIXES.get(gender.lower(), "") if species.has_gender_differences else ""
            path = f"data/images/{species.id}{gender_suffix}.png"
            image = discord.File(path, filename="pokemon.png")
            embed.set_image(url="attachment://pokemon.png")

        if incense:
            incense.spawns_remaining -= 1
            footer = textwrap.dedent(
                f"""
                Incense: Active.
                Spawns Remaining: {incense.spawns_remaining}.
                Spawn Interval: {incense.interval}s."""
            )
            if incense.ends_at:
                footer += f"\nEnds in {converters.strfdelta(incense.ends_in)} at"
                embed.timestamp = incense.ends_at

            embed.set_footer(
                text=footer
            )

        self.caught_users[channel.id] = set()
        await self.bot.redis.hset("wild", channel.id, species.id)

        if redeem:
            await self.bot.redis.set(f"redeem:{channel.id}", 1)
            await self.bot.redis.expire(f"redeem:{channel.id}", 30)

        await self.bot.redis.hset("gender", channel.id, gender)

        await channel.send(
            file=image,
            embed=embed,
        )

        return True

    @checks.has_started()
    @commands.cooldown(1, 10, commands.BucketType.channel)
    @commands.cooldown(1, 20, commands.BucketType.user)
    @commands.command(aliases=("h",))
    async def hint(self, ctx):
        """Get a hint for the wild pokémon."""

        if not await self.bot.redis.hexists("wild", ctx.channel.id):
            return

        if await self.bot.redis.hexists("captcha", ctx.author.id):
            return await ctx.send(
                f"Whoa there. Please tell us you're human! https://verify.poketwo.net/captcha/{ctx.author.id}"
            )

        count = await self.bot.redis.hincrby(f"catches:{ctx.author.id}", 1)
        if count == 1:
            await self.bot.redis.expire(f"catches:{ctx.author.id}", 86400)
        elif count >= 1000:
            await self.bot.redis.hset("captcha", ctx.author.id, 1)
            await self.bot.redis.delete(f"catches:{ctx.author.id}")

        species_id = await self.bot.redis.hget("wild", ctx.channel.id)
        species = self.bot.data.species_by_number(int(species_id))

        inds = [i for i, x in enumerate(species.name) if x.isalpha()]
        blanks = random.sample(inds, len(inds) // 2)
        hint = "".join("\\_" if i in blanks else x for i, x in enumerate(species.name))

        await ctx.send(f"The pokémon is {hint}.")

    @checks.has_started()
    @commands.max_concurrency(1, commands.BucketType.channel, wait=True)
    @commands.command(aliases=("c",))
    async def catch(self, ctx, *, guess: str):
        """Catch a wild pokémon."""

        # Retrieve correct species and level from tracker

        if not await self.bot.redis.hexists("wild", ctx.channel.id):
            return

        captcha_message = f"Whoa there. Please tell us you're human! https://verify.poketwo.net/captcha/{ctx.author.id}"

        if await self.bot.redis.hexists("captcha", ctx.author.id):
            return await ctx.send(captcha_message)

        count = await self.bot.redis.hincrby(f"catches:{ctx.author.id}", 1)
        captcha_set = False
        if count == 1:
            await self.bot.redis.expire(f"catches:{ctx.author.id}", 86400)
        elif count >= 1000:
            captcha_set = True
            await self.bot.redis.hset("captcha", ctx.author.id, 1)
            await self.bot.redis.delete(f"catches:{ctx.author.id}")

        species_id = await self.bot.redis.hget("wild", ctx.channel.id)
        species = self.bot.data.species_by_number(int(species_id))
        gender = await self.bot.redis.hget("gender", ctx.channel.id)
        if gender is not None:
            gender = gender.decode("ASCII")
        else:
            gender = genders.generate_gender(species)

        if models.deaccent(guess.lower().replace("′", "'")) not in species.correct_guesses:
            return await ctx.send("That is the wrong pokémon!")

        # Correct guess, add to database

        if ctx.channel.id == 759559123657293835:
            if ctx.author.id in self.caught_users[ctx.channel.id]:
                return await ctx.send("You have already caught this pokémon!")

            self.caught_users[ctx.channel.id].add(ctx.author.id)
        else:
            current_species_id = await self.bot.redis.hget("wild", ctx.channel.id)
            if current_species_id is not None and current_species_id == species_id:
                await self.bot.redis.hdel("wild", ctx.channel.id)

        member = await self.bot.mongo.fetch_member_info(ctx.author)

        pokemon = await self.bot.mongo.make_pokemon(member, species, gender=gender)
        pokemon_obj = self.bot.mongo.Pokemon.build_from_mongo(pokemon)

        gmax = species.id == species.dex_number and species.gmax and random.random() < GMAX_CHANCE
        if gmax:
            pokemon["species_id"] = species.gmax.id

        r = await self.bot.mongo.db.pokemon.insert_one(pokemon)

        inc = {}
        if pokemon_obj.shiny:
            inc["shinies_caught"] = 1
        if gmax:
            inc["gmax_caught"] = 1

        if inc:
            await self.bot.mongo.update_member(ctx.author, {"$inc": inc})

        spec = "lng!s" + ("P" if member.catch_ivs else "")
        message = f"Congratulations {ctx.author.mention}! You caught a {pokemon_obj:{spec}}!"

        memberp = await self.bot.mongo.fetch_pokedex(ctx.author, species.dex_number, species.dex_number + 1)

        if str(species.dex_number) not in memberp.pokedex:
            message += " Added to Pokédex. You received 35 Pokécoins!"

            await self.bot.mongo.update_member(
                ctx.author,
                {
                    "$set": {f"pokedex.{species.dex_number}": 1},
                    "$inc": {"balance": 35},
                },
            )

        else:
            inc_bal = 0

            if memberp.pokedex[str(species.dex_number)] + 1 == 10:
                message += f" This is your 10th {self.bot.data.species_by_number(species.dex_number)}! You received 350 Pokécoins."
                inc_bal = 350

            elif memberp.pokedex[str(species.dex_number)] + 1 == 100:
                message += f" This is your 100th {self.bot.data.species_by_number(species.dex_number)}! You received 3,500 Pokécoins."
                inc_bal = 3500

            elif memberp.pokedex[str(species.dex_number)] + 1 == 1000:
                message += f" This is your 1,000th {self.bot.data.species_by_number(species.dex_number)}! You received 35,000 Pokécoins."
                inc_bal = 35000

            elif memberp.pokedex[str(species.dex_number)] + 1 == 10000:
                message += f" This is your 10,000th {self.bot.data.species_by_number(species.dex_number)}! You received 350,000 Pokécoins."
                inc_bal = 350000

            elif memberp.pokedex[str(species.dex_number)] + 1 == 100000:
                message += f" This is your 100,000th {self.bot.data.species_by_number(species.dex_number)}! You received 3,500,000 Pokécoins."
                inc_bal = 3500000

            await self.bot.mongo.update_member(
                ctx.author,
                {
                    "$inc": {"balance": inc_bal, f"pokedex.{species.dex_number}": 1},
                },
            )

        if gmax:
            message += f"\nWoah! It seems that this pokémon has the Gigantamax Factor... {self.bot.sprites['gmax']}"

        if member.shiny_hunt == species.dex_number:
            if pokemon_obj.shiny:
                message += f"\n\nShiny streak reset. (**{member.shiny_streak + 1}**)"
                await self.bot.mongo.update_member(ctx.author, {"$set": {"shiny_streak": 0}})
            else:
                message += f"\n\n+1 Shiny chain! (**{member.shiny_streak + 1}**)"
                await self.bot.mongo.update_member(ctx.author, {"$inc": {"shiny_streak": 1}})

        if pokemon_obj.shiny:
            message += "\n\nThese colors seem unusual... ✨"

        await self.bot.redis.delete(f"redeem:{ctx.channel.id}")

        self.bot.dispatch("catch", ctx, species, r.inserted_id)
        ctx.log.info("pokemon_caught")

        if member.catch_mention:
            await ctx.send(message)
        else:
            await ctx.send(message, allowed_mentions=discord.AllowedMentions.none())

        if captcha_set:
            return await ctx.send(captcha_message)

    @checks.has_started()
    @commands.command(aliases=("sh",))
    async def shinyhunt(self, ctx, *, species: str = None):
        """Hunt for a shiny pokémon species."""

        member = await self.bot.mongo.fetch_member_info(ctx.author)

        if species is None:
            embed = self.bot.Embed(
                title=f"Shiny Hunt ✨",
                description="You can select a specific pokémon to shiny hunt. Each time you catch that pokémon, your chain will increase. The longer your chain, the higher your chance of catching a shiny one!",
            )

            embed.add_field(
                name=f"Currently Hunting",
                value=(
                    self.bot.data.species_by_number(member.shiny_hunt).name
                    if member.shiny_hunt
                    else f"Type `{ctx.clean_prefix}shinyhunt <pokémon>` to begin!"
                ),
            )

            if member.shiny_hunt:
                embed.add_field(name=f"Chain", value=str(member.shiny_streak))

            if member.shiny_charm_active:
                timespan = member.shiny_charm_expires - datetime.utcnow()
                timespan = humanfriendly.format_timespan(timespan.total_seconds())
                embed.set_footer(text=f"You have a shiny charm active that expires in {timespan}.")

            return await ctx.send(embed=embed)

        species = self.bot.data.species_by_name(species)
        species = self.bot.data.species_by_number(species.dex_number)

        if species is None:
            return await ctx.send(f"Could not find a pokémon matching `{species}`.")

        if not species.catchable:
            return await ctx.send("This pokémon can't be caught in the wild!")

        if species.id == member.shiny_hunt:
            return await ctx.send(f"You are already hunting this pokémon with a streak of **{member.shiny_streak}**.")

        if member.shiny_streak > 0:
            result = await ctx.confirm(
                f"Are you sure you want to shiny hunt a different pokémon? Your streak will be reset."
            )
            if result is None:
                return await ctx.send("Time's up. Aborted.")
            if result is False:
                return await ctx.send("Aborted.")

        await self.bot.mongo.update_member(
            ctx.author,
            {
                "$set": {"shiny_hunt": species.id, "shiny_streak": 0},
            },
        )

        await ctx.send(f"You are now shiny hunting **{species}**.")


async def setup(bot: commands.Bot):
    await bot.add_cog(Spawning(bot))
