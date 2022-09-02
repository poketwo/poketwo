from discord.ext import commands

from helpers.views import ConfirmUpdatedTermsOfServiceView


class NotStarted(commands.CheckFailure):
    pass


class AcceptTermsOfService(commands.CheckFailure):
    pass


class Suspended(commands.CheckFailure):
    def __init__(self, reason, *args):
        super().__init__(*args)
        self.reason = reason


def is_admin():
    return commands.check_any(commands.is_owner(), commands.has_permissions(administrator=True))


def has_started():
    async def predicate(ctx):
        member = await ctx.bot.mongo.Member.find_one({"id": ctx.author.id}, {"suspended": 1, "suspension_reason": 1})
        if member is None:
            raise NotStarted(
                f"Please pick a starter pokémon by typing `{ctx.clean_prefix} start` before using this command!"
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
            {"id": ctx.author.id}, {"suspended": 1, "suspension_reason": 1, "tos": 1}
        )
        if member is None:
            return True

        if member.suspended:
            raise Suspended(member.suspension_reason)

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
