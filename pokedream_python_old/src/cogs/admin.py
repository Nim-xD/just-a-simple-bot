from __future__ import annotations
from datetime import datetime

from discord.ext.commands.converter import (
    GuildConverter,
    TextChannelConverter,
    RoleConverter,
)
import models

from discord.ext import commands, tasks
import discord
import typing

from utils.methods import split_args

if typing.TYPE_CHECKING:
    from core.bot import PokeBest

from utils.converters import SpeciesConverter, TrainerConverter
from core.views import Confirm, SpawnDuelView
from contextlib import suppress
from config import OWNERS
from argparse import ArgumentParser
from utils.exceptions import PokeBestError
import random
from utils import constants
from typing import List, Optional
from data import data
import config
import pickle


class ArgParser(ArgumentParser):
    def error(self, message):
        raise PokeBestError(message)


class Admin(commands.Cog):
    def __init__(self, bot: PokeBest) -> None:
        self.bot: PokeBest = bot

        self.send_normal_spawn.start()

    def __str__(self) -> str:
        return "Admin"

    async def cog_check(self, ctx: commands.Context) -> bool:
        if ctx.author.id in self.bot.bot_config.admins or ctx.author.id in OWNERS:
            return True

        raise commands.CheckFailure("You are not an admin of this bot.")

    @commands.command()
    async def givebal(self, ctx: commands.Context, mem: TrainerConverter, bal: int):
        """Give balance to a member"""
        if mem is None:
            return await ctx.reply(
                "Sorry, that member didn't picked any starter yet!",
                mention_author=False,
            )

        confirm_view: Confirm = Confirm(ctx)
        msg: discord.Message = await ctx.reply(
            f"Are you sure you want to give {mem.name} {bal} credits?",
            mention_author=False,
            view=confirm_view,
        )

        await confirm_view.wait()

        if confirm_view.value is None:
            with suppress(discord.Forbidden, discord.HTTPException):
                return await msg.edit("Time's up!", view=None, allowed_mentions=None)

        if confirm_view.value is False:
            with suppress(discord.Forbidden, discord.HTTPException):
                return await msg.edit("Action aborted!", view=None, allowed_mentions=None)

        with ctx.typing():
            member: models.Member = await self.bot.manager.fetch_member_info(mem.id)
            member.balance += bal
            await member.save()

        with suppress(discord.Forbidden, discord.HTTPException):
            return await msg.edit("Successfully gave credits!", view=None, allowed_mentions=None)

    @commands.command()
    async def giveshards(self, ctx: commands.Context, mem: TrainerConverter, shards: int):
        """Give shards to a member"""
        if mem is None:
            return await ctx.reply(
                "Sorry, that member didn't picked any starter yet!",
                mention_author=False,
            )

        confirm_view: Confirm = Confirm(ctx)
        msg: discord.Message = await ctx.reply(
            f"Are you sure you want to give {mem.name} {shards} shards?",
            mention_author=False,
            view=confirm_view,
        )

        await confirm_view.wait()

        if confirm_view.value is None:
            with suppress(discord.Forbidden, discord.HTTPException):
                return await msg.edit("Time's up!", view=None, allowed_mentions=None)

        if confirm_view.value is False:
            with suppress(discord.Forbidden, discord.HTTPException):
                return await msg.edit("Action aborted!", view=None, allowed_mentions=None)

        with ctx.typing():
            member: models.Member = await self.bot.manager.fetch_member_info(mem.id)
            member.shards += shards
            await member.save()

        with suppress(discord.Forbidden, discord.HTTPException):
            return await msg.edit("Successfully gave shards!", view=None, allowed_mentions=None)

    @commands.command()
    async def giveredeems(self, ctx: commands.Context, mem: TrainerConverter, redeems: int):
        """Give redeems to a member"""
        if mem is None:
            return await ctx.reply(
                "Sorry, that member didn't picked any starter yet!",
                mention_author=False,
            )

        confirm_view: Confirm = Confirm(ctx)
        msg: discord.Message = await ctx.reply(
            f"Are you sure you want to give {mem.name} {redeems} redeems?",
            mention_author=False,
            view=confirm_view,
        )

        await confirm_view.wait()

        if confirm_view.value is None:
            with suppress(discord.Forbidden, discord.HTTPException):
                return await msg.edit("Time's up!", view=None, allowed_mentions=None)

        if confirm_view.value is False:
            with suppress(discord.Forbidden, discord.HTTPException):
                return await msg.edit("Action aborted!", view=None, allowed_mentions=None)

        with ctx.typing():
            member: models.Member = await self.bot.manager.fetch_member_info(mem.id)
            member.redeems += redeems
            await member.save()

        with suppress(discord.Forbidden, discord.HTTPException):
            return await msg.edit("Successfully gave redeems!", view=None, allowed_mentions=None)

    @commands.command()
    async def suspend(
        self,
        ctx: commands.Context,
        mem: TrainerConverter,
        *,
        reason: typing.Optional[str] = None,
    ):
        """Suspend a trainer"""
        if mem is None:
            return await ctx.reply(
                "Sorry, that member didn't picked any starter yet!",
                mention_author=False,
            )

        confirm_view: Confirm = Confirm(ctx)
        msg: discord.Message = await ctx.reply(
            "Are you sure you want to blacklist that member?",
            mention_author=False,
            view=confirm_view,
        )

        await confirm_view.wait()

        if confirm_view.value is None:
            with suppress(discord.Forbidden, discord.HTTPException):
                return await msg.edit("Time's up!", view=None, allowed_mentions=None)

        if confirm_view.value is False:
            with suppress(discord.Forbidden, discord.HTTPException):
                return await msg.edit("Action aborted!", view=None, allowed_mentions=None)

        with ctx.typing():
            member: models.Member = await self.bot.manager.fetch_member_info(mem.id)

            member.suspended = True
            if reason is not None:
                member.suspended_reason = reason

            await member.save()

        with suppress(discord.Forbidden, discord.HTTPException):
            return await msg.edit("Successfully suspened member!", view=None, allowed_mentions=None)

    @commands.command()
    async def unsuspend(self, ctx: commands.Context, mem: TrainerConverter):
        """Suspend a trainer"""
        if mem is None:
            return await ctx.reply(
                "Sorry, that member didn't picked any starter yet!",
                mention_author=False,
            )

        confirm_view: Confirm = Confirm(ctx)
        msg: discord.Message = await ctx.reply(
            "Are you sure you want to unsuspend that member?",
            mention_author=False,
            view=confirm_view,
        )

        await confirm_view.wait()

        if confirm_view.value is None:
            with suppress(discord.Forbidden, discord.HTTPException):
                return await msg.edit("Time's up!", view=None, allowed_mentions=None)

        if confirm_view.value is False:
            with suppress(discord.Forbidden, discord.HTTPException):
                return await msg.edit("Action aborted!", view=None, allowed_mentions=None)

        with ctx.typing():
            member: models.Member = await self.bot.manager.fetch_member_info(mem.id)

            member.suspended = False

            await member.save()

        with suppress(discord.Forbidden, discord.HTTPException):
            return await msg.edit("Successfully unsuspened member!", view=None, allowed_mentions=None)

    @commands.command()
    async def pokemon_add(self, ctx: commands.Context, user: TrainerConverter, *, args: str):
        """Byaku's favorite command"""
        parser: ArgParser = ArgParser(add_help=False, allow_abbrev=False)
        parser.add_argument("--name", nargs="+")
        parser.add_argument("--level", type=int)
        parser.add_argument("--shiny", action="store_true")
        parser.add_argument("--hp", type=int)
        parser.add_argument("--atk", type=int)
        parser.add_argument("--satk", type=int)
        parser.add_argument("--sdef", type=int)
        parser.add_argument("--speed", type=int)
        parser.add_argument("--defn", type=int)
        parser.add_argument("--xp", type=int)

        def random_iv():
            return random.randint(0, 31)

        args = parser.parse_args(split_args(args))
        count: int = (await self.bot.manager.fetch_pokemon_list(user.id)).__len__()

        if not args.name:
            return await ctx.reply("Name must be provided!", mention_author=False)

        pokemon = await SpeciesConverter().convert(ctx, " ".join(x for x in args.name))
        if pokemon is None:
            return await ctx.reply("There is no pokemon available with such name.", mention_author=False)

        level: int = random.randint(1, 30) if not args.level else args.level

        shiny: bool = args.shiny

        hp: int = random_iv() if not args.hp else args.hp
        atk: int = random_iv() if not args.atk else args.atk
        satk: int = random_iv() if not args.satk else args.satk
        sdef: int = random_iv() if not args.sdef else args.sdef
        speed: int = random_iv() if not args.speed else args.speed
        defn: int = random_iv() if not args.defn else args.defn
        xp: int = random_iv() if not args.xp else args.xp

        def random_nature():
            return random.choice(constants.NATURES[1:])

        _idx: int = await self.bot.manager.get_next_idx(user.id)
        pk = models.Pokemon(
            owner_id=user.id,
            level=level,
            iv_hp=hp,
            iv_atk=atk,
            iv_defn=defn,
            iv_spd=speed,
            iv_sdef=sdef,
            iv_satk=satk,
            species_id=pokemon["species_id"],
            nature=random_nature(),
            timestamp=datetime.utcnow(),
            iv_total=hp + atk + defn + speed + sdef + satk,
            idx=_idx,
            xp=xp,
            shiny=shiny,
        )

        embed: discord.Embed = self.bot.Embed(color=pk.normal_color, title=f"{pk:l}")
        embed.set_thumbnail(url=pk.normal_image)
        embed.description = "\n".join(pk.get_stats)

        _view: Confirm = Confirm(ctx)
        msg: discord.Message = await ctx.reply(embed=embed, mention_author=False, view=_view)

        await _view.wait()
        if not _view.value:
            with suppress(discord.Forbidden, discord.HTTPException):
                return await msg.edit("Aborted", view=None, embed=None)

        await pk.save()
        await self.bot.manager.update_idx(user.id)

        with suppress(discord.Forbidden, discord.HTTPException):
            return await msg.edit("Added successfully!", view=None, embed=None)

    @commands.command()
    async def hostevent(self, ctx: commands.Context):
        """Host event"""

        def msg_check(m: discord.Message) -> bool:
            return m.author.id == ctx.author.id

        await ctx.send("Enter the description of event.")
        desc_msg: discord.Message = await self.bot.wait_for("message", check=msg_check, timeout=120)
        desc: str = desc_msg.content

        await ctx.send("Enter the title of event.")
        title_msg: discord.Message = await self.bot.wait_for("message", check=msg_check, timeout=120)
        title: str = title_msg.content

        await ctx.send("Enter event thumbnail.\nEnter `None` for nothing.")
        thumb_msg: discord.Message = await self.bot.wait_for("message", check=msg_check, timeout=120)
        thumb: str = thumb_msg.content if thumb_msg.content.lower() != "none" else None

        await ctx.send("Enter event image.\nEnter `None` for nothing,")
        image_msg: discord.Message = await self.bot.wait_for("message", check=msg_check, timeout=120)
        image: str = image_msg.content if image_msg.content.lower() != "none" else None

        confirm_view: Confirm = Confirm(ctx)
        msg: discord.Message = await ctx.reply(
            "Are you sure you want to host this event?",
            mention_author=False,
            view=confirm_view,
        )

        await confirm_view.wait()

        if confirm_view.value is None:
            with suppress(discord.Forbidden, discord.HTTPException):
                return await msg.edit("Time's up!", view=None, allowed_mentions=None)

        if confirm_view.value is False:
            with suppress(discord.Forbidden, discord.HTTPException):
                return await msg.edit("Action aborted!", view=None, allowed_mentions=None)

        with ctx.typing():
            bot_config: models.BotConfig = self.bot.bot_config
            bot_config.event_title = title
            bot_config.event_txt = desc
            bot_config.event_image = image
            bot_config.event_thumbnail = thumb

        await bot_config.save()

        with suppress(discord.Forbidden, discord.HTTPException):
            return await msg.edit("Event hosted successfully!", view=None, allowed_mentions=None)

    @commands.command()
    async def endevent(self, ctx: commands.Context):
        """End an ongoing event"""
        if self.bot.bot_config.event_txt is None:
            return await ctx.reply("There are no ongoing events!", mention_author=False)

        confirm_view: Confirm = Confirm(ctx)
        msg: discord.Message = await ctx.reply(
            "Are you sure you want to end this event?",
            mention_author=False,
            view=confirm_view,
        )

        await confirm_view.wait()

        if confirm_view.value is None:
            with suppress(discord.Forbidden, discord.HTTPException):
                return await msg.edit("Time's up!", view=None, allowed_mentions=None)

        if confirm_view.value is False:
            with suppress(discord.Forbidden, discord.HTTPException):
                return await msg.edit("Action aborted!", view=None, allowed_mentions=None)

        with ctx.typing():
            bot_config: models.BotConfig = self.bot.bot_config
            bot_config.event_title = None
            bot_config.event_txt = None
            bot_config.event_image = None
            bot_config.event_thumbnail = None

        await bot_config.save()

        with suppress(discord.Forbidden, discord.HTTPException):
            return await msg.edit("Event ended successfully!", view=None, allowed_mentions=None)

    @commands.command()
    async def blacklist(self, ctx: commands.Context, guild: GuildConverter, *, reason: str = None):
        """Blacklist a guild"""
        reason: str = reason or "No reason given."

        if guild not in self.bot.guilds:
            return await ctx.reply("Bot is not present in that guild!", mention_author=False)

        confirm_view: Confirm = Confirm(ctx)
        msg: discord.Message = await ctx.reply(
            "Are you sure you want to blacklist that guild?",
            mention_author=False,
            view=confirm_view,
        )

        await confirm_view.wait()

        if confirm_view.value is None:
            with suppress(discord.Forbidden, discord.HTTPException):
                return await msg.edit("Time's up!", view=None, allowed_mentions=None)

        if confirm_view.value is False:
            with suppress(discord.Forbidden, discord.HTTPException):
                return await msg.edit("Action aborted!", view=None, allowed_mentions=None)

        g: models.Guild = await models.Guild.get_or_create(id=guild.id)

        if guild.owner is not None:
            with suppress(discord.HTTPException, discord.Forbidden):
                await guild.owner.send(
                    embed=self.bot.Embed(
                        color=discord.Color.red(),
                        title="❌ Guild Blacklisted!",
                        description=f"This is to inform you that your server **{guild.name}** has been blacklisted from using this bot."
                        + f"If you think this is a mistake or you want to appeal for unsuspension then consider joining our [support server]({config.SUPPORT_SERVER_LINK})!",
                    ).add_field(name="Reason", value=reason)
                )

        await guild.leave()
        g[0].blacklisted = True
        await g[0].save()

        self.bot.cache.guilds[f"{ctx.guild.id}"] = await models.Guild.get(id=guild.id)

        with suppress(discord.Forbidden, discord.HTTPException):
            return await msg.edit("Successfully blacklisted that guild!", view=None, allowed_mentions=None)

    @commands.command()
    async def unblacklist(self, ctx: commands.Context, guild: GuildConverter):
        """Unblacklist a guild"""
        if guild not in self.bot.guilds:
            return await ctx.reply("Bot is not present in that guild!", mention_author=False)

        g: models.Guild = await models.Guild.get_or_create(id=guild.id)
        if g[0].blacklisted is False:
            return await ctx.reply("That guild isn't blackisted!", mention_author=False)

        confirm_view: Confirm = Confirm(ctx)
        msg: discord.Message = await ctx.reply(
            "Are you sure you want to unblacklist that guild?",
            mention_author=False,
            view=confirm_view,
        )

        await confirm_view.wait()

        if confirm_view.value is None:
            with suppress(discord.Forbidden, discord.HTTPException):
                return await msg.edit("Time's up!", view=None, allowed_mentions=None)

        if confirm_view.value is False:
            with suppress(discord.Forbidden, discord.HTTPException):
                return await msg.edit("Action aborted!", view=None, allowed_mentions=None)

        g[0].blacklisted = False
        await g[0].save()

        self.bot.cache.guilds[f"{ctx.guild.id}"] = await models.Guild.get(id=guild.id)

        with suppress(discord.Forbidden, discord.HTTPException):
            return await msg.edit(
                "Successfully unblacklisted that guild!",
                view=None,
                allowed_mentions=None,
            )

    @tasks.loop(minutes=1)
    async def send_normal_spawn(self):
        spawn_channels: List[discord.TextChannel] = []

        for chid in self.bot.bot_config.normal_spawns:
            try:
                channel = self.bot.get_channel(chid) or (await self.bot.fetch_channel(chid))
            except (discord.NotFound, discord.HTTPException):
                channel = None

            if channel is not None:
                spawn_channels.append(channel)

        for channel in spawn_channels:
            if channel is None:
                continue

            _species = data.random_pokemon()

            message: Optional[discord.Message] = channel.last_message

            if message is not None:
                _ctx: commands.Context = await self.bot.get_context(message)
                spawn_duel: SpawnDuelView = SpawnDuelView(
                    self.bot, _ctx, message.channel, _species.__getitem__("species_id")
                )

                self.bot.dispatch(
                    "spawn",
                    message.channel,
                    species_id=_species["species_id"],
                    redeemed=False,
                    member=message.author,
                    spawn_duel=spawn_duel,
                )

            else:
                self.bot.dispatch("spawn", channel, species_id=_species["species_id"])

    @send_normal_spawn.before_loop
    async def before_send_normal_spawn(self):
        await self.bot.wait_until_ready()

    @commands.command()
    async def raidchannel(self, ctx: commands.Context, channel: TextChannelConverter):
        """Set the current raid announcement channel"""
        if channel is None:
            return await ctx.reply("Invalid channel!", mention_author=False)

        if channel.id == self.bot.bot_config.raids_announcement_channel:
            return await ctx.reply("That channel is already a raid channel!", mention_author=False)

        self.bot.bot_config.raids_announcement_channel = channel.id
        await self.bot.bot_config.save()

        with suppress(discord.HTTPException):
            return await ctx.reply(
                f"Successfully added {channel.mention} as raid announcement channel!",
                mention_author=False,
            )

    @commands.command()
    async def raidping(self, ctx: commands.Context, role: RoleConverter):
        """Set the role to ping for raids"""
        if role is None:
            return await ctx.reply("Please provide a valid role.", mention_author=False)

        if role.id == self.bot.bot_config.raids_announcement_role:
            return await ctx.reply("That role is already a raid ping role!", mention_author=False)

        self.bot.bot_config.raids_announcement_role = role.id
        await self.bot.bot_config.save()

        with suppress(discord.HTTPException, discord.Forbidden):
            return await ctx.reply(
                "Successfully set that role to raid announcement role!",
                mention_author=False,
            )


def setup(bot: PokeBest):
    bot.add_cog(Admin(bot))


def teardown(bot: PokeBest) -> Admin:
    cog: Admin = Admin(bot)
    cog.send_normal_spawn.stop()

    bot.remove_cog(cog)
