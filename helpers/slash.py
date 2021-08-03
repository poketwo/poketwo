from __future__ import annotations

from collections import OrderedDict
from inspect import Parameter
from typing import Any, Literal, Optional, Union, get_args, get_origin

import discord
from discord.ext import commands, flags

from helpers.constants import SLASH_COMMAND_CONVERTER_TYPES


class SlashCommandOption:
    def __init__(
        self,
        name: str,
        description: str,
        required: bool,
        type: int,
        choices: Optional[Any] = None,
        *,
        _param: Parameter = None,
        _converter: Any = None,
        _greedy: bool = False,
    ):
        self.name = name
        self.description = description[:100]
        self.required = required
        self.type = type
        self.choices = choices
        self._param = _param
        self._converter = _converter
        self._greedy = _greedy

    @classmethod
    def from_param(cls, name: str, param: Parameter):
        kwargs = dict(name=name, description=name, required=True, _param=param)
        annotation = param.annotation
        if isinstance(annotation, commands.Greedy):
            kwargs["_greedy"] = True
            annotation = annotation.converter

        origin = get_origin(annotation)
        args = get_args(annotation)

        if origin is Union:
            if args[-1] is type(None):
                kwargs["required"] = False
                *args, _ = args
            if len(args) == 1:
                annotation = args[0]
                origin = get_origin(annotation)
                args = get_args(annotation)
            else:
                raise NotImplementedError("Union is not yet implemented")

        if origin is Literal:
            kwargs["choices"] = args
            annotation = type(args[0])
            if len(set(type(x) for x in args)) != 1:
                raise ValueError("Literal must be all the same type")

        if param.kind is param.VAR_KEYWORD:
            raise NotImplementedError("Variadic kwargs are not yet implemented")

        if param.default is not param.empty:
            kwargs["required"] = False

        if annotation is param.empty:
            annotation = str

        try:
            kwargs["type"] = SLASH_COMMAND_CONVERTER_TYPES[annotation]
        except KeyError:
            kwargs["type"] = SLASH_COMMAND_CONVERTER_TYPES[str]
            kwargs["_converter"] = annotation

        return cls(**kwargs)

    def to_json(self):
        base = {
            "name": self.name,
            "description": self.description,
            "required": self.required,
            "type": self.type,
        }
        if self.choices is not None:
            base["choices"] = self.choices
        return base

    def copy(self):
        return self.__class__(
            self.name,
            self.description,
            self.required,
            self.type,
            self.choices,
            _param=self._param,
            _converter=self._converter,
            _greedy=self._greedy,
        )


class SlashGroup:
    pass


class SlashCommand:
    def __init__(
        self,
        name: str,
        description: str,
        options: list[SlashCommandOption],
        *,
        parent: SlashGroup = None,
        command: commands.Command = None,
    ):
        self.name = name
        self.description = description
        self.parent = parent
        self._options = options
        self.command = command

    def get_options(self):
        opts = self._options
        if self.command.cog:
            opts = opts[1:]
        return OrderedDict([(x.name, x) for x in opts])

    def __str__(self):
        return self.name

    def __repr__(self):
        return f"<{self.__class__.__name__} name={self.name!r} options={self.get_options()!r}>"

    def to_json(self):
        base = {
            "name": self.name,
            "description": self.description,
        }
        opts = self.get_options()
        if len(opts) > 0:
            base["options"] = [x.to_json() for x in opts.values()]
        return base

    def copy(self):
        return self.__class__(
            self.name,
            self.description,
            [x.copy() for x in self._options],
            parent=self.parent,
            command=self.command,
        )

    async def _parse_arguments(self, ctx: SlashContext):
        ctx.args = [ctx] if self.command.cog is None else [self.command.cog, ctx]
        ctx.kwargs = {}

        options = {x["name"]: x for x in ctx.interaction.data.get("options", [])}

        for name, option in self.get_options().items():
            param = option._param

            try:
                val = options[name]
            except KeyError:
                val = [param.default]
            else:
                val = [val["value"]]
                if param.kind == param.VAR_POSITIONAL or option._greedy:
                    val = val[0].split()

                if option._converter is not None:
                    val = [
                        await commands.run_converters(ctx, option._converter, x, param) for x in val
                    ]

            if param.kind == param.VAR_POSITIONAL:
                ctx.args.extend(val)
            elif option._greedy:
                ctx.args.append(val)
            elif param.kind in (param.POSITIONAL_OR_KEYWORD, param.POSITIONAL_ONLY):
                ctx.args.append(val[0])
            elif param.kind == param.KEYWORD_ONLY:
                ctx.kwargs[name] = val[0]

    async def __call__(self, ctx: SlashContext):
        await self._parse_arguments(ctx)
        ctx.bot.dispatch("command", ctx)

        print("command", ctx.command, ctx.args, ctx.kwargs)

        try:
            if await self.command.can_run(ctx):
                await self.command.callback(*ctx.args, **ctx.kwargs)
            else:
                raise commands.CheckFailure("The global check once functions failed.")
        except commands.CommandError as exc:
            await ctx.command.dispatch_error(ctx, exc)
        else:
            ctx.bot.dispatch("command_completion", ctx)


