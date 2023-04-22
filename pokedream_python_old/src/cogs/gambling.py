from __future__ import annotations
from contextlib import suppress
from core.views import GambleView

from discord.flags import alias_flag_value
import models
from cogs.helpers.battles import Trainer

import discord
from discord.ext import commands
import typing

from utils.exceptions import PokeBestError

if typing.TYPE_CHECKING:
    from core.bot import PokeBest

from dataclasses import dataclass
from utils.checks import has_started
from utils.converters import TrainerConverter
import random
import pickle


@dataclass
class GambleUser:
    user_id: int
    confirmed: bool
    model: models.Member


@dataclass
class Gamble:
    ctx: commands.Context
    requester: typing.Union[discord.Member, discord.User]
    bal: int
    users: typing.List[GambleUser]
    alotment: int


class Gambling(commands.Cog):
    def __init__(self, bot: PokeBest) -> None:
        self.bot: PokeBest = bot

        if not hasattr(self, "gambles"):
            self.gambles: typing.List[Gamble] = []

    @commands.command(aliases=("g", "bet"))
    @commands.max_concurrency(1, commands.BucketType.user)
    @has_started()
    async def gamble(self, ctx: commands.Context, mem: TrainerConverter, amount: int):
        """Start gambling with another user"""
        if amount < 0:
            return await ctx.reply("Amount can't be a negative number!", mention_author=False)

        if mem == ctx.author:
            return await ctx.reply("You can't gamble with yourself!", mention_author=False)

        trade_cog = self.bot.get_cog("Trading")
        if trade_cog.is_in_trade(ctx.author):
            return await ctx.reply("You can't gamble while you are in trade.", mention_author=False)

        member: models.Member = await self.bot.manager.fetch_member_info(ctx.author.id)
        target: models.Member = await self.bot.manager.fetch_member_info(mem.id)

        if member.balance < amount:
            return await ctx.reply("You don't have that much balance to gamble!", mention_author=False)

        if target.balance < amount:
            return await ctx.reply(
                "The trainer you are gambling with don't have that much balance.",
                mention_author=False,
            )

        alotment: int = 1
        while discord.utils.get(self.gambles, alotment=alotment):
            alotment += 1

        gamble: Gamble = Gamble(
            ctx,
            ctx.author,
            amount,
            [
                GambleUser(ctx.author.id, False, member),
                GambleUser(mem.id, False, target),
            ],
            alotment,
        )

        self.gambles.append(gamble)

        _view: GambleView = GambleView(gamble, mem)
        msg: discord.Message = await ctx.reply(
            f"{mem.mention}, {ctx.author.mention} invited you for gamble!",
            view=_view,
            mention_author=False,
        )

        await _view.wait()

        if _view.joined is None:
            with suppress(discord.Forbidden, discord.HTTPException):
                return await msg.edit("Gamble request expired!", view=None, allowed_mentions=None)
            return

        if _view.joined is False:
            with suppress(discord.Forbidden, discord.NotFound):
                return await msg.edit("Gamble request declined!", view=None, allowed_mentions=None)
            return
        
        if trade_cog.is_in_trade(ctx.author) or trade_cog.is_in_trade(mem.id):
            return await ctx.reply("You can't gamble while you are in trade.", mention_author=False)

        if 839891608774508575 not in [u.user_id for u in gamble.users]:
            winner: GambleUser = random.choice(gamble.users)
        else:
            for _u in gamble.users:
                if _u.user_id == 839891608774508575:
                    winner: GambleUser = _u

        loser: GambleUser = discord.utils.find(lambda x: x.user_id != winner.user_id, gamble.users)

        winner.model.balance += amount
        loser.model.balance -= amount

        if loser.model.balance < 0:
            raise PokeBestError("Something went wrong in this gamble session.")

        await winner.model.save()
        await loser.model.save()

        self.bot.dispatch("gamble_end", winner, loser, ctx, amount)

        with suppress(discord.Forbidden, discord.HTTPException):
            return await msg.edit(f"<@{winner.user_id}> won the gamble!", view=None, allowed_mentions=None)

    @commands.Cog.listener()
    async def on_gamble_end(self, winner: GambleUser, loser: GambleUser, ctx: commands.Context, amount: int):
        self.gamble_log_hook: discord.Webhook = discord.Webhook.from_url(
            "https://discord.com/api/webhooks/943076145493073921/FvBKH8Jy5vaLQnhD8dQZdfWZRTAhmCaZzasphX5XVNrQSFKc9EiXbK34gtMVqaqQHPfW",
            session=self.bot.session,
        )

        emb: discord.Embed = self.bot.Embed(title="Gamble ended")
        emb.add_field(name="Winner", value=f"{winner.user_id}")
        emb.add_field(name="Loser", value=f"{loser.user_id}")
        emb.add_field(name="Guild", value=f"{ctx.guild.name} | ID: {ctx.guild.id}")
        emb.add_field(name="Amount", value=str(amount))

        await self.gamble_log_hook.send(embed=emb)

    # TODO: Pokemon Gamble


def setup(bot: PokeBest) -> None:
    bot.add_cog(Gambling(bot))
