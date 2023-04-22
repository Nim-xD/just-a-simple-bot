from __future__ import annotations
from datetime import datetime, timedelta
import enum

from discord.ext import commands, tasks
import discord

import typing
from utils.constants import UTC

import models
from models.helpers import ArrayAppend, ArrayRemove, ArrayReplace
from utils.constants import TYPES

if typing.TYPE_CHECKING:
    from core.bot import PokeBest

from utils.emojis import emojis
from tortoise.exceptions import ConfigurationError
from utils.time import human_timedelta
from utils.checks import has_started
from contextlib import suppress
import random
from data import data
import json
import math
from core.paginator import SimplePaginator

QUESTS: typing.List[dict] = [
    {
        "quest_id": 1,
        "text": "Catch 5 {0}",
        "number": 5,
        "event": "on_catch",
        "reward": "💎 25 Shards",
        "shards": 25,
    },
    # {
    #     "quest_id": 2,
    #     "text": "Catch a Santa Pikachu",
    #     "event": "on_catch",
    #     "reward": "💰 25 Shards",
    #     "shards": 25,
    #     "number": 1,
    #     "species_id": 10393,
    # },
    {
        "quest_id": 2,
        "text": "Catch 20 Ice type pokémon",
        "type": "ice",
        "event": "on_catch",
        "reward": "💎 25 Shards",
        "shards": 25,
        "number": 20,
    },
    {
        "quest_id": 3,
        "text": "Catch 20 Water type pokémon",
        "type": "water",
        "event": "on_catch",
        "reward": "💎 25 Shards",
        "shards": 25,
        "number": 20,
    },
    {
        "quest_id": 4,
        "text": "Catch 20 Fire type pokémon",
        "type": "fire",
        "event": "on_catch",
        "reward": "💎 25 Shards",
        "shards": 25,
        "number": 20,
    },
    {
        "quest_id": 5,
        "text": "Catch 20 Grass type pokémon",
        "type": "grass",
        "event": "on_catch",
        "reward": "💎 25 Shards",
        "shards": 25,
        "number": 20,
    },
    {
        "quest_id": 6,
        "text": "Catch 20 Poison type pokémon",
        "type": "poison",
        "event": "on_catch",
        "reward": "💎 25 Shards",
        "shards": 25,
        "number": 20,
    },
    {
        "quest_id": 7,
        "text": "Catch 20 Flying type pokémon",
        "type": "flying",
        "event": "on_catch",
        "reward": "💎 25 Shards",
        "shards": 25,
        "number": 20,
    },
    {
        "quest_id": 8,
        "text": "Catch 20 Electric type pokémon",
        "type": "electric",
        "event": "on_catch",
        "reward": "💎 25 Shards",
        "shards": 25,
        "number": 20,
    },
    {
        "quest_id": 9,
        "text": "Catch 20 Dragon type pokémon",
        "type": "dragon",
        "event": "on_catch",
        "reward": "💎 25 Shards",
        "shards": 25,
        "number": 20,
    },
    # {
    #     "quest_id": 9,
    #     "text": "Catch 100 pokémon",
    #     "event": "on_catch",
    #     "reward": "💎 25 Shards",
    #     "shards": 25,
    #     "number": 100,
    # },
]


