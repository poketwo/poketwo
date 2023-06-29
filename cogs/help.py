import itertools
import math

from discord.ext import commands
from helpers import flags, pagination


class CustomHelpCommand(commands.HelpCommand):
    async def on_help_command_error(self, ctx, error):
        if isinstance(error, commands.CommandInvokeError):
            await ctx.send(str(error.original))

    def resolve_command_help(self, command: commands.Command) -> str:
        """Resolve a command's help message using Fluent, falling back to the
        command's docstring."""
        resolved_help = command.help

        kebab_command_name = command.qualified_name.replace(" ", "-")
        message_id = f"command-{kebab_command_name}-help.help"
        try:
            resolved_help = self.context._(message_id)
        except KeyError:
            self.context.bot.log.warn(
                "command is missing a help string in Fluent", command=command.qualified_name, message_id=message_id
            )

        if resolved_help:
            if command.description:
                resolved_help = command.description + "\n\n" + resolved_help
        else:
            resolved_help = self.context._("help-not-found")

        return resolved_help

    def resolve_cog_description(self, cog: commands.Cog) -> str:
        """Resolve a cog's description using Fluent, falling back to the cog's
        docstring."""
        description = cog.description

        try:
            # Replacing spaces with dashes might be useless here since all of
            # Pokétwo's cogs have single-word names, but we'll do it anyways just
            # in case.
            message_id = f'cog-{cog.qualified_name.lower().replace(" ", "-")}-help.description'
            description = self.context._(message_id)
        except KeyError:
            self.context.bot.log.warn("cog is missing a description string in Fluent", cog=cog.qualified_name)

        if not description:
            description = self.context._("categories-no-description")

        return description

    def make_page_embed(self, commands, title, description=None):
        embed = self.context.bot.Embed(color=0xFE9AC9, title=title, description=description)
        embed.set_footer(text=self.context._("help-command-command-cta"))

        for command in commands:
            signature = f"{self.context.clean_prefix}{command.qualified_name} "

            # If the command takes flags, add a textual affordance to let the
            # user know.
            signature += (
                self.context._("command-signature-flags")
                if isinstance(command, flags.FlagCommand)
                else command.signature
            )

            embed.add_field(
                name=signature,
                value=self.resolve_command_help(command),
                inline=False,
            )

        return embed

    def make_default_embed(self, cogs, title, description=None):
        embed = self.context.bot.Embed(color=0xFE9AC9, title=title, description=description)

        counter = 0
        for cog in cogs:
            cog, description, command_list = cog

            command_list = "".join(f"`{command.qualified_name}` " for command in command_list)
            if cog is None:
                embed_description = command_list
            else:
                embed_description = f"{self.resolve_cog_description(cog)}\n{command_list}"
            embed.add_field(name=cog.qualified_name, value=embed_description, inline=False)
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
            description = cog is not None and self.resolve_cog_description(cog) or None
            embed_pages.append((cog, description, commands))

        async def get_page(source, menu, pidx):
            cogs = embed_pages[min(len(embed_pages) - 1, pidx * 6) : min(len(embed_pages) - 1, pidx * 6 + 6)]

            embed = self.make_default_embed(
                cogs,
                title=self.context._("bot-help-embed.title", current=pidx + 1, max=len(embed_pages) // 6 + 1),
                description=(
                    self.context._("help-command-command-cta") + "\n" + self.context._("help-command-category-cta")
                ),
            )

            return embed

        pages = pagination.ContinuablePages(pagination.FunctionPageSource(math.ceil(len(embed_pages) / 6), get_page))
        ctx.bot.menus[ctx.author.id] = pages
        await pages.start(ctx)

    async def send_cog_help(self, cog):
        ctx = self.context
        ctx.invoked_with = "help"
        bot = ctx.bot

        filtered = await self.filter_commands(cog.get_commands(), sort=True)

        qualified_name = cog and cog.qualified_name or ctx._("cog-fallback-name")
        embed = self.make_page_embed(
            filtered,
            title=ctx._("cog-embed.title", cog=qualified_name),
            description=None if cog is None else cog.description,
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
            [group, *filtered],
            title=group.qualified_name,
            description=self.resolve_command_help(group),
        )

        await ctx.send(embed=embed)

    async def send_command_help(self, command):
        embed = self.context.bot.Embed(color=0xFE9AC9, title=f"{self.context.clean_prefix}{command.qualified_name}")

        help = self.resolve_command_help(command)
        embed.description = help

        embed.add_field(name=self.context._("command-embed-signature"), value=self.get_command_signature(command))

        await self.context.send(embed=embed)


async def setup(bot):
    bot.old_help_command = bot.help_command
    bot.help_command = CustomHelpCommand()


async def teardown(bot):
    bot.help_command = bot.old_help_command
