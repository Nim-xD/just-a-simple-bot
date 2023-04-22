from __future__ import annotations
import json
from discord import embeds, emoji

from discord.ext import commands
import discord

import typing
from core.views import ResearchTasksView

import models
from utils.methods import clear_empty_fields

if typing.TYPE_CHECKING:
    from core.bot import PokeBest

from utils.emojis import emojis
from utils.constants import TYPES, BattleEngine
from models.helpers import ArrayAppend, ArrayRemove
from utils.checks import has_started
from contextlib import suppress
import pickle

TASKS: list = [
    {
        "idx": 1,
        "type": "catch",
        "text": f"Catch 40 {emojis.fire} Fire type pokémon",
        "event": "catch",
        "redeems": 1,
        "pokemon_type": "fire",
        "number": 40,
    },
    {
        "idx": 2,
        "type": "catch",
        "text": f"Catch 40 {emojis.grass} Grass type pokémon",
        "event": "catch",
        "redeems": 1,
        "pokemon_type": "grass",
        "number": 40,
    },
    {
        "idx": 3,
        "type": "catch",
        "text": f"Catch 40 {emojis.water} Water type pokémon",
        "event": "catch",
        "redeems": 1,
        "pokemon_type": "water",
        "number": 40,
    },
    # {"idx": 4, "type": "evolve", "text": "Evolve a pokémon", "event": "evolution", "credits": 5000, "number": 1},
    {
        "idx": 5,
        "type": "levelup",
        "text": "Power up 10 Pokémon to level 100",
        "event": "levelup",
        "number": 10,
        "gift": 1,
        "level": 100,
    },
    {
        "idx": 6,
        "type": "duelai",
        "text": "Beat our duel AI 15 Times",
        "event": "battle_finish",
        "credits": 10000,
        "number": 15,
    },
    {
        "idx": 7,
        "type": "collect",
        "text": "Collect 50 crackers",
        "event": "collect",
        "gift": 2,
        "number": 50,
    },
    # {
    #     "idx": 8,
    #     "type": "catch",
    #     "text": "Catch a legendary pokémon",
    #     "event": "catch",
    #     "credits": 10000,
    #     "pokemon_rarity": "legendary",
    #     "number": 1,
    # },
]


