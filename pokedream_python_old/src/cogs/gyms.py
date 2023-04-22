from __future__ import annotations
from datetime import datetime, timedelta
import typing

from tortoise import ConfigurationError

from utils.constants import UTC

if typing.TYPE_CHECKING:
    from core.bot import PokeBest

import discord
from discord.ext import commands, tasks
from utils.checks import has_started
from PIL import Image, ImageDraw
from data import data
import models
import config
import requests
from io import BytesIO
from cogs.helpers.battles import Battle, BattleEngine, Trainer, BattleType, Reward
from utils.time import human_timedelta
from contextlib import suppress


class Gyms(commands.Cog):
    def __init__(self, bot: PokeBest) -> None:
        self.bot: PokeBest = bot
        self.TRUSTED_SERVERS = [927565368548016148, 898224376292450374]

        self.check_jammed_gym_battles.start()
        self.reset_gym_collection.start()

    class GymEmbed(discord.Embed):
        def __init__(self, ctx: commands.Context, description: str = "", **kwargs):
            self.set_author(name=f"{ctx.guild.name} Gym", icon_url=ctx.guild.icon.url)
            super().__init__(description=description, color=config.DEFAULT_COLOR, **kwargs)

    async def cog_check(self, ctx: commands.Context) -> bool:
        if ctx.guild.id not in self.TRUSTED_SERVERS and ctx.guild.member_count < 500:
            raise commands.CheckFailure("Gyms are currently available for guilds with more than 500 members.")
        return True

    async def unclaimed_gym(self, ctx: commands.Context):
        emb: discord.Embed = self.bot.Embed(
            title="Unclaimed Gym!",
            description=f"This Gym has no leader currently, please try again later. If you think that you are capable to handle this gym, then you can join the gym as leader by using `{ctx.prefix}gym join` command!",
            color=discord.Color.red(),
        )

        emb.set_author(name=ctx.guild.name, icon_url=ctx.guild.icon.url)

        await ctx.reply(embed=emb, mention_author=False)

    def make_gym_image(self, species_id: int, shiny: bool) -> bytes:
        img: Image = Image.new("RGBA", (320, 300), (25, 0, 0, 0))
        draw: ImageDraw = ImageDraw.Draw(img)

        trainer: Image = Image.open(
            requests.get(
                "https://cdn.discordapp.com/attachments/928198352129126400/935213492401746000/red_pokc3a9monfrlg.png",
                stream=True,
            ).raw
        )

        trainer.thumbnail((200, 200))

        _nos: str = "shiny" if shiny else "normal"
        pk_image: Image = Image.open(requests.get(data.species_by_num(species_id)["sprites"][_nos], stream=True).raw)

        sp: dict = data.species_by_num(species_id)

        if (int(sp["height"]) / 10) >= 2:
            pk_image.thumbnail((230, 230))
            img.paste(pk_image, (90, 50), mask=pk_image)
        else:
            pk_image.thumbnail((180, 180))
            img.paste(pk_image, (90, 110), mask=pk_image)

        img.paste(trainer, (10, 70), mask=trainer)

        img_bytes = BytesIO()
        img.save(img_bytes, "PNG")
        img_bytes.seek(0)

        return img_bytes

    @commands.group(invoke_without_command=True)
    @has_started()
    async def gym(self, ctx: commands.Context):
        """The base command for gyms"""
        if ctx.invoked_subcommand is None:
            return await ctx.send_help(ctx.command)

    @gym.command(name="join")
    @has_started()
    async def gym_join(self, ctx: commands.Context):
        """Join a gym and become its gym leader"""
        gym: typing.Optional[models.Gym] = await models.Gym.get_or_none(guild_id=ctx.guild.id)

        if gym is not None and (leader := gym.gym_leader) is not None:
            return await ctx.reply(
                embed=self.GymEmbed(
                    ctx,
                    f"This gym has <@{leader}> as its leader currently. You can become leader by defeating him/her in a gym battle. To begin battle, you can use `{ctx.prefix}gym battle` command.",
                ),
                mention_author=False,
            )

        mem: models.Member = await self.bot.manager.fetch_member_info(ctx.author.id)
        pk: models.Pokemon = await self.bot.manager.fetch_selected_pokemon(mem.id)

        if pk.specie in list(data.list_gmax + data.list_legendary + data.list_mythical + data.list_ub) or pk.specie[
            "names"
        ]["9"].lower().startswith("gmax "):
            return await ctx.reply(
                "You can't use any Mythical or Legendary pokemon in gyms at this moment.",
                mention_author=False,
            )

        if gym is not None:
            gym.gym_leader = ctx.author.id
            gym.gym_pokemon = mem.selected_id
            gym.gym_leader_since = discord.utils.utcnow()

        else:
            gym: models.Gym = models.Gym(
                gym_leader=ctx.author.id,
                guild_id=ctx.guild.id,
                gym_pokemon=mem.selected_id,
                gym_leader_since=discord.utils.utcnow(),
            )

        await gym.save()

        return await ctx.reply(
            embed=self.GymEmbed(
                ctx,
                f"Congratulations {ctx.author.mention}! You are now the leader of this gym. To leave this post, you can use `{ctx.prefix}gym flee` command. On every defeat, you will be given 💎 *10 Shards*.",
                title="New gym leader!",
            ),
            mention_author=False,
        )

    @gym.command(name="info")
    @has_started()
    async def gym_info(self, ctx: commands.Context):
        """Shows the information about the current gym"""
        gym: typing.Optional[models.Gym] = await models.Gym.get_or_none(guild_id=ctx.guild.id)

        if gym is None or gym.gym_leader is None:
            return await self.unclaimed_gym(ctx)

        gym_pk: models.Pokemon = await models.Pokemon.get(owner_id=gym.gym_leader, idx=gym.gym_pokemon)
        gym_pk.level = 155

        emb: discord.Embed = self.GymEmbed(ctx)
        emb.add_field(
            name="Gym Information",
            value=f"> **Gym Leader:** <@{gym.gym_leader}>\n"
            + f"> **Leader since**: {discord.utils.format_dt(gym.gym_leader_since)}\n"
            + f"> **Defeats**: {len(gym.defeats)}\n",
            inline=False,
        )

        emb.add_field(
            name="Gym Pokemon",
            value=f"**Level:** 100 |  **HP:** {gym_pk.max_hp} | **IV:** {gym_pk.iv_total/186:.2%}",
        )

        img_bytes: bytes = self.make_gym_image(gym_pk.species_id, gym_pk.shiny)
        file: discord.File = discord.File(img_bytes, "gym.png")

        emb.set_image(url="attachment://gym.png")

        emb.set_footer(text="⚠️Note: You can challange the gym leader once!")

        return await ctx.reply(embed=emb, mention_author=False, file=file)

    # @gym.command(name="flee")
    # @has_started()
    async def gym_flee(self, ctx: commands.Context):
        """Flee from Gym Leader post"""
        gym: typing.Optional[models.Gym] = await models.Gym.get_or_none(guild_id=ctx.guild.id)

        if gym is None:
            return await self.unclaimed_gym(ctx)

        if gym.gym_leader != ctx.author.id:
            return await ctx.reply("You are not the gym leader of this gym.", mention_author=False)

        gym.gym_leader = None
        gym.defeats = []

        await gym.save()

        return await ctx.reply("You successfully left the post of Gym leader.", mention_author=False)

    # @gym.command(name="claim")
    # @commands.cooldown(1, 10, commands.BucketType.guild)
    # @has_started()
    # async def gym_claim(self, ctx: commands.Context):
    #     """Claim your daily shards"""
    #     gym: typing.Optional[models.Gym] = await models.Gym.get_or_none(guild_id=ctx.guild.id)

    #     if gym is None:
    #         return await self.unclaimed_gym(ctx)

    #     if gym.gym_leader != ctx.author.id:
    #         return await ctx.reply("You are not the gym leader of this gym.", mention_author=False)

    #     if len(gym.defeats) < 10:
    #         return await ctx.reply(
    #             f"You can't claim shards right now. Your pokemon need to defend you against {10 - len(gym.defeats)} competitors.",
    #             mention_author=False,
    #         )

    #     # if (gym.salary_collect_time.replace(tzinfo=UTC) + timedelta(hours=24)) > discord.utils.utcnow():
    #     #     return await ctx.reply(
    #     #         f"You can claim your shards in **{human_timedelta(gym.salary_collect_time + timedelta(hours=24))}**.",
    #     #         mention_author=False,
    #     #     )

    #     mem: models.Member = await self.bot.manager.fetch_member_info(ctx.author.id)

    #     mem.shards += 200
    #     await mem.save()

    #     gym.salary_collect_time = discord.utils.utcnow()
    #     gym.gym_leader = None
    #     gym.defeats = []

    #     await gym.save()

    #     return await ctx.reply("You successfully claimed your daily shards.", mention_author=False)

    @gym.command(name="battle")
    @commands.cooldown(1, 10, commands.BucketType.user)
    @has_started()
    async def gym_battle(self, ctx: commands.Context):
        """Battle with gym leader"""
        gym: typing.Optional[models.Gym] = await models.Gym.get_or_none(guild_id=ctx.guild.id)

        if gym is None:
            return await self.unclaimed_gym(ctx)

        if gym.gym_leader == ctx.author.id:
            return await ctx.reply(
                "You are the leader of gym, you can't battle yourself.",
                mention_author=False,
            )

        if ctx.author.id in gym.defeats:
            return await ctx.reply("You were already defeated by gym leader.", mention_author=False)

        for b in self.bot.battles:
            if b.reward == Reward.Gym and b.ctx.guild.id == ctx.guild.id:
                return await ctx.reply(
                    "The leader is already in a battle with someone else. Please try again later.",
                    mention_author=False,
                )

        pk2: models.Pokemon = await models.Pokemon.get(owner_id=gym.gym_leader, idx=gym.gym_pokemon)

        pk2.level = 155
        pk2sp = data.species_by_num(pk2.species_id)
        pk1: models.Pokemon = await self.bot.manager.fetch_selected_pokemon(ctx.author.id)

        if pk1 is None:
            return await ctx.reply(f"{ctx.author.mention}, please select a pokemon!", mention_author=False)

        if pk1.specie in list(data.list_gmax + data.list_legendary + data.list_mythical + data.list_ub) or pk1.specie[
            "names"
        ]["9"].lower().startswith("gmax "):
            return await ctx.reply(
                "You can't use any Mythical or Legendary pokemon in gyms at this moment.",
                mention_author=False,
            )

        await ctx.reply(
            f"You took out your {self.bot.sprites.get(pk1.species_id, pk1.shiny)} **{pk1}** and <@{gym.gym_leader}> takes out his {self.bot.sprites.get(pk2sp['species_id'])} **{pk2sp['names']['9']}**...",
            mention_author=False,
            allowed_mentions=discord.AllowedMentions(users=False),
        )

        moves: list = data.get_pokemon_moves(pk2.species_id)
        if not moves:
            moves: list = data.get_pokemon_moves(pk2.specie["dex_number"])
        move_ids: list = [m["move_id"] for m in moves]

        pk2.moves = move_ids[:4]

        trainer1: Trainer = Trainer(ctx.author, [pk1], 0, pk1, False)
        trainer2: Trainer = Trainer(self.bot.user, [pk2], 0, pk2, True)

        msg: discord.Message = await ctx.reply("Battle is being loaded...", mention_author=False)

        with ctx.typing():
            battle: Battle = Battle(
                self.bot,
                ctx,
                [trainer1, trainer2],
                BattleType.oneVone,
                BattleEngine.AI,
                Reward.Gym,
            )
            self.bot.battles.append(battle)

            await battle.send_battle()
            await msg.delete()

    @commands.Cog.listener()
    async def on_member_leave(self, member: discord.Member):
        gym: typing.Optional[models.Gym] = await models.Gym.get_or_none(guild_id=member.guild.id, gym_leader=member.id)
        if gym is not None:
            gym.gym_leader = None
            gym.gym_pokemon = None
            await gym.save()

    @tasks.loop(seconds=10)
    async def check_jammed_gym_battles(self):
        await self.bot.wait_until_ready()

        for b in self.bot.battles:
            if b.reward == Reward.Gym and (datetime.utcnow() - b.last_modified).seconds > 120:
                with suppress(Exception):
                    await b.ctx.send("Battle timed out! Failed to use move.")
                self.bot.battles.remove(b)

    @tasks.loop(hours=24)
    async def reset_gym_collection(self):
        await self.bot.wait_until_ready()
        with suppress(ConfigurationError):
            gyms = await models.Gym.all()
            for gym in gyms:
                gym.collected_shards = 0
                await gym.save()


def setup(bot: PokeBest) -> None:
    bot.add_cog(Gyms(bot))
