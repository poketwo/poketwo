from discord.ext import commands


def is_admin():
    return commands.check_any(commands.is_owner(), commands.has_permissions(administrator=True))


def has_started():
    async def predicate(ctx):
        member = await ctx.bot.mongo.Member.find_one({"id": ctx.author.id}, {"suspended": 1})

        if member is None:
            raise commands.CheckFailure(
                f"Please pick a starter pokémon by typing `{ctx.prefix}start` before using this command!"
            )

        if member.suspended:
            raise commands.CheckFailure("Your account has been suspended.")

        return True

    return commands.check(predicate)
