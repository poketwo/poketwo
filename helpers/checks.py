from discord.ext import commands

from . import mongo


class MustHaveStarted(commands.CheckFailure):
    pass


class Suspended(commands.CheckFailure):
    pass


def is_admin():
    return commands.check_any(
        commands.is_owner(), commands.has_permissions(administrator=True)
    )


def has_started():
    async def predicate(ctx: commands.Context):
        member = await mongo.Member.find_one({"id": ctx.author.id}, {"suspended": 1})

        if member is None:
            raise MustHaveStarted(
                f"Please pick a starter pokémon by typing `{ctx.prefix}start` before using this command!"
            )

        if member.suspended:
            raise Suspended("Your account has been suspended.")

        return True

    return commands.check(predicate)


class ShuttingDown(commands.CheckFailure):
    pass


def enabled(bot):
    async def predicate(ctx: commands.Context):
        if ctx.author.id == 398686833153933313:
            return True

        if not bot.enabled:
            raise ShuttingDown(
                "The bot's currently refreshing. Try again in a couple seconds."
            )

        return True

    return predicate
