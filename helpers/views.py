from datetime import datetime

import discord


class ViewTermsOfServiceView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=0)
        self.add_item(discord.ui.Button(label="View Terms", url="https://poketwo.net/terms"))


class ConfirmTermsOfServiceView(discord.ui.View):
    def __init__(self, ctx, *, timeout=120, delete_after) -> None:
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

    def on_timeout(self):
        if self.message:
            self.message.update(view=ViewTermsOfServiceView())


class ConfirmUpdatedTermsOfServiceView(discord.ui.View):
    def __init__(self, ctx, *, timeout=120) -> None:
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

    def on_timeout(self):
        if self.message:
            self.message.update(view=ViewTermsOfServiceView())
