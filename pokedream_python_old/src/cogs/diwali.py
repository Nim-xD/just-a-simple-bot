from __future__ import annotations

import discord
from discord.ext import commands
import typing

if typing.TYPE_CHECKING:
    from core.bot import PokeBest

from utils.checks import has_started
from models import models
from data import data
from datetime import datetime
import random
import pickle


async def not_enough_crackers(ctx: commands.Context):
    await ctx.reply("You don't have enough crackers to buy this item!", mention_author=False)


class DiwaliEvent(commands.Cog):
    def __init__(self, bot: PokeBest) -> None:
        self.bot: PokeBest = bot
        self.DIWALI_THEME = 0xFF7300

    class Embed(discord.Embed):
        def __init__(self, *args, **kwargs):
            self.color = 0xFF7300
            super().__init__(color=self.color, *args, **kwargs)

    @commands.group(invoke_without_command=True)
    @has_started()
    async def diwali(self, ctx: commands.Context):
        mem: models.Member = await self.bot.manager.fetch_member_info(ctx.author.id)

        emb: discord.Embed = self.Embed(
            title="🪔 Diwali Shop 🪔",
            description=f"An exclusive shop for you on the occasion of Diwali! Get some new Pokemon and gifts by using crackers. Use `{ctx.prefix}diwali buy <item>` to buy items."
            + f"\n\n**Your crackers:** 🧨 {mem.crackers}",
        )

        items: typing.Dict[str, str] = {
            "Hisuian Zorua": "50 Crackers",
            "Hisuian Growlithe": "50 Crackers",
            "Hisuian Braviary": "50 Crackers",
            "Gift": "10 Crackers",
            "Redeem": "25 Crackers",
        }

        for item, price in items.items():
            emb.add_field(name=item, value=price, inline=True)

        await ctx.reply(embed=emb, mention_author=False)

    @diwali.command(name="buy")
    @has_started()
    async def diwali_buy(self, ctx, *, item: str):  # sourcery no-metrics
        mem: models.Member = await self.bot.manager.fetch_member_info(ctx.author.id)

        if item.lower() == "hisuian zorua":
            if mem.crackers < 50:
                return await not_enough_crackers(ctx)

            species: dict = data.species_by_name("hisuian zorua")

            pokemon: models.Pokemon = models.Pokemon.get_random(
                species_id=species["species_id"],
                level=random.randint(1, 50),
                xp=0,
                owner_id=ctx.author.id,
                timestamp=datetime.now(),
                idx=mem.next_idx,
            )

            await pokemon.save()
            await self.bot.manager.update_idx(ctx.author.id)

            mem.crackers -= 50
            await mem.save()

            return await ctx.reply(
                f"You successfully purchased `{species['names']['9']}`!",
                mention_author=False,
            )

        elif item.lower() == "hisuian growlithe":
            if mem.crackers < 50:
                return await not_enough_crackers(ctx)

            species: dict = data.species_by_name("hisuian growlithe")

            pokemon: models.Pokemon = models.Pokemon.get_random(
                species_id=species["species_id"],
                level=random.randint(1, 50),
                xp=0,
                owner_id=ctx.author.id,
                timestamp=datetime.now(),
                idx=mem.next_idx,
            )

            await pokemon.save()
            await self.bot.manager.update_idx(ctx.author.id)

            mem.crackers -= 50
            await mem.save()

            return await ctx.reply(
                f"You successfully purchased `{species['names']['9']}`!",
                mention_author=False,
            )

        elif item.lower() == "hisuian braviary":
            if mem.crackers < 50:
                return await not_enough_crackers(ctx)

            species: dict = data.species_by_name("hisuian braviary")

            pokemon: models.Pokemon = models.Pokemon.get_random(
                species_id=species["species_id"],
                level=random.randint(1, 50),
                xp=0,
                owner_id=ctx.author.id,
                timestamp=datetime.now(),
                idx=mem.next_idx,
            )

            await pokemon.save()
            await self.bot.manager.update_idx(ctx.author.id)

            mem.crackers -= 50
            await mem.save()

            return await ctx.reply(
                f"You successfully purchased `{species['names']['9']}`!",
                mention_author=False,
            )

        elif item.lower() == "redeem":
            if mem.crackers < 25:
                return await not_enough_crackers(ctx)

            mem.redeems += 1
            mem.crackers -= 25

            await mem.save()

            return await ctx.reply("You successfully purchased a redeem!")

        elif item.lower() == "gift":
            if mem.crackers < 10:
                return await not_enough_crackers(ctx)

            mem.gift += 1
            mem.crackers -= 10

            await mem.save()

            return await ctx.reply("You successfully purchased a gift!")

        else:
            return await ctx.reply("That item doesn't seems to exist in diwali shop.", mention_author=False)


def setup(bot: PokeBest) -> None:
    bot.add_cog(DiwaliEvent(bot))
