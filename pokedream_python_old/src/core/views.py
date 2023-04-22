# from cogs.trading import Trade
from datetime import datetime, time, timedelta
from os import name
from discord.channel import TextChannel
from discord.ext.commands.converter import UserConverter
from discord.ext.commands.errors import MemberNotFound, UserNotFound
from cogs.helpers.battles import Battle, BattleEngine, BattleType, Reward, Trainer

from discord.interactions import InteractionMessage
from discord.user import User

import models
from .bot import PokeBest
from core.paginator import SimplePaginator, SimplePaginatorView
from discord.ui import View, button, Select
from discord.ext import commands
from discord import ButtonStyle, emoji
import discord
import asyncio

from contextlib import suppress
from utils.constants import (
    TYPES,
    LANGUAGES,
    SHOP_FORMS,
    UTC,
    BattleCategory,
    BattleType,
)
from utils.converters import AuctionConverter, MarketConverter, PokemonConverter
from utils.methods import ParseDictToStr
from utils.emojis import emojis
from models import Member
from typing import Dict, List, Iterable, Optional, Type, Union, TYPE_CHECKING
from data import data
import config
import random
import json
import itertools
from aioredis_lock import RedisLock, LockTimeoutError

if TYPE_CHECKING:
    from cogs.helpers.battles import Battle, Trainer


class PokedexView(View):
    def __init__(
        self,
        bot: PokeBest,
        ctx: commands.Context,
        specie,
        shiny: bool,
        base_embed: discord.Embed,
        timeout: int = 100,
    ) -> None:
        self.bot: PokeBest = bot
        self.ctx: commands.Context = ctx
        self.specie = specie
        self.shiny: bool = shiny
        self.base_embed: discord.Embed = base_embed
        super().__init__(timeout=timeout)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message(
                "Sorry, you can't use this interaction as it is not started by you.",
                ephemeral=True,
            )
            return False
        return True

    async def on_timeout(self) -> None:
        for child in self.children:
            child.disabled = True
        with suppress(discord.NotFound):
            # await self._paginator_obj._context.message.edit(view=None)
            self.stop()

    @button(label="Stats", style=ButtonStyle.blurple)
    async def show_stats(self, button: discord.ui.Button, interaction: discord.Interaction):
        embed: discord.Embed = self.bot.Embed(
            color=int(data.specie_color(self.specie["dex_number"]), 16),
            title=f"#{self.specie['species_id']} — {self.specie['names']['9']}",
        )

        stats: Iterable[str] = (
            f"**HP**: {self.specie['base_stats'][0]}",
            f"**Attack**: {self.specie['base_stats'][1]}",
            f"**Defense**: {self.specie['base_stats'][2]}",
            f"**Sp. Atk**: {self.specie['base_stats'][3]}",
            f"**Sp. Def**: {self.specie['base_stats'][4]}",
            f"**Speed**: {self.specie['base_stats'][5]}",
        )

        embed.add_field(name="Stats", value="\n".join(stats))

        _nos: str = "normal" if not self.shiny else "shiny"

        embed.set_thumbnail(url=self.specie["sprites"].__getitem__(_nos))

        for b in self.children:
            b.disabled = b == button
        await interaction.response.edit_message(embed=embed, view=self)

    @button(label="Names", style=ButtonStyle.blurple)
    async def show_names(self, button: discord.ui.Button, interaction: discord.Interaction):
        embed: discord.Embed = self.bot.Embed(
            color=int(data.specie_color(self.specie["dex_number"]), 16),
            title=f"#{self.specie['species_id']} — {self.specie['names']['9']}",
        )

        names: List[str] = []
        for idx, name in self.specie["names"].items():
            with suppress(IndexError):
                names.append(f"{LANGUAGES[int(idx)][2]} {name}")

        embed.add_field(name="Alternative Names", value="\n".join(names), inline=False)

        _nos: str = "normal" if not self.shiny else "shiny"

        embed.set_thumbnail(url=self.specie["sprites"].__getitem__(_nos))

        for b in self.children:
            b.disabled = b == button
        await interaction.response.edit_message(embed=embed, view=self)

    @button(label="Types", style=ButtonStyle.blurple)
    async def show_types(self, button: discord.ui.Button, interaction: discord.Interaction):
        embed: discord.Embed = self.bot.Embed(
            color=int(data.specie_color(self.specie["dex_number"]), 16),
            title=f"#{self.specie['species_id']} — {self.specie['names']['9']}",
        )

        types: List[str] = []
        for type_id in self.specie["types"]:
            types.append(TYPES[type_id])

        embed.add_field(name="Types", value="\n".join(types), inline=True)

        _nos: str = "normal" if not self.shiny else "shiny"

        embed.set_thumbnail(url=self.specie["sprites"].__getitem__(_nos))

        for b in self.children:
            b.disabled = b == button
        await interaction.response.edit_message(embed=embed, view=self)

    @button(label="Appearance", style=ButtonStyle.blurple)
    async def show_appearance(self, button: discord.ui.Button, interaction: discord.Interaction):
        embed: discord.Embed = self.bot.Embed(
            color=int(data.specie_color(self.specie["dex_number"]), 16),
            title=f"#{self.specie['species_id']} — {self.specie['names']['9']}",
        )

        embed.add_field(
            name="Appearance",
            value=f"Height: {int(self.specie['height'])/10}m\nWeight: {int(self.specie['weight'])/10}kg",
            inline=True,
        )

        _nos: str = "normal" if not self.shiny else "shiny"

        embed.set_thumbnail(url=self.specie["sprites"].__getitem__(_nos))

        for b in self.children:
            b.disabled = b == button
        await interaction.response.edit_message(embed=embed, view=self)

    @button(label="Back", style=ButtonStyle.blurple)
    async def go_back(self, button: discord.ui.Button, interaction: discord.Interaction):
        for b in self.children:
            b.disabled = b == button
        await interaction.response.edit_message(embed=self.base_embed, view=self)


