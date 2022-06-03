import asyncio
import io
import random
import time
from collections import defaultdict
from urllib.parse import urljoin

import aiohttp
import discord
from discord.ext import commands, tasks
from helpers import checks

from data import models

from . import mongo


def write_fp(data):
    arr = io.BytesIO()
    arr.write(data)
    arr.seek(0)
    return arr


class Spawning(commands.Cog):
    """For basic bot operation."""

    def __init__(self, bot):
        self.bot = bot

        self.caught_users = defaultdict(list)
        self.bot.cooldown_users = {}
        self.bot.cooldown_guilds = {}

        self.spawn_incense.start()

        if not hasattr(self.bot, "guild_counter"):
            self.bot.guild_counter = {}

    @tasks.loop(seconds=20)
    async def spawn_incense(self):
        channels = self.bot.mongo.db.channel.find({"spawns_remaining": {"$gt": 0}})
        async for result in channels:
            guild = self.bot.get_guild(result["guild_id"])
            channel = None if guild is None else guild.get_channel_or_thread(result["_id"])

            if channel is not None:
                self.bot.loop.create_task(self.spawn_pokemon(channel, incense=result["spawns_remaining"]))
                await self.bot.mongo.update_channel(channel, {"$inc": {"spawns_remaining": -1}})

    @spawn_incense.before_loop
    async def before_spawn_incense(self):
        await self.bot.wait_until_ready()

    async def increase_xp(self, message):
        member = await self.bot.mongo.fetch_member_info(message.author)

        if member is not None:
            if member.suspended:
                return

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

                    if pokemon.shiny:
                        embed.set_thumbnail(url=pokemon.species.shiny_image_url)
                    else:
                        embed.set_thumbnail(url=pokemon.species.image_url)

                    pokemon.level += 1
                    guild = await self.bot.mongo.fetch_guild(message.channel.guild)
                    if pokemon.get_next_evolution(guild.is_day) is not None:
                        evo = pokemon.get_next_evolution(guild.is_day)
                        embed.add_field(
                            name=f"Your {name} is evolving!",
                            value=f"Your {name} has turned into a {evo}!",
                        )

                        if pokemon.shiny:
                            embed.set_thumbnail(url=evo.shiny_image_url)
                        else:
                            embed.set_thumbnail(url=evo.image_url)

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

                    if not silence:
                        permissions = message.channel.permissions_for(message.guild.me)
                        if permissions.send_messages and permissions.attach_files and permissions.embed_links:
                            await message.channel.send(embed=embed)

                    if silence and pokemon.level == 100:
                        await message.author.send(embed=embed)

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

        # Increase XP on selected pokemon

        await self.increase_xp(message)

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

    async def spawn_pokemon(self, channel, species=None, incense=None, redeem=False):
        prev_species = None
        if await self.bot.redis.hexists("wild", channel.id):
            prev_species_id = await self.bot.redis.hget("wild", channel.id)
            prev_species = self.bot.data.species_by_number(int(prev_species_id))

        if species is None:
            species = self.bot.data.random_spawn()

        if not redeem and await self.bot.redis.get(f"redeem:{channel.id}"):
            return

        self.bot.log.info(
            "Pokemon spawned",
            extra={
                "guild_id": channel.id,
                "channel_id": channel.id,
                "species_id": species.id,
                "species": species,
                "incense": incense,
                "redeem": redeem,
            },
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

        prefix = await self.bot.get_cog("Bot").determine_prefix(channel.guild)
        prefix = prefix[0]
        embed.description = f"Guess the pokémon and type `{prefix}catch <pokémon>` to catch it!"

        image = None

        if hasattr(self.bot.config, "SERVER_URL"):
            url = urljoin(self.bot.config.SERVER_URL, f"image?species={species.id}&time=")
            url += "day" if guild.is_day else "night"
            async with self.bot.http_session.get(url) as resp:
                if resp.status == 200:
                    arr = await self.bot.loop.run_in_executor(None, write_fp, await resp.read())
                    image = discord.File(arr, filename="pokemon.jpg")
                    embed.set_image(url="attachment://pokemon.jpg")

        if image is None:
            image = discord.File(f"data/images/{species.id}.png", filename="pokemon.png")
            embed.set_image(url="attachment://pokemon.png")

        if incense:
            embed.set_footer(text=f"Incense: Active.\nSpawns Remaining: {incense-1}.")

        self.caught_users[channel.id] = set()
        await self.bot.redis.hset("wild", channel.id, species.id)

        if redeem:
            await self.bot.redis.set(f"redeem:{channel.id}", 1)
            await self.bot.redis.expire(f"redeem:{channel.id}", 30)

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

        if models.deaccent(guess.lower().replace("′", "'")) not in species.correct_guesses:
            return await ctx.send("That is the wrong pokémon!")

        # Correct guess, add to database

        if ctx.channel.id == 759559123657293835:
            if ctx.author.id in self.caught_users[ctx.channel.id]:
                return await ctx.send("You have already caught this pokémon!")

            self.caught_users[ctx.channel.id].add(ctx.author.id)
        else:
            await self.bot.redis.hdel("wild", ctx.channel.id)

        member = await self.bot.mongo.fetch_member_info(ctx.author)

        shiny = member.determine_shiny(species)
        level = min(max(int(random.normalvariate(20, 10)), 1), 100)
        moves = [x.move.id for x in species.moves if level >= x.method.level]
        random.shuffle(moves)

        ivs = [mongo.random_iv() for i in range(6)]

        await self.bot.mongo.db.pokemon.insert_one(
            {
                "owner_id": ctx.author.id,
                "owned_by": "user",
                "species_id": species.id,
                "level": level,
                "xp": 0,
                "nature": mongo.random_nature(),
                "iv_hp": ivs[0],
                "iv_atk": ivs[1],
                "iv_defn": ivs[2],
                "iv_satk": ivs[3],
                "iv_sdef": ivs[4],
                "iv_spd": ivs[5],
                "iv_total": sum(ivs),
                "moves": moves[:4],
                "shiny": shiny,
                "idx": await self.bot.mongo.fetch_next_idx(ctx.author),
            }
        )
        if shiny:
            await self.bot.mongo.update_member(ctx.author, {"$inc": {"shinies_caught": 1}})

        message = f"Congratulations {ctx.author.mention}! You caught a level {level} {species}!"

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

        if member.shiny_hunt == species.dex_number:
            if shiny:
                message += f"\n\nShiny streak reset. (**{member.shiny_streak + 1}**)"
                await self.bot.mongo.update_member(ctx.author, {"$set": {"shiny_streak": 0}})
            else:
                message += f"\n\n+1 Shiny chain! (**{member.shiny_streak + 1}**)"
                await self.bot.mongo.update_member(ctx.author, {"$inc": {"shiny_streak": 1}})

        if shiny:
            message += "\n\nThese colors seem unusual... ✨"

        await self.bot.redis.delete(f"redeem:{ctx.channel.id}")

        self.bot.dispatch("catch", ctx, species)
        if member.catch_mention:
            await ctx.send(message)
        else:
            await ctx.send(message, allowed_mentions=discord.AllowedMentions.none())

    @checks.has_started()
    @commands.command()
    async def togglemention(self, ctx):
        """Toggle getting mentioned when catching a pokémon."""
        member = await self.bot.mongo.fetch_member_info(ctx.author)

        await self.bot.mongo.update_member(ctx.author, {"$set": {"catch_mention": not member.catch_mention}})

        if member.catch_mention:
            await ctx.send(f"You will no longer receive catch pings.")
        else:
            await ctx.send("You will now be pinged on catches.")

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
                value=self.bot.data.species_by_number(member.shiny_hunt).name
                if member.shiny_hunt
                else f"Type `{ctx.prefix}shinyhunt <pokémon>` to begin!",
            )

            if member.shiny_hunt:
                embed.add_field(name=f"Chain", value=str(member.shiny_streak))

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

    def cog_unload(self):
        self.spawn_incense.cancel()
        self.send_spawns.cancel()


async def setup(bot: commands.Bot):
    await bot.add_cog(Spawning(bot))
