import typing

import discord
import structlog
from discord.ext import commands


class Select(discord.ui.Select):
    async def callback(self, interaction):
        await interaction.response.defer()
        if self.view.message:
            await self.view.message.edit(view=None)
        self.view.result = self.values
        await self.view.stop()


class SelectView(discord.ui.View):
    def __init__(self, ctx, *, options: typing.List[discord.SelectOption], timeout) -> None:
        super().__init__(timeout=timeout)
        self.result = None
        self.ctx = ctx
        self.message = None
        self.add_item(Select(options=options))

    async def interaction_check(self, interaction):
        if interaction.user.id not in {
            self.ctx.bot.owner_id,
            self.ctx.author.id,
            *self.ctx.bot.owner_ids,
        }:
            await interaction.response.send_message("You can't use this!", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        if self.message:
            await self.message.delete()


class ConfirmationView(discord.ui.View):
    def __init__(self, ctx, *, timeout) -> None:
        super().__init__(timeout=timeout)
        self.result = None
        self.ctx = ctx
        self.message = None

    async def interaction_check(self, interaction):
        if interaction.user.id not in {
            self.ctx.bot.owner_id,
            self.ctx.author.id,
            *self.ctx.bot.owner_ids,
        }:
            await interaction.response.send_message("You can't use this!", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.green)
    async def confirm(self, interaction, button):
        await interaction.response.defer()
        if self.message:
            await self.message.edit(view=None)
        self.result = True
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.red)
    async def cancel(self, interaction, button):
        await interaction.response.defer()
        if self.message:
            await self.message.edit(view=None)
        self.result = False
        self.stop()

    async def on_timeout(self):
        if self.message:
            await self.message.delete()


class PoketwoContext(commands.Context):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.log = self.bot.log.bind(
            guild=self.guild and self.guild.name,
            guild_id=self.guild and self.guild.id,
            channel=self.channel.name,
            channel_id=self.channel.id,
            user_id=self.author.id,
            user=str(self.author),
            message=self.message.content,
            message_id=self.message.id,
            command=self.command and self.command.qualified_name,
            command_args=self.args,
            command_kwargs=self.kwargs,
        )

    async def confirm(self, message=None, *, embed=None, timeout=40, cls=ConfirmationView):
        view = cls(self, timeout=timeout)
        view.message = await self.send(
            message,
            embed=embed,
            view=view,
            allowed_mentions=discord.AllowedMentions.none(),
        )
        await view.wait()
        return view.result

    async def select(
        self, message=None, *, embed=None, timeout=40, options: typing.List[discord.SelectOption], cls=SelectView
    ):
        view = cls(self, options=options, timeout=timeout)
        view.message = await self.send(
            message,
            embed=embed,
            view=view,
            allowed_mentions=discord.AllowedMentions.none(),
        )
        await view.wait()
        return view.result

    @property
    def clean_prefix(self) -> str:
        return super().clean_prefix.strip() + " "