class ResearchTasks(commands.Cog):
    def __init__(self, bot: PokeBest) -> None:
        self.bot: PokeBest = bot

    async def get_quest(self, quest_idx: int, member: models.Member):
        quest = {}
        index = None
        for idx, _quest in enumerate(member.quests):
            if _quest["idx"] == quest_idx:
                quest = _quest
                index = idx

        return quest, index

    def make_progress_bar(self, progress: int, total_progress: int) -> str:
        txt: str = ""
        bar_progress: int = round((progress / total_progress) * 12)
        spaces: int = 12 - bar_progress

        if progress == 0:
            txt += emojis.quest_empty_front + emojis.quest_empty * (12 - 2) + emojis.quest_empty_back
            return txt

        for _ in range(15):
            filled: str = f"{emojis.quest_fill_front}" + f"".join(f"{emojis.quest_fill}" for _ in range(bar_progress - 2))

            if bar_progress != 12:
                empty: str = f"".join(f"{emojis.quest_empty}" for _ in range(spaces - 1)) + f"{emojis.quest_empty_back}"
            else:
                empty: str = f"{emojis.quest_fill_back}"

        return filled + empty

    def cook_reward_text(self, quest: dict) -> str:
        txt: str = ""
        if quest.get("credits") is not None:
            txt = f"💰 {quest['credits']} credits"

        elif quest.get("redeems") is not None:
            txt = f"🎫 {quest['redeems']} redeem(s)"

        elif quest.get("gift") is not None:
            txt = f"{emojis.gift} {quest['gift']} gift(s)"

        return txt

    async def insert_or_update_task(self, mem_id: int, quest):
        mem: models.Member = await self.bot.manager.fetch_member_info(mem_id)
        task, idx = await self.get_quest(quest["idx"], mem)

        if quest.get("number") is not None and quest.get("number") <= task.get("progress", 1):
            return

        if not task:
            task = {
                "idx": quest["idx"],
                "progress": 1,
                "reward_claimed": False,
                "done": False,
            }
            mem.quests = ArrayAppend("quests", json.dumps(task))

        else:
            mem.quests = ArrayRemove("quests", json.dumps(task))

            task["progress"] += 1
            mem.quests = ArrayAppend("quests", json.dumps(task))

        if task["progress"] >= quest.get("number", 1):
            mem.quests = ArrayRemove("quests", json.dumps(task))

            task["done"] = True
            mem.quests = ArrayAppend("quests", json.dumps(task))

            self.bot.dispatch("task_finish", task, mem, quest)

        await mem.save()

    @commands.command(aliases=("rs",))
    @has_started()
    async def researchtask(self, ctx: commands.Context):
        """See list and progress of your research tasks"""
        mem: models.Member = await self.bot.manager.fetch_member_info(ctx.author.id)

        emb: discord.Embed = self.bot.Embed(
            title="Research Tasks",
            description="Do complete the following task for awesome rewards!",
        )

        count = 0
        pages: typing.List[discord.Embed] = []

        for task in TASKS:
            quest, _ = await self.get_quest(task["idx"], mem)
            emb.add_field(
                name=f'{task.__getitem__("text")} [{quest.get("progress", 0)}/{task.get("number", 1)}]',
                value=f"{self.make_progress_bar(quest.get('progress', 0), task.get('number', 1))}"
                + f"\n**Reward:** {self.cook_reward_text(task)}",
                inline=False,
            )
            count += 1

            if count % 3 == 0:
                pages.append(emb)
                emb = self.bot.Embed(
                    title="Research Tasks",
                    description="Do complete the following task for awesome rewards!",
                )

        pages.append(emb)

        pages = clear_empty_fields(pages)

        # Final Rewards Display
        # final_rewards: discord.Embed = self.bot.Embed(
        #     title="🪔 Light Up Special Research Task 🪔",
        #     description=f"**Final Rewards:**\n{emojis.gift} - 2 Gifts\n<:light_xerneas:904963004456636488> - Light Xerneas",
        # )
        # pages.append(final_rewards)

        _view: ResearchTasksView = ResearchTasksView(ctx, pages)

        await _view.paginate()

    @commands.Cog.listener()
    async def on_catch(self, ctx: commands.Context, pokemon: models.Pokemon):
        pokemon_types: list = [TYPES[type_id].lower() for type_id in pokemon.specie["types"]]
        pokemon_rarity = "normal"

        if pokemon.specie["legendary"]:
            pokemon_rarity = "legendary"

        elif pokemon.specie["mythical"]:
            pokemon_rarity = "mythical"

        quest: typing.Optional[dict] = None

        for t in TASKS:
            if t.get("pokemon_type") in pokemon_types or t.get("pokemon_rarity") == pokemon_rarity:
                quest = t

        if quest is None:
            return

        await self.insert_or_update_task(ctx.author.id, quest)

    @commands.Cog.listener()
    async def on_levelup(self, message: discord.Message, pokemon: models.Pokemon):
        quest = None

        for t in TASKS:
            if t["type"] == "levelup":
                quest = t
                break

        if quest is None:
            return

        if quest["level"] > pokemon.level:
            return

        await self.insert_or_update_task(message.author.id, quest)

    @commands.Cog.listener()
    async def on_evolve(self, message: discord.Message, pokemon: models.Pokemon):
        quest = None

        for t in TASKS:
            if t["type"] == "evolve":
                quest = t

        if quest is None:
            return

        await self.insert_or_update_task(message.author.id, quest)

    @commands.Cog.listener()  # NOTE: This could have one task problem
    async def on_battle_finish(self, battle, trainer):
        quest = None

        for t in TASKS:
            if t["type"] in ["duel", "duelai"]:
                quest = t
                break

        if quest is None:
            return

        if (
            t["type"] == "duel"
            and battle.battle_engine != BattleEngine.Human
            or t["type"] == "duelai"
            and battle.battle_engine != BattleEngine.AI
        ):
            return

        if trainer.user.id == self.bot.user.id:
            return

        await self.insert_or_update_task(trainer.user.id, quest)

    @commands.Cog.listener()
    async def on_collect(self, mem: models.Member):
        quest = None

        for t in TASKS:
            if t["type"] == "collect":
                quest = t
                break

        if quest is None:
            return

        await self.insert_or_update_task(mem.id, quest)

    @commands.Cog.listener()
    async def on_task_finish(self, task, mem: models.Member, quest):
        if quest.get("credits") is not None:
            mem.balance += quest["credits"]

        if quest.get("redeems") is not None:
            mem.redeems += quest["redeems"]

        if quest.get("gift") is not None:
            mem.gift += quest["gift"]

        await mem.save()

        # NOTE: Disabled for future
        # finsihed_quests = [q for q in mem.quests if q["done"]]
        # if len(finsihed_quests) >= len(TASKS):
        #     mem.gift += 2
        #     pk: models.Pokemon = models.Pokemon.get_random(
        #         species_id=10379, level=15, xp=0, owner_id=mem.id, idx=mem.next_idx
        #     )

        #     await pk.save()
        #     await self.bot.manager.update_idx(mem.id)

        #     emb: discord.Embed = self.bot.Embed(
        #         title="🎉 Congratulations! You finished all your tasks!",
        #         description=f"**You received:**\n{emojis.gift} - 2 Gifts\n<:light_xerneas:904963004456636488> - Light Xerneas",
        #     )

        #     user: discord.User = self.bot.get_user(mem.id) or await self.bot.fetch_user(mem.id)

        #     with suppress(discord.HTTPException, discord.Forbidden):
        #         return await user.send(embed=emb)

        emb: discord.Embed = self.bot.Embed(
            title="🎉 Task Finished!",
            description=f"You successfully finished the research task:\n`{quest['text']}`!\nYou received **{self.cook_reward_text(quest)}**!",
        )

        user: discord.User = self.bot.get_user(mem.id) or await self.bot.fetch_user(mem.id)

        with suppress(discord.HTTPException, discord.Forbidden):
            await user.send(embed=emb)


def setup(bot: PokeBest) -> None:
    bot.add_cog(ResearchTasks(bot))
