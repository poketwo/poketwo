import itertools

import discord
from discord.ext import commands, flags
from bot import ClusterBot
from helpers import pagination


class CustomHelpCommand(commands.HelpCommand):
    def __init__(self):
        super().__init__(
            command_attrs={"help": "Show help about the bot, a command, or a category."}
        )

    async def on_help_command_error(self, ctx, error):
        if isinstance(error, commands.CommandInvokeError):
            await ctx.send(str(error.original))

    def make_page_embed(
        self, commands, title="Pokétwo Help", description=discord.Embed.Empty
    ):
        embed = self.context.bot.Embed()
        embed.title = title
        embed.description = description
        embed.set_footer(
            text=f'Use "{self.clean_prefix}help command" for more info on a command.'
        )

        for command in commands:
            signature = self.clean_prefix + command.qualified_name + " "

            signature += (
                "[args...]"
                if isinstance(command, flags.FlagCommand)
                else command.signature
            )

            embed.add_field(
                name=signature, value=command.help or "No help found...", inline=False,
            )

        return embed

    async def send_bot_help(self, mapping):
        ctx = self.context
        bot = ctx.bot

        def get_category(command):
            cog = command.cog
            return cog.qualified_name if cog is not None else "\u200bNo Category"

        pages = []
        total = 0

        filtered = await self.filter_commands(bot.commands, sort=True, key=get_category)

        for cog_name, commands in itertools.groupby(filtered, key=get_category):
            commands = sorted(commands, key=lambda c: c.name)

            if len(commands) == 0:
                continue

            total += len(commands)
            cog = bot.get_cog(cog_name)
            description = (cog and cog.description) or discord.Embed.Empty
            pages.append((cog, description, commands))

        async def get_page(pidx, clear):
            cog, description, commands = pages[pidx]

            embed = self.make_page_embed(
                commands,
                title=(cog and cog.qualified_name or "Other") + " Commands",
                description=discord.Embed.Empty if cog is None else cog.description,
            )
            embed.set_author(name=f"Page {pidx + 1}/{len(pages)} ({total} commands)")

            return embed

        paginator = pagination.Paginator(get_page, len(pages))
        await paginator.send(bot, ctx, 0)

    async def send_cog_help(self, cog):
        ctx = self.context
        bot = ctx.bot

        filtered = await self.filter_commands(cog.get_commands(), sort=True)

        embed = self.make_page_embed(
            filtered,
            title=(cog and cog.qualified_name or "Other") + " Commands",
            description=discord.Embed.Empty if cog is None else cog.description,
        )

        await ctx.send(embed=embed)

    async def send_group_help(self, group):
        ctx = self.context
        bot = ctx.bot

        subcommands = group.commands
        if len(subcommands) == 0:
            return await self.send_command_help(group)

        filtered = await self.filter_commands(subcommands, sort=True)

        embed = self.make_page_embed(
            filtered,
            title=group.qualified_name,
            description=f"{group.description}\n\n{group.help}"
            if group.description
            else group.help or "No help found...",
        )

        await ctx.send(embed=embed)

    async def send_command_help(self, command):
        embed = self.context.bot.Embed()
        embed.title = self.clean_prefix + command.qualified_name

        if command.description:
            embed.description = f"{command.description}\n\n{command.help}"
        else:
            embed.description = command.help or "No help found..."

        embed.add_field(name="Signature", value=self.get_command_signature(command))

        await self.context.send(embed=embed)


def setup(bot: ClusterBot):
    bot.old_help_command = bot.help_command
    bot.help_command = CustomHelpCommand()


def teardown(bot: ClusterBot):
    bot.help_command = bot.old_help_command
