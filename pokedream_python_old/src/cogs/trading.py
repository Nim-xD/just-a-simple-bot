import asyncio
from discord.ext.commands.converter import MemberConverter
from utils.exceptions import PokeBestError
from discord.ui import view
from core.views import Confirm
from typing import Any, Dict, Iterable, Optional, Union, List
import discord
from discord.ext import commands, tasks
from tortoise.fields import data

from core.bot import PokeBest
from utils.checks import has_started
from dataclasses import dataclass, field
import datetime
import models
from contextlib import suppress
from utils.converters import SpeciesConverter, PokemonConverter
from data import data
from aioredis_lock import RedisLock, LockTimeoutError


@dataclass
class TradeItems:
    balance: int = 0
    redeems: int = 0
    shards: int = 0
    pokemon: list = field(default_factory=list)

    @property
    def is_empty_trade(self):
        if self.balance == 0 and self.redeems == 0 and self.pokemon.__len__() == 0 and self.shards == 0:
            return True
        return False


@dataclass
class Trader:
    user: discord.User
    items: TradeItems
    another: int
    confirmed: bool = field(default=False)

    @property
    def id(self) -> int:
        return self.user.id

    def __str__(self) -> str:
        return self.user.__str__()


@dataclass
class Trade:
    traders: Iterable[Trader]
    ctx: commands.Context
    last_modified: Any  # Datetime object

    _confirmed: bool = field(default=False)

    def __repr__(self) -> str:
        return f"<Trade:{self.traders[0].user.name}|{self.traders[1].user.name}>"

    @property
    def can_confirm(self) -> bool:
        return datetime.datetime.now().second - self.last_modified.second < 3

    def trader_exists(self, trader_id: int) -> bool:
        return trader_id in [trader.id for trader in self.traders]


def cook_trade_items(items: TradeItems) -> str:
    txt: str = ""

    if items.balance != 0:
        txt += f"> **Credits**: {items.balance}\n"

    if items.redeems != 0:
        txt += f"> **Redeems**: {items.redeems}\n"

    if items.shards != 0:
        txt += f"> **Shards**: {items.shards}\n"

    if items.pokemon.__len__() != 0:
        for idx, pk in enumerate(items.pokemon, start=1):
            txt += f"> `{idx}` | {pk:l}\n"

    return txt if txt != "" else "Nothing"


async def parse_trade_items(ctx: commands.Context, items: str):
    trade_payload: Dict[str, str] = {}

    if items[-2:].lower() == "cr":
        try:
            balance: str = items.replace("cr", "")
            trade_payload["balance"] = int(balance)
        except BaseException:
            return None

    elif items[-1:].lower() == "r":
        try:
            redeems: str = items.replace("r", "")
            trade_payload["redeems"] = int(redeems)
        except BaseException:
            return None

    elif items[-1:].lower() == "s":
        try:
            shards: str = items.replace("s", "")
            trade_payload["shards"] = int(shards)
        except BaseException:
            return None

    elif items.isdigit():
        try:
            trade_payload["pokemon"] = await PokemonConverter().convert(ctx, items)
        except Exception:
            return None

    elif items.lower() == "all":
        try:
            # trade_payload["pokemons"] = await models.Pokemon.filter(owner_id=ctx.author.id).all()
            trade_payload["pokemons"] = []
            mem: models.Member = await ctx.bot.manager.fetch_member_info(ctx.author.id)
            pks: List[models.Pokemon] = await models.Pokemon.filter(owner_id=ctx.author.id).all()

            for pk in pks:
                if pk.idx != mem.selected_id:
                    trade_payload["pokemons"].append(pk)

        except Exception as e:
            return None

    return trade_payload


def get_trader_from_trade(trade: Trade, user: Union[discord.User, discord.Member, int]) -> Trader:
    for trader in trade.traders:
        if not isinstance(user, int) and trader.user == user or isinstance(user, int) and trader.user.id == user:
            return trader


