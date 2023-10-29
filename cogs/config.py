from typing import Union

import discord
import geocoder
from discord.ext import commands

from helpers import constants, checks


def geocode(location):
    return geocoder.osm(location)


class Configuration(commands.Cog):
    """Configuration commands to change bot behavior."""

    def __init__(self, bot):
        self.bot = bot

    def make_config_embed(self, ctx, guild, commands={}):
        embed = ctx.localized_embed(
            "config-embed",
            field_ordering=["level-up", "location", "spawning-channels"],
            block_fields=True,
            field_values={
                "level-up": ctx._("config-yes" if guild.silence else "config-no"),
                "location": guild.loc,
                "spawning-channels": "\n".join(f"<#{x}>" for x in guild.channels),
            },
            silenceCommand=commands.get("silence_command", ""),
            locationCommand=commands.get("location_command", ""),
            redirectCommand=commands.get("redirect_command", ""),
        )
        embed.color = constants.PINK

        if ctx.guild.icon is not None:
            embed.set_thumbnail(url=ctx.guild.icon.url)

        return embed

    @commands.guild_only()
    @commands.group(
        aliases=("config", "serverconfig"),
        invoke_without_command=True,
        case_insensitive=True,
    )
    async def configuration(self, ctx: commands.Context):
        guild = await self.bot.mongo.fetch_guild(ctx.guild)

        embed = self.make_config_embed(ctx, guild)
        await ctx.send(embed=embed)

    @commands.guild_only()
    @configuration.command(name="help")
    async def advanced_configuration(self, ctx: commands.Context):
        guild = await self.bot.mongo.fetch_guild(ctx.guild)

        commands = {
            f"{key}_command": f"\n`{ctx.clean_prefix}{ctx._(f'command-example-{key}')}`"
            for key in ("silence", "location", "redirect")
        }

        embed = self.make_config_embed(ctx, guild, commands)

        await ctx.send(embed=embed)

    @checks.has_started()
    @commands.command()
    async def silence(self, ctx: commands.Context):
        """Silence level up messages for yourself."""

        member = await self.bot.mongo.fetch_member_info(ctx.author)

        await self.bot.mongo.update_member(ctx.author, {"$set": {"silence": not member.silence}})

        if member.silence:
            await ctx.send(ctx._("silence-off"))
        else:
            await ctx.send(ctx._("silence-on"))

    @checks.is_admin()
    @commands.command()
    async def serversilence(self, ctx: commands.Context):
        """Silence level up messages server-wide."""

        guild = await self.bot.mongo.fetch_guild(ctx.guild)
        await self.bot.mongo.update_guild(ctx.guild, {"$set": {"silence": not guild.silence}})

        if guild.silence:
            await ctx.send(ctx._("serversilence-off"))
        else:
            await ctx.send(ctx._("serversilence-on"))

    @checks.is_admin()
    @commands.group(invoke_without_command=True, case_insensitive=True)
    async def redirect(
        self,
        ctx: commands.Context,
        channels: commands.Greedy[Union[discord.TextChannel, discord.Thread]],
    ):
        """Redirect pokémon catches to one or more channels."""

        if len(channels) == 0:
            return await ctx.send(ctx._("redirect-requires-channels"))

        await self.bot.mongo.update_guild(ctx.guild, {"$set": {"channels": [x.id for x in channels]}})
        await ctx.send(ctx._("redirect-completed", channels=", ".join(x.mention for x in channels)))

    @checks.is_admin()
    @redirect.command()
    async def reset(self, ctx: commands.Context):
        """Reset channel redirect."""

        await self.bot.mongo.update_guild(ctx.guild, {"$set": {"channels": []}})
        await ctx.send(ctx._("reset-completed"))

    @checks.is_admin()
    @commands.command(aliases=("timezone", "tz"))
    async def location(self, ctx: commands.Context, *, location: str = None):
        if location is None:
            guild = await self.bot.mongo.fetch_guild(ctx.guild)
            return await ctx.send(
                ctx._("location-current", latitude=guild.lat, location=guild.loc, longitude=guild.lng)
            )

        async with ctx.typing():
            g = await self.bot.loop.run_in_executor(None, geocode, location)

            if g.latlng is None:
                return await ctx.send(ctx._("unknown-location"))

            lat, lng = g.latlng
            await self.bot.mongo.update_guild(ctx.guild, {"$set": {"lat": lat, "lng": lng, "loc": g.address}})
            await ctx.send(ctx._("set-location", location=g.address, longitude=lng, latitude=lat))

    @commands.command()
    async def time(self, ctx: commands.Context):
        guild = await self.bot.mongo.fetch_guild(ctx.guild)

        embed = self.bot.Embed(title=ctx._("time-day-title") if guild.is_day else ctx._("time-night-title"))
        embed.description = ctx._("time-day-description" if guild.is_day else "time-night-description")

        embed.add_field(
            name=ctx._("server-location-field-name"),
            value=ctx._("server-location-field-name", location=guild.loc, latitude=guild.lat, longitude=guild.lng),
        )

        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Configuration(bot))
