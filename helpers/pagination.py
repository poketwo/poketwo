from __future__ import annotations

import textwrap
from typing import TYPE_CHECKING, Any, List, Optional
import discord
import math
import discord
from data.models import Species
from helpers import constants

from discord.ext import menus
from discord.ext.menus.views import ViewMenuPages
from helpers.context import PoketwoContext
from lib import radio

if TYPE_CHECKING:
    from cogs.mongo import Member


REMOVE_BUTTONS = [
    "\N{BLACK LEFT-POINTING DOUBLE TRIANGLE WITH VERTICAL BAR}\ufe0f",
    "\N{BLACK RIGHT-POINTING DOUBLE TRIANGLE WITH VERTICAL BAR}\ufe0f",
    "\N{BLACK SQUARE FOR STOP}\ufe0f",
]


class FunctionPageSource(menus.PageSource):
    def __init__(self, num_pages, format_page):
        self.num_pages = num_pages
        self.format_page = format_page.__get__(self)

    def is_paginating(self):
        return self.num_pages > 1

    async def get_page(self, page_number):
        return page_number

    def get_max_pages(self):
        return self.num_pages


class AsyncListPageSource(menus.AsyncIteratorPageSource):
    def __init__(
        self,
        data,
        title=None,
        show_index=False,
        prepare_page=lambda self, items: None,
        format_item=str,
        per_page=20,
        count=None,
    ):
        super().__init__(data, per_page=per_page)
        self.title = title
        self.show_index = show_index
        self.prepare_page = prepare_page.__get__(self)
        self.format_item = format_item.__get__(self)
        self.count = count

    def get_max_pages(self):
        if self.count is None:
            return None
        else:
            return math.ceil(self.count / self.per_page)

    async def format_page(self, menu, entries):
        self.prepare_page(entries)
        lines = [
            f"{i+1}. {self.format_item(x)}" if self.show_index else self.format_item(x)
            for i, x in enumerate(entries, start=menu.current_page * self.per_page)
        ]
        start = menu.current_page * self.per_page
        footer = f"Showing entries {start + 1}–{start + len(lines)}"
        if self.count is not None:
            footer += f" out of {self.count}."
        else:
            footer += "."

        embed = menu.ctx.bot.Embed(
            title=self.title,
            description=f"\n".join(lines)[:4096],
        )
        embed.set_footer(text=footer)
        return embed


class ContinuablePages(ViewMenuPages):
    def __init__(
        self, source, allow_last=True, allow_go=True, loop_pages=True, mention_author=False, timeout=120, **kwargs
    ):
        super().__init__(source, **kwargs, timeout=timeout)
        self.allow_last = allow_last
        self.allow_go = allow_go
        self.loop_pages = loop_pages
        self.mention_author = mention_author
        for x in REMOVE_BUTTONS:
            self.remove_button(x)

    def build_view(self):
        if getattr(self, "view"):  # Not using default because view can be None
            return self.view

        view = super().build_view()
        if view:

            async def interaction_check(interaction):
                if interaction.user.id not in {self.ctx.bot.owner_id, self.ctx.author.id, *self.ctx.bot.owner_ids}:
                    await interaction.response.send_message("You can't use this!", ephemeral=True)
                    return False
                return True

            view.interaction_check = interaction_check

        return view

    async def _get_kwargs_from_page(self, page):
        value = await discord.utils.maybe_coroutine(self._source.format_page, self, page)
        if isinstance(value, dict):
            return value
        elif isinstance(value, str):
            return {"content": value, "embed": None}
        elif isinstance(value, discord.Embed):
            return {"embed": value, "content": None}
        elif isinstance(value, list):
            if all([isinstance(i, discord.Embed) for i in value]):
                return {"embeds": value, "content": None}

    async def send_initial_message(self, ctx, channel):
        page = await self._source.get_page(self.current_page)
        kwargs = await self._get_kwargs_from_page(page)
        kwargs["reference"] = ctx.message
        kwargs["mention_author"] = self.mention_author
        return await self.send_with_view(channel, **kwargs)

    async def show_checked_page(self, page_number):
        max_pages = self._source.get_max_pages()
        try:
            if max_pages is None:
                await self.show_page(page_number)
            elif page_number < 0 and not self.allow_last:
                await self.ctx.send(
                    "Sorry, this does not support going to last page. Try sorting in the reverse direction instead."
                )
            elif page_number < 0 or page_number >= (max_pages):
                if self.loop_pages is True:
                    await self.show_page(page_number % max_pages)
            else:
                await self.show_page(page_number)
        except IndexError:
            pass

    async def continue_at(self, ctx, page, *, channel=None, wait=False):
        self.stop()
        max_pages = self._source.get_max_pages()
        if max_pages is None:
            self.current_page = page
        else:
            self.current_page = page % self._source.get_max_pages()
        self.message = None
        await self.start(ctx, channel=channel, wait=wait)


