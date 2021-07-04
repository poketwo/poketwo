from discord.ext import commands


class NotStarted(commands.CheckFailure):
    pass


class Suspended(commands.CheckFailure):
    def __init__(self, reason, *args):
        super().__init__(*args)
        self.reason = reason


def is_admin():
    return commands.check_any(commands.is_owner(), commands.has_permissions(administrator=True))


def has_started():
    async def predicate(ctx):
        member = await ctx.bot.mongo.Member.find_one(
            {"id": ctx.author.id}, {"suspended": 1, "suspension_reason": 1}
        )

        if member is None:
            raise NotStarted(
                f"Please pick a starter pokémon by typing `{ctx.prefix}start` before using this command!"
            )

        if member.suspended:
            raise Suspended(member.suspension_reason)

        return True

    return commands.check(predicate)
