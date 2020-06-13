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
                raise MustHaveStarted

        users.add(ctx.author.id)

        return True

    return commands.check(predicate)


class ShuttingDown(commands.CheckFailure):
    pass


def accepting_commands(bot):
    async def predicate(ctx: commands.Context):
        if not bot.accepting_commands:
            raise ShuttingDown(
                "Sorry, you can't do that right now! The bot is either restarting for updates or has been manually stopped by the developer for another reason. Please try again later."
            )

        return True

    return predicate
