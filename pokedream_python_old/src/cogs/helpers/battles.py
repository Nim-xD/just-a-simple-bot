from __future__ import annotations
from datetime import datetime
import enum


from dataclasses import dataclass, field
from enum import Enum, IntEnum
from functools import cached_property
import json
from typing import List, Optional, TYPE_CHECKING, Set
import aiohttp
import discord
from discord.ext import commands
import models
from data import data
from contextlib import suppress
from PIL import Image
from utils.constants import UTC, BattleType, BattleEngine, BattleCategory
from utils.methods import make_hp_bar, write_fp
from utils.emojis import emojis
from utils import constants
from io import BytesIO
from models.helpers import ArrayAppend
import requests
import random
import math
import pickle

if TYPE_CHECKING:
    from core.bot import PokeBest

## TODO: Secure moves using locks !!

# ===================================================================================================================================================================


class MoveChoiceButton(discord.ui.Button):
    def __init__(self, battle, move):
        self.battle = battle
        self.move = move
        super().__init__(label=f'{move["name"].title()} | {move["pp"]}')

    async def callback(self, interaction: discord.Interaction):
        self._view.move_choice = self.move

        with suppress(TypeError):
            await self._view.stop()


class MoveChoiceView(discord.ui.View):
    def __init__(self, buttons: List[MoveChoiceButton]):
        self.buttons: List[MoveChoiceButton] = buttons
        self.move_choice = None
        super().__init__(timeout=None)

        for btn in self.buttons:
            self.add_item(btn)


class FightButton(discord.ui.Button):
    def __init__(self, battle: "Battle", view: discord.ui.View):
        self.battle: "Battle" = battle
        self.battle_view = view
        super().__init__(label="Fight", style=discord.ButtonStyle.blurple, emoji="⚔️")

    async def callback(self, interaction: discord.Interaction):
        self.battle_view.stop()  ## ! Experimental ! ##
        trainers: list = self.battle.trainers

        _trainer = None
        for trainer in trainers:
            if trainer.user.id == interaction.user.id:
                _trainer = trainer

        if interaction.user.id in self.battle.used:
            return await interaction.followup.send("You already choose a move. Wait for your opponent!", ephemeral=True)

        if interaction.user.id in list(self.battle.used):
            return await interaction.followup.send("You already used a move!", ephemeral=True)

        _move_buttons: List[MoveChoiceButton] = []
        for mv in _trainer.get_moves:
            _move_buttons.append(MoveChoiceButton(self.battle, mv))

        _view: MoveChoiceView = MoveChoiceView(_move_buttons)
        # self.battle_view.stop()  ## !EXPERIMENTAL! ##

        await interaction.followup.send(content="Choose any move from the following:", view=_view, ephemeral=True)

        await _view.wait()

        if _view.move_choice is not None:
            if self.battle.used.__len__() < 2:
                self.battle.used.add(interaction.user.id)
                self.battle.last_modified = datetime.utcnow()
                await self.battle.run_move(_view.move_choice, interaction.user.id)

                if (
                    self.battle.battle_engine.value == 1
                    and self.battle.used.__len__() < 2
                    and self.battle.bot.user not in self.battle.used
                ):
                    o = self.battle._get_another_trainer(interaction.user.id)

                    await self.battle.run_move(random.choice(o.get_moves), self.battle.bot.user.id)
                    _view.stop()
                    self.battle.used.add(self.battle.bot.user.id)

                    await self.battle.send_move_result()
                    # self.disabled = True

                with suppress(discord.Forbidden, discord.HTTPException):
                    await interaction.edit_original_message(
                        content=f"You picked {_view.move_choice['name']}! Waiting for your opponent...",
                        view=None,
                    )
                    # self.disabled = True

            if self.battle.used.__len__() == 2:
                await self.battle.send_move_result()
        # await _msg.delete()


class FleeButton(discord.ui.Button):
    def __init__(self, bot: PokeBest, battle):
        self.bot: PokeBest = bot
        self.battle = battle
        super().__init__(label="Flee", emoji="🏃")

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        await interaction.followup.send(f"{interaction.user.display_name} flew from battle!")

        if self.battle.reward.value == 7:
            gym: models.Gym = await models.Gym.get(guild_id=self.battle.ctx.guild.id)

            gym.defeats = ArrayAppend("defeats", interaction.user.id)
            await gym.save()

        self.bot.battles.remove(self.battle)
        self.view.stop()


class BagButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Bag", emoji="🎒")


class PokemonSwitchButton(discord.ui.Button):
    def __init__(self, battle):
        self.battle = battle
        super().__init__(label="Pokemon", emoji="<:pkball1:893723694055178300>")

    async def callback(self, interaction: discord.Interaction):
        if self.battle.battle_type == BattleType.oneVone:
            return await interaction.response.send_message(
                "Sorry, but you can't switch your pokemon in 1v1 battles.",
                ephemeral=True,
            )


class BattleView(discord.ui.View):
    def __init__(self, battle):
        self.battle = battle
        super().__init__(timeout=None)

        self.add_item(FightButton(self.battle, self))
        self.add_item(FleeButton(self.battle.bot, self.battle))
        # self.add_item(BagButton())
        self.add_item(PokemonSwitchButton(self.battle))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        await interaction.response.defer()
        if interaction.user.id not in [t.user.id for t in self.battle.trainers]:
            await interaction.followup.send(
                "Sorry, you can't use this interaction as you are not in this battle.",
                ephemeral=True,
            )
            return False
        return True


# ====================================================================================================================================================================


