import math
from operator import itemgetter

import discord
from discord.ext import commands, flags

from .database import Database
from .helpers import checks
from .helpers.constants import *
from .helpers.models import GameData, SpeciesNotFoundError
from .helpers.pagination import Paginator


class Pokedex(commands.Cog):
    """Pokédex-related commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @property
    def db(self) -> Database:
        return self.bot.get_cog("Database")

    @flags.add_flag("page", nargs="*", type=str, default="1")
    @flags.add_flag("--caught", action="store_true")
    @flags.add_flag("--uncaught", action="store_true")
    @flags.add_flag("--legendary", action="store_true")
    @flags.add_flag("--mythical", action="store_true")
    @flags.add_flag("--orderd", action="store_true")
    @flags.add_flag("--ordera", action="store_true")
    @flags.add_flag("--ub", action="store_true")
    @flags.add_flag("--type", type=str)
    @checks.has_started()
    @flags.command(aliases=["dex"])
    @commands.bot_has_permissions(manage_messages=True, use_external_emojis=True)
    async def pokedex(self, ctx: commands.Context, **flags):
        """View your pokédex, or search for a pokémon species."""

        search_or_page = " ".join(flags["page"])

        if flags["orderd"] and flags["ordera"]:
            return await ctx.send(
                "You can use either --orderd or --ordera, but not both."
            )

        if flags["caught"] and flags["uncaught"]:
            return await ctx.send(
                "You can use either --caught or --uncaught, but not both."
            )

        if flags["mythical"] + flags["legendary"] + flags["ub"] > 1:
            return await ctx.send("You can't use more than one rarity flag!")

        if search_or_page is None:
            search_or_page = "1"

        if search_or_page.isdigit():
            pgstart = (int(search_or_page) - 1) * 20

            if pgstart >= 809 or pgstart < 0:
                return await ctx.send("There are no pokémon on this page.")

            num = await self.db.fetch_pokedex_count(ctx.author)

            do_emojis = ctx.channel.permissions_for(
                ctx.guild.get_member(self.bot.user.id)
            ).external_emojis

            member = await self.db.fetch_pokedex(ctx.author, 0, 809)
            pokedex = member.pokedex

            if not flags["uncaught"] and not flags["caught"]:
                for i in range(1, 810):
                    if str(i) not in pokedex:
                        pokedex[str(i)] = 0
            elif flags["uncaught"]:
                for i in range(1, 810):
                    if str(i) not in pokedex:
                        pokedex[str(i)] = 0
                    else:
                        del pokedex[str(i)]

            def include(key):
                if flags["legendary"] and key not in GameData.list_legendary():
                    return False
                if flags["mythical"] and key not in GameData.list_mythical():
                    return False
                if flags["ub"] and key not in GameData.list_ub():
                    return False

                if flags["type"] and key not in GameData.list_type(flags["type"]):
                    return False

                return True

            pokedex = {int(k): v for k, v in pokedex.items() if include(int(k))}

            if flags["ordera"]:
                pokedex = sorted(pokedex.items(), key=itemgetter(1))
            elif flags["orderd"]:
                pokedex = sorted(pokedex.items(), key=itemgetter(1), reverse=True)
            else:
                pokedex = sorted(pokedex.items(), key=itemgetter(0))

            async def get_page(pidx, clear):
                pgstart = (pidx) * 20
                pgend = min(pgstart + 20, len(pokedex))

                # Send embed

                embed = discord.Embed()
                embed.color = 0xF44336
                embed.title = f"Your pokédex"
                embed.description = f"You've caught {num} out of 809 pokémon!"

                if do_emojis:
                    embed.set_footer(
                        text=f"Showing {pgstart + 1}–{pgend} out of {len(pokedex)}."
                    )
                else:
                    embed.set_footer(
                        text=f"Showing {pgstart + 1}–{pgend} out of 809. Please give me permission to Use External Emojis! It'll make this menu look a lot better."
                    )

                # embed.description = (
                #     f"You've caught {len(member.pokedex)} out of 809 pokémon!"
                # )

                for k, v in pokedex[pgstart:pgend]:
                    species = GameData.species_by_number(k)

                    if do_emojis:
                        text = f"{EMOJIS.cross} Not caught yet!"
                    else:
                        text = "Not caught yet!"

                    if v > 0:
                        if do_emojis:
                            text = f"{EMOJIS.check} {v} caught!"
                        else:
                            text = f"{v} caught!"

                    if do_emojis:
                        emoji = str(EMOJIS.get(k)).replace("pokemon_sprite_", "") + " "
                    else:
                        emoji = ""

                    embed.add_field(
                        name=f"{emoji}{species.name} #{species.id}", value=text
                    )

                if pgend != 809:
                    embed.add_field(name="‎", value="‎")

                return embed

            paginator = Paginator(get_page, num_pages=math.ceil(len(pokedex) / 20))
            await paginator.send(self.bot, ctx, int(search_or_page) - 1)

        else:
            shiny = False
            search = search_or_page

            if search_or_page.lower().startswith("shiny "):
                shiny = True
                search = search_or_page[6:]

            try:
                species = GameData.species_by_name(search)
            except SpeciesNotFoundError:
                return await ctx.send(
                    f"Could not find a pokemon matching `{search_or_page}`."
                )

            member = await self.db.fetch_pokedex(
                ctx.author, species.dex_number, species.dex_number + 1
            )

            embed = discord.Embed()
            embed.color = 0xF44336
            embed.title = f"#{species.dex_number} — {species}"
            embed.description = species.evolution_text

            extrafooter = ""

            if shiny:
                embed.title += " ✨"
                embed.set_image(url=species.shiny_image_url)
                if species.id > 71:
                    extrafooter = " Note that we don't have artwork for this shiny pokémon yet! We're working hard to make all the shiny pokémon look shiny."
            else:
                embed.set_image(url=species.image_url)

            base_stats = (
                f"**HP:** {species.base_stats.hp}",
                f"**Attack:** {species.base_stats.atk}",
                f"**Defense:** {species.base_stats.defn}",
                f"**Sp. Atk:** {species.base_stats.satk}",
                f"**Sp. Def:** {species.base_stats.sdef}",
                f"**Speed:** {species.base_stats.spd}",
            )

            embed.add_field(
                name="Names",
                value="\n".join(f"{x} {y}" for x, y in species.names),
                inline=False,
            )
            embed.add_field(name="Base Stats", value="\n".join(base_stats))
            embed.add_field(
                name="Appearance",
                value=f"Height: {species.height} m\nWeight: {species.weight} kg",
            )
            embed.add_field(name="Types", value="\n".join(species.types))

            text = "You haven't caught this pokémon yet!"
            if str(species.dex_number) in member.pokedex:
                text = f"You've caught {member.pokedex[str(species.dex_number)]} of this pokémon!"

            embed.set_footer(text=text + extrafooter)

            await ctx.send(embed=embed)
