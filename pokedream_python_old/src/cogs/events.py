from __future__ import annotations

from discord.ext import commands
import discord

import typing

if typing.TYPE_CHECKING:
    from core.bot import PokeBest

import pickle


class Event(commands.Cog):
    def __init__(self, bot: PokeBest) -> None:
        self.bot: PokeBest = bot

    @commands.command()
    async def event(self, ctx: commands.Context):
        """Shows the ongoing event"""
        if self.bot.bot_config.event_txt is None:
            return await ctx.reply("There are no ongoing events currently.", mention_author=False)

        emb: discord.Embed = self.bot.Embed()

        if self.bot.bot_config.event_title is not None:
            emb.title = self.bot.bot_config.event_title

        if self.bot.bot_config.event_txt is not None:
            emb.description = self.bot.bot_config.event_txt

        if self.bot.bot_config.event_image is not None:
            emb.set_image(url=self.bot.bot_config.event_image)

        if self.bot.bot_config.event_thumbnail is not None:
            emb.set_thumbnail(url=self.bot.bot_config.event_thumbnail)

        await ctx.reply(embed=emb, mention_author=False)


def setup(bot: PokeBest) -> None:
    bot.add_cog(Event(bot))