@dataclass
class Trainer:
    user: discord.User
    pokemon: List[models.Pokemon]
    selected: int
    selected_pokemon: models.Pokemon
    is_bot: bool = False
    _hp: Optional[int] = None

    damage_delt: int = 0
    ailments: Set[str] = field(default_factory=set)

    def __str__(self) -> str:
        return self.user.__str__()

    async def send(self, *args):
        return await self.user.send(*args)

    @property
    def hp(self):
        return self._hp if self._hp is not None else self.selected_pokemon.max_hp

    @hp.setter
    def set_hp(self, value: int):
        self._hp = value

    @property
    def get_moves(self) -> list:
        _mv_list: List[dict] = []
        for mv in self.selected_pokemon.moves:
            _mv_list.append(data.move_by_id(mv))

        return _mv_list


class MoveEffect(IntEnum):
    missed = 1
    super_effective = 2
    not_effective = 3
    normal = 4
    nothing = 5


class Stage(IntEnum):
    PROGRESS = 1
    END = 2


class Reward(IntEnum):
    Basic = 1
    Pokemon = 2
    Christmas = 3
    TeamRocket = 4
    SpawnDuel = 5
    Raids = 6
    Gym = 7

    Journey = 8
    JourneyTrainer = 9


@dataclass
class StatStages:
    hp: int = 0
    atk: int = 0
    defn: int = 0
    satk: int = 0
    sdef: int = 0
    spd: int = 0
    evasion: int = 0
    accuracy: int = 0
    crit: int = 0

    def update(self, stages):
        self.hp += stages.hp
        self.atk += stages.atk
        self.defn += stages.defn
        self.satk += stages.satk
        self.sdef += stages.sdef
        self.spd += stages.spd
        self.evasion += stages.evasion
        self.accuracy += stages.accuracy
        self.crit += stages.crit


@dataclass
class StatChange:
    stat_id: int
    change: int

    @cached_property
    def stat(self):
        return ("hp", "atk", "defn", "satk", "spd", "evasion", "accuracy")[self.stat_id - 1]


@dataclass
class BattleMove:
    success: bool
    damage: int
    healing: int
    ailment: str
    effect: MoveEffect
    messages: List[str]
    stat_changes: List[StatChange]
    critical_hit: bool

    @property
    def text(self) -> str:
        if self.effect == MoveEffect.missed:
            message = "Uhh.. It missed!"
        elif self.effect == MoveEffect.super_effective:
            message = f"Woah! It was super effective! **`-{self.damage}`**"
        elif self.effect == MoveEffect.not_effective:
            message = f"It wasn't that effective. **`-{self.damage}`**"
        elif self.effect == MoveEffect.nothing:
            message = "It had no effect!"
        else:
            message = f"**`-{self.damage}`**"

        if self.effect not in (MoveEffect.missed, MoveEffect.nothing) and self.critical_hit:
            message = f"\nIt was a **CRITICAL HII! ** | **`-{self.damage}`**"

        return message


