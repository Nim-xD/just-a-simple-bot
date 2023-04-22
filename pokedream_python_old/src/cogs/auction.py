from datetime import date, datetime, timedelta
from operator import mod
from re import match
from typing import Iterable, List, Optional, Union
from utils.exceptions import AuctionNotFound, PokeBestError

import models
from utils.converters import PokemonConverter, AuctionConverter
import discord
from discord.ext import commands, tasks, menus
import pytz
import math
import pickle
from contextlib import suppress

from core.bot import PokeBest
from core.views import AuctionView, Confirm
from core.paginator import SimplePaginator, AdvancedPaginator
from utils.checks import has_started
from utils.time import FutureTime, UserFriendlyTime, human_timedelta
from tortoise.exceptions import ConfigurationError
from utils.methods import format_dt
from aioredis_lock import RedisLock, LockTimeoutError

UTC = pytz.UTC


class Auction(commands.Cog):
    """Auctions for pokemon"""

    def __init__(self, bot: PokeBest) -> None:
        self.bot: PokeBest = bot

        self.check_ongoing_auctions.start()

    @commands.group(name="auction", invoke_without_subcommand=True)
    async def auction(self, ctx: commands.Context):
        """All the commands related to auctions"""
        if ctx.invoked_subcommand is None:
            return await ctx.send_help(ctx.command)

    @auction.command(name="list")
    @has_started()
    async def auction_list(
        self,
        ctx: commands.Context,
        pokemon: PokemonConverter(accept_blank=False),
        auction_time: UserFriendlyTime(default="\u2026"),
        buyout: Optional[int] = None,
    ):
        """List your pokemon in auctions"""
        if pokemon is None:
            raise PokeBestError(
                f"Looks like you entered a wrong pokemon. To view the list of your pokemon use `{ctx.prefix}pokemon` command and enter a valid index."
            )

        if buyout is not None and buyout > 1000000:
            return await ctx.reply("Buyout is too high!", mention_author=False)

        if buyout is not None and buyout < 1:
            return await ctx.reply("Buyout cannot be negative!", mention_author=False)

        auction_time.dt += timedelta(seconds=10)  # Estimated average difference

        now = UTC.localize(datetime.utcnow())

        #############################################################
        # if (
        #     auction_time.dt - timedelta(weeks=1) > now
        #     or auction_time.dt - timedelta(minutes=5) < now
        # ):
        #     return await ctx.reply(
        #         "Time must be less than 1 week and more than 5 minutes!",
        #         mention_author=False,
        #     )
        #############################################################

        _view: Confirm = Confirm(ctx)

        msg: discord.Message = await ctx.reply(
            embed=self.bot.Embed(
                description=f"Are you sure you want to auction your `{pokemon:ln}`?\n**Ends:** {format_dt(auction_time.dt)}\n**Buyout:** {buyout} credit(s)\n\n⚠️ **Note:** You can't remove your pokemon from auction if someone bids on it!"
            ),
            view=_view,
            mention_author=False,
        )

        await _view.wait()

        if _view.value is None:
            return await msg.edit(content="Time's up!", view=None, embed=None, allowed_mentions=None)

        if _view.value is False:
            return await msg.edit(content="Cancelled!", view=None, embed=None, allowed_mentions=None)

        auction_res: models.Auctions = models.Auctions(
            owner_id=ctx.author.id,
            pokemon=pokemon.id,
            buyout=buyout,
            bidder=None,
            current_bid=None,
            expires=auction_time.dt,
        )

        _pk: Optional[models.Pokemon] = await self.bot.manager.fetch_pokemon_by_number(ctx.author.id, pokemon.idx)

        if _pk is None or _pk.owner_id is None:
            return await ctx.reply(
                "Looks like that pokemon has been already listed on auction or somewhere else.",
                mention_author=False,
            )

        await self.bot.manager.update_pokemon(pokemon.id, owner_id=None)

        await auction_res.save()

        with suppress(discord.Forbidden):
            await msg.delete()

        try:
            return await ctx.author.send(
                f"You are now auctioning your {self.bot.sprites.get(pokemon.specie['dex_number'], pokemon.shiny)} `{pokemon:l}` on auction **ID: {auction_res.id}**!"
            )

        # In case user's dms are closed for bot
        except discord.Forbidden:
            return await ctx.reply(
                f"You are now auctioning your {self.bot.sprites.get(pokemon.specie['dex_number'], pokemon.shiny)} `{pokemon:l}` on auction **ID: {auction_res.id}**!",
                mention_author=False,
            )

    async def prepare_auction_pages(
        self,
        ctx: commands.Context,
        title: str,
        specific_auctions: bool = False,
        bidded_auctions: bool = False,
    ) -> List[discord.Embed]:
        if not specific_auctions and not bidded_auctions:
            _auction_model_list: List[models.Auctions] = await self.bot.manager.fetch_all_auction_list()

        elif bidded_auctions is False and specific_auctions is True:
            _auction_model_list: List[models.Auctions] = await self.bot.manager.fetch_user_auctions(ctx.author.id)

        elif bidded_auctions is True:
            _auction_model_list: List[models.Auctions] = await self.bot.manager.fetch_bidded_auctions(ctx.author.id)

        if _auction_model_list.__len__() == 0:
            return None

        _auction_model_list.sort(key=lambda k: k.id)

        pages: List[discord.Embed] = []

        async def get_page(pidx: int):
            pgstart: int = pidx * 15
            pgend: int = max(min(pgstart + 15, _auction_model_list.__len__()), 0)
            txt: str = ""

            if pgstart != pgend:
                for auction in _auction_model_list[pgstart:pgend]:
                    pk = await self.bot.manager.fetch_pokemon_by_id(auction.pokemon)
                    txt += f"`{auction.id}` | {self.bot.sprites.get(pk.specie['dex_number'], pk.shiny)} **{pk:l}** | IV: {pk.iv_total/186:.2%} | Buyout: {auction.buyout} | Bid: {auction.current_bid}\n"
            else:
                for auction in [_auction_model_list[pgstart]]:
                    pk = await self.bot.manager.fetch_pokemon_by_id(auction.pokemon)
                    txt += f"`{auction.id}` | {self.bot.sprites.get(pk.specie['dex_number'], pk.shiny)} **{pk:l}** | IV: {pk.iv_total/186:.2%} | Buyout: {auction.buyout} | Bid: {auction.current_bid}\n"

            return self.bot.Embed(description=txt, title=title).set_footer(
                text=f"Showing {pgstart+1}-{pgend} of {_auction_model_list.__len__()} auctions."
            )

        total_pages: int = math.ceil(_auction_model_list.__len__() / 15)

        for i in range(total_pages):
            page = await get_page(i)
            pages.append(page)

        return pages

    @auction.command(name="search")
    @has_started()
    async def auction_search(self, ctx: commands.Context, *, args: str = ""):
        """Search any pokemon in auction"""

        with ctx.typing():
            pages: List[discord.Embed] = await self.prepare_auction_pages(ctx, "Available Auctions:", False)

        if pages is None:
            return await ctx.reply("There are no auctions matching the search!", mention_author=False)

        if len(pages) > 1:
            paginator: SimplePaginator = SimplePaginator(ctx, pages)
            await paginator.paginate(ctx)
        else:
            await ctx.send(embed=pages.__getitem__(0))

    @auction.command(name="listings")
    @has_started()
    async def auction_listings(self, ctx: commands.Context, *, args: str = ""):
        """Show the list of your auctions"""
        with ctx.typing():
            pages = await self.prepare_auction_pages(ctx, "Your Auctions:", True)

        if pages is None:
            return await ctx.reply("There are no auctions matching the search!", mention_author=False)

        if len(pages) > 1:
            paginator: SimplePaginator = SimplePaginator(ctx, pages)
            await paginator.paginate(ctx)
        else:
            await ctx.send(embed=pages[0])

    @auction.command(name="view")
    @has_started()
    async def auction_view(self, ctx: commands.Context, auction: AuctionConverter):
        """View an auction pokemon"""
        if auction is None:
            raise AuctionNotFound(ctx)

        pokemon_id: int = auction.pokemon
        pokemon: models.Pokemon = await models.Pokemon.get_or_none(id=pokemon_id)

        if pokemon is None:
            raise PokeBestError(
                f"That pokemon is not available in auctions now. To check the list of pokemon available in auctions you can use `{ctx.prefix}auction search` command."
            )

        # NIM ISKO THEEK KRKE DESIGN KR DENA
        _embed: discord.Embed = self.bot.Embed(
            title=f"{pokemon:l} | Auction ID: {auction.id}", color=pokemon.normal_color
        )

        _embed.add_field(
            name="Pokemon Stats:",
            value="\n".join(f"> {s}" for s in pokemon.get_stats),
            inline=False,
        )

        _auction_stats: Iterable[str] = (
            f"> **Auction Owner**: <@{auction.owner_id}>",
            f"> **Current Bid**: {auction.current_bid}",
            f"> **Current Bidder**: {'<@{0}>'.format(auction.bidder) if auction.bidder is not None else 'No bidder yet.'}",
            f"> **Time Remaining**: {format_dt(auction.expires)}"
            # f"> **Time Remaining**: {human_timedelta(auction.expires)}",
        )

        _embed.add_field(name="Auction Stats:", value="\n".join(_auction_stats), inline=False)

        _embed.set_thumbnail(url=pokemon.normal_image)

        await ctx.reply(embed=_embed, mention_author=False, view=AuctionView(ctx, auction))

    @auction.command(name="bid")
    @has_started()
    async def auction_bid(self, ctx: commands.Context, auction: AuctionConverter, bid: int):
        """Bid on auction"""
        if auction is None:
            raise AuctionNotFound(ctx)

        if bid < 1:
            return await ctx.reply("Bid amount cannot be negative!", mention_author=False)

        if auction.owner_id == ctx.author.id:
            return await ctx.reply("You can't bid on your owned auction!", mention_author=False)

        if auction.expires < datetime.now(tz=UTC):
            return await ctx.reply("You can't bid on this auction!", mention_author=False)

        if auction.bidder is not None and auction.bidder == ctx.author.id:
            return await ctx.reply(
                "You are already the highest bidder on this auction!",
                mention_author=False,
            )

        amount: int = 1 if auction.current_bid is None else auction.current_bid + 100
        if amount > bid:
            return await ctx.reply(f"Bid must be atleast of `{amount}` credits!", mention_author=False)

        member: models.Member = await self.bot.manager.fetch_member_info(ctx.author.id)

        if member.__getattribute__("balance") < bid:
            return await ctx.reply(
                "You don't have enough balance to bid on that auction!",
                mention_author=False,
            )

        _view: Confirm = Confirm(ctx)

        msg: discord.Message = await ctx.reply(
            "Are you sure you want to bid on this auction?",
            mention_author=False,
            view=_view,
        )

        await _view.wait()

        if _view.value is None:
            self.bot.cache._auction_bid_users.remove(ctx.author.id)
            return await msg.edit("Time's up!", view=None, allowed_mentions=None)

        elif _view.value is False:
            self.bot.cache._auction_bid_users.remove(ctx.author.id)
            return await msg.edit("Cancelled!", view=None, allowed_mentions=None)

        try:
            async with RedisLock(self.bot.redis, f"auction_bid:{auction.id}", 60, 1):
                member.balance -= bid
                await member.save()

                if (bidder := auction.bidder) is not None:
                    _bidder: models.Member = await self.bot.manager.fetch_member_info(bidder)
                    _bidder.balance += auction.current_bid

                    with suppress(discord.Forbidden, discord.NotFound):
                        bidder_user: Union[discord.Member, discord.User] = self.bot.get_user(
                            bidder
                        ) or await self.bot.fetch_user(bidder)
                        await bidder_user.send(f"You have been outbidded on the auction **ID: {auction.id}**!")

                    await _bidder.save()

                if (buyout := auction.buyout) is not None and buyout <= bid:
                    pokemon_id: int = auction.pokemon

                    _auc: models.Auctions = auction
                    await auction.delete()

                    await self.bot.manager.update_pokemon(pokemon_id, owner_id=ctx.author.id, idx=member.next_idx)
                    await self.bot.manager.update_idx(ctx.author.id)

                    _auction_owner: models.Member = await self.bot.manager.fetch_member_info(_auc.owner_id)
                    _auction_owner.balance += bid
                    await _auction_owner.save()

                    with suppress(discord.Forbidden):
                        await ctx.author.send(
                            f"You paid the buyout amount for Auction ID: {auction.id}. Do `{ctx.prefix}info latest` to check that pokemon!"
                        )

                    auction_owner: discord.User = self.bot.get_user(_auc.owner_id) or await self.bot.fetch_user(
                        _auc.owner_id
                    )

                    with suppress(discord.Forbidden):
                        await auction_owner.send(
                            f"Your pokemon in the auction with **ID: {auction.id}** has been sold for {bid} credits!"
                        )

                    self.bot.dispatch("auction_sold", ctx.author.id, _auc, bid)

                    self.bot.cache._auction_bid_users.remove(ctx.author.id)
                    return

                auction.bidder = ctx.author.id
                auction.current_bid = bid
                await auction.save()

                await msg.edit(
                    f"You successfully placed bid on Auction **ID: {auction.id}**!",
                    view=None,
                    allowed_mentions=None,
                )
        except LockTimeoutError:
            return await ctx.reply(
                "Someone is already bidding on this auction. Please try again later.", mention_author=False
            )

    @auction.command(name="remove")
    @has_started()
    async def auction_remove(self, ctx: commands.Context, auction: AuctionConverter):
        """Remove your pokemon from auctions"""
        if auction.owner_id != ctx.author.id:
            return await ctx.reply("This auction doesn't belong to you!", mention_author=False)

        if auction.current_bid is not None and auction.bidder is not None:
            return await ctx.reply(
                "Sorry, but you can't remove this pokemon from auction as someone already placed bid on it!",
                mention_author=False,
            )

        pokemon_id: int = auction.pokemon
        await auction.delete()

        await self.bot.manager.update_pokemon(pokemon_id, owner_id=ctx.author.id)

        return await ctx.reply(f"Successfully removed your pokemon from auction!", mention_author=False)

    @auction.command(name="bids")
    async def auction_bids(self, ctx: commands.Context):
        """Get the list of your bidded auctions"""
        with ctx.typing():
            pages = await self.prepare_auction_pages(ctx, "Your Bids:", bidded_auctions=True)

        if pages is None:
            return await ctx.reply("There are no auctions matching the search!", mention_author=False)

        if len(pages) > 1:
            paginator: SimplePaginator = SimplePaginator(ctx, pages)
            await paginator.paginate(ctx)
        else:
            await ctx.send(embed=pages[0])

    @commands.Cog.listener()
    async def on_auction_timer_complete(self, auction: models.Auctions):
        if auction.bidder is None:
            pokemon: models.Pokemon = await self.bot.manager.fetch_pokemon_by_id(auction.pokemon)
            pokemon.owner_id = auction.owner_id

            owner: discord.User = self.bot.get_user(auction.owner_id) or await self.bot.fetch_user(auction.owner_id)
            await pokemon.save()

            await auction.delete()
            with suppress(discord.Forbidden, discord.HTTPException):
                return await owner.send(
                    f"The Auction with **ID: {auction.id}** for your {self.bot.sprites.get(pokemon.specie['dex_number'], pokemon.shiny)} {pokemon:l} ended with *no bids*, so it returned back to you."
                )

        else:
            auc_owner: models.Member = await self.bot.manager.fetch_member_info(auction.owner_id)
            auc_bidder: models.Member = await self.bot.manager.fetch_member_info(auction.bidder)

            auc_owner.balance = auction.current_bid
            await auc_owner.save()

            await self.bot.manager.update_pokemon(auction.pokemon, owner_id=auction.bidder, idx=auc_bidder.next_idx)
            await self.bot.manager.update_idx(auction.bidder)

            bidder: discord.User = self.bot.get_user(auction.bidder) or await self.bot.fetch_user(auction.bidder)
            owner: discord.User = self.bot.get_user(auction.owner_id) or await self.bot.fetch_user(auction.owner_id)

            pk: models.Pokemon = await self.bot.manager.fetch_pokemon_by_id(auction.pokemon)

            self.bot.dispatch("auction_sold", bidder.id, auction, auction.current_bid)

            with suppress(discord.Forbidden, discord.HTTPException):
                await bidder.send(
                    embed=self.bot.Embed(
                        title=f"🎉 You won the auction with **ID: {auction.id}**!",
                        description=f"You received {self.bot.sprites.get(pk.specie['dex_number'], pk.shiny)} `{pk:l}`. Do `p!info latest` to view it!",
                    )
                )

            with suppress(discord.Forbidden, discord.HTTPException):
                await bidder.send(
                    embed=self.bot.Embed(
                        title="Auction Ended!",
                        description=f"Your auction with **ID: {auction.id}** ended with highest bid of `{auction.current_bid}` credits!",
                    )
                )

            await auction.delete()

    @commands.Cog.listener()
    async def on_auction_sold(self, bidder_id: int, auction: models.Auctions, sold_price: int):
        self.auction_log_hook: discord.Webhook = discord.Webhook.from_url(
            "https://discord.com/api/webhooks/943076814706851931/koI5qylxt-6Zk2KRftq8bv5XQ-uR1uWtQsUCZSudp5C3OiF1ENcFTOlEqsuutvtEkl8f",
            session=self.bot.session,
        )

        emb: discord.Embed = discord.Embed(title="Auction Ended")
        emb.add_field(name="Auction ID", value=auction.id)
        emb.add_field(name="Bidder", value=bidder_id)
        emb.add_field(name="Auction Owner", value=auction.owner_id)
        emb.add_field(name="Sold Price", value=sold_price)

        await self.auction_log_hook.send(embed=emb)

    @tasks.loop(seconds=10)
    async def check_ongoing_auctions(self):
        try:
            auctions: List[models.Auctions] = await models.Auctions.all()
        except ConfigurationError:
            return

        expired_auctions: List[models.Auctions] = []
        for auction in auctions:
            if auction.expires <= datetime.now(tz=UTC):
                expired_auctions.append(auction)

        for eauc in expired_auctions:
            self.bot.dispatch("auction_timer_complete", eauc)


def setup(bot: PokeBest) -> None:
    bot.add_cog(Auction(bot))