class CatchView(View):
    def __init__(self, ctx: commands.Context, timeout: int = 100):
        super().__init__(timeout=timeout)
        self.ctx: commands.Context = ctx

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message(
                "Sorry, you can't use this interaction as it is not started by you.",
                ephemeral=True,
            )
            return False
        return True

    async def on_timeout(self) -> None:
        for child in self.children:
            child.disabled = True
        with suppress(discord.NotFound):
            # await self._paginator_obj._context.message.edit(view=None)
            self.stop()

    @button(label="View", style=ButtonStyle.grey)
    async def redirect_to_info(self, button: discord.ui.Button, interaction: discord.Interaction):
        info_command = self.ctx.bot.get_command("info")
        pk = await PokemonConverter().convert(self.ctx, "latest")
        await info_command.__call__(self.ctx, pokemon=pk)
        self.stop()


class ShopDropdown(Select):
    def __init__(self, ctx: commands.Context):
        self._context: commands.Context = ctx
        options: List[discord.SelectOption] = [
            discord.SelectOption(
                label="Page 1 : XP Boosters & Rare Candies",
                description="Get the list of items like XP Boosters and Rare Candies!",
            ),
            discord.SelectOption(
                label="Page 2 : Rare Stones & Evolution Items",
                description="Get the list of items like stones and evolution items to evolve your pokemon!",
            ),
            discord.SelectOption(
                label="Page 3 : Nature Modifiers",
                description="Get the list of items like nature modifiers to change the nature of your pokemon!",
            ),
            discord.SelectOption(
                label="Page 4 : Held Items",
                description="Get the list of items to hold for your pokemon!",
            ),
            discord.SelectOption(
                label="Page 5 : Mega Evolutions",
                description="Get the list of items which will allow your pokemon to mega evolve!",
            ),
            discord.SelectOption(
                emoji="🔒",
                label="Page 6 : Forms",
                description="Get the list of forms of pokemons which you can buy to evolve your pokemon!",
            ),
            discord.SelectOption(
                label=f"Page 7 : Shard Shop",
                description="Get the list of items which you can buy using shards!",
            ),
            # discord.SelectOption(
            #     label=f"Page 8 : Battle Items",
            #     description="Get the list of items which you can use for battles!"
            # )
            # discord.SelectOption(
            #     label="Page 8 : Miscellaneous", description="Some miscellaneous and exclusive items which you can buy!"
            # ),
        ]

        super().__init__(placeholder="Choose a page.", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        # sourcery no-metrics
        # Process the shop pages
        from data import data

        embed: discord.Embed = self._context.bot.Embed(
            title=f"{self._selected_values.__getitem__(0)}",
        )

        member: Member = await self._context.bot.manager.fetch_member_info(self._context.author.id)

        embed.set_author(
            name=f"Balance: {member.balance} | Shards: {member.shards}",
            icon_url=self._context.author.avatar.url,
        )

        if "1" in self._selected_values[0]:
            embed.description = f"Get XP boosters to increase your XP gain from chatting and battling!\n\n**Note:** If you boosted our [support server]({config.SUPPORT_SERVER_LINK}) then you will get double xp booster for free until the boost remains."

            items: Dict[str, str] = {
                f"30 Minutes - 2X Multiplier": f"*Cost: 20 credits*\n`{self._context.prefix}buy 1`",
                f"1 Hour - 2X Multiplier": f"*Cost: 40 credits*\n`{self._context.prefix}buy 2`",
                f"2 Hour - 2X Multiplier": f"*Cost: 70 credits*\n`{self._context.prefix}buy 3`",
                f"3 Hour - 2X Multiplier": f"*Cost: 90 credits*\n`{self._context.prefix}buy 4`",
                f"<:rarecandy:939867992483848242> Rare Candies": f"*Cost: 50 credits* each\nRare candies level up your selected pokémon by one level for each candy you feed it.\n`{self._context.prefix}buy candy <quantity>`",
            }

            for item, desc in items.items():
                embed.add_field(name=item, value=desc, inline=True)

            await interaction.response.send_message(embed=embed)

        elif "2" in self._selected_values[0]:
            embed.description = f"Some pokémon don't evolve through leveling and need an evolution stone or high friendship to evolve. Here you can find all the evolution stones as well as a friendship bracelet for friendship evolutions.\n\n*All these items cost **150 credits**!*"

            items_to_display: List[dict] = []

            for item in data.pokemon_items:
                if item.__getitem__("page") == 2:
                    items_to_display.append(item)

            for _item in items_to_display:
                embed.add_field(
                    name=f"{_item.get('sprite', '')} {_item['name']}",
                    value=f"`{self._context.prefix}buy {' '.join(reversed(_item.__getitem__('name').lower().split(' ')))}`",
                )

            await interaction.response.send_message(embed=embed)

        elif "3" in self._selected_values[0]:
            embed.description = f"Nature modifiers change your selected pokémon's nature to a nature of your choice for credits. Use `{self._context.prefix}buy nature <nature>` to buy the nature you want!\n\n*All nature modifiers cost **50 credits**!*"

            items_to_display: List[dict] = []

            for item in data.pokemon_items:
                if item.__getitem__("page") == 5:
                    items_to_display.append(item)

            for _item in items_to_display:
                embed.add_field(
                    name=f"{_item.get('sprite', '')} {_item['name']}",
                    value=_item.__getitem__("description"),
                )

            await interaction.response.send_message(embed=embed)

        elif "4" in self._selected_values[0]:
            embed.description = f"Buy items for your pokémon to hold using `{self._context.prefix}buy item <item name>`.\n\n*All held items cost **150 credits**!*"

            items_to_display: List[dict] = []

            for item in data.pokemon_items:
                if item.__getitem__("page") == 4:
                    items_to_display.append(item)

            for _item in items_to_display:
                embed.add_field(
                    name=f"{_item.get('sprite', '')} {_item['name']}",
                    value=f"`{self._context.prefix}buy item {' '.join(_item.__getitem__('name').lower().split(' '))}`",
                )

            await interaction.response.send_message(embed=embed)

        elif "5" in self._selected_values[0]:
            embed.description = f"Evolve your pokemon to mega forms!\n\n*All mega items cost **20,000 credits**!*"

            items: Dict[str, str] = {
                "Mega Evolution": f"`{self._context.prefix}buy mega`",
                "Mega X Evolution": f"`{self._context.prefix}buy mega x`",
                "Mega Y Evolution": f"`{self._context.prefix}buy mega y`",
            }

            for name, value in items.items():
                embed.add_field(name=name, value=value)

            await interaction.response.send_message(embed=embed)

        elif "6" in self._selected_values[0]:
            _mem: models.Member = await self._context.bot.manager.fetch_member_info(self._context.author.id)
            if _mem.vote_total >= 100 or _mem.vote_streak >= 100:
                embed.description = (
                    f"Some pokémon have different forms, you can buy them here to allow them to transform."
                )

                _pages: List[discord.Embed] = []
                count: int = 1

                for form, data in SHOP_FORMS.items():
                    embed.add_field(
                        name=f"{form.title()}",
                        value=f"{self._context.prefix}shop forms {form}",
                        inline=True,
                    )

                    count += 1
                    if count % 25 == 0:
                        _pages.append(embed)
                        embed = self._context.bot.Embed(
                            title=f"{self._selected_values.__getitem__(0)}",
                            description=f"Some pokémon have different forms, you can buy them here to allow them to transform.",
                        )

                        embed.set_author(
                            name=f"Balance: {member.balance} | Shards: {member.shards}",
                            icon_url=self._context.author.avatar.url,
                        )

                _pages.append(embed)
                _paginator: SimplePaginator = SimplePaginator(ctx=self._context, pages=_pages)

                await interaction.response.send_message(
                    embed=_paginator._pages.__getitem__(_paginator._current_page),
                    view=SimplePaginatorView(_paginator),
                )
            else:
                return await interaction.response.send_message(
                    "🔒The shopkeeper of this shop is not available at this time."
                )

        elif "7" in self._selected_values[0]:
            embed.description = "We have variety of items that you can purchase using shards."

            items: Dict[str, str] = {
                "Redeems": f"*200 Shards each*\nSpawn any catchable pokemon of your choice.\n`{self._context.prefix}buy redeems`",
                "Shiny Charm": f"*300 Shards*\nIncrease your shiny rate by 20% for 7 days.\n`{self._context.prefix}buy shiny charm`",
                "Gift": f"*50 Shards*\nBuy a gift box to use or to give someone!\n`{self._context.prefix}buy gift`",
                "Incense": f"*25 Shards*\nSpawns a private pokemon which you can catch, for 1 hour!\n`{self._context.prefix}buy incense`",
            }

            for item, desc in items.items():
                embed.add_field(name=item, value=desc)

            if self._context.bot.config.CHRISTMAS_MODE:
                embed.add_field(
                    name="__🎄 Christmas Special 🎄__",
                    value=f"**Christmas Bundle**: *500 Shards*\nGet **1 Redeem**, **2 Gifts** and a **Shadow Kyurem** with this special bundle!\n`{self._context.prefix}buy christmas bundle`\n\n"
                    + f"**✨ Santa Pikachu**: *10,000 Shards*\nGet a Shiny Santa Pikachu! This offer is for a limited time only.\n`{self._context.prefix}buy santa pikachu`",
                    inline=False,
                )

            if self._context.bot.config.VALENTINES_MODE:
                embed.add_field(
                    name="__💝 Valentines Special 💝__",
                    value=f"**✨ Heart Magikarp**: *5,000 Shards*\nGet a Shiny Heart Magikarp! This offer is for a limited time only.\n`{self._context.prefix}buy heart magikarp`",
                    inline=False,
                )

            ## NOTE: This is for event
            embed.add_field(
                name="__🎉 Event Special 🎉__",
                value=f"**✨ Starter Eevee**: *10,000 Shards*\nGet a Shiny Starter Eevee! This offer is for a limited time only.\n`{self._context.prefix}buy starter eevee`",
                inline=False,
            )

            await interaction.response.send_message(embed=embed)

        elif "8" in self._selected_values[0]:
            embed.description = "Some miscellaneous and exclusive items which you can buy!"

            items: Dict[str, str] = {
                f"{emojis.gift} Gift": f"*70,000 Credits*\nBuy a gift box to use or to give someone! Rewards will depend upon your luck.\n`{self._context.prefix}buy gift`"
            }

            for item, desc in items.items():
                embed.add_field(name=item, value=desc)

            await interaction.response.send_message(embed=embed)


class ShopMenuView(View):
    def __init__(self, ctx: commands.Context):
        self.ctx: commands.Context = ctx
        super().__init__(timeout=100)

        self.add_item(ShopDropdown(ctx))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message(
                "Sorry, you can't use this interaction as it is not started by you.",
                ephemeral=True,
            )
            return False
        return True

    async def on_timeout(self) -> None:
        for child in self.children:
            child.disabled = True
        with suppress(discord.NotFound):
            # await self._paginator_obj._context.message.edit(view=None)
            self.stop()


class Confirm(discord.ui.View):
    def __init__(self, ctx: commands.Context, author: Optional[int] = None):
        super().__init__()
        self.ctx: commands.Context = ctx
        self.author: Optional[int] = author
        self.value = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if self.author is None and interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message(
                "Sorry, you can't use this interaction as it is not started by you.",
                ephemeral=True,
            )
            return False

        elif self.author is not None and interaction.user.id != self.author:
            await interaction.response.send_message(
                "Sorry, you can't use this interaction as it is not for you.",
                ephemeral=True,
            )
            return False

        return True

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.green)
    async def confirm(self, _: discord.ui.Button, interaction: discord.Interaction):
        self.value = True
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.red)
    async def cancel(self, _: discord.ui.Button, interaction: discord.Interaction):
        self.value = False
        self.stop()


