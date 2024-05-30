from datetime import datetime

import discord
from discord.ext import commands

from helpers import constants
from helpers.views import ConfirmUpdatedTermsOfServiceView


class MissingIncensePermission(commands.CheckFailure):
    pass


class IncensesDisabled(commands.CheckFailure):
    pass


class NotStarted(commands.CheckFailure):
    pass


class AcceptTermsOfService(commands.CheckFailure):
    pass


class Suspended(commands.CheckFailure):
    def __init__(self, reason, until, *args):
        super().__init__(*args)
        self.reason = reason
        self.until = until


class NotInGuild(commands.CheckFailure):
    pass


def is_admin():
    return commands.check_any(commands.is_owner(), commands.has_permissions(administrator=True))


def is_developer():
    return commands.check_any(commands.is_owner(), commands.has_role(1120600250474827856))


def has_incense_role():
    async def predicate(ctx):
        permissions = ctx.channel.permissions_for(ctx.author)

        if (
            not permissions.administrator
            and discord.utils.find(lambda r: r.name.lower() == "incense", ctx.author.roles) is None
        ):
            raise MissingIncensePermission(
                "You must have administrator permissions or a role named Incense in order to do this!"
            )
        return True

    return commands.check(predicate)


def incenses_not_disabled():
    async def predicate(ctx):
        disabled_msg = await ctx.bot.redis.get("incense_disabled")
        if disabled_msg is not None:
            disabled_msg = disabled_msg.decode("utf-8")
            raise IncensesDisabled(
                "Incenses are currently unavailable. This could be due to bot instability or upcoming maintenance. "
                "They will be made available again as soon as the issue is resolved, check the #bot-outages channel "
                "in the official server for more details.\n### Note from Developers:\n"
                f">>> {disabled_msg}"
            )
        return True

    return commands.check(predicate)


def in_guilds(*guild_ids):
    def predicate(ctx):
        if ctx.guild is None or ctx.guild.id not in guild_ids:
            raise NotInGuild("Sorry, you cannot use this command outside of the official server at this time.")
        return True

    return commands.check(predicate)


def community_server_only():
    return in_guilds(constants.COMMUNITY_SERVER_ID)


def has_started():
    async def predicate(ctx):
        member = await ctx.bot.mongo.Member.find_one({"id": ctx.author.id})
        if member is None:
            raise NotStarted(
                f"Please pick a starter pokémon by typing `{ctx.clean_prefix}start` before using this command!"
            )
        return True

    return commands.check(predicate)


def is_not_in_trade():
    async def predicate(ctx):
        if await ctx.bot.get_cog("Trading").is_in_trade(ctx.author):
            raise commands.CheckFailure("You can't do that in a trade!")
        return True

    return commands.check(predicate)


def general_check():
    async def predicate(ctx):
        member = await ctx.bot.mongo.Member.find_one(
            {"id": ctx.author.id}, {"suspended": 1, "suspended_until": 1, "suspension_reason": 1, "tos": 1}
        )
        if member is None:
            return True

        if member.suspended:
            raise Suspended(member.suspension_reason, until=None)
        if datetime.utcnow() < member.suspended_until:
            raise Suspended(member.suspension_reason, until=member.suspended_until)

        if member.tos is None:
            embed = ctx.bot.Embed(
                title="Updated Terms of Service (Effective May 23, 2022)",
                description="Please read, understand, and accept our new Terms of Service to continue. "
                "Violations of these Terms may result in the suspension of your account. "
                "If you choose not to accept the new user terms, you will no longer be able to use Pokétwo.",
            )
            embed.set_author(name=str(ctx.author), icon_url=ctx.author.display_avatar.url)
            embed.set_footer(text="These Terms can also be found on our website at https://poketwo.net/terms.")
            view = ConfirmUpdatedTermsOfServiceView(ctx)
            view.message = await ctx.reply(embed=embed, view=view)

            raise AcceptTermsOfService()

        return True

    return commands.check(predicate)