# Idk why I made this XD
def get_trade_pokemon_from_idx(trade_items: TradeItems, pk_idx: int):
    try:
        return trade_items.pokemon[pk_idx - 1]
    except IndexError:
        return None


async def do_transfer(bot: PokeBest, trade: Trade):
    try:
        async with RedisLock(bot.redis, f"trade_process:{trade.traders[0].id}:{trade.traders[1].id}", 60, 1):
            trader: Trader = trade.traders[0]
            another: Trader = trade.traders[1]

            trader_model: models.Member = await models.Member.get(id=trader.user.id)
            another_model: models.Member = await models.Member.get(id=another.user.id)

            # Balance
            trader_model.balance += another.items.balance
            another_model.balance += trader.items.balance

            trader_model.balance -= trader.items.balance
            another_model.balance -= another.items.balance

            # Redeems
            trader_model.redeems += another.items.redeems
            another_model.redeems += trader.items.redeems

            trader_model.redeems -= trader.items.redeems
            another_model.redeems -= another.items.redeems

            # Shards
            trader_model.shards += another.items.shards
            another_model.shards += trader.items.shards

            trader_model.shards -= trader.items.shards
            another_model.shards -= another.items.shards

            if trader_model.balance < 0 or another_model.balance < 0:
                raise PokeBestError("Something went wrong while processing this trade.")

            # Exchanging pokemon
            if trader.items.pokemon.__len__() != 0:
                for pk in trader.items.pokemon:
                    pk.owner_id = another.user.id
                    pk.idx = another_model.next_idx

                    another_model.next_idx += 1

                    await pk.save()

            if another.items.pokemon.__len__() != 0:
                for pk in another.items.pokemon:
                    pk.owner_id = trader.user.id
                    pk.idx = trader_model.next_idx

                    trader_model.next_idx += 1

                    await pk.save()

            await trader_model.save()
            await another_model.save()

            bot.dispatch("trade_confirm", trade)

    except LockTimeoutError:
        return await trade.ctx.reply("This trade is getting processed. Please wait...", mention_author=False)


# This must be in `core.views` but I'm shifting it here due to circular imports
class TradeView(discord.ui.View):
    def __init__(self, bot: PokeBest, trade: Trade):
        super().__init__()
        self.trade: Trade = trade
        self.bot: PokeBest = bot

        self.__trade_lock: asyncio.Lock = asyncio.Lock()

    @property
    def trade_cog(self) -> "Trading":
        return self.bot.get_cog("Trading")

    @property
    def is_trade_avl(self) -> bool:
        return self.trade in self.trade_cog.trades

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id not in [trader.id for trader in self.trade.traders]:
            await interaction.response.send_message("You are not in this trade.", ephemeral=True)
            return False

        if self.is_trade_avl is False:
            await interaction.response.send_message("This trade is no longer available.", ephemeral=True)
            return False

        return True

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.success)
    async def confirm_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.defer()
        if self.__trade_lock.locked():
            return await interaction.followup.send("You already pressed confirm!", ephemeral=True)

        async with self.__trade_lock:
            if self.trade._confirmed:
                return await interaction.response.send_message("This trade is already confirmed!")

            if self.trade not in self.trade_cog.trades:
                return await interaction.response.send_message("This trade is no longer available.")

            self.stop()
            trader: Trader = get_trader_from_trade(self.trade, interaction.user)
            another: Trader = get_trader_from_trade(self.trade, trader.another)

            if another.items.is_empty_trade and trader.items.is_empty_trade:
                return await interaction.response.send_message(
                    "This trade is empty so it can't be confirmed!", ephemeral=True
                )

            trader.confirmed = True

            if trader.confirmed and another.confirmed:
                self.trade._confirmed = True

            trader_idx: int = self.trade.traders.index(trader)

            _b_trade: Trade = self.trade
            self.trade.traders[trader_idx] = trader
            self.trade.last_modified = datetime.datetime.now(datetime.timezone.utc)

            self.trade_cog.update_trade(_b_trade, self.trade)

            # Transfer the stuff if both are confirmed.
            if trader.confirmed and another.confirmed:
                msg: discord.Message = await self.trade.ctx.send(
                    "Trade is being processed, please wait and do **not** use any other commands until trade gets finished!"
                )

                await do_transfer(self.bot, self.trade)

                self.trade_cog.trades.remove(self.trade)
                await msg.delete()

                return await self.trade.ctx.send("Trade has been successfully processed!")

            await self.trade_cog.send_trade(self.trade.ctx, self.trade)

    @discord.ui.button(label="Cancel")
    async def cancel_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        self.trade_cog.trades.remove(self.trade)

        if hasattr(self, "message"):
            for b in self.children:
                b.style, b.disabled = discord.ButtonStyle.grey, True

            await self.message.edit(view=self)

        return await interaction.response.send_message("Trade has been cancelled.")


