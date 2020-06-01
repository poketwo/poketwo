from discord.ext import commands
from mongoengine import DoesNotExist

from . import mongo


class MustHaveStarted(commands.CheckFailure):
    pass


def is_admin():
    return commands.check_any(
        commands.is_owner(), commands.has_permissions(administrator=True)
    )


def has_started():
    async def predicate(ctx: commands.Context):
        try:
            mongo.Member.objects.get(id=ctx.author.id)
            return True
        except DoesNotExist:
            raise MustHaveStarted(
                "Please pick a starter pokémon by typing `p!start` before using this command!"
            )

    return commands.check(predicate)