class DexView(discord.ui.View):
    def __init__(self, ctx: PoketwoContext, species: Species, member: Member, is_shiny: bool, gender: bool):
        super().__init__()
        self.ctx = ctx
        self.bot = self.ctx.bot
        self.species = species
        self.member = member
        self.is_shiny = is_shiny
        self.gender = gender

        self.shiny_select = None
        self.gender_select = None
        self.update_species(species)

    def update_species(self, species: Species):
        self.species = species

        self.clear_items()

        # Select menu

        if len(self.species.variants) > 1:
            # Add select menus in chunks of 25 variants due to options limit
            for variants in discord.utils.as_chunks(self.species.variants, 25):
                self.add_item(VariantSelectMenu(self.ctx, self.species, variants))

        # Buttons

        all_pokemon = list(self.bot.data.all_pokemon())
        total_pokemon = len(all_pokemon)
        current_idx = all_pokemon.index(self.species)

        next_idx = (current_idx + 1) % total_pokemon  # modulo operator here allows looping back
        next_species = all_pokemon[next_idx]

        prev_idx = (current_idx - 1) % total_pokemon  # modulo operator here allows looping back
        prev_species = all_pokemon[prev_idx]

        # Previous Button
        self.add_item(DexPaginationButton(prev_species, emoji="◀️"))

        # Shiny Button
        selected_shiny = self.shiny_select.selected if self.shiny_select else self.is_shiny
        self.shiny_select = ShinyRadioGroup(self, is_selected=selected_shiny)
        self.shiny_select.add_to_view(self)

        # Gender Buttons
        if self.species.has_gender_differences == 1:
            selected_gender = self.gender_select.selected if self.gender_select else self.gender
            self.gender_select = GenderRadioGroup(self, selected_gender)
            self.gender_select.add_to_view(self)

        # Next Button
        self.add_item(DexPaginationButton(next_species, emoji="▶️"))

    async def interaction_check(self, interaction):
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("You can't use this!", ephemeral=True)
            return False
        return True

    def get_embed(self) -> discord.Embed:
        """Base embed based on current attributes and return it."""

        species = self.species
        embed = self.bot.Embed(title=f"#{species.dex_number} — {species} {'✨' if self.shiny_select.selected else ''}")

        if species.description:
            embed.description = species.description.replace("\n", " ")

        # Pokemon Rarity
        rarity = []
        if species.mythical:
            rarity.append("Mythical")
        if species.legendary:
            rarity.append("Legendary")
        if species.ultra_beast:
            rarity.append("Ultra Beast")
        if species.event:
            rarity.append("Event")

        if rarity:
            rarity = ", ".join(rarity)
            embed.add_field(
                name="Rarity",
                value=rarity,
                inline=False,
            )

        if species.evolution_text:
            embed.add_field(name="Evolution", value=species.evolution_text, inline=False)

        base_stats = (
            f"**HP:** {species.base_stats.hp}",
            f"**Attack:** {species.base_stats.atk}",
            f"**Defense:** {species.base_stats.defn}",
            f"**Sp. Atk:** {species.base_stats.satk}",
            f"**Sp. Def:** {species.base_stats.sdef}",
            f"**Speed:** {species.base_stats.spd}",
            f"**Total: {species.base_stats.total}**",
        )

        if species.gender_rate == -1:
            gender_rate = "Gender unknown"
        else:
            gender_rate = f"{constants.GENDER_EMOTES['male']} {species.gender_ratios[0]}% - {constants.GENDER_EMOTES['female']} {species.gender_ratios[1]}%"

        embed.add_field(
            name="Types", value="\n".join(f"{self.bot.sprites.get_type_sprite(t)} {t}" for t in species.types)
        )
        embed.add_field(name="Region", value=species.region.title())
        embed.add_field(name="Catchable", value="Yes" if species.catchable else "No")

        embed.add_field(name="Base Stats", value="\n".join(base_stats))
        embed.add_field(name="Names", value="\n".join(f"{x} {y}" for x, y in species.names))
        embed.add_field(name="Appearance", value=f"Height: {species.height} m\nWeight: {species.weight} kg")
        embed.add_field(name="Gender Ratio", value=f"{gender_rate}")

        text = "You haven't caught this pokémon yet!"
        if str(species.dex_number) in self.member.pokedex:
            text = f"You've caught {self.member.pokedex[str(species.dex_number)]} of this pokémon!"

        if species.art_credit:
            text = f"Artwork by {species.art_credit}.\nMay be derivative of artwork © The Pokémon Company.\n" + text

        embed.set_footer(text=text)

        # Update image for shiny/gender selection
        image_url = self.species.get_image_url(
            self.shiny_select.selected, None if not self.gender_select else self.gender_select.selected
        )
        embed.set_image(url=image_url + "?a")  # TODO: Temporary to bypass discord caching issue for the new summer moltres

        return embed

    async def update_embed(self, interaction):
        await interaction.response.edit_message(embed=self.get_embed(), view=self)


