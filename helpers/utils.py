import typing
import discord

from dataclasses import dataclass


class FakeAvatar(typing.NamedTuple):
    url: str


class FakeUser(discord.Object):
    __slots__ = ()

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
