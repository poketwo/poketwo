import random
import sys
import traceback
from datetime import datetime

import aiohttp
import discord
from discord.ext import commands, flags, tasks
from helpers import checks, constants, converters

from .database import Database


class Bot(commands.Cog):
    """For basic bot operation."""

    def __init__(self, bot):
        self.bot = bot

        if not hasattr(self.bot, "prefixes"):
            self.bot.prefixes = {}

        self.post_count.start()
        self.update_status.start()

        if self.bot.cluster_idx == 0:
            self.post_dbl.start()

        self.cd = commands.CooldownMapping.from_cooldown(8, 5, commands.BucketType.user)

    async def bot_check(self, ctx):
        if ctx.invoked_with.lower() == "help":
            return True

        bucket = self.cd.get_bucket(ctx.message)
        retry_after = bucket.update_rate_limit()
        if retry_after:
            raise commands.CommandOnCooldown(bucket, retry_after)

        return True

    @commands.Cog.listener()
    async def on_command_error(self, ctx: commands.Context, error):

        if isinstance(error, commands.CommandOnCooldown):
            self.bot.log.info(f"{ctx.author.id} hit cooldown")
            await ctx.message.add_reaction("⛔")
        elif isinstance(error, commands.MaxConcurrencyReached):
            name = error.per.name
            suffix = "per %s" % name if error.per.name != "default" else "globally"
            plural = "%s times %s" if error.number > 1 else "%s time %s"
            fmt = plural % (error.number, suffix)
            await ctx.send(f"This command can only be used {fmt} at the same time.")
        elif isinstance(error, commands.NoPrivateMessage):
            await ctx.send("This command cannot be used in private messages.")
        elif isinstance(error, commands.DisabledCommand):
            await ctx.send("Sorry. This command is disabled and cannot be used.")
        elif isinstance(error, commands.BotMissingPermissions):
            missing = [
                "`" + perm.replace("_", " ").replace("guild", "server").title() + "`"
                for perm in error.missing_perms
            ]
            fmt = "\n".join(missing)
            message = f"💥 Err, I need the following permissions to run this command:\n{fmt}\nPlease fix this and try again."
            botmember = (
                self.bot.user
                if ctx.guild is None
                else ctx.guild.get_member(self.bot.user.id)
            )
            if ctx.channel.permissions_for(botmember).send_messages:
                await ctx.send(message)
        elif isinstance(
            error,
            (
                commands.CheckFailure,
                converters.PokemonConversionError,
                commands.UserInputError,
                flags.ArgumentParsingError,
            ),
        ):
            await ctx.send(error)
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send_help(ctx.command)
        elif isinstance(error, commands.CommandNotFound):
            return
        else:
            print(f"Ignoring exception in command {ctx.command}")
            traceback.print_exception(
                type(error), error, error.__traceback__, file=sys.stderr
            )
            print("\n\n")

    @commands.Cog.listener()
    async def on_error(self, ctx: commands.Context, error):

        if isinstance(error, discord.NotFound):
            return
        else:
            print(f"Ignoring exception in command {ctx.command}:")
            traceback.print_exception(
                type(error), error, error.__traceback__, file=sys.stderr
            )
            print("\n\n")

    @property
    def db(self) -> Database:
        return self.bot.get_cog("Database")

    async def determine_prefix(self, guild):
        if guild:
            if guild.id not in self.bot.prefixes:
                data = await self.bot.mongo.Guild.find_one({"id": guild.id})
                if data is None:
                    data = self.bot.mongo.Guild(id=guild.id)
                    await data.commit()

                self.bot.prefixes[guild.id] = data.prefix

            if self.bot.prefixes[guild.id] is not None:
                return [
                    self.bot.prefixes[guild.id],
                    self.bot.user.mention + " ",
                    self.bot.user.mention[:2] + "!" + self.bot.user.mention[2:] + " ",
                ]

        return [
            "p!",
            "P!",
            self.bot.user.mention + " ",
            self.bot.user.mention[:2] + "!" + self.bot.user.mention[2:] + " ",
        ]

    @commands.command()
    async def invite(self, ctx: commands.Context):
        """View the invite link for the bot."""

        embed = self.bot.Embed(color=0xE67D23)
        embed.title = "Want to add me to your server? Use the link below!"
        embed.set_thumbnail(url=self.bot.user.avatar_url)
        embed.add_field(
            name="Invite Bot", value="https://invite.poketwo.net/", inline=False
        )
        embed.add_field(
            name="Join Server", value="https://discord.gg/poketwo", inline=False
        )

        await ctx.send(embed=embed)

    @commands.command()
    async def donate(self, ctx: commands.Context):
        """Donate to receive shards."""

        await ctx.send(
            "Pokétwo relies on players like you to stay up and running. "
            "You can help support the bot by donating to receive shards, which can be used to purchase redeems and other items in the shop.\n\n"
            "**Donation Link:** https://poketwo.net/store\n\n"
        )

    async def get_stats(self):
        result = await self.bot.mongo.db.stats.aggregate(
            [
                {
                    "$group": {
                        "_id": None,
                        "servers": {"$sum": "$servers"},
                        "shards": {"$sum": "$shards"},
                        "latency": {"$sum": "$latency"},
                    }
                }
            ]
        ).to_list(None)
        result = result[0]

        return result

    @tasks.loop(minutes=1)
    async def update_status(self):
        await self.bot.wait_until_ready()
        result = await self.get_stats()
        await self.bot.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name=f"{result['servers']:,} servers",
            )
        )

    @tasks.loop(minutes=5)
    async def post_dbl(self):
        await self.bot.wait_until_ready()

        result = await self.get_stats()

        headers = {"Authorization": self.bot.dbl_token}
        data = {"server_count": result["servers"], "shard_count": result["shards"]}
        async with aiohttp.ClientSession(headers=headers) as sess:
            r = await sess.post(
                f"https://top.gg/api/bots/{self.bot.user.id}/stats", data=data
            )

    @tasks.loop(minutes=1)
    async def post_count(self):
        await self.bot.wait_until_ready()
        await self.bot.mongo.db.stats.update_one(
            {"_id": self.bot.cluster_name},
            {
                "$set": {
                    "servers": len(self.bot.guilds),
                    "shards": len(self.bot.shards),
                    "latency": min(sum(x[1] for x in self.bot.latencies), 1),
                }
            },
            upsert=True,
        )

    @commands.command(aliases=["botinfo"])
    async def stats(self, ctx: commands.Context):
        """View bot info."""

        result = await self.get_stats()

        embed = self.bot.Embed(color=0xE67D23)
        embed.title = f"Pokétwo Statistics"
        embed.set_thumbnail(url=self.bot.user.avatar_url)

        embed.add_field(name="Servers", value=result["servers"], inline=False)
        embed.add_field(name="Shards", value=result["shards"], inline=False)
        embed.add_field(
            name="Trainers",
            value=await self.bot.mongo.db.member.estimated_document_count(),
            inline=False,
        )
        embed.add_field(
            name="Average Latency",
            value=f"{int(result['latency'] * 1000 / result['shards'])} ms",
            inline=False,
        )

        await ctx.send(embed=embed)

    @commands.command()
    async def ping(self, ctx: commands.Context):
        """View the bot's latency."""

        message = await ctx.send("Pong!")
        ms = int((message.created_at - ctx.message.created_at).total_seconds() * 1000)

        if ms > 300 and random.random() < 0.5:
            await message.edit(
                content=(
                    f"Pong! **{ms} ms**\n\n"
                    "Tired of bot slowdowns? Running a bot is expensive, but you can help! Donate at https://poketwo.net/store."
                )
            )
        else:
            await message.edit(content=f"Pong! **{ms} ms**")

    @commands.command()
    async def start(self, ctx: commands.Context):
        """View the starter pokémon."""

        embed = self.bot.Embed(color=0xE67D23)
        embed.title = "Welcome to the world of Pokémon!"
        embed.description = f"To start, choose one of the starter pokémon using the `{ctx.prefix}pick <pokemon>` command. "

        for gen, pokemon in constants.STARTER_GENERATION.items():
            embed.add_field(name=gen, value=" · ".join(pokemon), inline=False)

        await ctx.send(embed=embed)

    @commands.command()
    async def pick(self, ctx: commands.Context, *, name: str):
        """Pick a starter pokémon to get started."""

        member = await self.db.fetch_member_info(ctx.author)

        if member is not None:
            return await ctx.send(
                f"You have already chosen a starter pokémon! View your pokémon with `{ctx.prefix}pokemon`."
            )

        species = self.bot.data.species_by_name(name)

        if species is None or species.name.lower() not in constants.STARTER_POKEMON:
            return await ctx.send(
                f"Please select one of the starter pokémon. To view them, type `{ctx.prefix}start`."
            )

        starter = self.bot.mongo.Pokemon.random(
            owner_id=ctx.author.id,
            species_id=species.id,
            level=1,
            xp=0,
            idx=1,
        )

        result = await self.bot.mongo.db.pokemon.insert_one(starter.to_mongo())
        await self.bot.mongo.db.member.insert_one(
            {
                "_id": ctx.author.id,
                "selected_id": result.inserted_id,
                "joined_at": datetime.utcnow(),
                "next_idx": 2,
            }
        )

        await ctx.send(
            f"Congratulations on entering the world of pokémon! {species} is your first pokémon. Type `{ctx.prefix}info` to view it!"
        )

    @checks.has_started()
    @commands.command()
    async def profile(self, ctx: commands.Context):
        """View your profile."""

        embed = self.bot.Embed(color=0xE67D23)
        embed.title = f"{ctx.author}"

        member = await self.db.fetch_member_info(ctx.author)

        pokemon_caught = []
        pokemon_caught.append(
            "**Total: **" + str(await self.db.fetch_pokedex_sum(ctx.author))
        )

        for name, filt in (
            ("Mythical", self.bot.data.list_mythical),
            ("Legendary", self.bot.data.list_legendary),
            ("Ultra Beast", self.bot.data.list_ub),
        ):
            pokemon_caught.append(
                f"**{name}: **"
                + str(
                    await self.db.fetch_pokedex_sum(
                        ctx.author,
                        [{"$match": {"k": {"$in": [str(x) for x in filt]}}}],
                    )
                )
            )

        pokemon_caught.append("**Shiny: **" + str(member.shinies_caught))

        embed.add_field(name="Pokémon Caught", value="\n".join(pokemon_caught))

        await ctx.send(embed=embed)

    def cog_unload(self):
        self.post_count.cancel()
        self.update_status.cancel()

        if self.bot.cluster_idx == 0:
            self.post_dbl.cancel()


def setup(bot):
    bot.add_cog(Bot(bot))