class AuctionBidButton(discord.ui.Button):
    def __init__(self, ctx: commands.Context, auction: AuctionConverter):
        self._ctx: commands.Context = ctx
        self.auction: AuctionConverter = auction

        self.__input_lock = asyncio.Lock()

        super().__init__(label="Bid", style=discord.ButtonStyle.blurple)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        try:
            async with RedisLock(self._ctx.bot.redis, f"auction_bid:{self.auction.id}", 60, 1):
                await interaction.followup.send(
                    "Please enter the amount you want to bid on this auction.", ephemeral=True
                )

                try:
                    _amount_msg: discord.Message = await self._ctx.bot.wait_for(
                        "message",
                        check=lambda m: m.author.id == self._ctx.author.id and m.channel.id == self._ctx.channel.id,
                        timeout=120,
                    )

                except asyncio.TimeoutError:
                    return await interaction.followup.send("Time's up!", ephemeral=True)

                bid_amount_str: str = _amount_msg.content

                if not bid_amount_str.isdigit():
                    return await interaction.followup.send("Bid amount must be a number!", ephemeral=True)

                bid_amount: int = int(bid_amount_str)

                _bid_command: commands.Command = self._ctx.bot.get_command("auction bid")
                await _bid_command.__call__(self._ctx, self.auction, bid_amount)

        except LockTimeoutError:
            return await interaction.followup.send(
                "Someone is already bidding on this auction. Please try again later.", ephemeral=True
            )


