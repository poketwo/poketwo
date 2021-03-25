import discord
import geocoder
from discord.ext import commands
from helpers import checks


def geocode(location):
    return geocoder.osm(location)


class Configuration(commands.Cog):
    """Configuration commands to change bot behavior."""

    def __init__(self, bot):
        self.bot = bot

    def make_config_embed(self, ctx, guild, commands={}):
        prefix = guild.prefix if guild.prefix is not None else "p!"

        embed = self.bot.Embed()
        embed.title = "Server Configuration"
        embed.set_thumbnail(url=ctx.guild.icon_url)
        embed.add_field(
            name=f"Prefix {commands.get('prefix_command', '')}",
            value=f"`{prefix}`",
            inline=True,
        )
        embed.add_field(
            name=f"Display level-up messages? {commands.get('silence_command', '')}",
            value=(("Yes", "No")[guild.silence]),
            inline=True,
        )
        embed.add_field(
            name=f"Location {commands.get('location_command', '')}",
            value=guild.loc,
            inline=False,
        )
        embed.add_field(
            name=f"Spawning Channels {commands.get('redirect_command', '')}",
            value="\n".join(f"<#{x}>" for x in guild.channels) or "All Channels",
            inline=False,
        )
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
        prefix = guild.prefix if guild.prefix is not None else "p!"

        commands = {
            "prefix_command": f"\n`{prefix}prefix <new prefix>`",
            "silence_command": f"\n`{prefix}serversilence`",
            "location_command": f"\n`{prefix}location <location>`",
            "redirect_command": f"\n`{prefix}redirect <channel 1> <channel 2> ...`",
        }

        embed = self.make_config_embed(ctx, guild, commands)

        await ctx.send(embed=embed)

    @checks.is_admin()
    @commands.guild_only()
    @commands.command(aliases=("setprefix",))
    async def prefix(self, ctx: commands.Context, *, prefix: str = None):
        """Change the bot prefix."""

        if prefix is None:
            guild = await self.bot.mongo.fetch_guild(ctx.guild)
            current = guild.prefix
            if type(current) == list:
                current = current[0]
            return await ctx.send(f"My prefix is `{current}` in this server.")

        if prefix in ("reset", "p!", "P!"):
            await self.bot.mongo.update_guild(ctx.guild, {"$set": {"prefix": None}})
            self.bot.prefixes[ctx.guild.id] = None

            return await ctx.send("Reset prefix to `p!` for this server.")

        if len(prefix) > 100:
            return await ctx.send("Prefix must not be longer than 100 characters.")

        await self.bot.mongo.update_guild(ctx.guild, {"$set": {"prefix": prefix}})
        self.bot.prefixes[ctx.guild.id] = prefix

        await ctx.send(f"Changed prefix to `{prefix}` for this server.")

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
    @commands.group(invoke_without_command=True, case_insensitive=True)
    async def redirect(self, ctx: commands.Context, channels: commands.Greedy[discord.TextChannel]):
        """Redirect pokémon catches to one or more channels."""

        if len(channels) == 0:
            return await ctx.send("Please specify channels to redirect to!")

        await self.bot.mongo.update_guild(
            ctx.guild, {"$set": {"channels": [x.id for x in channels]}}
        )
        await ctx.send("Now redirecting spawns to " + ", ".join(x.mention for x in channels))

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
            return await ctx.send(
                f"The server's current location is **{guild.loc}** ({guild.lat}, {guild.lng})."
            )

        async with ctx.typing():
            g = await self.bot.loop.run_in_executor(None, geocode, location)

            if g.latlng is None:
                return await ctx.send("Couldn't find that location!")

            lat, lng = g.latlng
            await self.bot.mongo.update_guild(
                ctx.guild, {"$set": {"lat": lat, "lng": lng, "loc": g.address}}
            )
            await ctx.send(f"Set server location to **{g.address}** ({lat}, {lng}).")

    @commands.command()
    async def time(self, ctx: commands.Context):
        guild = await self.bot.mongo.fetch_guild(ctx.guild)

        embed = self.bot.Embed()
        embed.title = f"Time: Day ☀️" if guild.is_day else "Time: Night 🌛"
        embed.description = (
            "It is currently " + ("day" if guild.is_day else "night") + "time in this server."
        )
        embed.add_field(name="Server Location", value=f"{guild.loc}\n{guild.lat}, {guild.lng}")

        await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(Configuration(bot))
