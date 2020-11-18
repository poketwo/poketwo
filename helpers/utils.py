import discord


class FakeUser(discord.Object):
    @property
    def avatar_url(self):
        return "https://cdn.discordapp.com/embed/avatars/0.png"

    @property
    def mention(self):
        return "<@{0.id}>".format(self)

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