class AuctionView(discord.ui.View):
    def __init__(self, ctx: commands.Context, auction: AuctionConverter, timeout: int = 120) -> None:
        self.timeout: int = timeout
        self.ctx: commands.Context = ctx
        self.auction: AuctionConverter = auction
        super().__init__(timeout=self.timeout)

        self.add_item(AuctionBidButton(self.ctx, self.auction))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message(
                "Sorry, you can't use this interaction as it is not started by you.",
                ephemeral=True,
            )
            return False
        return True


class MarketBuyButton(discord.ui.Button):
    def __init__(self, ctx: commands.Context, market: MarketConverter):
        self._ctx: commands.Context = ctx
        self.market: MarketConverter = market
        super().__init__(label="Buy", style=discord.ButtonStyle.blurple)

    async def callback(self, interaction: discord.Interaction):
        _buy_command: commands.Command = self._ctx.bot.get_command("market buy")
        await _buy_command.__call__(self._ctx, self.market)


class MarketView(discord.ui.View):
    def __init__(self, ctx: commands.Context, market: MarketConverter, timeout: int = 120) -> None:
        self.timeout: int = timeout
        self.ctx: commands.Context = ctx
        self.market: MarketConverter = market
        super().__init__(timeout=self.timeout)

        self.add_item(MarketBuyButton(self.ctx, self.market))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message(
                "Sorry, you can't use this interaction as it is not started by you.",
                ephemeral=True,
            )
            return False
        return True


class MoveLearnButton(discord.ui.Button):
    def __init__(self, idx: int, move_name: str):
        self.idx: int = idx
        self.move_name: str = move_name
        super().__init__(label=f"{idx} | {move_name}", style=discord.ButtonStyle.blurple)

    async def callback(self, interaction: discord.Interaction):
        self.view.value = self.idx
        return await self.view._stop(interaction)


class MoveLearnView(discord.ui.View):
    def __init__(self, ctx: commands.Context, moves: list):
        self.ctx: commands.Context = ctx
        self.moves: list = moves
        self.value: int = None
        super().__init__(timeout=120)

        for idx, move in enumerate(self.moves, start=1):
            self.add_item((MoveLearnButton(idx, move)))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message(
                "Sorry, you can't use this interaction as it is not started by you.",
                ephemeral=True,
            )
            return False
        return True

    async def _stop(self, interaction: discord.Interaction):
        for b in self.children:
            b.disabled = True

        await interaction.response.edit_message(view=self)

        super().stop()


# class TradeView(discord.ui.View):
#     def __init__(self, trade: Trade):
#         self.trade: Trade = trade
#         super().__init__()

#     @button(style=discord.ButtonStyle.success, label="Confirm")
#     async def confirm_button(self, button: discord.ui.Button, interaction: discord.Interaction):
#         ...