class Quests(commands.Cog):
    def __init__(self, bot: PokeBest) -> None:
        self.bot: PokeBest = bot

        self.reset_or_give_daily_quests.start()

    def make_progress_bar(self, _progress: int, _total_progress: int) -> str:
        progress = _progress / _total_progress
        func = math.ceil if progress < 0.5 else math.floor
        bars = min(func(progress * 10), 10)
        first, last = bars > 0, bars == 10
        mid = bars - (1 if last else 0) - (1 if first else 0)

        ret = emojis.quest_fill_front if first else emojis.quest_empty_front
        ret += mid * emojis.quest_fill
        ret += (8 - mid) * emojis.quest_empty
        ret += emojis.quest_fill_back if last else emojis.quest_empty_back

        return ret

    async def assign_daily_species(self, mem: models.Member):
        species_id: int = random.randint(1, 898)
        species: dict = data.species_by_num(species_id)

        if species.__getitem__("catchable") is False:
            await self.assign_daily_species(mem)

        __this_quest: typing.Optional[dict] = None

        for _quest in mem.daily_quests:
            if _quest["quest_id"] == 1:
                __this_quest = _quest
                break

        if __this_quest is None:
            mem.daily_quests = ArrayAppend(
                "daily_quests",
                json.dumps(
                    {
                        "quest_id": 1,
                        "quest_progress": 0,
                        "species_id": species_id,
                        "quest_done": False,
                    }
                ),
            )

        else:
            mem.daily_quests = ArrayRemove("daily_quests", json.dumps(__this_quest))
            mem.daily_quests = ArrayAppend(
                "daily_quests",
                json.dumps(
                    {
                        "quest_id": 1,
                        "quest_progress": 0,
                        "species_id": species_id,
                        "quest_done": False,
                    }
                ),
            )

        await mem.save()

    @commands.command(aliases=("q",))
    @has_started()
    async def quest(self, ctx: commands.Context):
        mem: models.Member = await self.bot.manager.fetch_member_info(ctx.author.id)
        emb: discord.Embed = self.bot.Embed(
            title="Daily Quest",
            description=f"Your daily quest will reset in **{human_timedelta(mem.daily_quests_timestamp) if mem.daily_quests_timestamp is not None else 'Not alloted yet! Please wait.'}**",
        )

        if mem.daily_quests.__len__() == 0:
            return await ctx.reply(
                "Your quest data is currently getting synced. Please wait...",
                mention_author=False,
            )

        pages: typing.List[discord.Embed] = []
        _count: int = 0

        for quest in mem.daily_quests:
            if not isinstance(quest, str):
                __quest_data = QUESTS[quest["quest_id"] - 1]
            elif isinstance(quest, str):
                __quest_data = QUESTS[json.loads(quest)["quest_id"] - 1]
                quest = json.loads(quest)

            _count += 1

            if quest.__getitem__("quest_id") == 1:
                specie: dict = data.species_by_num(quest["species_id"])
                emb.add_field(
                    name=f"Catch 5 {specie['names']['9']} [{quest['quest_progress']}/{__quest_data['number']}]",
                    value=f"{self.make_progress_bar(quest['quest_progress'], __quest_data['number'])}\n**Reward**: 💎 25 Shards",
                    inline=False,
                )

            else:
                emb.add_field(
                    name=__quest_data["text"] + f" [{quest['quest_progress']}/{__quest_data['number']}]",
                    value=f"{self.make_progress_bar(quest['quest_progress'], __quest_data['number'])}\n**Reward**: {__quest_data['reward']}",
                    inline=False,
                )

            if _count % 4 == 0:
                emb.add_field(
                    name="Special Research",
                    value=f"No Special Research is going on currently check `{ctx.prefix}event` for more info!"
                    if self.bot.bot_config.is_there_event
                    else f"There is a event going on! Check it out using `{ctx.prefix}event` command!",
                )
                pages.append(emb)
                emb: discord.Embed = self.bot.Embed(
                    title="Daily Quest",
                    description=f"Your daily quest will reset in **{human_timedelta(mem.daily_quests_timestamp) if mem.daily_quests_timestamp is not None else 'Not alloted yet! Please wait.'}**",
                )

        emb.add_field(
            name="Special Research",
            value=f"No Special Research is going on currently check `{ctx.prefix}event` for more info!"
            if self.bot.bot_config.is_there_event
            else f"There is a event going on! Check it out using `{ctx.prefix}event` command!",
        )
        pages.append(emb)

        paginator: SimplePaginator = SimplePaginator(ctx, pages)

        # await ctx.reply(embed=emb, mention_author=False)
        await paginator.paginate(ctx)

    async def update_quest_progress(self, mem: models.Member, _quest):
        _qidx: int = 0
        for idx, q in enumerate(mem.daily_quests):
            if type(_quest) == str:
                _quest = json.loads(_quest)

            if type(q) == str:
                q = json.loads(q)

            if q["quest_id"] == _quest["quest_id"]:
                _qidx = idx
                break

        # mem: models.Member = await self.bot.manager.fetch_member_info(mem.id)
        _quest["quest_progress"] = _quest["quest_progress"] + 1

        if _quest["quest_progress"] > QUESTS[_quest["quest_id"] - 1]["number"]:
            _quest["quest_progress"] = QUESTS[_quest["quest_id"] - 1]["number"]

        _daily_quest_array: list = mem.daily_quests
        _daily_quest_array[_qidx] = _quest

        _daily_quest_array = list(map(json.dumps, _daily_quest_array))

        # await self.bot.pool.execute("UPDATE member SET daily_quests = $1 WHERE id = $2", _daily_quest_array, mem.id)
        mem.daily_quests = _daily_quest_array

        if _quest["quest_progress"] >= QUESTS[_quest["quest_id"] - 1]["number"]:
            if QUESTS[_quest["quest_id"] - 1]["event"] == "on_catch":
                self.bot.dispatch("catch_quest_done", mem, _quest)

            elif QUESTS[_quest["quest_id"] - 1]["event"] == "on_vote":
                ...

        await mem.save()

    @commands.Cog.listener()
    async def on_catch(self, ctx: commands.Context, pokemon: models.Pokemon):
        mem: models.Member = await self.bot.manager.fetch_member_info(ctx.author.id)

        for _quest in mem.daily_quests:
            __quest_mem_copy = _quest
            __quest_data = QUESTS[_quest["quest_id"] - 1]
            if __quest_data["event"] == "on_catch":
                if _quest.get("species_id", None) is not None and pokemon.species_id == _quest["species_id"]:
                    species: dict = data.species_by_num(_quest["species_id"])
                    await self.update_quest_progress(mem, __quest_mem_copy)

                if __quest_data.get("species_id", None) is not None and __quest_data["species_id"] == pokemon.species_id:
                    await self.update_quest_progress(mem, __quest_mem_copy)

                if __quest_data.get("type", None) is not None:
                    species: dict = data.species_by_num(pokemon.species_id)
                    type_id: int = TYPES.index(__quest_data["type"].title())
                    if type_id in species["types"]:
                        await self.update_quest_progress(mem, __quest_mem_copy)

                if _quest.get("species_id", None) is None and __quest_data.get("type") is None:
                    await self.update_quest_progress(mem, _quest)

    @commands.Cog.listener()
    async def on_catch_quest_done(self, mem: models.Member, quest: dict):
        if quest["quest_done"]:
            return

        _daily_quest_array = mem.daily_quests
        qidx: int = 0
        for idx, q in enumerate(_daily_quest_array):
            if json.loads(q)["quest_id"] == quest["quest_id"]:
                qidx = idx
                break

        _daily_quest_array[qidx] = None

        mem: models.Member = await self.bot.manager.fetch_member_info(mem.id)
        quest["quest_done"] = True

        __quest_data: dict = QUESTS[quest["quest_id"] - 1]

        if quest["quest_progress"] > __quest_data["number"]:
            quest["quest_progress"] = __quest_data["number"]

        if __quest_data.get("shards", None) is not None:
            mem.shards += __quest_data["shards"]

        if __quest_data.get("credits", None) is not None:
            mem.balance += __quest_data["credits"]

        user: discord.User = self.bot.get_user(mem.id) or await self.bot.fetch_user(mem.id)

        if quest.get("species_id", None) is not None:
            species: dict = data.species_by_num(quest["species_id"])
            __quest_data["text"].format(species["names"]["9"])

        with suppress(discord.Forbidden, discord.HTTPException):
            await user.send(
                embed=self.bot.Embed(
                    title="🎉 Daily Quest Completed!",
                    description=f"You successfully completed your daily quest `{__quest_data['text']}`! You received *{__quest_data['reward']}*",
                )
            )

        _daily_quest_array[qidx] = quest
        _daily_quest_array = list(map(json.dumps, _daily_quest_array))

        mem.daily_quests = _daily_quest_array

        await mem.save()

    async def _reset_or_give_daily_quests(self):
        with suppress(ConfigurationError):
            async for member in models.Member.all():
                if member.daily_quests_timestamp is None:
                    # await self.assign_daily_species(member)
                    member: models.Member = await models.Member.get(id=member.id)

                    for quest in QUESTS:
                        if quest["quest_id"] != 1:
                            member.daily_quests = ArrayAppend(
                                "daily_quests",
                                json.dumps(
                                    {
                                        "quest_id": quest["quest_id"],
                                        "quest_progress": 0,
                                        "quest_done": False,
                                    }
                                ),
                            )

                            await member.save()
                            member: models.Member = await models.Member.get(id=member.id)

                    member.daily_quests_timestamp = datetime.now(tz=UTC) + timedelta(hours=24)
                    await member.save()

                elif member.daily_quests_timestamp < datetime.now(tz=UTC):
                    member.daily_quests = []
                    await member.save()

                    member: models.Member = await models.Member.get(id=member.id)

                    # await self.assign_daily_species(member)

                    for quest in QUESTS:
                        if quest["quest_id"] != 1:
                            member.daily_quests = ArrayAppend(
                                "daily_quests",
                                json.dumps(
                                    {
                                        "quest_id": quest["quest_id"],
                                        "quest_progress": 0,
                                        "quest_done": False,
                                    }
                                ),
                            )
                            await member.save()

                            member: models.Member = await models.Member.get(id=member.id)

                    member.daily_quests_timestamp = datetime.now(tz=UTC) + timedelta(hours=24)
                    await member.save()

    @tasks.loop(minutes=25)
    async def reset_or_give_daily_quests(self):
        await self.bot.loop.create_task(self._reset_or_give_daily_quests())

    @reset_or_give_daily_quests.before_loop
    async def before_reset_or_give_daily_quests(self):
        await self.bot.wait_until_ready()


def setup(bot: PokeBest) -> None:
    bot.add_cog(Quests(bot))
