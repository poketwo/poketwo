from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

import discord
from discord.ext import commands

from helpers.context import PoketwoContext


class ViewTermsOfServiceView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=0)
        self.add_item(discord.ui.Button(label="View Terms", url="https://poketwo.net/terms"))


class ConfirmTermsOfServiceView(discord.ui.View):
    def __init__(self, ctx, *, timeout=120, **kwargs) -> None:
        super().__init__(timeout=timeout)
        self.result = None
        self.ctx = ctx
        self.message = None
        self.add_item(discord.ui.Button(label="View Terms", url="https://poketwo.net/terms"))

    async def interaction_check(self, interaction):
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("You can't use this!", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Accept", style=discord.ButtonStyle.green)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.message:
            return
        self.result = True
        await interaction.response.defer()
        await self.message.edit(view=ViewTermsOfServiceView())
        self.stop()

    @discord.ui.button(label="Decline", style=discord.ButtonStyle.red)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.result = False
        await interaction.response.defer()
        await self.message.edit(view=ViewTermsOfServiceView())
        self.stop()

    async def on_timeout(self):
        if self.message:
            await self.message.edit(view=ViewTermsOfServiceView())


class ConfirmUpdatedTermsOfServiceView(discord.ui.View):
    def __init__(self, ctx, *, timeout=120, **kwargs) -> None:
        super().__init__(timeout=timeout)
        self.ctx = ctx
        self.message = None
        self.add_item(discord.ui.Button(label="View Terms", url="https://poketwo.net/terms"))

    async def interaction_check(self, interaction):
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("You can't use this!", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Accept", style=discord.ButtonStyle.green)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.message:
            return
        await self.ctx.bot.mongo.update_member(interaction.user, {"$set": {"tos": datetime.utcnow()}})
        await interaction.response.send_message(
            "Thank you for accepting our updated Terms of Service. You may now continue using Pokétwo.",
            ephemeral=True,
        )
        await self.message.edit(view=ViewTermsOfServiceView())

    @discord.ui.button(label="Decline", style=discord.ButtonStyle.red)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            "Since you chose not to accept the new user terms, we are unable to grant you access to Pokétwo.\n"
            "If you wish to continue, please run any command and agree to our updated Terms of Service to continue.",
            ephemeral=True,
        )
        await self.message.edit(view=ViewTermsOfServiceView())

    async def on_timeout(self):
        if self.message:
            await self.message.edit(view=ViewTermsOfServiceView())


@dataclass
class CommandInvocation:
    label: str
    command: commands.Command
    args: Optional[list] = None
    kwargs: Optional[dict] = None
    description: Optional[str] = None


class CommandInvokeSelectMenu(discord.ui.Select):
    def __init__(self, command_invocations: List[CommandInvocation], *args, **kwargs):
        self.command_invocations = command_invocations

        options = [
            discord.SelectOption(
                label=invocation.label,
                value=str(i),
                description=invocation.description,
            )
            for i, invocation in enumerate(command_invocations)
        ]
        super().__init__(options=options, *args, **kwargs)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        invocation = self.command_invocations[int(self.values[0])]
        args = invocation.args or []
        kwargs = invocation.kwargs or {}
        return await self.view.ctx.invoke(invocation.command, *args, **kwargs)


class CommandInvokeView(discord.ui.View):
    def __init__(
        self, ctx: PoketwoContext, command_invocations: List[CommandInvocation], *, placeholder: Optional[str] = None
    ):
        self.ctx = ctx
        self.command_invocations = command_invocations

        self.message = None

        super().__init__(timeout=120)
        self.add_item(CommandInvokeSelectMenu(command_invocations, placeholder=placeholder))

    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("You can't use this!", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        if self.message:
            await self.message.edit(view=None)