class Trading(commands.Cog):
    def __init__(self, bot: PokeBest):
        self.bot: PokeBest = bot
        self.trades: List[Trade] = []

        self.clear_abondant_trades.start()

    def is_in_trade(self, user: Union[discord.User, discord.Member]) -> bool:
        for trade in self.trades:
            for trader in trade.traders:
                if trader.user.id == user.id:
                    return True

        return False

    def get_trade(self, user: Union[discord.User, discord.Member]) -> Optional[Trade]:
        for trade in self.trades:
            for trader in trade.traders:
                if trader.user == user:
                    return trade

        return None

    def update_trade(self, trade_before: Trade, trade_after: Trade):
        idx: int = self.trades.index(trade_before)
        self.trades[idx] = trade_after

    async def send_trade(self, ctx: commands.Context, trade: Trade):
        trader: Trader = trade.traders[0]
        another: Trader = trade.traders[1]

        trade_emb: discord.Embed = self.bot.Embed(
            title=f"Trade between {trader.user} and {another.user}.",
            description=f"To see more information about trading, use `{ctx.prefix}help trade` command!",
        )

        trade_emb.add_field(
            name=f"{'🔴' if not trader.confirmed else '🟢'} | {trader.user.name} is offering:",
            value=cook_trade_items(trader.items),
            inline=True,
        )
        trade_emb.add_field(
            name=f"{'🔴' if not another.confirmed else '🟢'} | {another.user.name} is offering:",
            value=cook_trade_items(another.items),
            inline=True,
        )

        await ctx.send(embed=trade_emb, view=TradeView(self.bot, trade))

    @commands.group(aliases=("t",), invoke_without_command=True)
    @commands.guild_only()
    @has_started()
    async def trade(self, ctx: commands.Context, *, user: discord.Member):
        """Trade stuff with another trainer"""
        if user.id == ctx.author.id:
            return await ctx.reply("You can't trade with yourself!", mention_author=False)

        if self.is_in_trade(ctx.author):
            return await ctx.reply("You are already in one trade!", mention_author=False)

        if self.is_in_trade(user):
            return await ctx.reply(
                "Someone you are trying to trade with is already in one trade.",
                mention_author=False,
            )

        member: models.Member = await self.bot.manager.fetch_member_info(user.id)

        if not member or member is None:
            return await ctx.reply(
                "Someone you are trying to trade with haven't picked a starter yet!",
                mention_author=False,
            )

        _view: Confirm = Confirm(ctx, user.id)

        msg: discord.Message = await ctx.reply(
            f"{user.mention}, {ctx.author.mention} is inviting you for a trade.",
            mention_author=False,
            view=_view,
        )

        await _view.wait()

        if _view.value is None:
            with suppress(discord.Forbidden):
                return await msg.edit(embed=None, content="Time's up!", view=None, allowed_mentions=None)

        if _view.value is False:
            with suppress(discord.Forbidden):
                return await msg.edit(embed=None, content="Cancelled!", view=False, allowed_mentions=None)

        # Cross-checking the trade here again due to buttons
        if self.is_in_trade(ctx.author):
            return await ctx.reply("You are already in one trade!", mention_author=False)

        if self.is_in_trade(user):
            return await ctx.reply(
                "Someone you are trying to trade with is already in one trade.",
                mention_author=False,
            )

        with suppress((discord.Forbidden, discord.HTTPException)):
            await msg.delete()

        _traders: Iterable[Trader] = [
            Trader(user=ctx.author, another=user, items=TradeItems(), confirmed=False),
            Trader(user=user, another=ctx.author, items=TradeItems(), confirmed=False),
        ]

        trade: Trade = Trade(traders=_traders, ctx=ctx, last_modified=datetime.datetime.utcnow())
        self.trades.append(trade)

        await self.send_trade(ctx, trade)

    @trade.command(name="add")
    @has_started()
    async def trade_add(self, ctx: commands.Context, *, item: str):
        """Add any item to ongoing trade"""
        if not self.is_in_trade(ctx.author):
            return await ctx.reply("You are not in a trade!", mention_author=False)

        trade: Trade = self.get_trade(ctx.author)

        if trade.ctx.channel != ctx.channel:
            return await ctx.reply("You must be in same channel where trade started!", mention_author=False)

        trade_items: Optional[dict] = await parse_trade_items(ctx, item)

        if trade_items is None:
            raise PokeBestError(
                "Hey, looks like you used this command wrong. To add items in trade, here are the following commands:\n\n"
                + f"`{ctx.prefix}trade add <pokemon_id>` - To add Pokemon\n"
                + f"`{ctx.prefix}trade add <credits>cr` - To add credits\n"
                + f"`{ctx.prefix}trade add <redeems>r` - To add redeems\n"
                + f"`{ctx.prefix}trade add <shards>s` - To add shards"
            )

        trader: Trader = get_trader_from_trade(trade, ctx.author)

        member: models.Member = await self.bot.manager.fetch_member_info(ctx.author.id)

        if trade_items.get("balance", None) is not None:
            if member.balance < trade_items["balance"]:
                return await ctx.reply("You don't have that much balance!", mention_author=False)

            if trader.items.balance + trade_items["balance"] > member.balance:
                return await ctx.reply("You don't have that much balance to add!", mention_author=False)

            if trade_items["balance"] < 1:
                return await ctx.reply("Balance must be greater than zero!", mention_author=False)

            trader.items.balance += trade_items.get("balance")

        if trade_items.get("redeems", None) is not None:
            if member.balance < trade_items["redeems"]:
                return await ctx.reply("You don't have that much redeems!", mention_author=False)

            if trader.items.redeems + trade_items["redeems"] > member.redeems:
                return await ctx.reply("You don't have that much redeems to add!", mention_author=False)

            if trade_items["redeems"] < 1:
                return await ctx.reply("Amount of redeems must be greater than zero!", mention_author=False)

            trader.items.redeems += trade_items.get("redeems")

        if trade_items.get("shards", None) is not None:
            if member.shards < trade_items["shards"]:
                return await ctx.reply("You don't have that much shards!", mention_author=False)

            if trader.items.shards + trade_items["shards"] > member.shards:
                return await ctx.reply("You don't have that much shards to add!", mention_author=False)

            if trade_items["shards"] < 1:
                return await ctx.reply("Amount of shards must be greater than zero!", mention_author=False)

            trader.items.shards += trade_items.get("shards")

        if trade_items.get("pokemon", None) is not None:
            pokemon: Optional[models.Pokemon] = trade_items.get("pokemon")

            if pokemon is None:
                raise PokeBestError(
                    f"Hey, I guess you don't have any pokemon on that number! Use `{ctx.prefix}pokemon` command to view your pokemon collection and enter a correct number this time."
                )

            if pokemon in trader.items.pokemon:
                return await ctx.reply("This pokemon is already added in trade!", mention_author=False)

            if pokemon.idx == member.selected_id:
                return await ctx.reply("You can't trade your selected pokemon!", mention_author=False)

            if pokemon.favorite is True:
                return await ctx.reply("You can't trade your favourite pokemon!", mention_author=False)

            trader.items.pokemon.append(trade_items.get("pokemon"))

        trader_idx: int = trade.traders.index(trader)

        _b_trade: Trade = trade
        trade.traders[trader_idx] = trader
        trade.last_modified = datetime.datetime.utcnow()

        self.update_trade(_b_trade, trade)

        await self.send_trade(ctx, trade)

    @trade.command(name="remove")
    @has_started()
    async def trade_remove(self, ctx: commands.Context, *, item: str):
        """Remove a item from trade"""
        if not self.is_in_trade(ctx.author):
            return await ctx.reply("You are not in a trade!", mention_author=False)

        trade: Trade = self.get_trade(ctx.author)

        if trade.ctx.channel != ctx.channel:
            return await ctx.reply("You must be in same channel where trade started!", mention_author=False)

        trade_items: Optional[dict] = await parse_trade_items(ctx, item)

        if trade_items is None:
            raise PokeBestError(
                "Hey, looks like you used this command wrong. To remove items from trade, here are the following commands:\n\n"
                + f"`{ctx.prefix}trade remove <pokemon_id>` - To remove Pokemon\n"
                + f"`{ctx.prefix}trade remove <credits>cr` - To remove credits\n"
                + f"`{ctx.prefix}trade remove <redeems>r` - To remove redeems\n"
                + f"`{ctx.prefix}trade remove <shards>s` - To remove shards"
            )

        trader: Trader = get_trader_from_trade(trade, ctx.author)

        if trade_items.get("balance", None) is not None:
            if trader.items.balance - trade_items["balance"] < 0:
                return await ctx.reply(
                    "There aren't that much credits added in this trade!",
                    mention_author=False,
                )

            if trade_items["balance"] < 1:
                return await ctx.reply("Balance must be greater than zero!", mention_author=False)

            trader.items.balance -= trade_items.get("balance")

        if trade_items.get("redeems", None) is not None:
            if trader.items.redeems - trade_items["redeems"] < 0:
                return await ctx.reply(
                    "There aren't that much redeems added in this trade!",
                    mention_author=False,
                )

            if trade_items["redeems"] < 1:
                return await ctx.reply("Amount of redeems must be greater than zero!", mention_author=False)

            trader.items.redeems -= trade_items.get("redeems")

        if trade_items.get("shards", None) is not None:
            if trader.items.shards - trade_items["shards"] < 0:
                return await ctx.reply(
                    "There aren't that much shards added in this trade!",
                    mention_author=False,
                )

            if trade_items["shards"] < 1:
                return await ctx.reply("Amount of shards must be greater than zero!", mention_author=False)

            trader.items.shards -= trade_items.get("shards")

        if item.isdigit():
            pokemon: Optional[models.Pokemon] = get_trade_pokemon_from_idx(trader.items, int(item))

            if pokemon is None:
                return await ctx.reply("Looks like that pokemon is not in trade.", mention_author=False)

            if pokemon not in trader.items.pokemon:
                return await ctx.reply("This pokemon is not added in trade!", mention_author=False)

            trader.items.pokemon.remove(pokemon)

        trader_idx: int = trade.traders.index(trader)

        _b_trade: Trade = trade
        trade.traders[trader_idx] = trader
        trade.last_modified = datetime.datetime.utcnow()

        self.update_trade(_b_trade, trade)

        await self.send_trade(ctx, trade)

    @trade.command(name="addall")
    @has_started()
    async def trade_addall(self, ctx: commands.Context):
        """Add all your pokemon in trade"""
        if not self.is_in_trade(ctx.author):
            return await ctx.reply("You are not in a trade!", mention_author=False)

        trade: Trade = self.get_trade(ctx.author)

        if trade.ctx.channel != ctx.channel:
            return await ctx.reply("You must be in same channel where trade started!", mention_author=False)

        trade_items: Optional[dict] = await parse_trade_items(ctx, "all")

        trader: Trader = get_trader_from_trade(trade, ctx.author)
        trader.items.pokemon = []

        if trade_items is None:
            return await ctx.reply(
                "Something went wrong... Maybe you don't have any pokemon.",
                mention_author=False,
            )

        for pk in trade_items["pokemons"]:
            trader.items.pokemon.append(pk)

        trader_idx: int = trade.traders.index(trader)

        _b_trade: Trade = trade
        trade.traders[trader_idx] = trader
        trade.last_modified = datetime.datetime.utcnow()

        self.update_trade(_b_trade, trade)

        await self.send_trade(ctx, trade)

    @trade.command(name="removeall")
    @has_started()
    async def trade_removeall(self, ctx: commands.Context):
        if not self.is_in_trade(ctx.author):
            return await ctx.reply("You are not in a trade!", mention_author=False)

        trade: Trade = self.get_trade(ctx.author)

        if trade.ctx.channel != ctx.channel:
            return await ctx.reply("You must be in same channel where trade started!", mention_author=False)

        trade_items: Optional[dict] = await parse_trade_items(ctx, "all")

        trader: Trader = get_trader_from_trade(trade, ctx.author)

        trader.items.balance = 0
        trader.items.shards = 0
        trader.items.redeems = 0
        trader.items.pokemon = []

        trader_idx: int = trade.traders.index(trader)

        _b_trade: Trade = trade
        trade.traders[trader_idx] = trader
        trade.last_modified = datetime.datetime.utcnow()

        self.update_trade(_b_trade, trade)

        await self.send_trade(ctx, trade)

    @trade.command(name="cancel")
    @has_started()
    async def trade_cancel(self, ctx: commands.Context):
        """Cancels ongoing trade"""
        if not self.is_in_trade(ctx.author):
            return await ctx.reply("You are not in a trade!", mention_author=False)

        for trade in self.trades:
            if trade.trader_exists(ctx.author.id):
                self.trades.remove(trade)
                return await ctx.reply("Trade cancelled!", mention_author=False)

        return await ctx.reply("Eh... I don't think you are in a trade.", mention_author=False)

    # @commands.command()
    # async def gift(self, ctx: commands.Context, mem: MemberConverter, pokemon: PokemonConverter):
    #     """Gift a pokemon to a trainer"""
    #     ...

    @commands.Cog.listener()
    async def on_trade_confirm(self, trade: Trade):
        self.trade_log_hook: discord.Webhook = discord.Webhook.from_url(
            "https://discord.com/api/webhooks/943076011631853608/FoHSxdYzvBrGIk9rzcd5kpEL-W-lccoT0HLzPh2krD-3SOnbTilkvv3HQmmzKIJInopm",
            session=self.bot.session,
        )

        trader: Trader = trade.traders[0]
        another: Trader = trade.traders[1]

        trade_emb: discord.Embed = self.bot.Embed(
            title=f"Trade between {trader.user} and {another.user}.",
        )

        trade_emb.add_field(
            name=f"{'🔴' if not trader.confirmed else '🟢'} | {trader.user.name} is offering:",
            value=cook_trade_items(trader.items),
            inline=True,
        )
        trade_emb.add_field(
            name=f"{'🔴' if not another.confirmed else '🟢'} | {another.user.name} is offering:",
            value=cook_trade_items(another.items),
            inline=True,
        )

        trade_emb.add_field(name="Guild ID", value=trade.ctx.guild.id)
        trade_emb.add_field(name="Guild Name", value=trade.ctx.guild.name)
        trade_emb.add_field(name=f"{trader.user} ID", value=trader.user.id)
        trade_emb.add_field(name=f"{another.user} ID", value=another.user.id)
        await self.trade_log_hook.send(embed=trade_emb)

    @tasks.loop(seconds=10)
    async def clear_abondant_trades(self):
        for trade in self.trades:
            if (datetime.datetime.utcnow() - trade.last_modified).seconds > 120:
                with suppress(discord.HTTPException, discord.Forbidden, Exception):
                    await trade.ctx.send("Cancelling trade due to inactivity.")
                self.trades.remove(trade)

    @clear_abondant_trades.before_loop
    async def before_clear_abondant_trades(self):
        await self.bot.wait_until_ready()


def setup(bot: PokeBest) -> None:
    bot.add_cog(Trading(bot))
