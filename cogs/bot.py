import pickle
import random
import sys
import textwrap
import traceback
from datetime import datetime, timedelta
from typing import Counter, List

import aiohttp
import discord
import humanfriendly
from discord.channel import TextChannel
from discord.ext import commands, flags, tasks

from cogs.quests import DEFAULT_BADGES
from helpers import checks, constants, converters
from helpers.views import ConfirmTermsOfServiceView

GENERAL_CHANNEL_NAMES = {"welcome", "general", "lounge", "chat", "talk", "main"}

VOTING_PROVIDERS = {
    "topgg": {"name": "Top.gg", "url": "https://top.gg/bot/716390085896962058/vote"},
    "dbl": {"name": "Discord Bot List", "url": "https://discordbotlist.com/bots/poketwo/upvote"},
}


class Blacklisted(commands.CheckFailure):
    pass


def get_badges_text(badges: List[str], *, per_line: int = 10) -> str:
    """Formats a list of badges into lines of `per_line` badges"""

    lines = [" ".join(chunk) for chunk in discord.utils.as_chunks(badges, per_line)]
    return "\n".join(lines) or "No badges"


class Bot(commands.Cog):
    """For basic bot operation."""

    def __init__(self, bot):
        self.bot = bot
        headers = {"Authorization": self.bot.config.DBL_TOKEN}
        self.dbl_session = aiohttp.ClientSession(headers=headers)

        self.post_count.start()

        if self.bot.cluster_idx == 0 and self.bot.config.DBL_TOKEN is not None:
            self.post_dbl.start()
            self.remind_votes.start()

        self.cd = commands.CooldownMapping.from_cooldown(5, 3, commands.BucketType.user)
        self.bot.loop.create_task(self.process_dms())

    async def bot_check(self, ctx):
        if ctx.invoked_with.lower() == "help":
            return True

        bucket = self.cd.get_bucket(ctx.message)
        if retry_after := bucket.update_rate_limit():
            raise commands.CommandOnCooldown(bucket, retry_after, commands.BucketType.user)

        return True

    async def process_dms(self):
        await self.bot.wait_until_ready()
        with await self.bot.redis as r:
            while True:
                req = await r.blpop("send_dm")
                uid, content = pickle.loads(req[1])
                self.bot.loop.create_task(self.bot.send_dm(uid, content))

    @commands.Cog.listener("on_message")
    @commands.Cog.listener("on_message_edit")
    async def role_mention_alert_listener(self, *messages: discord.Message):
        """Notifies user of their mistake if role mention is detected, either on message sent or edited."""

        message = messages[-1]
        if not message.guild or message.author.bot:
            return

        author = message.author
        self_role = message.guild.self_role
        self_name = self.bot.user.name
        self_mention = self.bot.user.mention

        if self_role in message.role_mentions:
            embed = self.bot.Embed(
                title="Role Mention Detected",
                description=textwrap.dedent(
                    f"""
                    It seems like you may have accidentally pinged {self_name}'s *role* ({self_role.mention}) instead of {self_name} itself ({self_mention}) for the prefix, which does not work due to Discord limitations.

                    This is a common mistake due to the role being the same name as the bot. If you are a server administrator, you can remedy this by renaming the role to something else.
                    """
                ),
                color=constants.YELLOW,
            )
            embed.add_field(
                name=f"Please re-run the command by mentioning @{self.bot.user} as the prefix. You can also copy the following, which directly mentions the bot:",
                value=f"```\n{self_mention}\n```",
            )
            embed.set_author(name=str(author), icon_url=author.display_avatar.url)
            await message.reply(embed=embed)

    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
        if after.content != before.content:
            after.content = after.content.replace("—", "--").replace("'", "′").replace("‘", "′").replace("’", "′")
            await self.bot.process_commands(after)

    @commands.Cog.listener()
    async def on_command(self, ctx):
        ctx.log.info("command")

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.CommandOnCooldown):
            ctx.log.info("command.error.ComamndOnCooldown", retry_after=error.retry_after)
            await ctx.message.add_reaction("\N{HOURGLASS}")
        elif isinstance(error, commands.MaxConcurrencyReached):
            ctx.log.info("command.error.MaxConcurrencyReached")
            name = error.per.name
            suffix = "per %s" % name if error.per.name != "default" else "globally"
            plural = "%s times %s" if error.number > 1 else "%s time %s"
            fmt = plural % (error.number, suffix)
            await ctx.send(f"This command can only be used {fmt} at the same time.")
        elif isinstance(error, commands.NoPrivateMessage):
            await ctx.send("This command cannot be used in private messages.")
        elif isinstance(error, commands.DisabledCommand):
            ctx.log.info("command.error.DisabledCommand")
            await ctx.send("Sorry. This command is disabled and cannot be used.")
        elif isinstance(error, commands.BotMissingPermissions):
            ctx.log.info("command.error.BotMissingPermissions")
            missing = [
                f"`{perm.replace('_', ' ').replace('guild', 'server').title()}`" for perm in error.missing_permissions
            ]
            fmt = "\n".join(missing)
            message = (
                f"💥 Err, I need the following permissions to run this command:\n{fmt}\nPlease fix this and try again."
            )
            botmember = self.bot.user if ctx.guild is None else ctx.guild.get_member(self.bot.user.id)
            if ctx.channel.permissions_for(botmember).send_messages:
                await ctx.send(message)
        elif isinstance(error, commands.ConversionError):
            await ctx.send(error.original)
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send_help(ctx.command)
        elif isinstance(error, checks.Suspended):
            ctx.log.info("command.error.Suspended", reason=error.reason)
            embed = discord.Embed(
                color=discord.Color.red(),
                title="Account Suspended",
                description="Your account was found to be in violation of the [Pokétwo Terms of Service](https://poketwo.net/terms) and has been blacklisted from Pokétwo.",
            )
            if error.until is not None:
                embed.add_field(name="Expires", value=converters.strfdelta(error.until - datetime.utcnow(), long=True))
            embed.add_field(name="Reason", value=error.reason or "No reason provided", inline=False)
            embed.add_field(
                name="Appeals",
                value="If, after reading and understanding the reason provided above, you believe your account was suspended in error, and that you did not violate the Terms of Service, you may submit a [Bot Suspension Appeal](https://forms.poketwo.net/a/suspension-appeal) to request a re-review of your case.",
                inline=False,
            )
            await ctx.send(embed=embed)
        elif isinstance(error, checks.AcceptTermsOfService):
            ctx.log.info("command.error.AcceptTermsOfService")
        elif isinstance(error, (commands.CheckFailure, commands.UserInputError, flags.ArgumentParsingError)):
            await ctx.send(error)
        elif isinstance(error, commands.CommandNotFound):
            return
        else:
            print(error)
            ctx.log.exception("command.error")

    @commands.Cog.listener()
    async def on_error(self, event, *args, **kwargs):
        self.bot.log.info("error", event=event, event_args=args, event_kwargs=kwargs)

    def sendable_channel(self, channel):
        if channel.permissions_for(channel.guild.me).send_messages:
            return channel
        return None

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        priority_channels = []
        channels = []
        for channel in guild.channels:
            if channel == guild.system_channel or any(x in channel.name for x in GENERAL_CHANNEL_NAMES):
                priority_channels.append(channel)
            else:
                channels.append(channel)
        channels = priority_channels + channels
        try:
            channel = next(
                x for x in channels if isinstance(x, TextChannel) and x.permissions_for(guild.me).send_messages
            )
        except StopIteration:
            return

        prefix = f"@{self.bot.user} "

        embed = self.bot.Embed(
            title="Thanks for adding me to your server! \N{WAVING HAND SIGN}",
            description=f"To get started, do `{prefix}start` to pick your starter pokémon. As server members talk, wild pokémon will automatically spawn in the server, and you'll be able to catch them with `{prefix}catch <pokémon>`! For a full command list, do `{prefix}help`.",
        )
        embed.add_field(
            name="Common Configuration Options",
            value=(
                f"- `{prefix}redirect <channel>` to redirect pokémon spawns to one channel\n"
                f"- More can be found in `{prefix}config help`\n"
                f"- Consider renaming my server role ({guild.self_role.mention}), as this can cause confusion with the prefix ({self.bot.user.mention}) because of the same name."
            ),
            inline=False,
        )
        embed.add_field(
            name="Support Server",
            value="Join our server at https://discord.gg/poketwo for support.",
            inline=False,
        )
        await channel.send(embed=embed)

    @commands.command()
    async def invite(self, ctx):
        """View the invite link for the bot."""

        embed = self.bot.Embed(title="Want to add me to your server? Use the link below!")
        embed.set_thumbnail(url=self.bot.user.display_avatar.url)
        embed.add_field(name="Invite Bot", value="https://invite.poketwo.net/", inline=False)
        embed.add_field(name="Join Server", value="https://discord.gg/poketwo", inline=False)

        await ctx.send(embed=embed)

    @commands.command()
    async def donate(self, ctx):
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

    @tasks.loop(minutes=5)
    async def post_dbl(self):
        result = await self.get_stats()
        data = {"server_count": result["servers"], "shard_count": result["shards"]}
        await self.dbl_session.post(f"https://top.gg/api/bots/{self.bot.user.id}/stats", data=data)

    @post_dbl.before_loop
    async def before_post_dbl(self):
        await self.bot.wait_until_ready()

    async def send_voting_reminder(self, uid, provider):
        message = f"Your vote timer on **{provider['name']}** has refreshed. You can now vote again!"
        view = discord.ui.View(timeout=0)
        view.add_item(discord.ui.Button(label=f"Visit {provider['name']}", url=provider["url"]))
        await self.bot.send_dm(uid, message, view=view)

    @tasks.loop(seconds=15)
    async def remind_votes(self):
        for pid, provider in VOTING_PROVIDERS.items():
            query = {
                f"need_vote_reminder_on.{pid}": True,
                f"last_voted_on.{pid}": {"$lt": datetime.utcnow() - timedelta(hours=12)},
            }

            ids = [int(x["_id"]) async for x in self.bot.mongo.db.member.find(query, {"_id": 1})]
            if len(ids) == 0:
                continue

            for uid in ids:
                self.bot.loop.create_task(self.send_voting_reminder(uid, provider))

            await self.bot.mongo.db.member.update_many(
                {"_id": {"$in": ids}}, {"$set": {f"need_vote_reminder_on.{pid}": False}}
            )
            await self.bot.redis.hdel("db:member", *ids)

    @remind_votes.before_loop
    async def before_remind_votes(self):
        await self.bot.wait_until_ready()

    @tasks.loop(minutes=1)
    async def post_count(self):
        await self.bot.mongo.db.stats.update_one(
            {"_id": self.bot.cluster_name},
            {
                "$max": {"servers": len(self.bot.guilds)},
                "$set": {
                    "shards": len(self.bot.shards),
                    "latency": min(sum(x[1] for x in self.bot.latencies), 1),
                },
            },
            upsert=True,
        )

    @post_count.before_loop
    async def before_post_count(self):
        await self.bot.wait_until_ready()

    @checks.has_started()
    @commands.command(aliases=("v", "daily", "boxes"))
    async def vote(self, ctx):
        """View information on voting rewards."""

        member = await self.bot.mongo.fetch_member_info(ctx.author)
        embed = self.bot.Embed(title=f"Voting Rewards")
        view = discord.ui.View(timeout=0)

        embed.description = (
            f"Vote for us on "
            + " and ".join(f"**[{provider['name']}]({provider['url']})**" for provider in VOTING_PROVIDERS.values())
            + " to receive mystery boxes! "
            + "You can vote once per 12 hours on each site. Build your streak to get better rewards!"
        )

        for pid, provider in VOTING_PROVIDERS.items():
            next_vote = member.last_voted_on.get(pid, datetime.min) + timedelta(hours=12)

            if next_vote < datetime.utcnow():
                message = f"[You can vote right now!]({provider['url']})"
            else:
                timespan = next_vote - datetime.utcnow()
                formatted = humanfriendly.format_timespan(timespan.total_seconds())
                message = f"You can vote again in **{formatted}**."

            embed.add_field(name=f"{provider['name']} Timer", value=message, inline=True)
            view.add_item(discord.ui.Button(label=f"Visit {provider['name']}", url=provider["url"]))

        embed.add_field(
            name="Voting Streak",
            value=str(self.bot.sprites.check) * min(member.vote_streak, 14)
            + str(self.bot.sprites.gray) * (14 - min(member.vote_streak, 14))
            + f"\nCurrent Streak: {member.vote_streak} votes!",
            inline=False,
        )

        embed.add_field(
            name="Your Rewards",
            value=(
                f"{self.bot.sprites.gift_normal} **Normal Mystery Box:** {member.gifts_normal}\n"
                f"{self.bot.sprites.gift_great} **Great Mystery Box:** {member.gifts_great}\n"
                f"{self.bot.sprites.gift_ultra} **Ultra Mystery Box:** {member.gifts_ultra}\n"
                f"{self.bot.sprites.gift_master} **Master Mystery Box:** {member.gifts_master}\n"
            ),
            inline=False,
        )

        embed.add_field(
            name="Claiming Rewards",
            value=f"Use `{ctx.clean_prefix}open <normal|great|ultra|master> [amt]` to open your boxes!",
            inline=False,
        )

        embed.set_footer(text="You will automatically receive your rewards when you vote.")

        # TODO: Possibly use discordbotlist?
        # if ctx.guild and ctx.guild.id == 716390832034414685:
        #     embed.add_field(
        #         name="Server Voting",
        #         value="You can also vote for our server [here](https://top.gg/servers/716390832034414685/vote) to receive a colored role.",
        #         inline=False,
        #     )

        await ctx.send(embed=embed, view=view)

    @commands.command(aliases=("botinfo",))
    async def stats(self, ctx):
        """View bot info."""

        result = await self.get_stats()

        embed = self.bot.Embed(title=f"Pokétwo Statistics")
        embed.set_thumbnail(url=self.bot.user.display_avatar.url)

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
    async def ping(self, ctx):
        """View the bot's latency."""

        message = await ctx.send("Pong!")
        ms = int((message.created_at - ctx.message.created_at).total_seconds() * 1000)

        if ms > 300 and random.random() < 0.3:
            await message.edit(
                content=(
                    f"Pong! **{ms} ms**\n\n"
                    "Tired of bot slowdowns? Running a bot is expensive, but you can help! Donate at https://poketwo.net/store."
                )
            )
        else:
            await message.edit(content=f"Pong! **{ms} ms**")

    @commands.command()
    async def start(self, ctx):
        """View the starter pokémon."""

        embed = self.bot.Embed(
            title="Welcome to the world of Pokémon!",
            description=f"To start, choose one of the starter pokémon using the `{ctx.clean_prefix}pick <pokemon>` command. ",
        )

        for gen, pokemon in constants.STARTER_GENERATION.items():
            pokemon_texts = []
            for pokemon_name in pokemon:
                species = self.bot.data.species_by_name(pokemon_name)
                sprite = self.bot.sprites.get(species)
                pokemon_texts.append(f"{sprite} {species.name}")

            embed.add_field(name=gen, value=" \u200b · \u200b ".join(pokemon_texts), inline=False)

        await ctx.send(embed=embed)

    @commands.command()
    async def pick(self, ctx, *, name: str):
        """Pick a starter pokémon to get started."""

        member = await self.bot.mongo.fetch_member_info(ctx.author)

        if member is not None:
            return await ctx.send(
                f"You have already chosen a starter pokémon! View your pokémon with `{ctx.clean_prefix}pokemon`."
            )

        species = self.bot.data.species_by_name(name)

        if species is None or species.name.lower() not in constants.STARTER_POKEMON:
            return await ctx.send(
                f"Please select one of the starter pokémon. To view them, type `{ctx.clean_prefix}start`."
            )

        # ToS

        embed = ctx.bot.Embed(
            title="Pokétwo Terms of Service",
            description="Please read, understand, and accept our Terms of Service to continue. "
            "Violations of these Terms may result in the suspension of your account. "
            "If you choose not to accept the user terms, you will not be able to use Pokétwo.",
            url="https://poketwo.net/terms",
        )
        embed.set_author(name=str(ctx.author), icon_url=ctx.author.display_avatar.url)
        embed.set_footer(text="These Terms can also be found on our website at https://poketwo.net/terms.")

        result = await ctx.confirm(embed=embed, cls=ConfirmTermsOfServiceView)
        if result is None:
            return await ctx.send("Time's up. Aborted.")
        if result is False:
            return await ctx.send(
                "Since you chose not to accept the new user terms, we are unable to grant you access to Pokétwo.\n"
                "If you wish to continue, please re-run the command and agree to our Terms of Service to continue.",
            )

        member = await self.bot.mongo.fetch_member_info(ctx.author)

        if member is not None:
            return await ctx.send(
                f"You have already chosen a starter pokémon! View your pokémon with `{ctx.clean_prefix}pokemon`."
            )

        # Go

        starter = self.bot.mongo.Pokemon.random(
            owner_id=ctx.author.id,
            owned_by="user",
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
                "tos": datetime.utcnow(),
                "next_idx": 2,
            }
        )
        await self.bot.redis.hdel("db:member", ctx.author.id)

        await ctx.send(
            f"Congratulations on entering the world of pokémon! {species} is your first pokémon. Type `{ctx.clean_prefix}info` to view it!"
        )

    @checks.has_started()
    @commands.command()
    async def profile(self, ctx):
        """View your profile."""

        member = await self.bot.mongo.fetch_member_info(ctx.author)

        pokedex_completed = await self.bot.mongo.fetch_pokedex_count(ctx.author)
        pokedex_total = self.bot.data.total_pokedex_count
        pokedex_percent = int(pokedex_completed / pokedex_total * 100)

        embed = self.bot.Embed(title="Trainer Profile")
        embed.set_author(name=str(ctx.author), icon_url=ctx.author.display_avatar.url)

        pokemon_caught = []
        total = await self.bot.mongo.fetch_pokedex_sum(ctx.author)
        pokemon_caught.append(f"**Total:** {total}")

        for name, filt in (
            ("Mythical", self.bot.data.list_mythical),
            ("Legendary", self.bot.data.list_legendary),
            ("Ultra Beast", self.bot.data.list_ub),
        ):
            pokemon_caught.append(
                f"> **{name}:** "
                + str(
                    await self.bot.mongo.fetch_pokedex_sum(
                        ctx.author,
                        [{"$match": {"k": {"$in": [str(x) for x in filt]}}}],
                    )
                )
            )
        pokemon_caught.append(f"**Pokédex:** {pokedex_completed}/{pokedex_total} ({pokedex_percent}%)")
        pokemon_caught.append("**Gigantamax: **" + str(member.gmax_caught))
        pokemon_caught.append("**Shiny: **" + str(member.shinies_caught))
        embed.add_field(name="Pokémon Caught", value="\n".join(pokemon_caught))

        all_badges = [k for k, v in member.badges.items() if v]
        if member.halloween_badge:
            all_badges.append("halloween")

        default_badges = []
        exclusive_badges = []
        for badge in all_badges:
            badge_emoji = getattr(self.bot.sprites, f"badge_{badge}")
            if badge in DEFAULT_BADGES:
                default_badges.append(badge_emoji)
            else:
                exclusive_badges.append(badge_emoji)

        embed.add_field(
            name="Badges",
            value=get_badges_text(default_badges),
            inline=False,
        )

        #! This will cause character limit errors if the user has ~43+
        #! badges, because each badge is around 24 characters long!
        if exclusive_badges:
            embed.add_field(
                name="Exclusive Badges",
                value=get_badges_text(exclusive_badges),
                inline=False,
            )

        await ctx.send(embed=embed)

    def cog_unload(self):
        self.post_count.cancel()

        if self.bot.cluster_idx == 0 and self.bot.config.DBL_TOKEN is not None:
            self.post_dbl.cancel()
            self.remind_votes.cancel()

    @commands.command()
    @commands.has_permissions(manage_messages=True)
    async def cleanup(self, ctx, search=100):
        """Cleans up the bot's messages from the channel."""

        await ctx.message.delete()
        prefixes = await ctx.bot.command_prefix(ctx.bot, ctx.message)

        def check(m):
            return m.author == ctx.me or any((m.content.startswith(prefix) for prefix in prefixes))

        deleted = await ctx.channel.purge(limit=search, check=check, before=ctx.message)
        spammers = Counter(m.author.display_name for m in deleted)
        count = len(deleted)

        messages = [f'{count:,} message{" was" if count == 1 else "s were"} removed.']
        if len(deleted) > 0:
            messages.append("")
            spammers = sorted(spammers.items(), key=lambda t: t[1], reverse=True)
            messages.extend(f"– **{author}**: {count}" for author, count in spammers)

        await ctx.send("\n".join(messages), delete_after=5)


async def setup(bot: commands.Bot):
    await bot.add_cog(Bot(bot))
