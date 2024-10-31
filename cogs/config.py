from __future__ import annotations

from typing import Optional, Union, List

import discord
import geocoder
from discord.ext import commands

from helpers import checks, pagination
from helpers.constants import CharacterLimits
from helpers.context import PoketwoContext
from helpers.utils import build_channels_message, unique
from lib.multi_field_paginator import MultiFieldPageSource, PaginatedField


def geocode(location):
    return geocoder.arcgis(location)


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
                name="Spawning Channels",
                entries=[f"{i}. <#{x}>" for i, x in enumerate(guild.channels, 1)] or ["All Channels"],
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
                    value="\n".join(entries)
                    + (
                        f"\n**Showing page {min(total_pages, current_page + 1)}/{total_pages}**"
                        if total_pages > 1
                        else ""
                    ),
                    inline=False,
                )

            return embed

        pages = pagination.ContinuablePages(MultiFieldPageSource(paginated_fields, make_config_embed, per_page=5))
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
    @commands.command(invoke_without_command=True)
    async def togglemention(self, ctx):
        """Toggle settings."""

        return await ctx.send(
            f"This command has migrated to `{ctx.clean_prefix}{self.toggle_mention.qualified_name}`, please use that instead."
        )

    @checks.has_started()
    @commands.group(invoke_without_command=True)
    async def toggle(self, ctx):
        """Toggle settings."""

        return await ctx.send_help(ctx.command)

    @checks.has_started()
    @toggle.group(name="catch-ivs", aliases=("catch-iv", "catchivs"), invoke_without_command=True)
    async def toggle_catch_ivs(self, ctx):
        """Toggle seeing pokémon IVs in catch messages."""
        member = await self.bot.mongo.fetch_member_info(ctx.author)

        await self.bot.mongo.update_member(ctx.author, {"$set": {"catch_ivs": not member.catch_ivs}})

        if member.catch_ivs:
            await ctx.send(f"You will no longer see the pokémon IV in catch messages.")
        else:
            await ctx.send("You will now see the pokémon IV in catch messages.")

    @checks.has_started()
    @toggle.group(name="bold-ids", aliases=("bold-id", "boldids", "bold"), invoke_without_command=True)
    async def toggle_bold_ids(self, ctx):
        """Toggle bolding of IDs in inventory commands (pokemon, market, auctions, etc)."""
        member = await self.bot.mongo.fetch_member_info(ctx.author)

        await self.bot.mongo.update_member(ctx.author, {"$set": {"bold_ids": not member.bold_ids}})

        if member.bold_ids:
            await ctx.send("IDs will no longer be bold in inventories.")
        else:
            await ctx.send("IDs will now be bold in inventories.")

    @checks.has_started()
    @toggle.group(name="mention", invoke_without_command=True)
    async def toggle_mention(self, ctx):
        """Toggle getting mentioned in various cases."""

        return await ctx.send_help(ctx.command)

    @toggle_mention.command(name="catch", aliases=("catching",))
    async def catching_mentions(self, ctx):
        """Toggle getting mentioned when catching a pokémon."""
        member = await self.bot.mongo.fetch_member_info(ctx.author)

        await self.bot.mongo.update_member(ctx.author, {"$set": {"catch_mention": not member.catch_mention}})

        if member.catch_mention:
            await ctx.send(f"You will no longer receive catch pings.")
        else:
            await ctx.send("You will now be pinged on catches.")

    @toggle_mention.command(name="confirm", aliases=("confirmations", "confirmation"))
    async def confirmation_mentions(self, ctx):
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

        content = build_channels_message(
            "Now redirecting spawns to {channels}.",
            channels,
            see_all_tip=f"Use `{ctx.clean_prefix}config` to see them all.",
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

        content = build_channels_message(
            "Added {channels} to redirected channels.",
            channels,
            see_all_tip=f"Use `{ctx.clean_prefix}config` to see them all.",
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
        await self.bot.mongo.update_guild(ctx.guild, {"$pull": {"channels": {"$in": [x.id for x in channels]}}})

        content = build_channels_message(
            "Removed {channels} from redirected channels.",
            channels,
            see_all_tip=f"Use `{ctx.clean_prefix}config` to see them all.",
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

        current_time = guild.time
        embed = self.bot.Embed(title=f"Time: {current_time}")
        embed.description = f"It is currently {current_time.text} in this server."
        embed.add_field(name="Server Location", value=f"{guild.loc}\n{guild.lat}, {guild.lng}")

        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Configuration(bot))
