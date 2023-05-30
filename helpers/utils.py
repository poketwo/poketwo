import io
import math
from dataclasses import dataclass

import discord


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


def make_slider(bot, progress):
    func = math.ceil if progress < 0.5 else math.floor
    bars = min(func(progress * 10), 10)
    first, last = bars > 0, bars == 10
    mid = bars - (1 if last else 0) - (1 if first else 0)

    ret = bot.sprites.slider_start_full if first else bot.sprites.slider_start_empty
    ret += mid * bot.sprites.slider_mid_full
    ret += (8 - mid) * bot.sprites.slider_mid_empty
    ret += bot.sprites.slider_end_full if last else bot.sprites.slider_end_empty

    return ret
