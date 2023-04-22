from contextlib import suppress
from operator import mod

from discord.enums import ContentFilter
from core.views import Confirm, MarketView
import models
from utils.converters import MarketConverter, PokemonConverter
from utils.checks import has_started
from discord.ext import commands
import discord

from core.bot import PokeBest
from utils.exceptions import MarketNotFound, PokeBestError
from typing import Iterable, List, Optional
import math
from core.paginator import SimplePaginator
from utils import flags
from utils.filters import create_filter
from aioredis_lock import RedisLock, LockTimeoutError


class Market(commands.Cog):
    def __init__(self, bot: PokeBest) -> None:
        self.bot: PokeBest = bot

    @commands.group(name="market")
    @has_started()
    async def market(self, ctx: commands.Context):
        """All commands used for markets"""
        if ctx.invoked_subcommand is None:
            return await ctx.send_help(ctx.command)

    @market.command(name="list", aliases=("l",))
    @has_started()
    async def market_list(
        self,
        ctx: commands.Context,
        pokemon: PokemonConverter(accept_blank=False),
        price: int,
    ):
        """List your pokemon in market"""
        member: models.Member = await self.bot.manager.fetch_member_info(ctx.author.id)

        if member.selected_id == pokemon.idx:
            return await ctx.reply("You can't list your selected pokemon!", mention_author=False)

        if pokemon is None:
            raise PokeBestError(
                f"Looks like you entered a wrong pokemon. To view the list of your pokemon use `{ctx.prefix}pokemon` command and enter a valid index."
            )

        if price < 1:
            return await ctx.reply("Price can't be negative!", mention_author=False)

        if price > 10000000:
            return await ctx.reply("Price is too high!", mention_author=False)

        _view: Confirm = Confirm(ctx)

        msg: discord.Message = await ctx.reply(
            f"Are you sure you want to list your {self.bot.sprites.get(pokemon.specie['dex_number'], pokemon.shiny)} `{pokemon:l}` in market for **{price}** credits?",
            mention_author=False,
            view=_view,
        )

        await _view.wait()

        if _view.value is None:
            with suppress(discord.Forbidden):
                return await msg.edit("Time's up!", view=None, allowed_mentions=None)
            return

        if _view.value is False:
            with suppress(discord.Forbidden):
                return await msg.edit("Cancelled!", view=False, allowed_mentions=None)
            return

        market_res: models.Listings = models.Listings(pokemon=pokemon.id, user_id=ctx.author.id, price=price)
        pokemon.owner_id = None

        _pk: Optional[models.Pokemon] = await self.bot.manager.fetch_pokemon_by_number(ctx.author.id, pokemon.idx)

        if _pk is None or _pk.owner_id is None:
            return await ctx.reply(
                "Looks like that pokemon has been already listed on market or somewhere else.",
                mention_author=False,
            )

        await pokemon.save()
        await market_res.save()

        try:
            return await msg.edit(
                f"Successfully listed your {self.bot.sprites.get(pokemon.specie['dex_number'], pokemon.shiny)} {pokemon:l} on market with **ID: {market_res.id}**!",
                allowed_mentions=None,
                view=None,
            )

        except discord.Forbidden:
            return await ctx.reply(
                f"Successfully listed your {self.bot.sprites.get(pokemon.specie['dex_number'], pokemon.shiny)} {pokemon:l} on market with **ID: {market_res.id}**!",
                mention_author=False,
                view=None,
            )

    async def prepare_market_pages(
        self, ctx: commands.Context, title: str, specific_market: bool = False, flags={}
    ) -> List[discord.Embed]:
        if not specific_market:
            _market_model_list: List[models.Listings] = await self.bot.manager.fetch_all_market_list()

        elif specific_market is True:
            _market_model_list: List[models.Listings] = await self.bot.manager.fetch_user_market(ctx.author.id)

        _market_model_list = await create_filter(flags, ctx, _market_model_list, market=True)

        if _market_model_list.__len__() == 0:
            return None

        _market_model_list.sort(key=lambda k: k.id)

        pages: List[discord.Embed] = []

        async def get_page(pidx: int):
            pgstart: int = pidx * 15
            pgend: int = max(min(pgstart + 15, _market_model_list.__len__()), 0)
            txt: str = ""

            if pgstart != pgend:
                for market in _market_model_list[pgstart:pgend]:
                    pk = await self.bot.manager.fetch_pokemon_by_id(market.pokemon)
                    if pk is None:
                        await market.delete()
                        continue

                    txt += f"`{market.id}` | {self.bot.sprites.get(pk.specie['dex_number'], pk.shiny)} **{pk:l}** | IV: {pk.iv_total/186:.2%} | Price: {market.price}\n"
            else:
                for market in [_market_model_list[pgstart]]:
                    pk = await self.bot.manager.fetch_pokemon_by_id(market.pokemon)
                    if pk is None:
                        await market.delete()
                        continue

                    txt += f"`{market.id}` | {self.bot.sprites.get(pk.specie['dex_number'], pk.shiny)} **{pk:l}** | IV: {pk.iv_total/186:.2%} | Price: {market.price}\n"

            return self.bot.Embed(description=txt, title=title).set_footer(
                text=f"Showing {pgstart+1}-{pgend} of {_market_model_list.__len__()} markets."
            )

        total_pages: int = math.ceil(_market_model_list.__len__() / 15)

        for i in range(total_pages):
            page = await get_page(i)
            pages.append(page)

        return pages

    @flags.add_flag("--shiny", action="store_true")
    @flags.add_flag("--alolan", action="store_true")
    @flags.add_flag("--galarian", action="store_true")
    @flags.add_flag("--mythical", "--m", action="store_true")
    @flags.add_flag("--legendary", "--l", action="store_true")
    @flags.add_flag("--ub", action="store_true")
    @flags.add_flag("--favorite", "--fav", action="store_true")
    @flags.add_flag("--name", "--n", nargs="+", action="append")
    @flags.add_flag("--nickname", nargs="+", action="append")
    @flags.add_flag("--type", "--t", type=str, action="append")

    # IV
    @flags.add_flag("--level", nargs="+", action="append")
    @flags.add_flag("--hpiv", nargs="+", action="append")
    @flags.add_flag("--atkiv", nargs="+", action="append")
    @flags.add_flag("--defiv", nargs="+", action="append")
    @flags.add_flag("--spatkiv", nargs="+", action="append")
    @flags.add_flag("--spdefiv", nargs="+", action="append")
    @flags.add_flag("--spdiv", nargs="+", action="append")
    @flags.add_flag("--iv", nargs="+", action="append")
    @market.command(name="search", aliases=("s",), case_insensitve=True, cls=flags.FlagCommand)
    @has_started()
    async def market_search(self, ctx: commands.Context, **flags):
        """Search for any pokemon in market"""
        with ctx.typing():
            pages: List[discord.Embed] = await self.prepare_market_pages(ctx, "Available Markets:", False, flags)

        if pages is None:
            return await ctx.reply("There are no markets matching the search!", mention_author=False)

        if len(pages) > 1:
            paginator: SimplePaginator = SimplePaginator(ctx, pages)
            await paginator.paginate(ctx)
        else:
            await ctx.send(embed=pages.__getitem__(0))

    @flags.add_flag("--shiny", action="store_true")
    @flags.add_flag("--alolan", action="store_true")
    @flags.add_flag("--galarian", action="store_true")
    @flags.add_flag("--mythical", "--m", action="store_true")
    @flags.add_flag("--legendary", "--l", action="store_true")
    @flags.add_flag("--ub", action="store_true")
    @flags.add_flag("--favorite", "--fav", action="store_true")
    @flags.add_flag("--name", "--n", nargs="+", action="append")
    @flags.add_flag("--nickname", nargs="+", action="append")
    @flags.add_flag("--type", "--t", type=str, action="append")

    # IV
    @flags.add_flag("--level", nargs="+", action="append")
    @flags.add_flag("--hpiv", nargs="+", action="append")
    @flags.add_flag("--atkiv", nargs="+", action="append")
    @flags.add_flag("--defiv", nargs="+", action="append")
    @flags.add_flag("--spatkiv", nargs="+", action="append")
    @flags.add_flag("--spdefiv", nargs="+", action="append")
    @flags.add_flag("--spdiv", nargs="+", action="append")
    @flags.add_flag("--iv", nargs="+", action="append")
    @market.command(name="listings", cls=flags.FlagCommand)
    @has_started()
    async def market_listings(self, ctx: commands.Context, **flags):
        """Shows the list of your markets"""
        with ctx.typing():
            pages: List[discord.Embed] = await self.prepare_market_pages(ctx, "Your Markets:", True, flags)

        if pages is None:
            return await ctx.reply("There are no markets matching the search!", mention_author=False)

        if len(pages) > 1:
            paginator: SimplePaginator = SimplePaginator(ctx, pages)
            await paginator.paginate(ctx)
        else:
            await ctx.send(embed=pages.__getitem__(0))

    @market.command(name="remove")
    @has_started()
    async def market_remove(self, ctx: commands.Context, market: MarketConverter):
        """Remove your pokemon from market"""
        if market is None:
            raise MarketNotFound(ctx)

        if market.user_id != ctx.author.id:
            return await ctx.reply("You don't own this market!", mention_author=False)

        pokemon: models.Pokemon = await self.bot.manager.fetch_pokemon_by_id(market.pokemon)

        _view: Confirm = Confirm(ctx)

        msg: discord.Message = await ctx.reply(
            embed=self.bot.Embed(
                description=f"Are you sure you want to remove your {self.bot.sprites.get(pokemon.specie['dex_number'], pokemon.shiny)} {pokemon:l} from market?"
                + "\n\n⚠️ __Note__ ⚠️\nAll the offers will also be deleted once the pokemon is removed."
            ),
            mention_author=False,
            view=_view,
        )

        await _view.wait()

        if _view.value is None:
            with suppress(discord.Forbidden):
                return await msg.edit(embed=None, content="Time's up!", view=None, allowed_mentions=None)
            return

        if _view.value is False:
            with suppress(discord.Forbidden):
                return await msg.edit(embed=None, content="Cancelled!", view=False, allowed_mentions=None)
            return
        
        pokemon.owner_id = ctx.author.id
        await pokemon.save()

        await market.delete()

        return await msg.edit(
            content=f"Successfully removed your {self.bot.sprites.get(pokemon.specie['dex_number'], pokemon.shiny)} {pokemon:l} from market!",
            embed=None,
            allowed_mentions=None,
            view=None,
        )

    async def _log_market_buy(self, ctx: commands.Context, market: models.Listings, pokemon: models.Pokemon):
        _log_embed: discord.Embed = self.bot.Embed(title="Pokemon Sold")
        _log_embed.add_field(
            name="Pokemon",
            value=f"{self.bot.sprites.get(pokemon.specie['dex_number'], pokemon.shiny)} `{pokemon:l}`",
        )
        _log_embed.add_field(name="Market Owner:", value=f"{market.user_id}")
        _log_embed.add_field(name="Market ID", value=f"{market.id}")
        _log_embed.add_field(name="Price", value=f"{market.price}")
        _log_embed.add_field(name="Bought by", value=f"{ctx.author.name} | ID: `{ctx.author.id}`")

        self.market_log_hook: discord.Webhook = discord.Webhook.from_url(
            "https://discord.com/api/webhooks/943076907220602940/02gpQJtwthpg8f4Bb2S4-PTPnwBoZodCF4y_KYzyGUParME8zWp2_ywoV1hNyIP7iZ78",
            session=self.bot.session,
        )
        await self.market_log_hook.send(embed=_log_embed)

        await market.delete()

    @market.command(name="buy")
    @commands.max_concurrency(1, per=commands.BucketType.guild)
    @has_started()
    async def market_buy(self, ctx: commands.Context, market: MarketConverter):
        """Buy a pokemon from market"""
        if not market:
            raise MarketNotFound(ctx)

        if market.user_id == ctx.author.id:
            return await ctx.reply("You can't buy your own pokemon!", mention_author=False)

        member: models.Member = await self.bot.manager.fetch_member_info(ctx.author.id)

        if market.price > member.balance:
            return await ctx.reply(
                "You don't have enough balance to buy this pokemon!",
                mention_author=False,
            )

        pokemon: models.Pokemon = await self.bot.manager.fetch_pokemon_by_id(market.pokemon)

        _view: Confirm = Confirm(ctx)
        msg: discord.Message = await ctx.reply(
            f"Are you want to buy {pokemon:l} for {market.price} credits?",
            mention_author=False,
            view=_view,
        )

        await _view.wait()

        if _view.value is None:
            with suppress(discord.Forbidden):
                return await msg.edit(embed=None, content="Time's up!", view=None, allowed_mentions=None)
            return

        if _view.value is False:
            with suppress(discord.Forbidden):
                return await msg.edit(embed=None, content="Cancelled!", view=False, allowed_mentions=None)
            return

        # Process the buying procedure
        with ctx.typing():
            try:
                async with RedisLock(self.bot.redis, f"market_buy:{market.id}", 60, 1):
                    _pk: Optional[models.Pokemon] = await self.bot.manager.fetch_pokemon_by_id(pokemon.id)
                    if _pk.owner_id is not None:
                        return await ctx.reply(
                            "This pokemon is not available in market anymore.",
                            mention_author=False,
                        )

                    pokemon.owner_id = ctx.author.id
                    pokemon.idx = member.next_idx

                    member.balance -= market.price
                    member.next_idx += 1

                    await pokemon.save()
                    await member.save()

                    market_owner: models.Member = await self.bot.manager.fetch_member_info(market.user_id)
                    await self.bot.manager.update_member(market_owner.id, balance=market_owner.balance + market.price)

                    with suppress(discord.Forbidden):
                        owner: discord.User = self.bot.get_user(market_owner.id) or await self.bot.fetch_user(
                            market.user_id
                        )
                        await owner.send(
                            f"Your {self.bot.sprites.get(pokemon.specie['dex_number'], pokemon.shiny)} {pokemon:l} has been sold for {market.price} credits in market!"
                        )

                    await self._log_market_buy(ctx, market, pokemon)

                    return await msg.edit(
                        f"Successfully completed transaction! Use `{ctx.prefix}info latest` command to view this pokemon!",
                        allowed_mentions=None,
                        view=None,
                    )
            except LockTimeoutError:
                return await ctx.reply("Someone is already buying this market.", mention_author=False)

    @market.command(name="info")
    @has_started()
    async def market_info(self, ctx: commands.Context, market: MarketConverter):
        """View any market pokemon"""
        if not market:
            raise MarketNotFound(ctx)

        pokemon_id: int = market.pokemon
        pokemon: models.Pokemon = await self.bot.manager.fetch_pokemon_by_id(pokemon_id)

        if pokemon is None:
            raise PokeBestError(
                f"That pokemon is not available in market now. To check the list of pokemon available in market you can use `{ctx.prefix}market search` command."
            )

        _embed: discord.Embed = self.bot.Embed(title=f"{pokemon:l} | ID: {market.id}")

        _embed.add_field(name="Pokemon Stats", value="\n".join(f"> {s}" for s in pokemon.get_stats))

        _market_info: Iterable[str] = (
            f"> **Price**: {market.price} credits",
            f"> **Owner**: <@{market.user_id}>",
        )

        _embed.add_field(name="Market Info", value="\n".join(_market_info), inline=False)

        _embed.set_thumbnail(url=pokemon.normal_image)

        await ctx.reply(embed=_embed, mention_author=False, view=MarketView(ctx, market))

    # @market.group(name="offer", invoke_without_command=True)
    # @has_started()
    # async def market_offer(self, ctx: commands.Context, market: MarketConverter, price: int):  # sourcery no-metrics
    #     """Bargain a pokemon in market"""
    #     if not market:
    #         raise MarketNotFound(ctx)

    #     if market.user_id == ctx.author.id:
    #         return await ctx.reply(
    #             "You can't perform this action on your own market!",
    #             mention_author=False,
    #         )

    #     if price < 1:
    #         return await ctx.reply("Price can't be a negative number!", mention_author=False)

    #     if price > 10000000:
    #         return await ctx.reply("Price is too high!", mention_author=False)

    #     mem: models.Member = await self.bot.manager.fetch_member_info(ctx.author.id)
    #     if mem.balance < price:
    #         return await ctx.reply("You don't have that much balance to offer.", mention_author=False)

    #     highest: int = 0
    #     highest_user: int = None
    #     if market.offers is not None or market.offers.__len__() != 0:
    #         for odata in market.offers:
    #             if odata["price"] > highest:
    #                 highest = odata["price"]
    #                 highest_user = odata["user_id"]

    #     if highest_user == ctx.author.id:
    #         return await ctx.reply("You are already the highest offerer!", mention_author=False)

    #     if highest != 0 and price < highest:
    #         return await ctx.reply(f"Offer must be greater that {highest}!", mention_author=False)

    #     _view: Confirm = Confirm(ctx)

    #     pokemon: models.Pokemon = await self.bot.manager.fetch_pokemon_by_id(market.pokemon)

    #     msg: discord.Message = await ctx.reply(
    #         f"Are you sure you want to offer **{price}** credits for {self.bot.sprites.get(pokemon.specie['dex_number'], pokemon.shiny)} `{pokemon:l}`?",
    #         mention_author=False,
    #         view=_view,
    #     )

    #     await _view.wait()

    #     if _view.value is None:
    #         with suppress(discord.Forbidden):
    #             return await msg.edit(embed=None, content="Time's up!", view=None, allowed_mentions=None)

    #     if _view.value is False:
    #         with suppress(discord.Forbidden):
    #             return await msg.edit(embed=None, content="Cancelled!", view=False, allowed_mentions=None)

    #     offer_payload: dict = {
    #         "offer_id": market.offers.__len__() + 1,
    #         "user_id": ctx.author.id,
    #         "price": price,
    #     }

    #     market.offers = ArrayAppend("offers", json.dumps(offer_payload))

    #     await market.save()

    #     with suppress((discord.HTTPException, discord.Forbidden)):
    #         market_owner: discord.User = self.bot.get_user(market.user_id) or await self.bot.fetch_user(market.user_id)

    #         offer_emb: discord.Embed = self.bot.Embed(
    #             title="You received an offer!",
    #             description=f"You received a new offer for your {self.bot.sprites.get(pokemon.specie['dex_number'], pokemon.shiny)} `{pokemon:l}` which you listed in market *(ID: {market.id})*."
    #             + f"\nThe amount you are offered is: **{price} credits**!"
    #             + f"\n\nTo see the list of offers use `{ctx.prefix} market offers {market.id}` command and to accept this one use `{ctx.prefix}market offer accept {offer_payload.__getitem__('offer_id')}` command.",
    #         )

    #         await market_owner.send(embed=offer_emb)

    #     return await msg.edit("Successfully added your offer!", allowed_mentions=None, view=None)

    # async def prepare_offer_pages(self, title: str, market: MarketConverter):
    #     offers = await self.bot.manager.fetch_market_offers(market.id)

    #     if offers.__len__() == 0:
    #         return None

    #     pages: List[discord.Embed] = []

    #     async def get_page(pidx: int):
    #         pgstart: int = pidx * 15
    #         pgend: int = max(min(pgstart + 15, offers.__len__()), 0)
    #         txt: str = ""

    #         if pgstart != pgend:
    #             for offer in offers[pgstart:pgend]:
    #                 txt += f"`{offer['offer_id']}` | **Amount**: {offer['price']} | By: <@{offer['user_id']}>\n"
    #         else:
    #             for offer in [offers[pgstart]]:
    #                 txt += f"`{offer['offer_id']}` | **Amount**: {offer['price']} | By: <@{offer['user_id']}>\n"

    #         return self.bot.Embed(description=txt, title=title).set_footer(
    #             text=f"Showing {pgstart+1}-{pgend} of {offers.__len__()} offers."
    #         )

    #     total_pages: int = math.ceil(offers.__len__() / 15)

    #     for i in range(total_pages):
    #         page = await get_page(i)
    #         pages.append(page)

    #     return pages

    # @market.command(name="offers")
    # @has_started()
    # async def market_offers(self, ctx: commands.Context, market: MarketConverter):
    #     """View your market offers"""
    #     if not market:
    #         raise MarketNotFound(ctx)

    #     if market.user_id != ctx.author.id:
    #         return await ctx.reply(
    #             "You don't own this market!",
    #             mention_author=False,
    #         )

    #     with ctx.typing():
    #         pages: List[discord.Embed] = await self.prepare_offer_pages(f"Your offers for Market ID: {market.id}", market)

    #     if pages is None:
    #         return await ctx.reply("There are no offers matching the search!", mention_author=False)

    #     if len(pages) > 1:
    #         paginator: SimplePaginator = SimplePaginator(ctx, pages)
    #         await paginator.paginate(ctx)
    #     else:
    #         await ctx.send(embed=pages.__getitem__(0))

    # @market_offer.command(name="accept")
    # @has_started()
    # async def market_offer_accept(self, ctx: commands.Context, market: MarketConverter, offer_id: int):
    #     if market.user_id != ctx.author.id:
    #         return await ctx.reply("You don't own this market!", mention_author=False)

    #     try:
    #         offer_data: dict = market.offers[offer_id - 1]
    #     except IndexError:
    #         raise PokeBestError(
    #             f"You don't have any offer on that number for your market {market.id}. To see the full list of offers you have on your market use `{ctx.prefix}market offers {market.id}` command`."
    #         )

    #     _view: Confirm = Confirm(ctx)

    #     msg: discord.Message = await ctx.reply(
    #         "Are you sure you want to accept this offer?",
    #         mention_author=False,
    #         view=_view,
    #     )

    #     await _view.wait()

    #     if _view.value is None:
    #         with suppress(discord.Forbidden):
    #             return await msg.edit(embed=None, content="Time's up!", view=None, allowed_mentions=None)

    #     if _view.value is False:
    #         with suppress(discord.Forbidden):
    #             return await msg.edit(embed=None, content="Cancelled!", view=False, allowed_mentions=None)

    #     with ctx.typing():
    #         pokemon: models.Pokemon = await self.bot.manager.fetch_pokemon_by_id(market.pokemon)

    #         if pokemon.owner_id is not None:
    #             return await ctx.reply("That pokemon is already owned by someone.", mention_author=False)

    #         member: models.Member = await self.bot.manager.fetch_member_info(ctx.author.id)
    #         offerer: models.Member = await self.bot.manager.fetch_member_info(offer_data.__getitem__("user_id"))

    #         pokemon.owner_id = offer_data["user_id"]
    #         pokemon.idx = offerer.next_idx
    #         await self.bot.manager.update_member(ctx.author.id, balance=member.balance + offer_data["price"])
    #         await self.bot.manager.update_idx(offerer.id)

    #         await pokemon.save()

    #         await self.bot.manager.update_member(offerer.id, balance=offerer.balance - offer_data["price"])

    #         with suppress(discord.Forbidden):
    #             offerer_user: discord.User = self.bot.get_user(offerer.id) or await self.bot.fetch_user(offerer.id)
    #             await offerer_user.send(
    #                 f"Your offer has been accepted for market **ID: {market.id}**! Use `p!info latest` command to see the pokemon!"
    #             )

    #         await market.delete()

    #     return await msg.edit(
    #         f"Successfully completed transaction! Your pokemon has been sold for **{offer_data['price']}** credits!",
    #         allowed_mentions=None,
    #         view=None,
    #     )


