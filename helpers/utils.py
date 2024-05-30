from __future__ import annotations

import io
import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, Dict, Iterable, List, Optional

import discord

from helpers.constants import CharacterLimits

if TYPE_CHECKING:
    from bot import ClusterBot


@dataclass
class FakeAvatar:
    url: str


class FakeUser(discord.Object):
    @property
    def avatar(self):
        return FakeAvatar("https://cdn.discordapp.com/embed/avatars/0.png")

    @property
    def mention(self):
        return f"<@{self.id}>"

    @property
    def roles(self):
        return []

    def __str__(self):
        return str(self.id)

    async def send(self, *args, **kwargs):
        pass

    async def add_roles(self, *args, **kwargs):
        pass

    async def remove_roles(self, *args, **kwargs):
        pass


def write_fp(data):
    arr = io.BytesIO()
    arr.write(data)
    arr.seek(0)
    return arr


def make_slider(bot, progress: float, length: Optional[int] = 10, return_list: Optional[bool] = False) -> str | List[str]:
    func = math.ceil if progress < 0.5 else math.floor
    bars = min(func(progress * length), length)
    first, last = bars > 0, bars == length
    mid = bars - (1 if last else 0) - (1 if first else 0)

    ret = [bot.sprites.slider_start_full if first else bot.sprites.slider_start_empty]
    ret.extend(mid * [bot.sprites.slider_mid_full])
    ret.extend((length - 2 - mid) * [bot.sprites.slider_mid_empty])
    ret.append(bot.sprites.slider_end_full if last else bot.sprites.slider_end_empty)

    return ret if return_list else "".join(ret)


def unwind(dictionary: Dict[tuple, Any], *, include_values: Optional[bool] = False):
    """Unwinds a dictionary with tuples keys, returning a dictionary where each tuple element is assigned to their respective values"""

    result = {key: value for tuple, value in dictionary.items() for key in tuple}
    # If include_values is true, add each item's value as a key aswell.
    # Useful for shortcutting items to include the original key
    if include_values is True:
        result.update({v: v for k, v in dictionary.items()})

    return result


@dataclass
class FlavorString:
    string: str
    emoji: Optional[str] = None
    plural: Optional[str] = None
    default_plural: Optional[bool] = False

    def __post_init__(self):
        self.plural = self.plural or f"{self.string}s"

    def __format__(self, format_spec) -> str:
        val = self.string
        emoji = self.emoji

        # Whether to use plural
        if "s" in format_spec or (self.default_plural and "!s" not in format_spec):
            val = self.plural

        # Whether to not show emoji
        if "!e" not in format_spec and emoji is not None:
            val = f"{emoji} {val}"

        # Whether to bold
        if "b" in format_spec:
            val = f"**{val}**"

        return val

    def __str__(self) -> str:
        return f"{self}"

    def __repr__(self) -> str:
        return self.__str__()


def add_moves_field(moves: list, embed: ClusterBot.Embed, bot: ClusterBot):
    embed.add_field(
        name="Current Moves",
        value="No Moves" if len(moves) == 0 else "\n".join(bot.data.move_by_number(x).name for x in moves),
    )


def unique(iterable: Iterable, key: Optional[Callable] = lambda x: x) -> list:
    """Get a list of unique elements, based on provided key if given"""

    _dict = {}
    for item in iterable:
        k = key(item)
        if k in _dict:
            continue
        _dict[k] = item

    return list(_dict.values())


def ordinal_indicator(number: int) -> str:
    return {"1": "st", "2": "nd", "3": "rd"}.get(str(number)[-1], "th")


def build_channels_message(
    base_text: str,
    channels: List[discord.TextChannel | discord.Thread],
    *,
    see_all_tip: Optional[str] = "",
) -> str:
    """
    Forms message with a list of channels. If it exceeds character limit, it shows the number of channels instead.
    `base_text` must have a formatting key `channels` where the channels text will be interpolated.
    """

    message = base_text.format_map(dict(channels=", ".join(f"<#{x.id}>" for x in channels)))
    if len(message) > CharacterLimits.MESSAGE_CONTENT.value or len(channels) == 0:
        message = base_text.format_map(dict(channels=f"{len(channels)} channel{'' if len(channels) == 1 else 's'}"))
        if see_all_tip:
            message += f" {see_all_tip}"

    return message
