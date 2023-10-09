from __future__ import annotations

import typing
from typing import Optional

import discord
from discord.ext import commands

if typing.TYPE_CHECKING:
    from bot import ClusterBot


class Select(discord.ui.Select):
    async def callback(self, interaction):
        await interaction.response.defer()
        if self.view.message:
            await self.view.message.edit(view=None)
        self.view.result = self.values
        self.view.stop()
        if self.view.delete_after:
            await self.view.message.delete()


class SelectView(discord.ui.View):
    def __init__(self, ctx, *, options: typing.List[discord.SelectOption], timeout, delete_after) -> None:
        super().__init__(timeout=timeout)
        self.result = None
        self.ctx = ctx
        self.message = None
        self.delete_after = delete_after
        self.select = Select(options=options)
        self.add_item(self.select)

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


class ConfirmationButton(discord.ui.Button):
    def __init__(self, *, label: str, result: bool, style: discord.ButtonStyle):
        self.result = result
        super().__init__(label=label, style=style)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        if self.view.message:
            await self.view.message.edit(view=None)
        self.view.result = self.result
        self.view.stop()
        if self.view.delete_after:
            await self.view.message.delete()


class ConfirmationView(discord.ui.View):
    def __init__(
        self,
        ctx: PoketwoContext,
        *,
        timeout: int,
        delete_after: bool,
        delete_after_timeout: bool
    ) -> None:
        super().__init__(timeout=timeout)
        self.result = None
        self.ctx = ctx
        self.message = None
        self.delete_after = delete_after
        self.delete_after_timeout = delete_after_timeout

        self.add_items()

    async def interaction_check(self, interaction):
        if interaction.user.id not in {
            self.ctx.bot.owner_id,
            self.ctx.author.id,
            *self.ctx.bot.owner_ids,
        }:
            await interaction.response.send_message("You can't use this!", ephemeral=True)
            return False
        return True

    def add_items(self):
        """The method that adds the buttons. This needs to be implemented in subclasses in order to change labels."""
        self.add_item(ConfirmationButton(label="Confirm", result=True, style=discord.ButtonStyle.green))
        self.add_item(ConfirmationButton(label="Cancel", result=False, style=discord.ButtonStyle.red))

    async def on_timeout(self):
        if self.message:
            if self.delete_after_timeout:
                await self.message.delete()
            else:
                await self.message.edit(view=None)


class ConfirmationYesNoView(ConfirmationView):
    def add_items(self):
        self.add_item(ConfirmationButton(label="Yes", result=True, style=discord.ButtonStyle.green))
        self.add_item(ConfirmationButton(label="No", result=False, style=discord.ButtonStyle.red))


class RequestView(ConfirmationView):
    def __init__(
        self,
        *args,
        requestee: typing.Union[discord.User, discord.Member],
        **kwargs
    ) -> None:
        super().__init__(*args, **kwargs)
        self.requestee = requestee

    async def interaction_check(self, interaction):
        if interaction.user.id not in {
            self.ctx.bot.owner_id,
            self.requestee.id,
            *self.ctx.bot.owner_ids,
        }:
            await interaction.response.send_message("You can't use this!", ephemeral=True)
            return False
        return True

    def add_items(self):
        self.add_item(ConfirmationButton(label="Accept", result=True, style=discord.ButtonStyle.green))
        self.add_item(ConfirmationButton(label="Reject", result=False, style=discord.ButtonStyle.red))


class PoketwoContext(commands.Context):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.log = self.bot.log.bind(
            guild=self.guild and self.guild.name,
            guild_id=self.guild and self.guild.id,
            channel=self.guild and self.channel.name,
            channel_id=self.channel.id,
            user_id=self.author.id,
            user=str(self.author),
            message=self.message.content,
            message_id=self.message.id,
            command=self.command and self.command.qualified_name,
            command_args=self.args,
            command_kwargs=self.kwargs,
        )

    async def confirm(
        self,
        message: Optional[discord.Message] = None,
        *,
        file: Optional[discord.File] = None,
        embed: Optional[ClusterBot.Embed] = None,
        timeout: Optional[int] = 40,
        delete_after: Optional[bool] = False,
        delete_after_timeout: Optional[bool] = True,
        cls: Optional[ConfirmationView] = ConfirmationView
    ):
        view = cls(self, timeout=timeout, delete_after=delete_after, delete_after_timeout=delete_after_timeout)
        view.message = await self.send(
            message,
            file=file,
            embed=embed,
            view=view,
            allowed_mentions=discord.AllowedMentions.none(),
        )
        await view.wait()
        return view.result

    async def request(
        self,
        requestee: typing.Union[discord.User, discord.Member],
        message: Optional[str] = None,
        *,
        file: Optional[discord.File] = None,
        embed: Optional[discord.Embed] = None,
        timeout: Optional[int] = 40,
        delete_after: Optional[bool] = False,
        delete_after_timeout: Optional[bool] = False,
    ):
        view = RequestView(self, requestee=requestee, timeout=timeout, delete_after=delete_after, delete_after_timeout=delete_after_timeout)
        view.message = await self.send(
            message,
            file=file,
            embed=embed,
            view=view,
        )
        await view.wait()
        return view.result

    async def select(
        self,
        message=None,
        *,
        embed=None,
        timeout=40,
        options: typing.List[discord.SelectOption],
        delete_after=False,
        cls=SelectView
    ):
        view = cls(self, options=options, timeout=timeout, delete_after=delete_after)
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