class GambleView(discord.ui.View):
    def __init__(self, gamble, target: Union[discord.User, discord.Member]) -> None:
        self.gamble = gamble
        self.joined: bool = None
        self.target: Union[discord.User, discord.Member] = target

        super().__init__(timeout=120)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.target.id:
            await interaction.response.send_message("You are not invited to join this gamble.", ephemeral=False)
            return False

        return True

    @button(label="Join", style=ButtonStyle.green)
    async def join_button(self, btn: discord.Button, interaction: discord.Interaction):
        self.joined = True
        self.stop()

    @button(label="Decline")
    async def decline_button(self, btn: discord.Button, interaction: discord.Interaction):
        self.joined = False
        self.stop()


class FishingView(discord.ui.View):
    def __init__(self, ctx: commands.Context, specie) -> None:
        self.ctx: commands.Context = ctx
        self.specie = specie

        self.ready: Optional[bool] = None

        super().__init__(timeout=120)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message(
                "Sorry, you can't use this interaction.",
                ephemeral=True,
            )
            return False
        return True

    async def on_timeout(self) -> None:
        self.ready = None

    @button(label="Fight", style=ButtonStyle.blurple, emoji="⚔️")
    async def fight_button(self, btn: discord.Button, interaction: discord.Interaction):
        self.ready = True
        self.stop()

    @button(label="Run", emoji="🏃‍♂️")
    async def run_button(self, btn: discord.Button, interaction: discord.Interaction):
        await interaction.response.send_message("Got away safely...")
        self.stop()


class InfoViewMarketButton(discord.ui.Button):
    def __init__(self, ctx: commands.Context, pokemon: models.Pokemon) -> None:
        self.ctx: commands.Context = ctx
        self.pokemon: models.Pokemon = pokemon
        super().__init__(label="List on Market", style=discord.ButtonStyle.blurple)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_message("Enter the price of pokemon to list on market.", ephemeral=True)

        try:
            msg: discord.Message = await self.ctx.bot.wait_for(
                "message",
                check=lambda m: m.author.id == self.ctx.author.id and m.channel.id == self.ctx.channel.id,
            )
        except asyncio.TimeoutError:
            return await interaction.response.edit_message("Time's up!")

        amt: str = msg.content
        if not amt.isdigit():
            return await interaction.response.edit_message("Please provide a valid number!")

        market_list_command: commands.Command = self.ctx.bot.get_command("market list")
        await market_list_command.__call__(self.ctx, self.pokemon, int(amt))


class InfoViewAuctionButton(discord.ui.Button):
    def __init__(self, ctx: commands.Context, pokemon: models.Pokemon) -> None:
        self.ctx: commands.Context = ctx
        self.pokemon: models.Pokemon = pokemon

        super().__init__(label="List on Auction", style=discord.ButtonStyle.blurple)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_message("Enter the price of pokemon to list on auction.", ephemeral=True)

        try:
            msg: discord.Message = await self.ctx.bot.wait_for(
                "message",
                check=lambda m: m.author.id == self.ctx.author.id and m.channel.id == self.ctx.channel.id,
            )
        except asyncio.TimeoutError:
            return await interaction.response.edit_message("Time's up!")

        amt: str = msg.content
        if not amt.isdigit():
            return await interaction.response.edit_message("Please provide a valid number!")

        auction_list_command: commands.Command = self.ctx.bot.get_command("auction list")
        await auction_list_command.__call__(self.ctx, self.pokemon, int(amt))


class InfoView(discord.ui.View):
    def __init__(self, ctx: commands.Context, pokemon: models.Pokemon) -> None:
        self.pokemon: models.Pokemon = pokemon
        self.ctx: commands.Context = ctx
        super().__init__(timeout=120)

        self.add_item(InfoViewMarketButton(self.ctx, self.pokemon))
        self.add_item(InfoViewAuctionButton(self.ctx, self.pokemon))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message(
                "Sorry, you can't use this interaction as it is not started by you.",
                ephemeral=True,
            )
            return False
        return True


