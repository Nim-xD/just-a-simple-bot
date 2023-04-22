from __future__ import annotations
from contextlib import suppress

from discord.ext import commands
import discord
import typing

from discord.ext.commands.converter import TextChannelConverter

if typing.TYPE_CHECKING:
    from core.bot import PokeBest, embed_color

from config import OWNERS
import models
from models.helpers import ArrayAppend, ArrayRemove
from core.views import Confirm
from data import data
from utils.converters import TrainerConverter


class Owner(commands.Cog):
    def __init__(self, bot: PokeBest) -> None:
        self.bot: PokeBest = bot

    async def cog_check(self, ctx: commands.Context) -> bool:
        if ctx.author.id in OWNERS:
            return True

        raise commands.CheckFailure("This command is for owners only.")

    @commands.group()
    async def admin(self, ctx: commands.Context):
        """Admin related commands bitch"""
        if ctx.invoked_subcommand is None:
            return await ctx.send_help(ctx.command)

    @admin.command(name="add")
    async def admin_add(self, ctx: commands.Context, mem: typing.Union[discord.User, discord.Member]):
        """Add admin in the bot data"""
        confirm_view: Confirm = Confirm(ctx)
        msg: discord.Message = await ctx.reply(
            f"Are you sure you want to add {mem.mention} as bot's admin?",
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

            bot_config.admins = ArrayAppend("admins", mem.id)
            await bot_config.save()

            self.bot.bot_config = (await models.BotConfig.all())[0]

        with suppress(discord.Forbidden, discord.HTTPException):
            return await msg.edit("Successfully added as admin!", view=None, allowed_mentions=None)

    @admin.command(name="remove")
    async def admin_remove(self, ctx: commands.Context, mem: typing.Union[discord.User, discord.Member]):
        """Remove bot admin"""
        bot_config = self.bot.bot_config

        current_admins: typing.List[int] = bot_config.admins

        if mem.id not in current_admins:
            return await ctx.reply("That member is not in admins of bot.", mention_author=False)

        confirm_view: Confirm = Confirm(ctx)
        msg: discord.Message = await ctx.reply(
            f"Are you sure you want to remove {mem.mention} as bot's admin?",
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

        bot_config.admins = ArrayRemove("admins", mem.id)
        await bot_config.save()

        self.bot.bot_config = (await models.BotConfig.all())[0]

        with suppress(discord.Forbidden, discord.HTTPException):
            return await msg.edit(
                "Successfully removed member from bot admin permissions!",
                view=None,
                allowed_mentions=None,
            )

    @commands.command()
    async def setnews(self, ctx: commands.Context, *, news: str):
        """Change the bot news"""
        bot_config = self.bot.bot_config

        confirm_view: Confirm = Confirm(ctx)
        msg: discord.Message = await ctx.reply(
            "Are you sure you want to change bot news?",
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

        bot_config.bot_news = news
        await bot_config.save()

        self.bot.bot_config = (await models.BotConfig.all())[0]

        with suppress(discord.Forbidden, discord.HTTPException):
            return await msg.edit("Successfully changed bot news!", view=None, allowed_mentions=None)

    @commands.group(invoke_without_command=True)
    async def normalspawn(self, ctx: commands.Context, channel: TextChannelConverter):
        """Add a channel to auto spawn"""
        confirm_view: Confirm = Confirm(ctx)
        msg: discord.Message = await ctx.reply(
            f"Are you sure you want to add <#{channel.id}> in auto spawns?",
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

        if channel.id in self.bot.bot_config.normal_spawns:
            return await ctx.reply("That channel already have spawns enabled!", mention_author=False)

        with ctx.typing():
            bot_config: models.BotConfig = self.bot.bot_config

            bot_config.normal_spawns = ArrayAppend("normal_spawns", channel.id)
            await bot_config.save()

            self.bot.bot_config = (await models.BotConfig.all())[0]

        with suppress(discord.Forbidden, discord.HTTPException):
            return await msg.edit(
                "Successfully added channel in auto spawns!",
                view=None,
                allowed_mentions=None,
            )

    @normalspawn.command(name="remove")
    async def normalspawn_remove(self, ctx: commands.Context, channel: TextChannelConverter):
        """Add a channel to auto spawn"""
        if channel.id not in self.bot.bot_config.normal_spawns:
            return await ctx.reply("That channel doesn't have spawns enabled!", mention_author=False)

        confirm_view: Confirm = Confirm(ctx)
        msg: discord.Message = await ctx.reply(
            f"Are you sure you want to remove <#{channel.id}> from auto spawns?",
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

            bot_config.normal_spawns = ArrayRemove("normal_spawns", channel.id)
            await bot_config.save()

            self.bot.bot_config = (await models.BotConfig.all())[0]

        with suppress(discord.Forbidden, discord.HTTPException):
            return await msg.edit(
                "Successfully removed channel from auto spawns!",
                view=None,
                allowed_mentions=None,
            )

    @commands.command()
    async def clearcache(self, ctx: commands.Context):
        """Clears bot cache"""
        confirm_view: Confirm = Confirm(ctx)
        msg: discord.Message = await ctx.reply(
            "Are you sure you want to clear cache of bot?\n⚠️ **Note:** This *can* effect the bot's performance!",
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

        methods: list = [
            data.species_by_num,
            data.species_by_name,
            data.specie_color,
            data.item_by_name,
            data.item_by_id,
            data.machine_by_number,
            data.pokemon_evolution_data,
            data.move_by_id,
            data.move_by_name,
            data.get_pokemon_moves,
            data.get_move_machines,
        ]

        for m in methods:
            m.cache_clear()

        with suppress(discord.Forbidden, discord.HTTPException):
            return await msg.edit("Successfully cleared all cache!", view=None, allowed_mentions=None)

    # @commands.command()
    async def changecolor(self, ctx: commands.Context, color):
        """Change bot's embed color"""
        try:
            clr = int(color, 16)
        except BaseException:
            return await ctx.reply("Please provide a valid hex value!", mention_author=False)

        self.bot.bot_config.embed_color = clr
        await self.bot.bot_config.save()

        embed_color = clr

        return await ctx.reply("Successfully changed the embed color!", mention_author=False)

    @commands.command()
    async def resetaccount(self, ctx: commands.Context, trainer: TrainerConverter):
        """Reset someone's account. ⚠️ **Warning:** This command can **not** be undone!"""
        user: discord.User = self.bot.get_user(trainer.id) or await self.bot.fetch_user(trainer.id)

        confirm_view: Confirm = Confirm(ctx)
        msg: discord.Message = await ctx.reply(
            f"Are you sure you want to *reset* `{user}`'s account?\n⚠️ **Warning:** This command can **not** be undone!",
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

        await msg.edit("This process takes time. Please wait...", view=None, allowed_mentions=None)

        # Reset process starts here
        async for pk in models.Pokemon.filter(owner_id=trainer.id):
            _market: typing.Optional[models.Listings] = await models.Listings.get_or_none(pokemon=pk.id)
            _auction: typing.Optional[models.Auctions] = await models.Auctions.get_or_none(pokemon=pk.id)

            if _market is not None:
                await _market.delete()

            if _auction is not None:
                await _auction.delete()

            await pk.delete()

        async for market in models.Listings.filter(user_id=trainer.id):
            await market.delete()

        async for auction in models.Auctions.filter(owner_id=trainer.id):
            await auction.delete()

        _trainer_model: models.Member = await self.bot.manager.fetch_member_info(trainer.id)
        await _trainer_model.delete()

        with suppress(discord.Forbidden, discord.HTTPException):
            return await msg.edit(
                f"Successfully reset {trainer.mention}'s account!",
                view=None,
                allowed_mentions=None,
            )

    # @commands.command()
    # async def
    # TODO: Maintenance, command locking


def setup(bot: PokeBest) -> None:
    bot.add_cog(Owner(bot))