class GenderRadioGroup(radio.RadioGroup):
    def __init__(self, view: DexView, gender):
        super().__init__()
        self.view = view
        male_selected = False if gender == "female" else True
        self.add_option("", "male", is_selected=male_selected, emoji=constants.GENDER_EMOTES["male"])
        self.add_option("", "female", is_selected=not male_selected, emoji=constants.GENDER_EMOTES["female"])

    async def callback(self, interaction, button):
        super().callback(interaction, button)
        await self.view.update_embed(interaction)


class ShinyRadioGroup(radio.RadioGroup):
    def __init__(self, view: DexView, is_selected: bool = False):
        super().__init__(
            default_style=discord.ButtonStyle.red, selected_style=discord.ButtonStyle.green, allow_deselect=True
        )
        self.view = view
        self.add_option("✨", "shiny", is_selected=is_selected)

    @property
    def selected(self):
        # This isn't a normal radio group — it only has one button and
        # we just care about whether it's selected or not.
        return self._selected is not None

    async def callback(self, interaction, button):
        super().callback(interaction, button)
        await self.view.update_embed(interaction)


class VariantSelectMenu(discord.ui.Select):
    def __init__(self, ctx: PoketwoContext, species: Species, variants: List[Species]):
        self.ctx = ctx
        self.bot = ctx.bot
        self.species = species
        self.variants = variants

        options = [
            discord.SelectOption(
                label=variant.name,
                value=str(variant.id),
                description=textwrap.shorten(variant.description, 100) if variant.description else None,
                emoji=self.bot.sprites.get(variant),
                default=variant.id == self.species.id,
            )
            for variant in variants
        ]

        super().__init__(placeholder="View a variant", options=options)

    async def callback(self, interaction: discord.Interaction) -> Any:
        species_id = int(self.values[0])
        species = self.bot.data.species_by_number(species_id)

        self.view.update_species(species)
        await self.view.update_embed(interaction)


class DexPaginationButton(discord.ui.Button):
    def __init__(self, species: Species, *args, **kwargs):
        self.species = species
        super().__init__(*args, **kwargs)

    async def callback(self, interaction: discord.Interaction):
        self.view.update_species(self.species)
        await self.view.update_embed(interaction)