class GiftView(discord.ui.View):
    def __init__(self, ctx: commands.Context):
        self.ctx: commands.Context = ctx

        self.__gift_lock: asyncio.Lock = asyncio.Lock()
        self.__give_lock: asyncio.Lock = asyncio.Lock()

        super().__init__(timeout=120)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message(
                "Sorry, you can't use this interaction as it is not started by you.",
                ephemeral=True,
            )
            return False
        return True

    async def _has_enough_gifts(self, ctx: commands.Context) -> bool:
        mem: models.Member = await ctx.bot.manager.fetch_member_info(ctx.author.id)

        if mem.gift <= 0:
            return False

        return True

    def _determine_reward(self) -> str:
        if random.randint(1, 3096) == 1:
            return "shiny"

        elif random.randint(1, 100) <= 5:
            return "redeem"

        else:
            return "pokemon"

    async def _insert_sp(self, sp, mem: models.Member) -> models.Pokemon:
        next_idx: int = await self.ctx.bot.manager.get_next_idx(self.ctx.author.id)
        pk: models.Pokemon = models.Pokemon.get_random(
            owner_id=self.ctx.author.id,
            idx=next_idx,
            species_id=sp.__getitem__("species_id"),
            level=random.randint(1, 50),
            xp=0,
        )
        mem.next_idx += 1

        return pk

    @button(label="Open", emoji="📤")
    async def open_gift(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.defer()

        if self.__gift_lock.locked():
            return await interaction.followup.send("You are already opening a gift.", ephemeral=True)

        async with self.__gift_lock:
            if not (await self._has_enough_gifts(self.ctx)):
                return await interaction.followup.send("You don't have any gifts to open!", ephemeral=True)

            reward_type: str = self._determine_reward()

            await interaction.followup.send(f"Opening {emojis.typing}")
            mem: models.Member = await self.ctx.bot.manager.fetch_member_info(self.ctx.author.id)
            pk: Optional[models.Pokemon] = None

            if reward_type == "pokemon":
                sp = data.species_by_num(random.randint(1, 898))
                pk: models.Pokemon = await self._insert_sp(sp, mem)

            elif reward_type == "redeem":
                mem.redeems += 1

            elif reward_type == "shiny":
                next_idx: int = await self.ctx.bot.manager.get_next_idx(self.ctx.author.id)
                pk: models.Pokemon = models.Pokemon.get_random(
                    owner_id=self.ctx.author.id,
                    shiny=True,
                    idx=next_idx,
                    species_id=random.randint(1, 898),
                )
                mem.next_idx += 1

            mem.balance += 1000

            if pk is not None:
                emb: discord.Embed = self.ctx.bot.Embed(
                    description=f"**You opened a {emojis.gift} giftbox and received:**\n\n{self.ctx.bot.sprites.get(pk.specie['dex_number'])} {pk:l} IV: {pk.iv_percentage:.2%}\n1000 credits!",
                )

            else:
                emb: discord.Embed = self.ctx.bot.Embed(
                    description=f"**You opened a {emojis.gift} giftbox and received:**\n\n1 Redeem\n1000 credits!"
                )

            with suppress(discord.Forbidden, discord.HTTPException):
                await interaction.delete_original_message()

            await self.ctx.reply(embed=emb, mention_author=False)

            mem.gift -= 1
            if pk is not None:
                await pk.save()
            await mem.save()

    @button(label="Give", emoji="🔁")
    async def give_gift(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.defer()

        if self.__give_lock.locked():
            return await interaction.followup.send(
                "You are already giving a gift to someone. Please wait until it finishes up.", ephemeral=True
            )

        async with self.__give_lock:
            if not await self._has_enough_gifts(self.ctx):
                return await interaction.followup.send("You don't have any gifts to give!", ephemeral=True)

            await interaction.followup.send("Enter the user you want to gift.", ephemeral=True)

            inp: discord.Message = await self.ctx.bot.wait_for(
                "message",
                check=lambda m: m.channel.id == self.ctx.channel.id and m.author.id == self.ctx.author.id,
            )

            try:
                _user_obj: Union[discord.Member, discord.User] = await UserConverter().convert(self.ctx, inp.content)
            except (UserNotFound, MemberNotFound):
                return await interaction.followup.edit_message(content="Sorry, I couldn't find any such user.")

            mem: Optional[models.Member] = await self.ctx.bot.manager.fetch_member_info(_user_obj.id)
            if mem is None:
                return await interaction.followup.send("That user haven't picked a starter yet!", ephemeral=True)

            mem.gift += 1
            await mem.save()

            with suppress(discord.Forbidden, discord.HTTPException):
                await interaction.delete_original_message()

            curr: models.Member = await self.ctx.bot.manager.fetch_member_info(self.ctx.author.id)
            curr.gift -= 1
            await curr.save()

            with suppress(discord.Forbidden, discord.HTTPException):
                emb: discord.Embed = self.ctx.bot.Embed(
                    title="Gift received!",
                    description=f"You received a {emojis.gift} gift from {self.ctx.author.name}!\n"
                    + "Check it out using `p!gift` command.",
                )
                await _user_obj.send(embed=emb)

            await interaction.followup.send(
                content=f"Successfully gave the trainer your {emojis.gift} gift!", ephemeral=True
            )


class ResearchTasksView(discord.ui.View):
    def __init__(self, ctx: commands.Context, pages: List[discord.Embed]) -> None:
        self.ctx: commands.Context = ctx
        self.pages: List[discord.Embed] = pages

        self.current_page: int = 0
        self.msg: discord.Message = None
        super().__init__(timeout=120)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message(
                "Sorry, you can't use this interaction as it is not started by you.",
                ephemeral=True,
            )
            return False
        return True

    async def on_timeout(self) -> None:
        for child in self.children:
            child.disabled = True
        with suppress(discord.NotFound):
            await self.msg.edit(view=None)

    async def paginate(self):
        msg: discord.Message = await self.ctx.reply(embed=self.pages[self.current_page], mention_author=False, view=self)
        self.msg = msg

    # @button(label="Claim Rewards", emoji=emojis.wild, style=discord.ButtonStyle.blurple)
    # async def claim_rewards(self, button: discord.ui.Button, interaction: discord.Interaction):
    #     mem: models.Member = await self.ctx.bot.manager.fetch_member_info(interaction.user.id)
    #     rewards = {}

    #     for quest in mem.quests:
    #         if quest["done"] and quest["reward_claimed"] is False:
    #             rewards["credits"]

    @button(label="Previous", emoji="⏮️")
    async def previous_page(self, button: discord.ui.Button, interaction: discord.Interaction):
        self.current_page -= 1

        try:
            page = self.pages[self.current_page]
        except IndexError:
            return

        await self.msg.edit(embed=page)

    @button(label="Next", emoji="⏭️")
    async def next_page(self, button: discord.ui.Button, interaction: discord.Interaction):
        self.current_page += 1

        try:
            page = self.pages[self.current_page]
        except IndexError:
            return

        await self.msg.edit(embed=page)


class CustomButton(discord.ui.Button):
    def __init__(
        self,
        style: discord.ButtonStyle,
        label: str,
        custom_id: str = None,
        url: str = None,
    ):
        super().__init__()
        self.style = style
        self.label = label
        self.custom_id = custom_id
        self.url = url

    async def callback(self, interaction: discord.Interaction):
        self.view.stop()
        self.view.custom_id = self.custom_id
        self.view.label = self.label
        return self.custom_id


class CustomButtonView(discord.ui.View):
    def __init__(self, ctx, buttons, timeout=120, disable_button=True):
        super().__init__(timeout=timeout)
        self.ctx = ctx
        self.author = ctx.author
        self.custom_id = None
        self.disable_button = disable_button

        for item in buttons:
            if item.custom_id:
                self.add_item(CustomButton(style=item.style, label=item.label, custom_id=item.custom_id))
            else:
                self.add_item(
                    CustomButton(
                        style=item.style,
                        label=item.label,
                        custom_id=item.custom_id,
                        url=item.url,
                    )
                )

    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.user != self.author:
            await interaction.response.send_message(
                "Sorry, you can't use this interaction as it is not started by you.",
                ephemeral=True,
            )
            return False
        return True

    async def on_timeout(self):
        self.custom_id = None
        if self.disable_button:
            message = None
            bot = self.ctx.bot

            for m_id, view in bot._connection._view_store._synced_message_views.items():
                if view is self:
                    if m := bot.get_message(m_id):
                        message = m

            if message is None:
                return

            for b in self.children:
                b.disabled = True
            await message.edit(view=self)

            await self.ctx.error("Time limit exceeded, please try again.")


class SpawnFightView(discord.ui.View):
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
        await _interaction.response.defer()
        self.stop()
        await _interaction.followup.send("Team Rocket Grunt takes out his Mewtwo....")
        pk1: models.Pokemon = await self.ctx.bot.manager.fetch_selected_pokemon(self.ctx.author.id)
        if pk1 is None:
            return await _interaction.followup.send(
                f"{self.ctx.author.mention}, please select a pokemon!", ephemeral=True
            )

        pk2sp = data.pokemon_data[149]  # Mewtwo
        pk2: models.Pokemon = models.Pokemon.get_random(
            owner_id=None, species_id=pk2sp["species_id"], level=150, idx=1, xp=0
        )

        moves: list = data.get_pokemon_moves(pk2.species_id)
        if not moves:
            moves: list = data.get_pokemon_moves(pk2.specie["dex_number"])

        move_ids: list = [m["move_id"] for m in moves]

        pk2.moves = move_ids[:4]

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
                Reward.TeamRocket,
            )
            self.ctx.bot.battles.append(battle)

            await battle.send_battle()
            await msg.delete()


class SpawnDuelView(View):
    def __init__(
        self,
        bot: PokeBest,
        ctx: commands.Context,
        channel: discord.TextChannel,
        species_id: int,
    ):
        self.ctx: commands.Context = ctx
        self.bot: PokeBest = bot

        self.channel: discord.TextChannel = channel or self.ctx.channel

        self.species_id: int = species_id

        super().__init__(timeout=60.0)

    @discord.ui.button(label="Fight", emoji="⚔", style=ButtonStyle.blurple)
    async def duel_to_catch_button(self, button: discord.Button, interaction: discord.Interaction):
        await interaction.response.defer()
        if (
            self.bot.spawn_cache.get(self.channel.id, None) is not None
            and self.bot.spawn_cache[self.channel.id].get("species_id", None) is not None
        ):
            if self.bot.spawn_cache[self.channel.id]["species_id"] != self.species_id:
                return await interaction.followup.send(
                    "This pokemon is no more available to catch or duel.",
                    ephemeral=True,
                )

            if self.bot.spawn_cache[self.channel.id]["is_engaged"]:
                return await interaction.followup.send(
                    "This pokemon is already in duel with another trainer.",
                    ephemeral=True,
                )

            self.ctx.author = interaction.user

            _mem: models.Member = await self.ctx.bot.manager.fetch_member_info(self.ctx.author.id)

            if _mem.spawn_duel_cooldown is not None and _mem.spawn_duel_cooldown.replace(
                tzinfo=UTC
            ) > datetime.now().replace(tzinfo=UTC):
                return await interaction.followup.send(
                    f"You can't duel for another {discord.utils.format_dt(_mem.spawn_duel_cooldown)}.",
                    ephemeral=True,
                )

            pk1: models.Pokemon = await self.ctx.bot.manager.fetch_selected_pokemon(self.ctx.author.id)
            if pk1 is None:
                return await self.ctx.send(
                    f"<@{self.ctx.author.id}>, please select a pokemon!",
                    mention_author=False,
                )

            self.bot.spawn_cache[self.channel.id]["is_engaged"] = True

            await interaction.followup.send(
                f"You took out your {self.bot.sprites.get(pk1.specie['dex_number'])} {pk1:l}..."
            )

            pk2sp = data.pokemon_data[self.species_id - 1]
            pk2: models.Pokemon = models.Pokemon.get_random(
                owner_id=None,
                species_id=pk2sp["species_id"],
                level=random.randint(1, 65),
                idx=1,
                xp=0,
            )

            moves: list = data.get_pokemon_moves(pk2.species_id)
            if len(moves) == 0:
                moves: list = data.get_pokemon_moves(pk2.specie["dex_number"])

            move_ids: list = [m["move_id"] for m in moves]

            pk2.moves = move_ids[:4]

            trainer1: Trainer = Trainer(self.ctx.author, [pk1], 0, pk1, False)
            trainer2: Trainer = Trainer(self.ctx.bot.user, [pk2], 0, pk2, True)

            msg: discord.Message = await self.ctx.send("Battle is being loaded...", mention_author=False)

            self.bot.spawn_cache[self.ctx.channel.id] = {
                "messages": 0,
                "species_id": None,
                "hint_used": False,
                "is_shiny": False,
                "is_engaged": False,
            }

            _mem.spawn_duel_cooldown = datetime.utcnow() + timedelta(minutes=15)
            await _mem.save()

            with self.ctx.typing():
                battle: Battle = Battle(
                    self.ctx.bot,
                    self.ctx,
                    [trainer1, trainer2],
                    BattleType.oneVone,
                    BattleEngine.AI,
                    Reward.Pokemon,
                    BattleCategory.Grass,
                )
                self.ctx.bot.battles.append(battle)

                await battle.send_battle()
                await msg.delete()


class PremiumCatchView(View):
    def __init__(self, mem: models.Member, raid: models.Raids):
        self.mem: models.Member = mem
        self.raids: models.Raids = raid

        self.tries: int = 0

        self.__button_lock: asyncio.Lock = asyncio.Lock()

        super().__init__(timeout=60.0)

    async def on_timeout(self) -> None:
        m: discord.User = self.bot.get_user(self.mem.id) or await self.bot.fetch_user(self.mem.id)
        await m.send("The raid boss fled...💨")
        self.stop()

    @button(label="Catch", emoji="<:premium_ball:932263197497507860>")
    async def premium_catch(self, button: discord.Button, interaction: discord.Interaction):
        await interaction.response.defer()
        if self.__button_lock.locked():
            await interaction.followup.send("Please wait for the previous action to finish.")

        async with self.__button_lock:
            if self.mem.premium_balls < 1:
                return await interaction.followup.send(
                    "You don't have premium balls to use! Take part in raids to get more."
                )

            await interaction.user.send("You threw your premium ball...")

            self.tries += 1

            if self.tries > 5:
                return await interaction.followup.send(f"You are out of {emojis.premium_ball} Premium Balls!")

            caught: bool = random.randint(1, 500) < 25

            if isinstance(self.raids.damage_data, dict):
                damage_data: dict = self.raids.damage_data
            else:
                damage_data: dict = json.loads(self.raids.damage_data)
            damage_data = dict(sorted(damage_data.items(), key=lambda x: x[1], reverse=True))

            top_3: dict = dict(itertools.islice(damage_data.items(), 3))

            if str(interaction.user.id) in top_3:
                caught: bool = True

            if not caught:
                await interaction.followup.send("Argh... You almost had it!")

            else:
                pk: models.Pokemon = models.Pokemon.get_random(
                    species_id=self.raids.species_id,
                    level=random.randint(1, 60),
                    xp=0,
                    owner_id=self.mem.id,
                    timestamp=datetime.now(),
                    idx=self.mem.next_idx,
                    shiny=random.randint(1, 1000) == 1,
                )

                self.mem.next_idx += 1
                await pk.save()

                emb: discord.Embed = discord.Embed(
                    title="You caught it!",
                    description=f"You successfully caught {pk:l}!",
                    color=discord.Color.blurple(),
                )
                emb.set_image(
                    url="https://media.discordapp.net/attachments/890889580021157918/932255203669979137/20220116_181839.gif"
                )

                self.mem.premium_balls -= 1
                await self.mem.save()

                await interaction.followup.send(embed=emb)

                self.stop()


class TrainerBattleView(discord.ui.View):
    def __init__(self, ctx: commands.Context, trainer_data: dict):
        self.ctx: commands.Context = ctx
        self.trainer_data: dict = trainer_data

        self.__button_lock: asyncio.Lock = asyncio.Lock()

    @button(label="Fight", style=discord.ButtonStyle.blurple, emoji="⚔️")
    async def fight_button(self, button: discord.Button, interaction: discord.Interaction):
        if self.__button_lock.locked():
            return await interaction.response.send_message("You already clicked this button once.", ephemeral=True)

        async with self.__button_lock:
            self.stop()
            _pokemon: str = random.choice(self.trainer_data.__getitem__("pokemon"))
            _level: int = random.choice(self.trainer_data.__getitem__("level"))

            mem: models.JourneyMember = await models.JourneyMember.get(id=self.ctx.author.id)

            pk1: models.JourneyMember = mem
            pk1.owner_id = mem.id

            pk2sp = data.species_by_name(_pokemon)
            pk2: models.Pokemon = models.Pokemon.get_random(
                owner_id=None,
                species_id=pk2sp["species_id"],
                level=_level,
                idx=1,
                xp=0,
            )

            moves: list = data.get_pokemon_moves(pk2.species_id)
            if not moves:
                moves: list = data.get_pokemon_moves(pk2.specie["dex_number"])

            move_ids: list = [m["move_id"] for m in moves]

            pk2.moves = move_ids[:4]

            trainer1: Trainer = Trainer(self.ctx.author, [pk1], 0, pk1, False)
            trainer2: Trainer = Trainer(self.ctx.bot.user, [pk2], 0, pk2, True)

            msg: discord.Message = await self.ctx.reply(
                f"{self.trainer_data['name']} send out {_pokemon}!", mention_author=False
            )

            with self.ctx.typing():
                battle: Battle = Battle(
                    self.ctx.bot,
                    self.ctx,
                    [trainer1, trainer2],
                    BattleType.oneVone,
                    BattleEngine.AI,
                    Reward.JourneyTrainer,
                    trainer_data=self.trainer_data,
                )
                self.ctx.bot.battles.append(battle)

                await battle.send_battle()
                await msg.delete()
