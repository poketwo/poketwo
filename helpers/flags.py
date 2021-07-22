from discord.ext import commands
from discord.ext.flags import *

class FlagCommand(FlagCommand):
    @property
    def old_signature(self):
        if self.usage is not None:
            return self.usage

        params = self.clean_params
        if not params:
            return ''

        result = []
        for name, param in params.items():
            greedy = isinstance(param.annotation, commands.converter.Greedy)

            if param.default is not param.empty:
                # We don't want None or '' to trigger the [name=value] case and instead it should
                # do [name] since [name=None] or [name=] are not exactly useful for the user.
                should_print = param.default if isinstance(param.default, str)else param.default is not None
                if should_print:
                    result.append('[%s=%s]' % (name, param.default) if not greedy else
                                  '[%s=%s]...' % (name, param.default))
                    continue
                else:
                    result.append('[%s]' % name)

            elif param.kind == param.VAR_POSITIONAL:
                result.append('[%s...]' % name)
            elif greedy:
                result.append('[%s]...' % name)
            elif self._is_typing_optional(param.annotation):
                result.append('[%s]' % name)
            elif param.kind == param.VAR_KEYWORD:
                pass
            else:
                result.append('<%s>' % name)

        return ' '.join(result)

def command(**kwargs):
    def inner(func):
        cls = kwargs.get('cls', FlagCommand)
        return cls(func, **kwargs)
    return inner 