class Battle:
    def __init__(
        self,
        bot: PokeBest,
        ctx: commands.Context,
        trainers: List[Trainer],
        battle_type: BattleType,
        battle_engine: BattleEngine,
        reward: Reward = Reward.Basic,
        category: BattleCategory = BattleCategory.Normal,
        raid_battle: bool = False,
        **kwargs,
    ) -> None:
        self.bot: PokeBest = bot
        self.ctx: commands.Context = ctx
        self.trainers: List[Trainer] = trainers
        self.battle_type: BattleType = battle_type
        self.battle_engine: BattleEngine = battle_engine
        self.category: BattleCategory = category
        self.used: set = set()
        self.last_modified = datetime.utcnow()

        self.kwargs = kwargs

        for trainer in self.trainers:
            trainer.set_hp = trainer.selected_pokemon.max_hp

        self.move_emb: discord.Embed = self.bot.Embed()
        self.battle_ended: bool = False
        self.reward = reward
        self.battle_view = None

        if self.reward == Reward.Christmas:
            self.move_emb.color = discord.Color.red()

        self._image_cache = {}
        self.raid_battle: bool = raid_battle

        for t in self.trainers:
            t.selected_pokemon.stages = StatStages()

    def __repr__(self) -> str:
        return f"<Battle:{self.trainers[0].user.id}|{self.trainers[1].user.id}>"

    def _build_moves_embed(self, trainer: Trainer, moves: list) -> discord.Embed:
        _emb: discord.Embed = self.bot.Embed(title=f"{trainer.selected_pokemon} Moves:")

        txt: str = ""

        for idx, move in enumerate(moves):
            txt += f"`{idx}` | {move['name']}\n"

        _emb.description = txt

        return _emb

    def _get_trainer_by_id(self, tid: int) -> Trainer:
        for tr in self.trainers:
            if tr.user.id == tid:
                return tr

        return None

    def _get_another_trainer(self, tid: int) -> Trainer:
        for tr in self.trainers:
            if tr.user.id != tid:
                return tr

    def _get_bar_emoji(self, hp: int):
        if hp > 7:
            return emojis.green

        elif hp > 4:
            return emojis.yellow

        else:
            return emojis.red

    async def send_moves(self):
        trainer1: Trainer = self.trainers[0]
        trainer2: Trainer = self.trainers[1]

        t1moves: list = []
        for mv in trainer1.selected_pokemon.moves:
            t1moves.append(data.move_by_id(mv))

        t2moves: list = []
        for mv in trainer2.selected_pokemon.moves:
            t2moves.append(data.move_by_id(mv))

        with suppress(discord.Forbidden):
            await trainer1.send(embed=self._build_moves_embed(trainer1, t1moves))

        with suppress(discord.Forbidden):
            await trainer2.send(embed=self._build_moves_embed(trainer2, t2moves))

    def make_battle_image(self, pk1_url: str, pk2_url: str) -> bytes:
        img: Image = Image.open(requests.get("https://i.imgur.com/KWdmvCn.png", stream=True).raw)

        pk1: Image = Image.open(requests.get(pk1_url, stream=True).raw)
        pk2: Image = Image.open(requests.get(pk2_url, stream=True).raw)

        img.paste(pk1, (175, 220), mask=pk1)
        img.paste(pk2, (1250, 220), mask=pk2)

        img_bytes = BytesIO()
        img.save(img_bytes, "PNG")
        img_bytes.seek(0)

        return img_bytes

    # TODO: Status Moves
    def calculate_damage(self, move, attacker: Trainer, defender: Trainer) -> BattleMove:
        move_meta: dict = data.get_move_meta(move["id"])
        if move["damage_class_id"] == 1 or move["power"] is None:
            success = True
            damage = 0
            hits = 0
            critical_hit = 1
        else:
            accu: int = move["accuracy"] if move["accuracy"] is not None else 100
            success: int = random.randrange(99) <= accu

            hits: int = random.randint(
                move_meta.__getitem__("min_hits") or 1,
                move_meta.__getitem__("max_hits") or 1,
            )

            # if move["power"] is None:
            #     move = data.move_by_id(33)

            if move["type_id"] in list(attacker.selected_pokemon.specie["types"]):
                stab = 1.5
            else:
                stab = 1

            target = 0.75 if move["target_id"] in [5, 9, 10, 11, 13, 14] else 1
            critical_hit = 2 if random.randint(1, 150) == 1 else 1
            rand = random.choice([0.1, 1, 0.75])

            if move["damage_class_id"] == 2:
                atk = (
                    attacker.selected_pokemon.specie["base_stats"][1]
                    * constants.STAT_STAGE_MULTIPLIERS[attacker.selected_pokemon.stages.atk]
                )
                defn = (
                    defender.selected_pokemon.specie["base_stats"][2]
                    * constants.STAT_STAGE_MULTIPLIERS[attacker.selected_pokemon.stages.defn]
                )

            else:
                atk = (
                    attacker.selected_pokemon.specie["base_stats"][3]
                    * constants.STAT_STAGE_MULTIPLIERS[attacker.selected_pokemon.stages.satk]
                )
                defn = (
                    defender.selected_pokemon.specie["base_stats"][4]
                    * constants.STAT_STAGE_MULTIPLIERS[attacker.selected_pokemon.stages.sdef]
                )

            damage = int((2 * attacker.selected_pokemon.level / 5 + 2) * move["power"] * atk / defn) / 50 + 2

            # damage *= stab * target * critical_hit * rand * typ_mult

        # return BattleMove(int(damage), effectiveness, critical_hit == 2)

        messages: List[str] = []

        typ_mult = 1
        for typ in defender.selected_pokemon.specie["types"]:
            typ_mult *= constants.TYPE_EFFICACY[move["type_id"]][typ]

        if not success:
            effectiveness = MoveEffect.missed
            messages.append("It missed!")
            typ_mult = 0

        elif typ_mult == 0:
            effectiveness = MoveEffect.not_effective
            messages.append("It had no effect!")

        elif typ_mult < 1:
            messages.append("It was not very effective...")
            effectiveness = MoveEffect.not_effective

        elif typ_mult == 1:
            effectiveness = MoveEffect.normal

        else:
            messages.append("It was super effective!")
            effectiveness = MoveEffect.super_effective

        if hits > 1:
            messages.append(f"It hit {hits} times!")

        healing = damage * move_meta["drain"] / 100
        healing += attacker.selected_pokemon.max_hp * move_meta["healing"] / 100

        for ailment in attacker.ailments:
            if ailment == "Paralysis":
                if random.random() < 0.25:
                    success = False
            elif ailment == "Sleep":
                if move["id"] not in (173, 214):
                    success = False
            elif ailment == "Freeze":
                if move["id"] not in (588, 172, 221, 293, 503, 592):
                    success = False
            elif ailment == "Burn":
                if move["damage_class_id"] == 2:
                    damage /= 2

            ## TODO: Add more ailments

        changes: list = []

        if random.randrange(100) < move_meta["stat_chance"]:
            changes.append(StatChange(move_meta["change_stat_id"], move_meta["stat_change"]))

        ailment = (
            constants.MOVE_AILMENTS[move_meta["meta_ailment_id"]]
            if random.randrange(100) < move_meta["ailment_chance"]
            else None
        )

        return BattleMove(
            success,
            round(damage),
            round(healing),
            ailment,
            effectiveness,
            messages,
            changes,
            critical_hit,
        )

    async def send_battle(self):
        img_bytes: bytes = await self.bot.loop.run_in_executor(
            None,
            self.make_battle_image,
            self.trainers[0].selected_pokemon.normal_image,
            self.trainers[1].selected_pokemon.normal_image,
        )

        resp: Optional[aiohttp.ClientResponse] = None

        pk1shinyint: int = 1 if self.trainers[0].selected_pokemon.shiny else 0
        pk2shinyint: int = 1 if self.trainers[1].selected_pokemon.shiny else 0

        pk1hpapi: int = round((self.trainers[0].selected_pokemon.hp / self.trainers[0].selected_pokemon.max_hp) * 75)
        pk2hpapi: int = round((self.trainers[1].selected_pokemon.hp / self.trainers[1].selected_pokemon.max_hp) * 75)

        _journey_urls = {
            BattleCategory.JourneyGrass: "grass",
            BattleCategory.JourneyDesert: "desert",
            BattleCategory.JourneyBadLand: "badland",
            BattleCategory.JourneyWild: "wild",
            BattleCategory.JourneyCave: "cave",
        }

        if self.battle_type == BattleType.oneVone:
            if (
                self.trainers[0].selected_pokemon.species_id <= 898
                and self.trainers[1].selected_pokemon.species_id <= 898
            ):
                # if self.category == BattleCategory.Normal:
                #     resp = requests.get(
                #         f"{self.bot.config.IMAGE_SERVER_URL}duelhp/{self.trainers[0].selected_pokemon.species_id}/{self.trainers[1].selected_pokemon.species_id}/{pk1shinyint}/{pk2shinyint}/{pk1hpapi}/{pk2hpapi}/{self.trainers[0].selected_pokemon.level}/{self.trainers[1].selected_pokemon.level}/{self.trainers[0].selected_pokemon}/{self.trainers[1].selected_pokemon}/normal"
                #     )

                if self.category == BattleCategory.Water:
                    pk1hpapi: int = round(
                        (self.trainers[0].selected_pokemon.hp / self.trainers[0].selected_pokemon.max_hp) * 109
                    )
                    pk2hpapi: int = round(
                        (self.trainers[1].selected_pokemon.hp / self.trainers[1].selected_pokemon.max_hp) * 109
                    )

                    async with self.bot.session.get(
                        f"{self.bot.config.IMAGE_SERVER_URL}duelhp/{self.trainers[0].selected_pokemon.species_id}/{self.trainers[1].selected_pokemon.species_id}/{pk1shinyint}/{pk2shinyint}/{pk1hpapi}/{pk2hpapi}/{self.trainers[0].selected_pokemon.level}/{self.trainers[1].selected_pokemon.level}/{self.trainers[0].selected_pokemon}/{self.trainers[1].selected_pokemon}/water"
                    ) as __resp:
                        resp = __resp

                        if resp is not None and resp.status == 200:
                            img_bytes = await self.bot.loop.run_in_executor(None, write_fp, await resp.read())

                    # resp = requests.get(
                    #     f"{self.bot.config.IMAGE_SERVER_URL}duelhp/{self.trainers[0].selected_pokemon.species_id}/{self.trainers[1].selected_pokemon.species_id}/{pk1shinyint}/{pk2shinyint}/{pk1hpapi}/{pk2hpapi}/{self.trainers[0].selected_pokemon.level}/{self.trainers[1].selected_pokemon.level}/{self.trainers[0].selected_pokemon}/{self.trainers[1].selected_pokemon}/water"
                    # )

                elif 8 <= self.category.value <= 12:
                    pk1hpapi: int = round(
                        (self.trainers[0].selected_pokemon.hp / self.trainers[0].selected_pokemon.max_hp) * 109
                    )
                    pk2hpapi: int = round(
                        (self.trainers[1].selected_pokemon.hp / self.trainers[1].selected_pokemon.max_hp) * 109
                    )

                    resp = requests.get(
                        f"{self.bot.config.IMAGE_SERVER_URL}dueljourney/{self.trainers[0].selected_pokemon.species_id}/{self.trainers[1].selected_pokemon.species_id}/{pk1shinyint}/{pk2shinyint}/{pk1hpapi}/{pk2hpapi}/{self.trainers[0].selected_pokemon.level}/{self.trainers[1].selected_pokemon.level}/{self.trainers[0].selected_pokemon}/{self.trainers[1].selected_pokemon}/{_journey_urls[self.category]}"
                    )

                else:
                    async with self.bot.session.get(
                        f"{self.bot.config.IMAGE_SERVER_URL}duelrl/{self.trainers[0].selected_pokemon.species_id}/{self.trainers[1].selected_pokemon.species_id}/{pk1shinyint}/{pk2shinyint}/{pk1hpapi}/{pk2hpapi}/{self.trainers[0].selected_pokemon.level}/{self.trainers[1].selected_pokemon.level}/{self.trainers[0].selected_pokemon}/{self.trainers[1].selected_pokemon}"
                    ) as __resp:
                        resp = __resp

                        if resp is not None and resp.status == 200:
                            img_bytes = await self.bot.loop.run_in_executor(None, write_fp, await resp.read())

                    # resp = requests.get(
                    #     f"{self.bot.config.IMAGE_SERVER_URL}duelrl/{self.trainers[0].selected_pokemon.species_id}/{self.trainers[1].selected_pokemon.species_id}/{pk1shinyint}/{pk2shinyint}/{pk1hpapi}/{pk2hpapi}/{self.trainers[0].selected_pokemon.level}/{self.trainers[1].selected_pokemon.level}/{self.trainers[0].selected_pokemon}/{self.trainers[1].selected_pokemon}"
                    # )

            if self.reward in [Reward.Raids, Reward.Gym] or self.category == BattleCategory.Gym:
                pk1hpapi: int = round(
                    (self.trainers[0].selected_pokemon.hp / self.trainers[0].selected_pokemon.max_hp) * 109
                )
                pk2hpapi: int = round(
                    (self.trainers[1].selected_pokemon.hp / self.trainers[1].selected_pokemon.max_hp) * 109
                )

                gmax_spid: Optional[int] = data.get_gmax_species(self.trainers[1].selected_pokemon.species_id)

                if gmax_spid is None:
                    gmax_spid = self.trainers[1].selected_pokemon.species_id

                # resp = requests.get(
                #     f"{self.bot.config.IMAGE_SERVER_URL}raid/{self.trainers[0].selected_pokemon.species_id}/{gmax_spid}/{pk1shinyint}/{pk2shinyint}/{pk1hpapi}/{pk2hpapi}/{self.trainers[0].selected_pokemon.level}/100/{self.trainers[0].selected_pokemon}/{self.trainers[1].selected_pokemon}"
                # )

                async with self.bot.session.get(
                    f"{self.bot.config.IMAGE_SERVER_URL}raid/{self.trainers[0].selected_pokemon.species_id}/{gmax_spid}/{pk1shinyint}/{pk2shinyint}/{pk1hpapi}/{pk2hpapi}/{self.trainers[0].selected_pokemon.level}/100/{self.trainers[0].selected_pokemon}/{self.trainers[1].selected_pokemon}"
                ) as __resp:
                    resp = __resp

                    if resp is not None and resp.status == 200:
                        img_bytes = await self.bot.loop.run_in_executor(None, write_fp, await resp.read())

                # elif self.category == BattleCategory.Grass:
                #     resp = requests.get(
                #         f"{self.bot.config.IMAGE_SERVER_URL}duelhp/{self.trainers[0].selected_pokemon.species_id}/{self.trainers[1].selected_pokemon.species_id}/{pk1shinyint}/{pk2shinyint}/{pk1hpapi}/{pk2hpapi}/{self.trainers[0].selected_pokemon.level}/{self.trainers[1].selected_pokemon.level}/{self.trainers[0].selected_pokemon}/{self.trainers[1].selected_pokemon}/grass"
                #     )

            if self.trainers[1].is_bot and self.reward == Reward.TeamRocket:
                _nm = "Team Rocket's Grunt"
            else:
                _nm = self.trainers[1].__str__()

            _file: discord.File = discord.File(img_bytes, "duel.png")
            embed: discord.Embed = self.bot.Embed(title=f"Battle between {self.trainers[0]} and {_nm}!")

            embed.add_field(
                name=f"{self.trainers[0].user.name}'s Pokemon:",
                value=f"{self.trainers[0].selected_pokemon} | **`{self.trainers[0].selected_pokemon.hp}`**/`{self.trainers[0].selected_pokemon.max_hp}` HP",
                inline=True,
            )

            embed.set_image(url="attachment://duel.png")

            # Refers to journey's battle
            if 8 <= self.category.value <= 12:
                _file = None
                embed: discord.Embed = self.bot.Embed()

                _t0hp: int = int(
                    (
                        self.trainers.__getitem__(0).selected_pokemon.hp
                        / self.trainers.__getitem__(0).selected_pokemon.max_hp
                    )
                    * 8
                )
                _t0emoji: str = self._get_bar_emoji(_t0hp)
                t0hpbar: str = make_hp_bar(8, _t0hp, _t0emoji)

                _t1hp: int = int(
                    (
                        self.trainers.__getitem__(1).selected_pokemon.hp
                        / self.trainers.__getitem__(1).selected_pokemon.max_hp
                    )
                    * 8
                )

                _t1emoji: str = self._get_bar_emoji(_t1hp)

                t1hpbar: str = make_hp_bar(8, _t1hp, _t1emoji)

                embed.add_field(
                    name=f"{self.trainers[0].selected_pokemon} - Lv. {self.trainers[0].selected_pokemon.level}",
                    value=f"**HP**: {t0hpbar} `{self.trainers[0].selected_pokemon.hp}/{self.trainers[0].selected_pokemon.max_hp}`",
                    inline=False,
                )

                embed.add_field(
                    name=f"{self.trainers[1].selected_pokemon} - Lv. {self.trainers[1].selected_pokemon.level}",
                    value=f"**HP**: {t1hpbar} `{self.trainers[1].selected_pokemon.hp}/{self.trainers[1].selected_pokemon.max_hp}`",
                    inline=False,
                )

                embed.set_footer(text=f"What will {self.trainers[0].selected_pokemon} do?")

                if self.reward == Reward.Journey:
                    embed.title = f"You encountered a Wild {self.trainers[1].selected_pokemon}!"

                elif self.reward == Reward.JourneyTrainer:
                    embed.title = f"You were challenged by {self.kwargs['trainer_data']['name']}!"

                # Adding GIFs
                embed.set_image(
                    url=f"https://img.pokemondb.net/sprites/black-white/anim/back-normal/{self.trainers[0].selected_pokemon.__str__().lower()}.gif"
                )
                embed.set_thumbnail(
                    url=f"https://img.pokemondb.net/sprites/black-white/anim/normal/{str(self.trainers[1].selected_pokemon).lower()}.gif"
                )

            else:
                embed.add_field(
                    name=f"{_nm}'s Pokemon:",
                    value=f"{self.trainers[1].selected_pokemon} | **`{self.trainers[1].selected_pokemon.hp}`**/`{self.trainers[1].selected_pokemon.max_hp}` HP",
                    inline=True,
                )

            _battle_view: BattleView = BattleView(self)
            self.battle_view = _battle_view

            if self.reward == Reward.Christmas:
                embed.color = discord.Color.red()

            return await self.ctx.send(embed=embed, file=_file, view=_battle_view)

    async def run_move(self, move, trainer_id: int):  # sourcery no-metrics
        _battle_exists: bool = False
        for b in self.bot.battles:
            if b.trainers == self.trainers or b.ctx == self.ctx:
                _battle_exists = True

        if not _battle_exists:
            return await self.ctx.reply("This battle is no longer active.")

        self.used.add(trainer_id)
        if self.battle_type == BattleType.oneVone:
            for trainer in self.trainers:
                if "Burn" in trainer.ailments:
                    trainer.selected_pokemon.hp -= 1 / 16 * trainer.selected_pokemon.max_hp
                if "Poison" in trainer.ailments:
                    trainer.selected_pokemon.hp -= 1 / 8 * trainer.selected_pokemon.max_hp

            t: Trainer = self._get_trainer_by_id(trainer_id)
            o: Trainer = self._get_another_trainer(trainer_id)

            tpk, opk = t.selected_pokemon, o.selected_pokemon

            bm: BattleMove = self.calculate_damage(move, t, o)
            text: str = "\n".join([f"{move['name']} dealt {bm.damage} damage!"] + bm.messages)

            # opk.hp -= bm.damage

            if bm.success:
                opk.hp -= bm.damage
                tpk.hp += bm.healing

                tpk.hp = int(round(tpk.hp))
                opk.hp = int(round(opk.hp))

                tpk.hp = min(tpk.hp, tpk.max_hp)

                if bm.healing > 0:
                    text += f"\n{tpk} restored {bm.healing} HP."
                elif bm.healing < 0:
                    text += f"\n{tpk} took {bm.damage} damage."

                if bm.ailment:
                    text += f"\nIt imposed {bm.ailment}!"
                    o.ailments.add(bm.ailment)

                for change in bm.stat_changes:
                    if move["target_id"] == 7:
                        target = tpk
                        if change.change < 0:
                            text += f"\n{target}'s {constants.STAT_NAMES[change.stat]} decreased by {-change.change}!"
                        else:
                            text += f"\n{target}'s {constants.STAT_NAMES[change.stat]} increased by {change.change}!"

                    else:
                        target = opk
                        if change.change < 0:
                            text += f"\n{target}'s {constants.STAT_NAMES[change.stat]} decreased by {-change.change}!"
                        else:
                            text += f"\n{target}'s {constants.STAT_NAMES[change.stat]} increased by {change.change}!"

                    setattr(
                        target.stages,
                        change.stat,
                        getattr(target.stages, change.stat) + change.change,
                    )

            else:
                text = "It missed!"

            opk.hp = max(opk.hp, 0)

            if opk.owner_id == self.bot.user.id:
                r: Optional[models.Raids] = await models.Raids.filter(pkmodel=opk.id).first()
                if r is not None:
                    r.pokemon_hp = opk.hp

                    if isinstance(r.damage_data, dict):
                        damage_data: dict = r.damage_data
                    else:
                        damage_data: dict = json.loads(r.damage_data)

                    damage_data[str(t.user.id)] += bm.damage

                    r.damage_data = json.dumps(damage_data)

                    await r.save()

            ext_fields = {}
            self.move_emb.add_field(
                name=f"{t.selected_pokemon} used {move['name']}:",
                value=text,
                inline=False,
            )

            if 8 <= self.category.value <= 12:
                self.move_emb.set_thumbnail(
                    url=f"https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/{tpk.species_id}.png"
                )
                self.move_emb.set_image(
                    url=f"https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/back/{opk.species_id}.png"
                )

            t.damage_delt += bm.damage

            if opk.hp == 0:
                text = f"{o}'s {opk} has fainted!"

                if self.reward == Reward.Basic:
                    xp = sum(
                        tpk.specie["base_stats"][idx]
                        for idx, _ in enumerate(["hp", "atk", "defn", "satk", "sdef", "spd"])
                    )

                    xp = awarded_xp = round(xp * opk.level / tpk.level)

                    update: dict = dict()
                    if tpk.held_item != 13001 and tpk.level < 100:
                        level = 0
                        while xp > 0:
                            if (tpk.xp + xp) > tpk.max_xp:
                                level += 1
                                tpk.xp += xp
                                xp = tpk.xp - tpk.max_xp
                                tpk.xp = 0
                            else:
                                tpk.xp += xp
                                xp = 0

                        if level + tpk.level > 100:
                            level = 100 - tpk.level

                        update["xp"] = tpk.xp

                        if level > 0:
                            update["level"] = level
                            ext_fields["⬆️ Level up!"] = f"{t}'s {tpk} is now level {tpk.level + level}!"
                            tpk.level += level

                        text = f"{t} was awarded with `{awarded_xp:,}XP` and `100` credits for winning!"

                    else:
                        text = f"{t} was awarded with `100` credits for winning!"

                    self.move_emb.add_field(name=f"🎉 {t} Wins!", value=text, inline=False)

                    tpk.level += update.get("update", 0)

                    with suppress(KeyError):
                        tpk.xp += update.__getitem__("xp")

                    if t.is_bot is False:
                        m: models.Member = await self.bot.manager.fetch_member_info(t.user.id)
                        m.balance += 100
                        await m.save()

                        await tpk.save()

                elif self.reward.value in (8, 9) and self.category != BattleCategory.Gym:
                    text: str = f"You won the battle against Wild {self.bot.sprites.get(opk.species_id)} {opk}!"
                    xp = sum(
                        tpk.specie["base_stats"][idx]
                        for idx, _ in enumerate(["hp", "atk", "defn", "satk", "sdef", "spd"])
                    )

                    if self.reward == Reward.Journey:
                        _bal: int = 50
                    elif self.reward == Reward.JourneyTrainer:
                        _bal: int = 100

                    xp = awarded_xp = round(xp * opk.level / tpk.level)

                    update: dict = dict()
                    if tpk.held_item != 13001 and tpk.level < 100:
                        level = 0
                        while xp > 0:
                            if (tpk.xp + xp) > tpk.max_xp:
                                level += 1
                                tpk.xp += xp
                                xp = tpk.xp - tpk.max_xp
                                tpk.xp = 0
                            else:
                                tpk.xp += xp
                                xp = 0

                        if level + tpk.level > 100:
                            level = 100 - tpk.level

                        update["xp"] = tpk.xp

                        if level > 0:
                            update["level"] = level
                            ext_fields[
                                "⬆️ Level up!"
                            ] = f"{self.bot.sprites.get(tpk.specie['dex_number'])} {tpk} gained `{awarded_xp:,}XP` grew to Level {tpk.level + level}!"
                            tpk.level += level
                        else:
                            text = f"{self.bot.sprites.get(tpk.specie['dex_number'])} {tpk} gained `{awarded_xp:,}XP` and `{_bal}` JC for winning!"

                    else:
                        text = f"You are awarded with `{_bal}` JC for winning!"

                    self.move_emb.add_field(name=f"Wild {opk} fainted!", value=text, inline=False)
                    self.move_emb.image = None
                    self.move_emb.set_image(url=None)

                    tpk.level += update.get("update", 0)

                    with suppress(KeyError):
                        tpk.xp += update.__getitem__("xp")

                    if t.is_bot is False:
                        _m: models.JourneyMember = await models.JourneyMember.get(id=t.user.id)
                        _m.journey_coins += _bal
                        await m.save()

                        await tpk.save()

                elif self.reward == Reward.Journey and self.category == BattleCategory.Gym:
                    if t.is_bot:
                        self.move_emb.add_field(
                            name=f"Your {opk} fainted!",
                            value=f"You lost the battle! Better luck next time.",
                            inline=False,
                        )

                    else:
                        journey_mem: models.JourneyMember = await models.JourneyMember.get(t.user.id)
                        _elite_four = constants.ELITE_FOUR_DATA[constants.ELITE_ROUTES[journey_mem.routes_unlocked]]
                        text: str = f"You won the battle against Elite Four member {constants.ELITE_ROUTES[journey_mem.routes_unlocked]}!"
                        xp = sum(
                            tpk.specie["base_stats"][idx]
                            for idx, _ in enumerate(["hp", "atk", "defn", "satk", "sdef", "spd"])
                        )

                        xp = awarded_xp = round(xp * opk.level / tpk.level)

                        update: dict = dict()
                        if tpk.held_item != 13001 and tpk.level < 100:
                            level = 0
                            while xp > 0:
                                if (tpk.xp + xp) > tpk.max_xp:
                                    level += 1
                                    tpk.xp += xp
                                    xp = tpk.xp - tpk.max_xp
                                    tpk.xp = 0
                                else:
                                    tpk.xp += xp
                                    xp = 0

                            if level + tpk.level > 100:
                                level = 100 - tpk.level

                            update["xp"] = tpk.xp

                            if level > 0:
                                update["level"] = level
                                ext_fields[
                                    "⬆️ Level up!"
                                ] = f"{self.bot.sprites.get(tpk.specie['dex_number'])} {tpk} gained `{awarded_xp:,}XP` grew to Level {tpk.level + level}!"
                                tpk.level += level
                            else:
                                text = f"{self.bot.sprites.get(tpk.specie['dex_number'])} {tpk} gained `{awarded_xp:,}XP` and *{_elite_four['reward']} shards* for winning!\n*🔓 New routes unlocked!"

                        else:
                            text = f"You are awarded with *{_elite_four['reward']} shards* for winning!\n*🔓 New routes unlocked!*"

                        text += f"\n\n{_elite_four['defeat_text']}"
                        self.move_emb.add_field(name=f"Wild {opk} fainted!", value=text, inline=False)
                        self.move_emb.image = None
                        self.move_emb.set_image(url=None)

                        tpk.level += update.get("update", 0)

                        with suppress(KeyError):
                            tpk.xp += update.__getitem__("xp")

                        m: models.Member = await self.bot.manager.fetch_member_info(t.user.id)
                        m.shards += int(_elite_four["reward"])

                        journey_mem.routes_unlocked += 3
                        await journey_mem.save()

                        await m.save()
                        await tpk.save()

                elif self.reward == Reward.Pokemon:
                    if t.is_bot is False:
                        opk.owner_id = t.user.id
                        _idx: int = await self.bot.manager.get_next_idx(t.user.id)

                        opk.idx = _idx
                        await self.bot.manager.update_idx(t.user.id)
                        await opk.save()

                        self.move_emb.add_field(
                            name=f"🎉 {t} Wins!",
                            value=f"{t} is awarded with {self.bot.sprites.get(opk.specie['dex_number'], opk.shiny)} **{opk:l}** for winning!"
                            + f"\n\n{'✨ Oh! The color on this one seems odd...' if opk.shiny else ''}",
                            inline=False,
                        )

                    else:
                        self.move_emb.add_field(
                            name=f"🎉 {t} Wins!",
                            value=f"Wild {self.bot.sprites.get(tpk.specie['dex_number'])} {tpk} got away...",
                        )

                elif self.reward == Reward.Christmas:
                    if t.is_bot is False:
                        mem: models.Member = await self.bot.manager.fetch_member_info(t.user.id)

                        mem.shards += 50
                        await mem.save()

                        self.move_emb.add_field(
                            name=f"You defeated santa!",
                            value=f"You received 💎 *50 Shards*!",
                        )

                    else:
                        mem: models.Member = await self.bot.manager.fetch_member_info(o.user.id)

                        mem.shards += 1
                        await mem.save()

                        self.move_emb.add_field(
                            name=f"You were defeated by santa!",
                            value="Hohoho! It was a nice Match 🎅 here is 💎 *1 Shards*!",
                        )

                elif self.reward == Reward.TeamRocket:
                    if t.is_bot is False:
                        self.move_emb.add_field(
                            name="You defeated Team Rocket!",
                            value=f"A {self.bot.sprites.get(150)} **Armoured Mewtwo** has been added to your account!",
                        )

                    else:
                        self.move_emb.add_field(
                            name=f"You were defeated by Team Rocket!",
                            value=f"Better luck next time...",
                        )

                elif self.reward == Reward.Raids:
                    if t.is_bot is False:
                        t.damage_delt += bm.damage

                        self.move_emb.add_field(
                            name="You defeated Raid Boss!",
                            value=f"You will recieve your rewards in few time... *Damn you are strong!*",
                        )

                    else:
                        self.move_emb.add_field(
                            name=f"You were defeated by the Raid Boss!",
                            value=f"Damage you delt: `{o.damage_delt}`",
                        )

                elif self.reward == Reward.Gym:
                    gym: models.Gym = await models.Gym.get(guild_id=self.ctx.guild.id)
                    if t.is_bot is True:
                        _defeats = gym.defeats
                        _defeats.append(o.user.id)  # Not using array append here to save from stuffs

                        gym.defeats = _defeats

                        gym_leader: discord.User = self.bot.get_user(gym.gym_leader) or await self.bot.fetch_user(
                            gym.gym_leader
                        )
                        _pk: models.Pokemon = await models.Pokemon.get(owner_id=gym_leader.id, idx=gym.gym_pokemon)

                        msg: str = f"Your {self.bot.sprites.get(_pk.specie['dex_number'])} **{_pk}**  has returned from the gym after a long battle"

                        if gym.collected_shards < 100:
                            msg += " with 💎 *10 shards*."
                            gym.salary_collect_time = datetime.utcnow()

                            mem: models.Member = await self.bot.manager.fetch_member_info(gym.gym_leader)
                            mem.shards += 10
                            gym.collected_shards += 10
                            await mem.save()

                        with suppress(Exception):
                            await gym_leader.send(
                                embed=self.bot.Embed(title=f"Battle Won!", description=msg).set_author(
                                    name=self.ctx.guild.name,
                                    icon_url=self.ctx.guild.icon.url,
                                )
                            )

                        if gym.defeats.__len__() >= 10:
                            gym.gym_leader = None
                            gym.defeats = []
                            await gym.save()

                            self.move_emb.add_field(
                                name=f"You were defeated by gym leader!",
                                value=f"Gym is now vacant! You can join gym by using `{self.ctx.prefix}gym join` command.",
                            )
                        else:
                            await gym.save()
                            self.move_emb.add_field(
                                name=f"You were defeated by gym leader!",
                                value=f"You can challange the gym leader again when it a new one is available.",
                            )

                    else:
                        gym.gym_leader = t.user.id
                        m: models.Member = await self.bot.manager.fetch_member_info(t.user.id)
                        pk: models.Pokemon = await self.bot.manager.fetch_selected_pokemon(t.user.id)

                        if pk.specie in list(
                            data.list_gmax + data.list_legendary + data.list_mythical + data.list_ub
                        ) or pk.specie["names"]["9"].lower().startswith("gmax "):
                            txt: str = f"You can now claim to be gym leader by using `{self.ctx.prefix}gym join` command."
                            gym.gym_pokemon = None
                            gym.defeats = []

                            await gym.save()

                        else:
                            gym.gym_pokemon = m.selected_id
                            gym.defeats = []

                            await gym.save()

                            txt: str = f"You are the new gym leader. You can leave the leader post by `{self.ctx.prefix}gym flee` command."

                        self.move_emb.add_field(name=f"You defeated gym leader!", value=txt)

                        # with suppress(discord.Forbidden, discord.HTTPException):
                        #     await o.user.send(
                        #         f"You were defeated in gym battle and you are no longer the leader of {self.ctx.guild.name} Gym!"
                        #     )

                self.battle_ended = True
                self.bot.dispatch("battle_finish", self, t, self.move_emb)

                # Stopping the view is necessary
                self.battle_view.stop()

            for name, value in ext_fields.items():
                self.move_emb.add_field(name=name, value=value)

                # return await self.ctx.send(embed=self.move_emb)

    async def send_move_result(self):
        self.used.clear()
        await self.ctx.send(embed=self.move_emb)
        self.move_emb = self.bot.Embed()

        if self.battle_ended is False:
            await self.send_battle()

        if self.battle_ended is True:
            self.bot.battles.remove(self)

    async def run_battle(self):
        await self.send_battle()


async def get_ai_duel(
    ctx: commands.Context,
    sp,
    pk1: models.Pokemon,
    reward: Reward = Reward.Basic,
    category: BattleCategory = BattleCategory.Normal,
    shiny: bool = False,
) -> Battle:
    pk2: models.Pokemon = models.Pokemon.get_random(
        owner_id=None,
        species_id=sp["species_id"],
        level=random.randint(15, 70),
        idx=1,
        xp=0,
        shiny=shiny,
    )

    moves: list = data.get_pokemon_moves(pk2.species_id)
    move_ids: list = [m["move_id"] for m in moves]

    pk2.moves = move_ids[:4]
    trainer1: Trainer = Trainer(ctx.author, [pk1], 0, pk1, False)
    trainer2: Trainer = Trainer(ctx.bot.user, [pk2], 0, pk2, True)

    msg: discord.Message = await ctx.reply("Battle is being loaded...", mention_author=False)

    battle: Battle = Battle(
        ctx.bot,
        ctx,
        [trainer1, trainer2],
        BattleType.oneVone,
        BattleEngine.AI,
        reward,
        category,
    )

    return battle
