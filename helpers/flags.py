from discord.ext import commands, flags
from discord.ext.flags import *


class FlagCommand(flags.FlagCommand):
    @property
    def old_signature(self):
        if self.usage is not None:
            return self.usage

        params = self.clean_params
        if not params:
            return ""

        result = []
        for name, param in params.items():
            greedy = isinstance(param.annotation, commands.converter.Greedy)

            if param.default is not param.empty:
                # We don't want None or '' to trigger the [name=value] case and instead it should
                # do [name] since [name=None] or [name=] are not exactly useful for the user.
                should_print = param.default if isinstance(param.default, str) else param.default is not None
                if should_print:
                    result.append(
                        "[%s=%s]" % (name, param.default) if not greedy else "[%s=%s]..." % (name, param.default)
                    )
                    continue
                else:
                    result.append("[%s]" % name)

            elif param.kind == param.VAR_POSITIONAL:
                result.append("[%s...]" % name)
            elif greedy:
                result.append("[%s]..." % name)
            elif self._is_typing_optional(param.annotation):
                result.append("[%s]" % name)
            elif param.kind == param.VAR_KEYWORD:
                pass
            else:
                result.append("<%s>" % name)

        return " ".join(result)

    async def _parse_arguments(self, ctx):
        ctx.args = [ctx] if self.cog is None else [self.cog, ctx]
        ctx.kwargs = {}
        args = ctx.args
        kwargs = ctx.kwargs
        attachments = commands.core._AttachmentIterator(ctx.message.attachments)

        view = ctx.view
        iterator = iter(self.params.items())

        for name, param in iterator:
            if param.kind == param.POSITIONAL_OR_KEYWORD:
                transformed = await self.transform(ctx, param, attachments)
                args.append(transformed)
            elif param.kind == param.KEYWORD_ONLY:
                # kwarg only param denotes "consume rest" semantics
                if self.rest_is_raw:
                    converter = self._get_converter(param)
                    argument = view.read_rest()
                    kwargs[name] = await self.do_conversion(ctx, converter, argument, param)
                else:
                    kwargs[name] = await self.transform(ctx, param, attachments)
                break
            elif param.kind == param.VAR_POSITIONAL:
                while not view.eof:
                    try:
                        transformed = await self.transform(ctx, param, attachments)
                        args.append(transformed)
                    except RuntimeError:
                        break
            elif param.kind == param.VAR_KEYWORD:
                await self._parse_flag_arguments(ctx)
                break

        if not self.ignore_extra:
            if not view.eof:
                raise commands.TooManyArguments('Too many arguments passed to ' + self.qualified_name)


class FlagGroup(FlagCommand, commands.Group):
    pass


def command(**kwargs):
    def inner(func):
        cls = kwargs.get("cls", FlagCommand)
        return cls(func, **kwargs)

    return inner
