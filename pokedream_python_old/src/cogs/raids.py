from __future__ import annotations
import datetime

import discord
from discord.ext import commands, tasks
import typing
from cogs.dueling import Dueling
from core.views import PremiumCatchView

from utils.converters import RaidConverter
from utils.emojis import emojis

if typing.TYPE_CHECKING:
    from core.bot import PokeBest

import random
from utils.checks import has_started
import models
from utils.methods import write_fp
from utils.exceptions import NoRaidGoing
from models.helpers import ArrayAppend
from data import data
from cogs.helpers.battles import Trainer, Battle, BattleEngine, BattleType, Reward
import json
from contextlib import suppress
import itertools
import asyncio

# TODO: Implement Ex-Raid Passes and make raids for different servers too


class Raids(commands.Cog):
    def __init__(self, bot: PokeBest) -> None:
        self.bot: PokeBest = bot

        self.start_or_end_raid.start()
        self.raid_cache: dict = {}
        self._event_dispatched: bool = False

    async def cog_check(self, ctx: commands.Context) -> bool:
        if ctx.guild.id != self.bot.config.SUPPORT_SERVER_ID:
            await ctx.reply(
                f"This command is available for support server only. Use `{ctx.prefix}support` to join support server."
            )
            return False
        return True

    @commands.group(aliases=("raid",))
    @has_started()
    async def raids(self, ctx: commands.Context):
        """All the commands related to raids"""
        if ctx.invoked_subcommand is None:
            return await ctx.send_help(ctx.command)

    async def send_raid_battle(self, ctx: commands.Context, latest_raid: models.Raids):
        # Here the battle starts
        pk1: models.Pokemon = await self.bot.manager.fetch_selected_pokemon(ctx.author.id)
        if pk1 is None:
            return await ctx.reply(f"{ctx.author.mention}, please select a pokemon!", mention_author=False)

        pk2: models.Pokemon = await self.bot.manager.fetch_pokemon_by_id(latest_raid.pkmodel)

        moves: list = data.get_pokemon_moves(pk2.specie["dex_number"])
        move_ids: list = [m["move_id"] for m in moves]

        pk2.moves = move_ids[:4]

        trainer1: Trainer = Trainer(ctx.author, [pk1], 0, pk1, False)
        trainer2: Trainer = Trainer(self.bot.user, [pk2], 0, pk2, True)

        _hp = latest_raid.pokemon_hp or trainer2.selected_pokemon.max_hp

        trainer2.set_hp = latest_raid.pokemon_hp
        trainer2.selected_pokemon.hp = _hp

        msg: discord.Message = await ctx.reply(
            embed=self.bot.Embed(
                title="Starting Raid Battle",
                description="Battle is being loaded, please be patient...",
            ).set_image(
                url="https://cdn.discordapp.com/attachments/890889580021157918/932639980973600818/20220117_194733.gif"
            ),
            mention_author=False,
        )

        with ctx.typing():
            battle: Battle = Battle(
                self.bot,
                ctx,
                [trainer1, trainer2],
                BattleType.oneVone,
                BattleEngine.AI,
                Reward.Raids,
                raid_battle=True,
            )
            battle.raid_battle = True
            self.bot.battles.append(battle)

            await battle.send_battle()
            await msg.delete()

    @raids.command(name="join", aliases=("j",))
    @has_started()
    async def raids_join(self, ctx: commands.Context):
        """Join a ongoing raid"""
        latest_raid: models.Raids = await models.Raids.all().order_by("-id").first()

        if latest_raid is None or latest_raid.is_expired or latest_raid.ended:
            raise NoRaidGoing(ctx)

        if ctx.author.id in latest_raid.members:
            return await ctx.reply("You have already joined this raid.", mention_author=False)

        if len(latest_raid.members) >= 10:
            return await ctx.reply(
                "This raid room is currently full. Please try again in another one.",
                mention_author=False,
            )

        _members: typing.List[int] = latest_raid.members

        latest_raid.members = ArrayAppend("members", ctx.author.id)
        latest_raid.damage_data = json.dumps({**latest_raid.damage_data, ctx.author.id: 0})

        await latest_raid.save()
        # self.raid_cache[f"{ctx.author.id}"] = False

        emb: discord.Embed = self.bot.Embed(title="Raid Information", description="")

        emb.description = (
            f"**Raid Boss:** {data.species_by_num(latest_raid.species_id)['names']['9']}\n"
            + f"**Time Remaining:** {discord.utils.format_dt(latest_raid.start_time + datetime.timedelta(minutes=30))}"
        )

        participants: str = ""
        if len(_members) != 0:
            participants = ", ".join((f"<@{pid}>" for pid in _members))
        else:
            participants = "No one has joined yet."

        emb.add_field(name="Current Participants:", value=participants)

        async with self.bot.session.get(data.species_by_num(latest_raid.species_id)["sprites"]["normal"]) as resp:
            arr = await self.bot.loop.run_in_executor(None, write_fp, await resp.read())
            image: discord.File = discord.File(arr, filename="pokemon.jpg")

            emb.set_thumbnail(url="attachment://pokemon.jpg")

        return await ctx.reply(
            content="You successfully joined the raid!",
            embed=emb,
            mention_author=False,
            file=image,
        )

    @raids.command(name="duel", aliases=("rj", "r", "rejoin"))
    @commands.cooldown(1, 5, commands.BucketType.user)
    @has_started()
    async def raids_duel(self, ctx: commands.Context):
        """Rejoin the raid you were in"""
        battles: Dueling = self.bot.get_cog("Dueling")

        if battles.get_battle(ctx.author.id) is not None:
            return await ctx.reply("You are already in a battle.", mention_author=False)

        latest_raid: typing.Optional[models.Raids] = await models.Raids.all().order_by("-id").first()

        if latest_raid is None or latest_raid.is_expired or latest_raid.ended:
            raise NoRaidGoing(ctx)

        if ctx.author.id not in latest_raid.members:
            return await ctx.reply(
                "You are not in this raid room. Please join the next raid.",
                mention_author=False,
            )

        await self.send_raid_battle(ctx, latest_raid)

    @tasks.loop(seconds=30)
    async def start_or_end_raid(self):
        if self.bot.bot_config is None:
            return

        if self.bot.bot_config.raids_announcement_channel is None or self.bot.bot_config.raids_announcement_role is None:
            return

        latest_raid: typing.Optional[models.Raids] = (
            await models.Raids.all().order_by("-id").first()
        )  # Thinking to add this in cache

        # This condition here is to start a raid
        if latest_raid is None or latest_raid.is_expired:
            if latest_raid is not None and not latest_raid.ended:
                # Here, the raid is ended. The reward distribution and the notification to raiders will be sended
                self.bot.dispatch("raid_finish", latest_raid)
                self._event_dispatched = True

            # Making a rough pokemon model to get access to its stats
            _choice_list: list = []
            if random.randint(1, 100) < 20:
                _choice_list += data.list_gmax
            else:
                _choice_list += data.list_mega

            species: dict = random.choice(_choice_list)

            ## NOTE: Armoured Mewtwo Raid Day
            # species: dict = data.species_by_num(10252)

            _species_id: int = species["species_id"]

            _pk: models.Pokemon = models.Pokemon.get_random(
                species_id=_species_id,
                level=2500,
                owner_id=self.bot.user.id,
                idx=random.randint(1, 100),
                xp=0,
            )
            await _pk.save()

            raid: models.Raids = models.Raids(
                species_id=_species_id,
                pokemon_hp=_pk.max_hp,
                start_time=discord.utils.utcnow(),
                pkmodel=_pk.id,
            )

            self._event_dispatched = False

            # Send the announcement with ping in the raids announcement channel
            channel_id: int = self.bot.bot_config.raids_announcement_channel
            channel: discord.TextChannel = self.bot.get_channel(channel_id) or await self.bot.fetch_channel(channel_id)

            emb: discord.Embed = self.bot.Embed(title="⚔️ Raid Announcement", color=discord.Color.blurple())
            emb.description = (
                "Attention trainers! A new raid has been started. Below is the information about the raid:"
                + f"\n> **Raid Boss:** {_pk}\n> **Time Remaining:** {discord.utils.format_dt(raid.start_time + datetime.timedelta(minutes=30))}"
            )

            emb.add_field(
                name="Rewards",
                value=(
                    f"> Every trainer in the raid will be awarded with {emojis.premium_ball} **Premium Balls** according to the *damage* they delt in raid.\n"
                    + f"> The raid boss will spawn in the dms of the participants and they can catch it with the help of their premium balls.\n"
                    + "> **10,000 credits** for everyone else who took part in raid and are in Top 5 leaderboard."
                ),
            )

            _gmax_species: typing.Optional[int] = data.get_gmax_species(_pk.species_id)
            if _gmax_species is None:
                _gmax_species = _pk.species_id

            async with self.bot.session.get(
                f"{self.bot.config.IMAGE_SERVER_URL}raidannouncement/{_gmax_species}/{_pk.specie['names']['9']}"
            ) as resp:
                arr = await self.bot.loop.run_in_executor(None, write_fp, await resp.read())
                image: discord.File = discord.File(arr, filename="pokemon.jpg")

                emb.set_image(url="attachment://pokemon.jpg")

            msg: discord.Message = await channel.send(
                content=f"<@&{self.bot.bot_config.raids_announcement_role}> {emojis.raids} **Attention Raiders**",
                embed=emb,
                file=image,
            )
            with suppress(discord.HTTPException, discord.Forbidden):
                await msg.publish()

            self.raid_cache = {}
            await raid.save()

    @commands.Cog.listener()
    async def on_raid_finish(self, raid: models.Raids):
        # The handler which handles the reward distribution
        if raid.dispatched or self._event_dispatched:
            return

        # Doing this thing here because of multiple gmax and leaderboard bug. Will find sometihin better later
        self._event_dispatched = True
        raid.dispatched = True

        if isinstance(raid.damage_data, dict):
            damage_data: dict = raid.damage_data
        else:
            damage_data: dict = json.loads(raid.damage_data)
        damage_data = dict(sorted(damage_data.items(), key=lambda x: x[1], reverse=True))

        channel: discord.TextChannel = self.bot.get_channel(
            self.bot.bot_config.raids_announcement_channel
        ) or await self.bot.fetch_channel(self.bot.bot_config.raids_announcement_channel)

        emb: discord.Embed = self.bot.Embed(title="📃Previous Raid Leaderboards:", description="")

        _top_5: dict = dict(itertools.islice(damage_data.items(), 5))

        for idx, (dealer, damage) in enumerate(damage_data.items(), start=1):
            emb.description += f"`0{idx}.` | <@{dealer}> | **Damage**: {damage}\n"

            if raid.ended:
                if damage == 0:
                    continue

                mem: models.Member = await self.bot.manager.fetch_member_info(int(dealer))
                user: discord.User = self.bot.get_user(mem.id) or await self.bot.fetch_user(mem.id)

                if dealer in _top_5:
                    mem.balance += 10000

                    balls: int = 5

                    mem.premium_balls += balls

                    dm_emb: discord.Embed = self.bot.Embed(
                        title="Raid Finished!",
                        description=f"Thanks for participating in the raid! You received {'**10,000 credits** and' if dealer in _top_5 else ''} **{balls} Premium Balls**! You have a chance to catch the raid boss.",
                    )

                    _nos: str = "normal"
                    # if random.randint(1, 25) == 1:
                    #     _nos: str = "shiny"

                    dm_emb.set_image(url=data.species_by_num(raid.species_id)["sprites"][_nos])

                    with suppress(discord.Forbidden, discord.HTTPException):
                        await user.send(embed=dm_emb, view=PremiumCatchView(mem, raid))

                else:
                    dm_emb: discord.Embed = self.bot.Embed(title="Raid Finished!")
                    if random.randint(1, 50) == 5:
                        mem.redeems += 1
                        dm_emb.description = "Thanks for participating in raid! You recieved **1 Redeem**."
                    else:
                        mem.gift += 1
                        dm_emb.description = f"Thanks for participating in raid! You recieved {emojis.gift} **1 Gift**."

                    with suppress(discord.Forbidden, discord.HTTPException):
                        await user.send(embed=dm_emb)

                await mem.save()

        raid.ended = True
        await raid.save()

        await channel.send(embed=emb)

    @commands.Cog.listener()
    async def on_battle_finish(self, battle: Battle, trainer: Trainer, move_emb: discord.Embed):
        # An easy af way to detect if the battle is a raid battle
        async with asyncio.Semaphore(3):
            if battle.reward == Reward.Raids:
                # If the boss wins
                if trainer.is_bot:
                    raider: Trainer = battle._get_another_trainer(trainer.user.id)

                    latest_raid: models.Raids = await models.Raids.all().order_by("-id").first()
                    _damage_data: dict = latest_raid.damage_data

                    _damage_data[str(raider.user.id)] += raider.damage_delt

                    latest_raid.damage_data = json.dumps(_damage_data)
                    latest_raid.pokemon_hp = trainer.selected_pokemon.hp

                    await latest_raid.save()

                else:
                    latest_raid: models.Raids = await models.Raids.all().order_by("-id").first()
                    _damage_data: dict = latest_raid.damage_data

                    _damage_data[str(trainer.user.id)] += trainer.damage_delt

                    latest_raid.damage_data = json.dumps(_damage_data)
                    latest_raid.pokemon_hp = trainer.selected_pokemon.hp

                    latest_raid.ended = True

                    await latest_raid.save()

                    # Clearing all the battles
                    for battle in self.bot.battles:
                        if battle.raid_battle:
                            self.bot.battles.remove(battle)
                            await battle.ctx.send("The raid is ended. Thanks for participating!")

                    self.bot.dispatch("raid_finish", latest_raid)

    @start_or_end_raid.before_loop
    async def before_start_or_end_raid(self):
        await self.bot.wait_until_ready()


def setup(bot: PokeBest) -> None:
    bot.add_cog(Raids(bot))