def setup(bot: PokeBest) -> None:
    bot.add_cog(Market(bot))
from contextlib import suppress
from operator import mod

from discord.enums import ContentFilter
from core.views import Confirm, MarketView
import models
from utils.converters import MarketConverter, PokemonConverter
from utils.checks import has_started
from discord.ext import commands
import discord

from core.bot import PokeBest
from utils.exceptions import MarketNotFound, PokeBestError
from typing import Iterable, List, Optional
import math
from core.paginator import SimplePaginator
from models.helpers import ArrayAppend
from utils import flags
import json
import pickle

from utils.filters import create_filter


class Market(commands.Cog):
    def __init__(self, bot: PokeBest) -> None:
        self.bot: PokeBest = bot

    @commands.group(name="market")
    @has_started()
    async def market(self, ctx: commands.Context):
        """All commands used for markets"""
        if ctx.invoked_subcommand is None:
            return await ctx.send_help(ctx.command)

    @market.command(name="list", aliases=("l",))
    @has_started()
    async def market_list(
        self,
        ctx: commands.Context,
        pokemon: PokemonConverter(accept_blank=False),
        price: int,
    ):
        """List your pokemon in market"""
        member: models.Member = await self.bot.manager.fetch_member_info(ctx.author.id)

        if member.selected_id == pokemon.idx:
            return await ctx.reply("You can't list your selected pokemon!", mention_author=False)

        if pokemon is None:
            raise PokeBestError(
                f"Looks like you entered a wrong pokemon. To view the list of your pokemon use `{ctx.prefix}pokemon` command and enter a valid index."
            )

        if price < 1:
            return await ctx.reply("Price can't be negative!", mention_author=False)

        if price > 10000000:
            return await ctx.reply("Price is too high!", mention_author=False)

        _view: Confirm = Confirm(ctx)

        msg: discord.Message = await ctx.reply(
            f"Are you sure you want to list your {self.bot.sprites.get(pokemon.specie['dex_number'], pokemon.shiny)} `{pokemon:l}` in market for **{price}** credits?",
            mention_author=False,
            view=_view,
        )

        await _view.wait()

        if _view.value is None:
            with suppress(discord.Forbidden):
                return await msg.edit("Time's up!", view=None, allowed_mentions=None)

        if _view.value is False:
            with suppress(discord.Forbidden):
                return await msg.edit("Cancelled!", view=False, allowed_mentions=None)

        market_res: models.Listings = models.Listings(pokemon=pokemon.id, user_id=ctx.author.id, price=price)
        pokemon.owner_id = None

        _pk: Optional[models.Pokemon] = await self.bot.manager.fetch_pokemon_by_number(ctx.author.id, pokemon.idx)

        if _pk is None or _pk.owner_id is None:
            return await ctx.reply(
                "Looks like that pokemon has been already listed on market or somewhere else.",
                mention_author=False,
            )

        await pokemon.save()
        await market_res.save()

        try:
            return await msg.edit(
                f"Successfully listed your {self.bot.sprites.get(pokemon.specie['dex_number'], pokemon.shiny)} {pokemon:l} on market with **ID: {market_res.id}**!",
                allowed_mentions=None,
                view=None,
            )

        except discord.Forbidden:
            return await ctx.reply(
                f"Successfully listed your {self.bot.sprites.get(pokemon.specie['dex_number'], pokemon.shiny)} {pokemon:l} on market with **ID: {market_res.id}**!",
                mention_author=False,
                view=None,
            )

    async def prepare_market_pages(
        self, ctx: commands.Context, title: str, specific_market: bool = False, flags={}
    ) -> List[discord.Embed]:
        if not specific_market:
            _market_model_list: List[models.Listings] = await self.bot.manager.fetch_all_market_list()

        elif specific_market is True:
            _market_model_list: List[models.Listings] = await self.bot.manager.fetch_user_market(ctx.author.id)

        _market_model_list = await create_filter(flags, ctx, _market_model_list, market=True)

        if _market_model_list.__len__() == 0:
            return None

        _market_model_list.sort(key=lambda k: k.id)

        pages: List[discord.Embed] = []

        async def get_page(pidx: int):
            pgstart: int = pidx * 15
            pgend: int = max(min(pgstart + 15, _market_model_list.__len__()), 0)
            txt: str = ""

            if pgstart != pgend:
                for market in _market_model_list[pgstart:pgend]:
                    pk = await self.bot.manager.fetch_pokemon_by_id(market.pokemon)
                    if pk is None:
                        await market.delete()
                        continue

                    txt += f"`{market.id}` | {self.bot.sprites.get(pk.specie['dex_number'], pk.shiny)} **{pk:l}** | IV: {pk.iv_total/186:.2%} | Price: {market.price}\n"
            else:
                for market in [_market_model_list[pgstart]]:
                    pk = await self.bot.manager.fetch_pokemon_by_id(market.pokemon)
                    if pk is None:
                        await market.delete()
                        continue

                    txt += f"`{market.id}` | {self.bot.sprites.get(pk.specie['dex_number'], pk.shiny)} **{pk:l}** | IV: {pk.iv_total/186:.2%} | Price: {market.price}\n"

            return self.bot.Embed(description=txt, title=title).set_footer(
                text=f"Showing {pgstart+1}-{pgend} of {_market_model_list.__len__()} markets."
            )

        total_pages: int = math.ceil(_market_model_list.__len__() / 15)

        for i in range(total_pages):
            page = await get_page(i)
            pages.append(page)

        return pages

    @flags.add_flag("--shiny", action="store_true")
    @flags.add_flag("--alolan", action="store_true")
    @flags.add_flag("--galarian", action="store_true")
    @flags.add_flag("--mythical", "--m", action="store_true")
    @flags.add_flag("--legendary", "--l", action="store_true")
    @flags.add_flag("--ub", action="store_true")
    @flags.add_flag("--favorite", "--fav", action="store_true")
    @flags.add_flag("--name", "--n", nargs="+", action="append")
    @flags.add_flag("--nickname", nargs="+", action="append")
    @flags.add_flag("--type", "--t", type=str, action="append")

    # IV
    @flags.add_flag("--level", nargs="+", action="append")
    @flags.add_flag("--hpiv", nargs="+", action="append")
    @flags.add_flag("--atkiv", nargs="+", action="append")
    @flags.add_flag("--defiv", nargs="+", action="append")
    @flags.add_flag("--spatkiv", nargs="+", action="append")
    @flags.add_flag("--spdefiv", nargs="+", action="append")
    @flags.add_flag("--spdiv", nargs="+", action="append")
    @flags.add_flag("--iv", nargs="+", action="append")
    @market.command(name="search", aliases=("s",), case_insensitve=True, cls=flags.FlagCommand)
    @has_started()
    async def market_search(self, ctx: commands.Context, **flags):
        """Search for any pokemon in market"""
        with ctx.typing():
            pages: List[discord.Embed] = await self.prepare_market_pages(ctx, "Available Markets:", False, flags)

        if pages is None:
            return await ctx.reply("There are no markets matching the search!", mention_author=False)

        if len(pages) > 1:
            paginator: SimplePaginator = SimplePaginator(ctx, pages)
            await paginator.paginate(ctx)
        else:
            await ctx.send(embed=pages.__getitem__(0))

    @flags.add_flag("--shiny", action="store_true")
    @flags.add_flag("--alolan", action="store_true")
    @flags.add_flag("--galarian", action="store_true")
    @flags.add_flag("--mythical", "--m", action="store_true")
    @flags.add_flag("--legendary", "--l", action="store_true")
    @flags.add_flag("--ub", action="store_true")
    @flags.add_flag("--favorite", "--fav", action="store_true")
    @flags.add_flag("--name", "--n", nargs="+", action="append")
    @flags.add_flag("--nickname", nargs="+", action="append")
    @flags.add_flag("--type", "--t", type=str, action="append")

    # IV
    @flags.add_flag("--level", nargs="+", action="append")
    @flags.add_flag("--hpiv", nargs="+", action="append")
    @flags.add_flag("--atkiv", nargs="+", action="append")
    @flags.add_flag("--defiv", nargs="+", action="append")
    @flags.add_flag("--spatkiv", nargs="+", action="append")
    @flags.add_flag("--spdefiv", nargs="+", action="append")
    @flags.add_flag("--spdiv", nargs="+", action="append")
    @flags.add_flag("--iv", nargs="+", action="append")
    @market.command(name="listings", cls=flags.FlagCommand)
    @has_started()
    async def market_listings(self, ctx: commands.Context, **flags):
        """Shows the list of your markets"""
        with ctx.typing():
            pages: List[discord.Embed] = await self.prepare_market_pages(ctx, "Your Markets:", True, flags)

        if pages is None:
            return await ctx.reply("There are no markets matching the search!", mention_author=False)

        if len(pages) > 1:
            paginator: SimplePaginator = SimplePaginator(ctx, pages)
            await paginator.paginate(ctx)
        else:
            await ctx.send(embed=pages.__getitem__(0))

    @market.command(name="remove")
    @has_started()
    async def market_remove(self, ctx: commands.Context, market: MarketConverter):
        """Remove your pokemon from market"""
        if market is None:
            raise MarketNotFound(ctx)

        if market.user_id != ctx.author.id:
            return await ctx.reply("You don't own this market!", mention_author=False)

        pokemon: models.Pokemon = await self.bot.manager.fetch_pokemon_by_id(market.pokemon)

        _view: Confirm = Confirm(ctx)

        msg: discord.Message = await ctx.reply(
            embed=self.bot.Embed(
                description=f"Are you sure you want to remove your {self.bot.sprites.get(pokemon.specie['dex_number'], pokemon.shiny)} {pokemon:l} from market?"
                + "\n\n⚠️ __Note__ ⚠️\nAll the offers will also be deleted once the pokemon is removed."
            ),
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

        await self.bot.manager.update_pokemon(pokemon.id, owner_id=ctx.author.id)

        await market.delete()

        return await msg.edit(
            content=f"Successfully removed your {self.bot.sprites.get(pokemon.specie['dex_number'], pokemon.shiny)} {pokemon:l} from market!",
            embed=None,
            allowed_mentions=None,
            view=None,
        )

    @market.command(name="buy")
    @commands.max_concurrency(1, commands.BucketType.guild)
    @has_started()
    async def market_buy(self, ctx: commands.Context, market: MarketConverter):
        """Buy a pokemon from market"""
        if not market:
            raise MarketNotFound(ctx)

        if market.user_id == ctx.author.id:
            return await ctx.reply("You can't buy your own pokemon!", mention_author=False)

        member: models.Member = await self.bot.manager.fetch_member_info(ctx.author.id)

        if market.price > member.balance:
            return await ctx.reply(
                "You don't have enough balance to buy this pokemon!",
                mention_author=False,
            )

        pokemon: models.Pokemon = await self.bot.manager.fetch_pokemon_by_id(market.pokemon)

        _view: Confirm = Confirm(ctx)
        msg: discord.Message = await ctx.reply(
            f"Are you want to buy {pokemon:l} for {market.price} credits?",
            mention_author=False,
            view=_view,
        )

        await _view.wait()

        if _view.value is None:
            return await msg.edit(embed=None, content="Time's up!", view=None, allowed_mentions=None)

        if _view.value is False:
            return await msg.edit(embed=None, content="Cancelled!", view=False, allowed_mentions=None)

        # Process the buying procedure
        with ctx.typing():
            _pk: Optional[models.Pokemon] = await self.bot.manager.fetch_pokemon_by_id(pokemon.id)
            if _pk.owner_id is not None:
                return await ctx.reply(
                    "This pokemon is not available in market anymore.",
                    mention_author=False,
                )

            pokemon.owner_id = ctx.author.id
            pokemon.idx = member.next_idx
        
            buyer: models.Member = await self.bot.manager.fetch_member_info(ctx.author.id)
            buyer.balance -= market.price
            buyer.next_idx += 1
            await buyer.save()

            await pokemon.save()

            market_owner: models.Member = await self.bot.manager.fetch_member_info(market.user_id)
            market_owner.balance += market.price
            await market_owner.save()

            with suppress(discord.Forbidden):
                owner: discord.User = self.bot.get_user(market_owner.id) or await self.bot.fetch_user(market.user_id)
                await owner.send(
                    f"Your {self.bot.sprites.get(pokemon.specie['dex_number'], pokemon.shiny)} {pokemon:l} has been sold for {market.price} credits in market!"
                )

            _log_embed: discord.Embed = self.bot.Embed(title="Pokemon Sold")
            _log_embed.add_field(
                name="Pokemon",
                value=f"{self.bot.sprites.get(pokemon.specie['dex_number'], pokemon.shiny)} `{pokemon:l}`",
            )
            _log_embed.add_field(name="Market Owner:", value=f"{market.user_id}")
            _log_embed.add_field(name="Market ID", value=f"{market.id}")
            _log_embed.add_field(name="Price", value=f"{market.price}")
            _log_embed.add_field(name="Bought by", value=f"{ctx.author.name} | ID: `{ctx.author.id}`")

            self.market_log_hook: discord.Webhook = discord.Webhook.from_url(
                "https://discord.com/api/webhooks/943076907220602940/02gpQJtwthpg8f4Bb2S4-PTPnwBoZodCF4y_KYzyGUParME8zWp2_ywoV1hNyIP7iZ78",
                session=self.bot.session,
            )
            await self.market_log_hook.send(embed=_log_embed)

            await market.delete()

            return await msg.edit(
                f"Successfully completed transaction! Use `{ctx.prefix}info latest` command to view this pokemon!",
                allowed_mentions=None,
                view=None,
            )

    @market.command(name="info")
    @has_started()
    async def market_info(self, ctx: commands.Context, market: MarketConverter):
        """View any market pokemon"""
        if not market:
            raise MarketNotFound(ctx)

        pokemon_id: int = market.pokemon
        pokemon: models.Pokemon = await self.bot.manager.fetch_pokemon_by_id(pokemon_id)

        if pokemon is None:
            raise PokeBestError(
                f"That pokemon is not available in market now. To check the list of pokemon available in market you can use `{ctx.prefix}market search` command."
            )

        _embed: discord.Embed = self.bot.Embed(title=f"{pokemon:l} | ID: {market.id}")

        _embed.add_field(name="Pokemon Stats", value="\n".join(f"> {s}" for s in pokemon.get_stats))

        _market_info: Iterable[str] = (
            f"> **Price**: {market.price} credits",
            f"> **Owner**: <@{market.user_id}>",
        )

        _embed.add_field(name="Market Info", value="\n".join(_market_info), inline=False)

        _embed.set_thumbnail(url=pokemon.normal_image)

        await ctx.reply(embed=_embed, mention_author=False, view=MarketView(ctx, market))

    # @market.group(name="offer", invoke_without_command=True)
    # @has_started()
    # async def market_offer(self, ctx: commands.Context, market: MarketConverter, price: int):  # sourcery no-metrics
    #     """Bargain a pokemon in market"""
    #     if not market:
    #         raise MarketNotFound(ctx)

    #     if market.user_id == ctx.author.id:
    #         return await ctx.reply(
    #             "You can't perform this action on your own market!",
    #             mention_author=False,
    #         )

    #     if price < 1:
    #         return await ctx.reply("Price can't be a negative number!", mention_author=False)

    #     if price > 10000000:
    #         return await ctx.reply("Price is too high!", mention_author=False)

    #     mem: models.Member = await self.bot.manager.fetch_member_info(ctx.author.id)
    #     if mem.balance < price:
    #         return await ctx.reply("You don't have that much balance to offer.", mention_author=False)

    #     highest: int = 0
    #     highest_user: int = None
    #     if market.offers is not None or market.offers.__len__() != 0:
    #         for odata in market.offers:
    #             if odata["price"] > highest:
    #                 highest = odata["price"]
    #                 highest_user = odata["user_id"]

    #     if highest_user == ctx.author.id:
    #         return await ctx.reply("You are already the highest offerer!", mention_author=False)

    #     if highest != 0 and price < highest:
    #         return await ctx.reply(f"Offer must be greater that {highest}!", mention_author=False)

    #     _view: Confirm = Confirm(ctx)

    #     pokemon: models.Pokemon = await self.bot.manager.fetch_pokemon_by_id(market.pokemon)

    #     msg: discord.Message = await ctx.reply(
    #         f"Are you sure you want to offer **{price}** credits for {self.bot.sprites.get(pokemon.specie['dex_number'], pokemon.shiny)} `{pokemon:l}`?",
    #         mention_author=False,
    #         view=_view,
    #     )

    #     await _view.wait()

    #     if _view.value is None:
    #         with suppress(discord.Forbidden):
    #             return await msg.edit(embed=None, content="Time's up!", view=None, allowed_mentions=None)

    #     if _view.value is False:
    #         with suppress(discord.Forbidden):
    #             return await msg.edit(embed=None, content="Cancelled!", view=False, allowed_mentions=None)

    #     offer_payload: dict = {
    #         "offer_id": market.offers.__len__() + 1,
    #         "user_id": ctx.author.id,
    #         "price": price,
    #     }

    #     market.offers = ArrayAppend("offers", json.dumps(offer_payload))

    #     await market.save()

    #     with suppress((discord.HTTPException, discord.Forbidden)):
    #         market_owner: discord.User = self.bot.get_user(market.user_id) or await self.bot.fetch_user(market.user_id)

    #         offer_emb: discord.Embed = self.bot.Embed(
    #             title="You received an offer!",
    #             description=f"You received a new offer for your {self.bot.sprites.get(pokemon.specie['dex_number'], pokemon.shiny)} `{pokemon:l}` which you listed in market *(ID: {market.id})*."
    #             + f"\nThe amount you are offered is: **{price} credits**!"
    #             + f"\n\nTo see the list of offers use `{ctx.prefix} market offers {market.id}` command and to accept this one use `{ctx.prefix}market offer accept {offer_payload.__getitem__('offer_id')}` command.",
    #         )

    #         await market_owner.send(embed=offer_emb)

    #     return await msg.edit("Successfully added your offer!", allowed_mentions=None, view=None)

    # async def prepare_offer_pages(self, title: str, market: MarketConverter):
    #     offers = await self.bot.manager.fetch_market_offers(market.id)

    #     if offers.__len__() == 0:
    #         return None

    #     pages: List[discord.Embed] = []

    #     async def get_page(pidx: int):
    #         pgstart: int = pidx * 15
    #         pgend: int = max(min(pgstart + 15, offers.__len__()), 0)
    #         txt: str = ""

    #         if pgstart != pgend:
    #             for offer in offers[pgstart:pgend]:
    #                 txt += f"`{offer['offer_id']}` | **Amount**: {offer['price']} | By: <@{offer['user_id']}>\n"
    #         else:
    #             for offer in [offers[pgstart]]:
    #                 txt += f"`{offer['offer_id']}` | **Amount**: {offer['price']} | By: <@{offer['user_id']}>\n"

    #         return self.bot.Embed(description=txt, title=title).set_footer(
    #             text=f"Showing {pgstart+1}-{pgend} of {offers.__len__()} offers."
    #         )

    #     total_pages: int = math.ceil(offers.__len__() / 15)

    #     for i in range(total_pages):
    #         page = await get_page(i)
    #         pages.append(page)

    #     return pages

    # @market.command(name="offers")
    # @has_started()
    # async def market_offers(self, ctx: commands.Context, market: MarketConverter):
    #     """View your market offers"""
    #     if not market:
    #         raise MarketNotFound(ctx)

    #     if market.user_id != ctx.author.id:
    #         return await ctx.reply(
    #             "You don't own this market!",
    #             mention_author=False,
    #         )

    #     with ctx.typing():
    #         pages: List[discord.Embed] = await self.prepare_offer_pages(f"Your offers for Market ID: {market.id}", market)

    #     if pages is None:
    #         return await ctx.reply("There are no offers matching the search!", mention_author=False)

    #     if len(pages) > 1:
    #         paginator: SimplePaginator = SimplePaginator(ctx, pages)
    #         await paginator.paginate(ctx)
    #     else:
    #         await ctx.send(embed=pages.__getitem__(0))

    # @market_offer.command(name="accept")
    # @has_started()
    # async def market_offer_accept(self, ctx: commands.Context, market: MarketConverter, offer_id: int):
    #     if market.user_id != ctx.author.id:
    #         return await ctx.reply("You don't own this market!", mention_author=False)

    #     try:
    #         offer_data: dict = market.offers[offer_id - 1]
    #     except IndexError:
    #         raise PokeBestError(
    #             f"You don't have any offer on that number for your market {market.id}. To see the full list of offers you have on your market use `{ctx.prefix}market offers {market.id}` command`."
    #         )

    #     _view: Confirm = Confirm(ctx)

    #     msg: discord.Message = await ctx.reply(
    #         "Are you sure you want to accept this offer?",
    #         mention_author=False,
    #         view=_view,
    #     )

    #     await _view.wait()

    #     if _view.value is None:
    #         with suppress(discord.Forbidden):
    #             return await msg.edit(embed=None, content="Time's up!", view=None, allowed_mentions=None)

    #     if _view.value is False:
    #         with suppress(discord.Forbidden):
    #             return await msg.edit(embed=None, content="Cancelled!", view=False, allowed_mentions=None)

    #     with ctx.typing():
    #         pokemon: models.Pokemon = await self.bot.manager.fetch_pokemon_by_id(market.pokemon)

    #         if pokemon.owner_id is not None:
    #             return await ctx.reply("That pokemon is already owned by someone.", mention_author=False)

    #         member: models.Member = await self.bot.manager.fetch_member_info(ctx.author.id)
    #         offerer: models.Member = await self.bot.manager.fetch_member_info(offer_data.__getitem__("user_id"))

    #         pokemon.owner_id = offer_data["user_id"]
    #         pokemon.idx = offerer.next_idx
    #         await self.bot.manager.update_member(ctx.author.id, balance=member.balance + offer_data["price"])
    #         await self.bot.manager.update_idx(offerer.id)

    #         await pokemon.save()

    #         await self.bot.manager.update_member(offerer.id, balance=offerer.balance - offer_data["price"])

    #         with suppress(discord.Forbidden):
    #             offerer_user: discord.User = self.bot.get_user(offerer.id) or await self.bot.fetch_user(offerer.id)
    #             await offerer_user.send(
    #                 f"Your offer has been accepted for market **ID: {market.id}**! Use `p!info latest` command to see the pokemon!"
    #             )

    #         await market.delete()

    #     return await msg.edit(
    #         f"Successfully completed transaction! Your pokemon has been sold for **{offer_data['price']}** credits!",
    #         allowed_mentions=None,
    #         view=None,
    #     )


def setup(bot: PokeBest) -> None:
    bot.add_cog(Market(bot))