class CommandWithSlashCommand(commands.Command):
    def __init__(self, func, *, slash_command: SlashCommand, **kwargs):
        super().__init__(func, **kwargs)
        self.slash_command = slash_command

    @classmethod
    def from_command(cls, command: commands.Command, slash_command: SlashCommand):
        ret = cls(command.callback, **command.__original_kwargs__, slash_command=slash_command)
        return command._ensure_assignment_on_copy(ret)

    def _ensure_assignment_on_copy(self, other):
        other = super()._ensure_assignment_on_copy(other)
        try:
            other.slash_command = self.slash_command.copy()
            other.slash_command.command = other
        except AttributeError:
            pass
        return other


class SlashMessage(discord.Message):
    def __init__(self, bot: commands.Bot, interaction: discord.Interaction):
        self._state = bot._get_state()
        self.id = int(interaction.id)
        self.author = interaction.user
        self.webhook_id = None
        self.reactions = []
        self.attachments = []
        self.embeds = []
        self.application = None
        self.activity = None
        self.channel = interaction.channel
        self._edited_timestamp = None
        self.type = discord.MessageType.default
        self.pinned = False
        self.flags = discord.MessageFlags._from_value(0)
        self.mention_everyone = False
        self.tts = False
        self.content = None
        self.nonce = None
        self.stickers = []
        self.components = []

    @property
    def guild(self):
        return self.channel.guild


class SlashContext(commands.Context):
    # self.message = attrs.pop('message', None)
    # self.bot = attrs.pop('bot', None)
    # self.args = attrs.pop('args', [])
    # self.kwargs = attrs.pop('kwargs', {})
    # self.prefix = attrs.pop('prefix')
    # self.command = attrs.pop('command', None)
    # self.view = attrs.pop('view', None)
    # self.invoked_with = attrs.pop('invoked_with', None)
    # self.invoked_parents = attrs.pop('invoked_parents', [])
    # self.invoked_subcommand = attrs.pop('invoked_subcommand', None)
    # self.subcommand_passed = attrs.pop('subcommand_passed', None)
    # self.command_failed = attrs.pop('command_failed', False)
    # self.current_parameter = attrs.pop('current_parameter', None)
    # self._state = self.message._state

    def __init__(self, **attrs):
        self.interaction: discord.Interaction = attrs.pop("interaction")
        self.slash_command: SlashCommand = attrs.pop("slash_command")
        super().__init__(**attrs)
        self.invoked_with = self.slash_command.name

    @classmethod
    def build_from_interaction(
        cls,
        bot: commands.Bot,
        interaction: discord.Interaction,
        slash_cmd: SlashCommand,
    ):
        return cls(
            bot=bot,
            prefix="/",
            command=slash_cmd.command,
            message=SlashMessage(bot, interaction),
            interaction=interaction,
            slash_command=slash_cmd,
        )

    async def send(self, *args, **kwargs):
        if self.interaction.response.is_done():
            kwargs.pop("nonce", None)
            kwargs.pop("delete_after", None)
            kwargs.pop("reference", None)
            kwargs.pop("mention_author", None)
            kwargs.pop("stickers", None)
            return await self.interaction.followup.send(*args, **kwargs)

        kwargs = {
            key: value
            for key, value in kwargs.items()
            if key in ("content", "embed", "embeds", "tts", "view", "ephemeral")
        }
        await self.interaction.response.send_message(*args, **kwargs)
        return await self.interaction.original_message()


def with_slash_command(*, name: str = None, description: str = None):
    def wrapper(command: commands.Command):
        if isinstance(command, flags.FlagCommand):
            raise NotImplementedError("Flag commands are not yet implemented")

        options = [SlashCommandOption.from_param(*x) for x in command.clean_params.items()]

        # Make sure no optional arguments before required ones
        required = False
        for option in reversed(options):
            if required:
                option.required = True
            if option.required:
                required = True

        slash_command = SlashCommand(
            name=name or command.name,
            description=description or command.help or "No help found",
            options=options,
            command=command,
        )

        return CommandWithSlashCommand.from_command(command, slash_command)

    return wrapper
