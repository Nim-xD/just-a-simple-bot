from __future__ import annotations

from operator import mod
from discord import member
from discord.ext import commands
import discord
import models
import asyncpg
from typing import Optional, Union, List, TYPE_CHECKING
import pickle

if TYPE_CHECKING:
    from core.bot import PokeBest


class Database(commands.Cog):
    def __init__(self, bot: PokeBest) -> None:
        self.bot: PokeBest = bot

    async def fetch_member_info(self, member_id: int) -> Union[None, models.Member]:
        # val: Optional[models.Member] = await self.bot.redis.hget("db:member", member_id)
        # if val is None:
        #     val = await models.Member.get_or_none(id=member_id)
        #     if val is not None:
        #         await self.bot.redis.hset("db:member", member_id, pickle.dumps(val))
        # return pickle.loads(val)
        return await models.Member.get_or_none(id=member_id)

    async def fetch_pokemon_list(self, member_id: int) -> List[models.Pokemon]:
        return await models.Pokemon.filter(owner_id=member_id)

    async def fetch_pokemon_by_number(self, member_id: int, number: int) -> Union[models.Pokemon, None]:
        return await models.Pokemon.get_or_none(owner_id=member_id, idx=number)

    async def fetch_pokemon_count(self, member_id: int) -> int:
        return (await self.fetch_pokemon_list(member_id)).__len__()

    async def update_idx(self, member_id: int) -> None:
        m = await self.fetch_member_info(member_id)
        _next_idx: int = m.next_idx

        await models.Member.filter(id=member_id).update(next_idx=_next_idx + 1)

    async def get_next_idx(self, member_id: int) -> int:
        return (await self.fetch_member_info(member_id)).next_idx

    async def update_pokemon(self, pokemon_id: int, **kwargs) -> None:
        await models.Pokemon.filter(id=pokemon_id).update(**kwargs)

    async def update_member(self, member_id: int, **kwargs) -> None:
        await models.Member.filter(id=member_id).update(**kwargs)

        m = await self.fetch_member_info(member_id)

    async def increase_credits(self, member_id: int, amt: int) -> None:
        mem: models.Member = await self.fetch_member_info(member_id)
        mem.balance += amt
        await mem.save()

    async def increase_shards(self, member_id: int, amt: int) -> None:
        mem: models.Member = await self.fetch_member_info(member_id)
        mem.shards += amt
        await mem.save()

    async def fetch_pokemon(self, member_id: int, pokemon_id: int) -> models.Pokemon:
        return await models.Pokemon.get_or_none(owner_id=member_id, idx=pokemon_id)

    async def fetch_selected_pokemon(self, member_id: int) -> models.Pokemon:
        _member: models.Member = await self.fetch_member_info(member_id)

        if _member is None or _member.selected_id is None:
            return

        _selected_id: int = _member.selected_id
        return await models.Pokemon.get_or_none(owner_id=member_id, idx=_selected_id)

    async def fetch_guild(self, guild_id: int) -> models.Guild:
        return await models.Guild.get_or_create(id=guild_id)

    async def update_guild(self, guild_id: int, **kwargs) -> None:
        await models.Guild.filter(id=guild_id).update(**kwargs)

    async def fetch_all_auction_list(self) -> List[models.Auctions]:
        return await models.Auctions.all()

    async def fetch_pokemon_by_id(self, pokemon_id: int) -> models.Pokemon:
        return await models.Pokemon.get_or_none(id=pokemon_id)

    async def fetch_user_auctions(self, member_id: int) -> List[models.Auctions]:
        return await models.Auctions.filter(owner_id=member_id)

    async def update_auction(self, auction_id: int, **kwargs):
        await models.Auctions.filter(id=auction_id).update(**kwargs)

    async def fetch_bidded_auctions(self, bidder_id: int) -> List[models.Auctions]:
        return await models.Auctions.filter(bidder=bidder_id)

    async def fetch_all_market_list(self) -> List[models.Listings]:
        return await models.Listings.all()

    async def fetch_user_market(self, member_id: int) -> List[models.Listings]:
        return await models.Listings.filter(user_id=member_id)

    async def fetch_market_offers(self, market_id: int):
        market: models.Listings = await models.Listings.get_or_none(id=market_id)
        if market is None:
            return None
        else:
            return market.offers

    async def update_pokemon_moves(self, pokemon: models.Pokemon, moves: list):
        pokemon.moves = [m["id"] for m in moves]
        await pokemon.save()

    async def update_guild(self, guild_id: int, **kwargs) -> None:
        _guild: Optional[models.Guild] = await models.Guild.get_or_none(id=guild_id)
        if _guild is None:
            await models.Guild.create(id=guild_id, **kwargs)
            return

        await models.Guild.filter(id=guild_id).update(**kwargs)


def setup(bot) -> None:
    bot.add_cog(Database(bot))
