import itertools
import math

import discord
from discord.ext import commands, flags
from helpers import pagination


class CustomHelpCommand(commands.HelpCommand):
    def __init__(self):
        super().__init__(
            command_attrs={"help": "Show help about the bot, a command, or a category."}
        )

    async def on_help_command_error(self, ctx, error):
        if isinstance(error, commands.CommandInvokeError):
            await ctx.send(str(error.original))

    def make_page_embed(self, commands, title="Pokétwo Help", description=discord.Embed.Empty):
        embed = self.context.bot.Embed(color=0x9CCFFF)
        embed.title = title
        embed.description = description
        embed.set_footer(text=f'Use "{self.clean_prefix}help command" for more info on a command.')

        for command in commands:
            signature = self.clean_prefix + command.qualified_name + " "

            signature += (
                "[args...]" if isinstance(command, flags.FlagCommand) else command.signature
            )

            embed.add_field(
                name=signature,
                value=command.help or "No help found...",
                inline=False,
            )

        return embed

    def make_default_embed(self, cogs, title="Pokétwo Categories", description=discord.Embed.Empty):
        embed = self.context.bot.Embed(color=0x9CCFFF)
        embed.title = title
        embed.description = description

        counter = 0
        for cog in cogs:
            cog, description, command_list = cog
            description = f"{description or 'No Description'} \n {''.join([f'`{command.qualified_name}` ' for command in command_list])}"
            embed.add_field(name=cog.qualified_name, value=description, inline=False)
            counter += 1

        return embed

    async def send_bot_help(self, mapping):
        ctx = self.context
        ctx.invoked_with = "help"
        bot = ctx.bot

        def get_category(command):
            cog = command.cog
            return cog.qualified_name if cog is not None else "\u200bNo Category"

        embed_pages = []
        total = 0

        filtered = await self.filter_commands(bot.commands, sort=True, key=get_category)

        for cog_name, commands in itertools.groupby(filtered, key=get_category):
            commands = sorted(commands, key=lambda c: c.name)

            if len(commands) == 0:
                continue

            total += len(commands)
            cog = bot.get_cog(cog_name)
            description = (
                (cog and cog.description)
                if (cog and cog.description) is not None
                else discord.Embed.Empty
            )
            embed_pages.append((cog, description, commands))

        async def get_page(source, menu, pidx):
            cogs = embed_pages[
                min(len(embed_pages) - 1, pidx * 6) : min(len(embed_pages) - 1, pidx * 6 + 6)
            ]

            embed = self.make_default_embed(
                cogs,
                title=f"Pokétwo Command Categories (Page {pidx+1}/{len(embed_pages)//6+1})",
                description=(
                    f"Use `{self.clean_prefix}help <command>` for more info on a command.\n"
                    f"Use `{self.clean_prefix}help <category>` for more info on a category."
                ),
            )

            return embed

        pages = pagination.ContinuablePages(
            pagination.FunctionPageSource(math.ceil(len(embed_pages) / 6), get_page)
        )
        ctx.bot.menus[ctx.author.id] = pages
        await pages.start(ctx)

    async def send_cog_help(self, cog):
        ctx = self.context
        ctx.invoked_with = "help"
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
        ctx.invoked_with = "help"
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
        embed = self.context.bot.Embed(color=0x9CCFFF)
        embed.title = self.clean_prefix + command.qualified_name

        if command.description:
            embed.description = f"{command.description}\n\n{command.help}"
        else:
            embed.description = command.help or "No help found..."

        embed.add_field(name="Signature", value=self.get_command_signature(command))

        await self.context.send(embed=embed)


def setup(bot):
    bot.old_help_command = bot.help_command
    bot.help_command = CustomHelpCommand()


def teardown(bot):
    bot.help_command = bot.old_help_command
