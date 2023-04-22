from __future__ import annotations
from datetime import timedelta, datetime
import random

import typing

if typing.TYPE_CHECKING:
    from core.bot import PokeBest

from core.views import CustomButtonView, CustomButton
from discord.ext import commands, tasks
from utils.checks import has_started
from data import data
from utils.constants import UTC, SHOP_FORMS, HISUI_POKEMONS
from utils.emojis import emojis
from utils.time import human_timedelta
import discord
import models


class Vote(commands.Cog):
    def __init__(self, bot: PokeBest) -> None:
        self.bot: PokeBest = bot
        self._form_list: list = []

        for _, d in SHOP_FORMS.items():
            self._form_list += d["forms"]
        
        # Adding hisui here
        self._form_list.extend(HISUI_POKEMONS)

    def _get_form_pokemon(self) -> dict:
        return data.species_by_name(random.choice(self._form_list))

    @commands.group(invoke_without_command=True)
    @has_started()
    async def vote(self, ctx: commands.Context):
        """Vote for us!"""
        mem: models.Member = await self.bot.manager.fetch_member_info(ctx.author.id)

        emb: discord.Embed = self.bot.Embed(
            title="Vote Us!",
            description=f"You can vote for us [here]({self.bot.config.TOP_GG_VOTE_LINK}) or by pressing the button below!",
        )

        if (later := mem.last_voted.replace(tzinfo=UTC) + timedelta(hours=12)) < discord.utils.utcnow():
            emb.description += "\n**Vote Timer**: You can vote now!"
            emb.set_thumbnail(
                url="https://media.discordapp.net/attachments/898225841983619123/935891253638348800/AngryPikachu.png"
            )

        else:
            formatted: str = human_timedelta(later)
            emb.description += f"\n**⌚Vote Timer**: Vote again after *{formatted}*."

            emb.set_thumbnail(
                url="https://media.discordapp.net/attachments/898225841983619123/935891253797715999/1528080678pikachu-emoji-pokemon-png.png"
            )

        emb.description += f"\n**🔮 Vote Crystals**: {mem.vote_crystals}"

        emb.add_field(
            name="Vote Streak",
            value=str(emojis.voted) * min(mem.vote_streak, 14)
            + str(emojis.not_voted) * (14 - min(mem.vote_streak, 14))
            + f"\n**Current Streak**: {mem.vote_streak} votes!",
            inline=False,
        )

        view: CustomButtonView = CustomButtonView(
            ctx,
            [
                CustomButton(
                    discord.ButtonStyle.link,
                    "Vote Now!",
                    url=self.bot.config.TOP_GG_VOTE_LINK,
                )
            ],
        )

        emb.add_field(
            name="❓What is vote crystal?",
            value=f"> A special type of crystal which gives you pokemon forms! To obtain them, you just need to vote for us and maintain your voting streak. Higher your streak, higher the number of crystals you get!\n*To use vote crystals, do `{ctx.prefix}vote open` command.*",
            inline=False,
        )

        await ctx.reply(embed=emb, mention_author=False, view=view)

    @vote.command(name="open")
    @commands.cooldown(1, 5, commands.BucketType.user)
    @has_started()
    async def vote_open(self, ctx: commands.Context):
        """Open a vote crystal"""
        mem: models.Member = await self.bot.manager.fetch_member_info(ctx.author.id)

        if mem.vote_crystals <= 0:
            return await ctx.reply(
                f"You don't have any vote crystals! Vote for us by using `{ctx.prefix}vote` command to get some.",
                mention_author=False,
            )

        pk: models.Pokemon = models.Pokemon.get_random(
            species_id=self._get_form_pokemon()["species_id"],
            level=random.randint(15, 70),
            xp=0,
            idx=mem.next_idx,
            owner_id=ctx.author.id,
            shiny=random.randint(1, 4096) == 1,
            timestamp=discord.utils.utcnow(),
        )

        mem.vote_crystals -= 1
        mem.next_idx += 1

        await mem.save()
        await pk.save()

        return await ctx.reply(
            f"You recieved a {self.bot.sprites.get(pk.specie['dex_number'])} **{pk:l}** from vote crystal!",
            mention_author=False,
        )

    @tasks.loop(minutes=10)
    async def send_bot_stats_to_dbl(self):
        ...


def setup(bot: PokeBest) -> None:
    bot.add_cog(Vote(bot))
