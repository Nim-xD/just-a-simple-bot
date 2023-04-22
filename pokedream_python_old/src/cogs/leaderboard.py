from __future__ import annotations
from datetime import datetime

import discord
from discord.ext import commands, tasks
import typing

if typing.TYPE_CHECKING:
    from core.bot import PokeBest

import models


class Leaderboard(commands.Cog):
    def __init__(self, bot: PokeBest) -> None:
        self.bot: PokeBest = bot

    @commands.Cog.listener()
    async def on_catch(self, ctx: commands.Context, pokemon: models.Pokemon):
        mem: models.Member = await self.bot.manager.fetch_member_info(ctx.author.id)

        mem.monthly_catches += 1
        await mem.save()

    @commands.command(aliases=("lb",))
    async def leaderboard(self, ctx: commands.Context):
        """Shows global catch leaderboard"""
        top_10: typing.List[models.Member] = await models.Member.all().order_by("-monthly_catches").limit(10)

        emb: discord.Embed = self.bot.Embed(title=f"{self.bot.user.name} Global Caught Leaderboard")

        for idx, mem in enumerate(top_10, start=1):
            user: discord.User = self.bot.get_user(mem.id) or await self.bot.fetch_user(mem.id)

            emb.add_field(name=f"#{idx} | {user.__str__()}", value=f"**Catches**: {mem.monthly_catches}")

        return await ctx.reply(embed=emb, mention_author=False)

    @tasks.loop(hours=48)
    async def reset_monthly_catches(self):
        _stamp: datetime = discord.utils.utcnow()

        if _stamp.day == 1:
            _top_20: typing.List[models.Member] = await models.Member.all().order_by("-monthly_catches").limit(20)

            for idx, mem in enumerate(_top_20, idx=1):
                mem: models.Member

                mem.redeems += 10 if idx <= 10 else 5
                await mem.save()

            async for mem in models.Member.all():
                mem.monthly_catches = 0
                await mem.save()


def setup(bot: PokeBest) -> None:
    bot.add_cog(Leaderboard(bot))
