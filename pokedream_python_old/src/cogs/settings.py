from __future__ import annotations
from models.helpers import ArrayAppend, ArrayRemove
import models

import discord
from discord.ext import commands
import typing

from discord.ext.commands import converter

if typing.TYPE_CHECKING:
    from core.bot import PokeBest

from core.views import Confirm


class Settings(commands.Cog):
    def __init__(self, bot: PokeBest) -> None:
        self.bot: PokeBest = bot

    @commands.command()
    @commands.has_guild_permissions(administrator=True)
    async def setprefix(self, ctx: commands.Context, args: str):
        """Set the new prefix of the bot"""
        if args.__len__() > 10:
            return await ctx.reply(
                "Sorry, you can't set prefix of more that 10 characters.",
                mention_author=False,
            )

        _view: Confirm = Confirm(ctx)
        msg: discord.Message = await ctx.reply(
            f"Are you sure you want to change the current prefix to `{args}`?",
            mention_author=False,
            view=_view,
        )

        await _view.wait()

        if _view.value is None:
            return await msg.edit("Time's up!", view=None, allowed_mentions=None)

        if _view.value is False:
            return await msg.edit("Cancelled!", view=None, allowed_mentions=None)

        with ctx.typing():
            await self.bot.manager.update_guild(ctx.guild.id, prefix=args)
            _guild: models.Guild = await models.Guild.get(id=ctx.guild.id)

            self.bot.cache.guilds[f"{ctx.guild.id}"] = _guild

        return await msg.edit(
            f"Successfully changed the server's prefix to `{args}`!",
            view=None,
            allowed_mentions=None,
        )

    @commands.group(invoke_without_subcommand=True)
    @commands.has_guild_permissions(administrator=True)
    async def redirect(self, ctx: commands.Context, channels: converter.Greedy[discord.TextChannel]):
        """Change the spawn channels"""
        if ctx.invoked_subcommand is None:
            if channels.__len__() == 0:
                return await ctx.reply(
                    "Please mention atleast one channel to redirect in.",
                    mention_author=False,
                )

            with ctx.typing():
                _guild: models.Guild = (await models.Guild.get_or_create(id=ctx.guild.id))[0]
                for channel in channels:
                    _guild.channels = ArrayAppend("channels", channel.id)

                await _guild.save()

                self.bot.cache.guilds[f"{ctx.guild.id}"] = await models.Guild.get(id=ctx.guild.id)

            return await ctx.reply(
                "All the spawns will now be redirected to following channels: "
                + " ".join(channel.mention for channel in channels)
                + "!",
                mention_author=False,
            )

    @redirect.command(name="disable")
    @commands.has_guild_permissions(administrator=True)
    async def redirect_disable(self, ctx: commands.Context):
        """Disable redirect channels"""
        guild: typing.Optional[models.Guild] = await models.Guild.get_or_none(id=ctx.guild.id)

        if guild is None:
            return await ctx.reply(
                "There are no redirect channels set in this server.",
                mention_author=False,
            )

        with ctx.typing():
            guild.channels = []

            await guild.save()
            self.bot.cache.guilds[f"{ctx.guild.id}"] = await models.Guild.get(id=ctx.guild.id)

        return await ctx.reply("Successfully disabled channel redirects.", mention_author=False)

    # TODO: Namespawns, IV Toggle, more things...


def setup(bot: PokeBest) -> None:
    bot.add_cog(Settings(bot))
