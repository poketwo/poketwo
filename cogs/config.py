from __future__ import annotations

from typing import Optional, Union, List

import discord
import geocoder
from discord.ext import commands

from helpers import checks, pagination
from helpers.constants import CharacterLimits
from helpers.context import PoketwoContext
from helpers.utils import unique
from lib.multi_field_paginator import MultiFieldPageSource, PaginatedField


def geocode(location):
    return geocoder.osm(location)


class Configuration(commands.Cog):
    """Configuration commands to change bot behavior."""

    def __init__(self, bot):
        self.bot = bot

    async def start_configuration_menu(self, ctx: PoketwoContext, *, show_help: Optional[bool] = False):
        bot = self.bot
        guild = await bot.mongo.fetch_guild(ctx.guild)

        # Define the commands' help messages if show_help is True
        commands = (
            {
                "silence_command": f"\n`{ctx.clean_prefix}serversilence`",
                "location_command": f"\n`{ctx.clean_prefix}location <location>`",
                "Spawning Channels": f"\n`{ctx.clean_prefix}redirect <channel 1> <channel 2> ...`",
            }
            if show_help
            else {}
        )

        paginated_fields = [
            PaginatedField(
                "Spawning Channels", [f"{i}. <#{x}>" for i, x in enumerate(guild.channels, 1)] or ["All Channels"]
            ),
        ]

        def make_config_embed(source: MultiFieldPageSource, page_fields: List[PaginatedField]):
            embed = bot.Embed(title="Server Configuration")

            if ctx.guild.icon is not None:
                embed.set_thumbnail(url=ctx.guild.icon.url)

            embed.add_field(
                name=f"Display level-up messages? {commands.get('silence_command', '')}",
                value=(("Yes", "No")[guild.silence]),
                inline=False,
            )
            embed.add_field(
                name=f"Location {commands.get('location_command', '')}",
                value=guild.loc,
                inline=False,
            )

            # Add the paginated fields
            per_page = source.per_page
            current_page = source.current_page
            for field in page_fields:
                entries = field.get_entries(current_page, per_page=per_page)
                total_pages = field.get_num_pages(per_page)

                embed.add_field(
                    name=f"{field} {commands.get(field.name, '')}",
                    value="\n".join(entries) + f"\n**Showing page {min(total_pages, current_page + 1)}/{total_pages}**",
                    inline=False,
                )

            return embed

        pages = pagination.ContinuablePages(
            MultiFieldPageSource(paginated_fields, make_config_embed, per_page=5), loop_pages=False
        )
        self.bot.menus[ctx.author.id] = pages
        await pages.start(ctx)

    @commands.guild_only()
    @commands.group(
        aliases=("config", "serverconfig"),
        invoke_without_command=True,
        case_insensitive=True,
    )
    async def configuration(self, ctx: commands.Context):
        await self.start_configuration_menu(ctx)

    @commands.guild_only()
    @configuration.command(name="help")
    async def advanced_configuration(self, ctx: commands.Context):
        await self.start_configuration_menu(ctx, show_help=True)

    @checks.has_started()
    @commands.group(invoke_without_command=True)
    async def togglemention(self, ctx):
        """Toggle getting mentioned in various cases."""

        return await ctx.send_help(ctx.command)

    @togglemention.command(name="catch", aliases=("catching",))
    async def catching(self, ctx):
        """Toggle getting mentioned when catching a pokémon."""
        member = await self.bot.mongo.fetch_member_info(ctx.author)

        await self.bot.mongo.update_member(ctx.author, {"$set": {"catch_mention": not member.catch_mention}})

        if member.catch_mention:
            await ctx.send(f"You will no longer receive catch pings.")
        else:
            await ctx.send("You will now be pinged on catches.")

    @togglemention.command(name="confirm", aliases=("confirmations", "confirmation"))
    async def confirmations(self, ctx):
        """Toggle getting mentioned for confirmation messages."""
        member = await self.bot.mongo.fetch_member_info(ctx.author)

        await self.bot.mongo.update_member(ctx.author, {"$set": {"confirm_mention": not member.confirm_mention}})

        if member.confirm_mention:
            await ctx.send(f"You will no longer receive confirmation pings.")
        else:
            await ctx.send("You will now be pinged for confirmation messages.")

    @checks.has_started()
    @commands.command()
    async def silence(self, ctx: commands.Context):
        """Silence level up messages for yourself."""

        member = await self.bot.mongo.fetch_member_info(ctx.author)

        await self.bot.mongo.update_member(ctx.author, {"$set": {"silence": not member.silence}})

        if member.silence:
            await ctx.send(f"Reverting to normal level up behavior.")
        else:
            await ctx.send(
                "I'll no longer send level up messages. You'll receive a DM when your pokémon evolves or reaches level 100."
            )

    @checks.is_admin()
    @commands.command()
    async def serversilence(self, ctx: commands.Context):
        """Silence level up messages server-wide."""

        guild = await self.bot.mongo.fetch_guild(ctx.guild)
        await self.bot.mongo.update_guild(ctx.guild, {"$set": {"silence": not guild.silence}})

        if guild.silence:
            await ctx.send(f"Level up messages are no longer disabled in this server.")
        else:
            await ctx.send(
                f"Disabled level up messages in this server. I'll send a DM when pokémon evolve or reach level 100."
            )

    def build_redirect_message(
        self, base_text: str, channels: List[Union[discord.TextChannel, discord.Thread]], *, prefix
    ) -> str:
        """
        Forms redirect message. If it exceeds character limit, it shows the number of channels instead.
        `base_text` must have a formatting key `channels` where the channels text will be interpolated.
        """

        message = base_text.format_map(dict(channels=", ".join(x.mention for x in channels)))
        if len(message) > CharacterLimits.MESSAGE_CONTENT.value or len(channels) == 0:
            message = (
                base_text.format_map(dict(channels=f"**{len(channels)}** channels"))
                + f" Use `{prefix}config` to see them all."
            )

        return message

    @checks.is_admin()
    @commands.guild_only()
    @commands.group(invoke_without_command=True, case_insensitive=True)
    async def redirect(
        self,
        ctx: commands.Context,
        channels: commands.Greedy[Union[discord.TextChannel, discord.Thread]],
    ):
        """Redirect pokémon catches to one or more channels."""

        if len(channels) == 0:
            return await ctx.send("Please specify channels to redirect to!")

        await self.bot.mongo.update_guild(ctx.guild, {"$set": {"channels": [x.id for x in channels]}})

        content = self.build_redirect_message(
            "Now redirecting spawns to {channels}.", channels, prefix=ctx.clean_prefix
        )
        await ctx.send(content)

    @checks.is_admin()
    @commands.guild_only()
    @redirect.command(aliases=("append",))
    async def add(
        self,
        ctx: commands.Context,
        channels: commands.Greedy[Union[discord.TextChannel, discord.Thread]] = commands.CurrentChannel,
    ):
        """Add channels to redirected channels."""

        if not isinstance(channels, list):
            channels = [channels]

        guild = await self.bot.mongo.fetch_guild(ctx.guild)
        channels = unique(channels, key=lambda ch: ch.id)
        await self.bot.mongo.update_guild(
            ctx.guild, {"$push": {"channels": {"$each": [x.id for x in channels if x.id not in guild.channels]}}}
        )

        content = self.build_redirect_message(
            "Added {channels} to redirected channels.", channels, prefix=ctx.clean_prefix
        )
        await ctx.send(content)

    @checks.is_admin()
    @commands.guild_only()
    @redirect.command()
    async def remove(
        self,
        ctx: commands.Context,
        channels: commands.Greedy[Union[discord.TextChannel, discord.Thread]] = commands.CurrentChannel,
    ):
        """Remove channels from redirected channels."""

        if not isinstance(channels, list):
            channels = [channels]

        guild = await self.bot.mongo.fetch_guild(ctx.guild)
        channels = unique([x for x in channels if x.id in guild.channels], key=lambda ch: ch.id)
        await self.bot.mongo.update_guild(
            ctx.guild, {"$pull": {"channels": {"$in": [x.id for x in channels]}}}
        )

        content = self.build_redirect_message(
            "Removed {channels} from redirected channels.", channels, prefix=ctx.clean_prefix
        )
        await ctx.send(content)

    @checks.is_admin()
    @redirect.command()
    async def reset(self, ctx: commands.Context):
        """Reset channel redirect."""

        await self.bot.mongo.update_guild(ctx.guild, {"$set": {"channels": []}})
        await ctx.send(f"No longer redirecting spawns.")

    @checks.is_admin()
    @commands.command(aliases=("timezone", "tz"))
    async def location(self, ctx: commands.Context, *, location: str = None):
        if location is None:
            guild = await self.bot.mongo.fetch_guild(ctx.guild)
            return await ctx.send(f"The server's current location is **{guild.loc}** ({guild.lat}, {guild.lng}).")

        async with ctx.typing():
            g = await self.bot.loop.run_in_executor(None, geocode, location)

            if g.latlng is None:
                return await ctx.send("Couldn't find that location!")

            lat, lng = g.latlng
            await self.bot.mongo.update_guild(ctx.guild, {"$set": {"lat": lat, "lng": lng, "loc": g.address}})
            await ctx.send(f"Set server location to **{g.address}** ({lat}, {lng}).")

    @commands.command()
    async def time(self, ctx: commands.Context):
        guild = await self.bot.mongo.fetch_guild(ctx.guild)

        embed = self.bot.Embed(title=f"Time: Day ☀️" if guild.is_day else "Time: Night 🌛")
        embed.description = f"It is currently {'day' if guild.is_day else 'night'} time in this server."
        embed.add_field(name="Server Location", value=f"{guild.loc}\n{guild.lat}, {guild.lng}")

        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Configuration(bot))
