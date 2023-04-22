from __future__ import annotations
from datetime import timedelta

import discord
from discord import interactions
from discord.enums import ButtonStyle
from discord.ext import commands
import typing
import models
import random

from data import data
from cogs.helpers.battles import Reward, Trainer, Battle, BattleType, BattleEngine

if typing.TYPE_CHECKING:
    from core.bot import PokeBest


class SantaView(discord.ui.View):
    def __init__(self, ctx: commands.Context, timeout: float = 120.0):
        self.ctx: commands.Context = ctx

        super().__init__(timeout=timeout)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("This interaction is not for you.", ephemeral=True)
            return False

        return True

    @discord.ui.button(label="Fight", emoji="⚔", style=ButtonStyle.blurple)
    async def fight_button(self, _button: discord.Button, _interaction: discord.Interaction):
        await _interaction.response.send_message("Santa takes out his Delibird....")
        self.stop()
        pk1: models.Pokemon = await self.ctx.bot.manager.fetch_selected_pokemon(self.ctx.author.id)
        if pk1 is None:
            return await self.ctx.reply(
                f"{self.ctx.author.mention}, please select a pokemon!",
                mention_author=False,
            )

        pk2sp = data.pokemon_data[224]
        pk2: models.Pokemon = models.Pokemon.get_random(
            owner_id=None, species_id=pk2sp["species_id"], level=150, idx=1, xp=0
        )

        moves: list = data.get_pokemon_moves(pk2.species_id)
        move_ids: list = [m["move_id"] for m in moves]

        pk2.moves = move_ids[:4]
        self.ctx.bot.user.name = "Santa Claus"

        trainer1: Trainer = Trainer(self.ctx.author, [pk1], 0, pk1, False)
        trainer2: Trainer = Trainer(self.ctx.bot.user, [pk2], 0, pk2, True)

        msg: discord.Message = await self.ctx.reply("Battle is being loaded...", mention_author=False)

        with self.ctx.typing():
            battle: Battle = Battle(
                self.ctx.bot,
                self.ctx,
                [trainer1, trainer2],
                BattleType.oneVone,
                BattleEngine.AI,
                Reward.Christmas,
            )
            self.ctx.bot.battles.append(battle)

            await battle.send_battle()
            await msg.delete()


class Christmas(commands.Cog):
    def __init__(self, bot: PokeBest) -> None:
        self.bot: PokeBest = bot

    @commands.Cog.listener()
    async def on_catch(self, ctx: commands.Context, pokemon: models.Pokemon):
        catch_streak: typing.Optional[str] = await self.bot.redis.get(f"streak:member:{ctx.author.id}", encoding="utf-8")

        if catch_streak is not None:
            catch_streak: int = int(catch_streak)

        if catch_streak is None:
            await self.bot.redis.set(f"streak:member:{ctx.author.id}", "1")
            catch_streak = 1

        else:
            await self.bot.redis.set(f"streak:member:{ctx.author.id}", str(catch_streak + 1))

        if int(catch_streak) % random.randint(15, 25) == 0:
            emb: discord.Embed = self.bot.Embed(
                title="You have been naughty!",
                description=f"{ctx.author.mention}, You have been challenged by 🎅 Santa!",
                color=0xFF0000,
            )

            emb.set_image(
                url="https://cdn.discordapp.com/attachments/899496727575396372/920362860226420757/20211214_224315.jpg"
            )

            emb.set_footer(text="❄️ Beating Santa rewards you 50 shards!")

            await ctx.reply(embed=emb, view=SantaView(ctx), mention_author=False)

    @commands.Cog.listener()
    async def on_battle_finish(self, battle: Battle, trainer: Trainer, move_emb: discord.Embed):
        if battle.battle_engine == BattleEngine.AI:
            if (tr := battle._get_trainer_by_id(self.bot.user.id)) is not None:
                if tr.pokemon[0].species_id == 225 and tr.pokemon[0].level == 150:
                    ...


def setup(bot: PokeBest) -> None:
    bot.add_cog(Christmas(bot))
