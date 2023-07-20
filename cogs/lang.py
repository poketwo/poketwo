__all__ = ("Lang", "setup")

from typing import Any, Tuple, cast

from discord.ext import commands
from fluent.runtime import FluentResourceLoader, FluentLocalization, FluentBundle
from fluent.runtime.resolver import Message
import structlog

# The listing of all Fluent localization files to load.
FLUENT_FILES = (
    "main.ftl",
    "help.ftl",
    "cogs.ftl",
    "commands.ftl",
    "errors.ftl",
    "shop.ftl",
    "pokemon.ftl",
)


class Fluent(FluentLocalization):
    """A subclass of ``python-fluent``'s ``FluentLocalization`` class that
    enables quick message attribute lookups via dot syntax (like
    ``message.attribute``). This isn't normally possible with the base class
    implementation.
    """

    _log: structlog.BoundLogger = structlog.get_logger()

    def get_message(self, msg_id: str) -> Tuple[Message, FluentBundle] | None:
        """Looks up a message by ID from all bundles.

        Returns ``None`` if the message wasn't found.
        """
        for bundle in self._bundles():
            if not bundle.has_message(msg_id):
                continue

            return (bundle.get_message(msg_id), bundle)

    def format_value(self, msg_id: str, args: dict[str, Any] | None = None) -> str:
        """Looks up a message by ID from all bundles, supporting dotted access
        for attributes.

        Passing variables into the message can be achieved via the ``args``
        parameter.

        If the message wasn't found, then the message ID itself is returned.
        """
        base_msg_id = msg_id
        attribute_name: str | None = None
        if "." in msg_id:
            base_msg_id, attribute_name = msg_id.split(".")

        for bundle in self._bundles():
            if not bundle.has_message(base_msg_id):
                continue

            msg = bundle.get_message(base_msg_id)

            value = msg.value
            if attribute_name is not None:
                value = msg.attributes[attribute_name]

            if not value:
                continue

            val, errors = bundle.format_pattern(value, args)

            if errors:
                self._log.error("fluent error", errors=errors)
                continue

            return cast(str, val)
        return msg_id


class Lang(commands.Cog):
    """Handles user-facing message localization."""

    def _fluent_command(self, command: str) -> str:
        """A function exposed to Fluent localizations that returns a command
        formatted as an inline code segment.
        """
        # XXX: This is implemented here and not in Fluent itself for flexibility
        # reasons; a future iteration of this might want to format the result
        # dynamically in a way that Fluent won't be able to express.
        return f"`{self._last_known_prefix}{command}`"

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._fluent_loader = FluentResourceLoader(bot.config.LANG_ROOT)
        self.fluent = Fluent(
            ["en-US"], list(FLUENT_FILES), self._fluent_loader, functions={"COMMAND": self._fluent_command}
        )
        self._last_known_prefix: str | None = "@Pokétwo "


async def setup(bot: commands.Bot):
    await bot.add_cog(Lang(bot))
