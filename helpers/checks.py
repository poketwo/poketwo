from discord.ext import commands

from . import mongo


class MustHaveStarted(commands.CheckFailure):
    pass


def is_admin():
    return commands.check_any(
        commands.is_owner(), commands.has_permissions(administrator=True)
    )


users = set()


def has_started():
    async def predicate(ctx: commands.Context):
        if ctx.author.id not in users:
            member = await mongo.Member.find_one({"id": ctx.author.id})

            if member is None:
                raise MustHaveStarted(
                    f"Please pick a starter pokémon by typing `{ctx.prefix}start` before using this command!"
                )

        users.add(ctx.author.id)

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
