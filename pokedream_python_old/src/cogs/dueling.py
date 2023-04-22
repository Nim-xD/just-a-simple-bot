from __future__ import annotations
from contextlib import suppress
from functools import lru_cache
import random
from models.models import Pokemon
import typing

if typing.TYPE_CHECKING:
    from core.bot import PokeBest

from discord.ext import commands, tasks
import discord
from utils.checks import has_started
from utils.converters import MoveConverter, PokemonConverter, SpeciesConverter
from utils.constants import TYPES, DAMAGE_CLASSES, TYPE_EFFICACY
from utils.emojis import emojis
from data import data
from core.paginator import SimplePaginator
import math
import models
from utils.exceptions import NoSelectedPokemon, PokeBestError
from core.views import MoveLearnView, Confirm
from cogs.helpers.battles import Battle, Trainer, BattleEngine, BattleType
from models.helpers import ArrayAppend
import datetime
import pickle


def is_in_battle():
    async def predicate(ctx: commands.Context) -> bool:
        duel_cog = ctx.bot.get_cog("Dueling")
        return duel_cog.get_battle(ctx.author.id) is not None

    return commands.check(predicate)


def move_not_used():
    async def predicate(ctx: commands.Context) -> bool:
        _in_battle: bool = await is_in_battle.predicate(ctx)
        if not _in_battle:
            raise PokeBestError(
                "Hey, it looks like you are not in any battle. To start dueling/battling use `{ctx.prefix}duel <trainer>` command to duel with any trainer. There are a lot of dueling modes which you can see in help menu."
            )

        dueling = ctx.bot.get_cog("Dueling")
        battle: Battle = dueling.get_battle(ctx.author.id)

        return ctx.author.id not in battle.used

    return commands.check(predicate)


def _create_moves_chunks(bot: PokeBest, moves: list, pokemon: SpeciesConverter):
    pages: typing.List[discord.Embed] = []

    def get_page(pidx: int):
        embed: discord.Embed = bot.Embed(title=f"#{pokemon['dex_number']} - {pokemon['names']['9']}")

        pgstart: int = pidx * 15
        pgend: int = max(min(pgstart + 15, moves.__len__()), 0)
        txt: str = "```\n"

        embed.description = "**Note:** Moves shown with a `🚫` symbol do not currently function in duels, and will be replaced by Tackle.\n\n"

        max_chars: int = max(len(data.move_by_id(_m["move_id"])["name"]) + 1 for _m in moves)

        if pgstart != pgend:
            for _move in moves[pgstart:pgend]:
                move: dict = data.move_by_id(_move["move_id"])

                name: str = move["name"]
                name += (max_chars - len(name)) * " "

                level_lnth: int = len(str(_move["level"]))
                level: str = f"{' ' * (3 - level_lnth)}{_move['level']}"

                if move["power"] != None:
                    txt += f"{name} | Level: {level} | \n"
                else:
                    txt += f"{name} | Level: {level} | 🚫\n"

        else:
            for _move in [moves[pgstart]]:
                move: dict = data.move_by_id(_move["move_id"])
                name: str = move["name"]
                name += (max_chars - len(name)) * " "

                level_lnth: int = len(str(_move["level"]))
                level: str = f"{' ' * (3 - level_lnth)}{_move['level']}"

                if move["power"] is None:
                    txt += f"{name} | Level: {level} | \n"
                else:
                    txt += f"{name} | Level: {level} | 🚫\n"

        txt += "```"
        embed.description += txt

        return embed.set_footer(text=f"Showing {pgstart+1}-{pgend} of {moves.__len__()} moves.")

    total_pages: int = math.ceil(moves.__len__() / 15)

    for i in range(total_pages):
        page = get_page(i)
        pages.append(page)

    return pages


class Dueling(commands.Cog):
    def __init__(self, bot: PokeBest) -> None:
        self.bot: PokeBest = bot

        self.check_unmodified_battles.start()

    def get_battle(self, user_id: int) -> typing.Optional[Battle]:
        for battle in self.bot.battles:
            if user_id in [t.user.id for t in battle.trainers]:
                return battle

        return None

    @commands.command(aliases=("mi",))
    @has_started()
    async def moveinfo(self, ctx: commands.Context, *, move: MoveConverter):
        """Get information about a move"""
        if move is None:
            return await ctx.reply("There is no move like that.", mention_author=False)

        embed: discord.Embed = self.bot.Embed(title=f"{move['name']}")

        move_info: typing.Iterable[str] = (
            f"**Power**: {move['power']}",
            f"**Accuracy**: {move['accuracy']}",
            f"**PP**: {move['pp']}",
            f"**Priority**: {move['priority']}",
            f"**Type**: {getattr(emojis, str(TYPES[move['type_id']]).lower())}",
            f"**Category**: {DAMAGE_CLASSES[move['damage_class_id']]}",
        )

        embed.description = "\n".join(move_info)

        await ctx.reply(embed=embed, mention_author=False)

    @commands.command()
    @has_started()
    async def moves(self, ctx: commands.Context, *, pokemon: SpeciesConverter = None):
        """Displays all moves that pokemon can learn"""
        if pokemon is not None:
            embed: discord.Embed = self.bot.Embed(title=f"#{pokemon['dex_number']} - {pokemon['names']['9']}")

            with ctx.typing():
                _pokemon_moves: list = data.get_pokemon_moves(pokemon["species_id"])
                if len(_pokemon_moves) == 0:
                    _pokemon_moves: list = data.get_pokemon_moves(pokemon["dex_number"])

                available_moves: typing.Iterable = list()
                for mv in _pokemon_moves:
                    if mv["move_method_id"] == 1 and mv not in available_moves:
                        available_moves.append(mv)

                available_moves = sorted(available_moves, key=lambda m: m["level"])

                chunks: typing.List[discord.Embed] = _create_moves_chunks(self.bot, available_moves, pokemon)

            if chunks is None:
                return await ctx.reply("There are no moves matching the search!", mention_author=False)

            if len(chunks) > 1:
                paginator: SimplePaginator = SimplePaginator(ctx, chunks)
                await paginator.paginate(ctx)
            else:
                await ctx.send(embed=chunks.__getitem__(0))

        else:
            pokemon: models.Pokemon = await self.bot.manager.fetch_selected_pokemon(ctx.author.id)
            member: models.Member = await self.bot.manager.fetch_member_info(ctx.author.id)

            available_moves: typing.Iterable = list()
            _pokemon_moves: list = data.get_pokemon_moves(pokemon.species_id)
            if len(_pokemon_moves) == 0:
                _pokemon_moves: list = data.get_pokemon_moves(pokemon.specie["dex_number"])

            available_tms: list = []

            for mv in _pokemon_moves:
                if mv in available_moves:
                    continue

                if mv["move_method_id"] == 1 and mv["level"] <= pokemon.level:
                    available_moves.append(mv)

                if mv["move_method_id"] == 4:
                    if mv in available_tms:
                        continue

                    machine: typing.List[dict] = data.get_move_machines(mv["move_id"])
                    for m in machine:
                        if m in member.technical_machines:
                            available_tms.append(mv)

            if available_tms.__len__() == 0:
                available_tms = ["None"]

            pk_moves: list = []
            for mv in pokemon.moves:
                move: dict = data.move_by_id(mv)
                pk_moves.append(move["name"])

            while pk_moves.__len__() < 4:
                pk_moves.append("Tackle")

            embed: discord.Embed = self.bot.Embed(
                title=f"{pokemon:l} Moves:",
                description=f"To learn a move, use the `{ctx.prefix}learn <move>` command.",
            )

            current_moves: list = []
            for idx, move in enumerate(pk_moves, start=1):
                # current_moves.append(f"`{idx}` | {move}")
                current_moves.append(f"[{idx}] | {move}")

            _crtxt: str = "```\n"
            _crtxt += "\n".join(current_moves)
            _crtxt += "```"

            # embed.add_field(name=f"Current Moves", value="\n".join(current_moves), inline=True)
            embed.add_field(name="Current Moves", value=_crtxt, inline=True)

            avail_moves: list = []
            for mv in available_moves:
                move: dict = data.move_by_id(mv.__getitem__("move_id"))
                # if move["power"] is None:
                #     if f'{move["name"]} 🚫' in avail_moves:
                #         continue
                #     avail_moves.append(f"{move['name']} 🚫")

                if move["name"] in avail_moves:
                    continue
                else:
                    avail_moves.append(move["name"])
            # embed.add_field(name=f"Available Moves:", value="\n".join(avail_moves), inline=True)
            _mvtxt: str = "```\n"
            _mvtxt += "\n".join(avail_moves)
            _mvtxt += "```"

            embed.add_field(name="Available Moves:", value=_mvtxt)

            avail_tms: list = []
            if available_tms[0] != "None":
                for _tm in available_tms:
                    move: dict = data.move_by_id(_tm["move_id"])
                    # if move["power"] is None:
                    #     avail_moves.append(f"{move['name']} 🚫")

                    # else:
                    #     avail_moves.append(move["name"])
                    avail_moves.append(move["name"])

            if avail_tms.__len__() == 0:
                avail_tms.append("None")

            _tmtxt: str = "```\n"
            _tmtxt += "\n".join(avail_tms)
            _tmtxt += "```"

            # embed.add_field(name="TM Moves:", value="\n".join(avail_tms), inline=True)
            embed.add_field(name="TM Moves:", value=_tmtxt, inline=True)

            embed.set_footer(
                text="Note: Moves shown with a `🚫` symbol do not currently function in duels, and will be replaced by Tackle."
            )

            await ctx.reply(embed=embed, mention_author=False)

    @commands.command()
    @has_started()
    async def learn(self, ctx: commands.Context, *, move: MoveConverter):
        """Make your pokemon learn a move"""
        if move is None:
            return await ctx.reply("That move doesn't exists.", mention_author=False)

        with ctx.typing():
            pokemon: models.Pokemon = await PokemonConverter().convert(ctx, "")
            if pokemon is None:
                raise NoSelectedPokemon(ctx)

            member: models.Member = await self.bot.manager.fetch_member_info(ctx.author.id)

            can_learn: bool = False

            pmoves: typing.List[dict] = []
            pmove: typing.Optional[dict] = None

            pokemon_moves: list = data.get_pokemon_moves(pokemon.species_id)
            if len(pokemon_moves) == 0:
                pokemon_moves: list = data.get_pokemon_moves(pokemon.specie["dex_number"])

            for mv in pokemon_moves:
                if mv["move_id"] == move["id"]:
                    pmoves.append(mv)

            if len(pmoves) != 0:
                for pmove in pmoves:
                    if pmove["move_method_id"] == 4:
                        _move_machines: typing.List[dict] = data.get_move_machines(pmove["move_id"])
                        for mch in _move_machines:
                            if mch["machine_number"] in member.technical_machines:
                                can_learn = True

                    elif pmove["move_method_id"] == 1:
                        if pmove["level"] <= pokemon.level:
                            can_learn = True
                            break

            if not can_learn:
                raise PokeBestError(
                    f"You cannot learn this move at this moment as your pokemon doesn't meets the requirements for it or this move doesn't exists. To see the list of moves your pokemon can learn, use `{ctx.prefix}moves` command."
                )

            replace_with: typing.Optional[int] = None

            moves: typing.List[dict] = []
            for mv in pokemon.moves:
                moves.append(data.move_by_id(mv))

        if moves and len(moves) >= 4:
            embed: discord.Embed = self.bot.Embed(title=f"{pokemon} Moves:")
            embed.description = f"Select the move you want to replace with `{move['name']}`.\n\n"

            # for idx, _move in enumerate(moves, start=1):
            #     embed.description += f"[`{idx}`] | {_move['name']}\n"

            _move_names: typing.List[str] = []
            for mv in moves:
                _move_names.append(mv["name"])

            _view: MoveLearnView = MoveLearnView(ctx, _move_names)
            msg: discord.Message = await ctx.send(embed=embed, view=_view)

            await _view.wait()

            replace_with = _view.value

            if replace_with is None:
                return await msg.edit(content="Time's up!", embed=None, view=None, allowed_mentions=None)

            omove = moves[replace_with - 1]
            moves[replace_with - 1] = move

            await self.bot.manager.update_pokemon_moves(pokemon, moves)

        return await ctx.reply(
            f"Successfully replaced `{omove['name']}` with `{move['name']}`!",
            mention_author=False,
        )

    @commands.group(invoke_without_command=True)
    @has_started()
    async def duel(self, ctx: commands.Context, trainer: discord.Member):
        """Duel with another trainer"""
        if self.get_battle(trainer.id) is not None:
            return await ctx.reply(
                "The trainer you are trying to battle with is already in another battle!",
                mention_author=False,
            )

        if self.get_battle(ctx.author.id) is not None:
            return await ctx.reply("Sorry, you are already in a battle!", mention_author=False)

        _view: Confirm = Confirm(ctx, author=trainer.id)
        msg: discord.Message = await ctx.reply(
            f"{trainer.mention}! {ctx.author.name} invited you for a duel!",
            view=_view,
            mention_author=False,
        )

        await _view.wait()

        if _view.value is None:
            return await msg.edit(content="Time's up!", view=None, allowed_mentions=None)

        if _view.value is False:
            return await msg.edit(content="Duel request declined!", view=None, allowed_mentions=None)

        if self.get_battle(trainer.id) is not None:
            return await ctx.reply(
                "The trainer you are trying to battle with is already in another battle!",
                mention_author=False,
            )

        pk1: models.Pokemon = await self.bot.manager.fetch_selected_pokemon(ctx.author.id)
        if pk1 is None:
            return await ctx.reply(f"{ctx.author.mention}, please select a pokemon!", mention_author=False)

        pk2: models.Pokemon = await self.bot.manager.fetch_selected_pokemon(trainer.id)
        if pk2 is None:
            return await ctx.reply(f"{trainer.mention}, please select a pokemon!", mention_author=False)

        trainer1: Trainer = Trainer(ctx.author, [pk1], 0, pk1, False)
        trainer2: Trainer = Trainer(trainer, [pk2], 0, pk2, False)

        await msg.edit(f"Battle is being loaded...", allowed_mentions=None, view=None)

        with ctx.typing():
            battle: Battle = Battle(
                self.bot,
                ctx,
                [trainer1, trainer2],
                BattleType.oneVone,
                BattleEngine.Human,
            )
            self.bot.battles.append(battle)

            await battle.send_battle()
            await msg.delete()

    @duel.command(name="cancel")
    async def duel_cancel(self, ctx: commands.Context):
        """Flee from your current duel"""
        battle: Battle = self.get_battle(ctx.author.id)
        if battle is None:
            return await ctx.reply("You are not in a battle!", mention_author=False)

        for b in self.bot.battles:
            if b.trainers[0].user.id == ctx.author.id or b.trainers[1].user.id == ctx.author.id:
                if b.reward.value == 7:
                    gym: models.Gym = await models.Gym.get(guild_id=b.ctx.guild.id)

                    gym.defeats = ArrayAppend("defeats", ctx.author.id)
                    await gym.save()

                self.bot.battles.remove(b)

        await ctx.reply("You have successfully fled from your battle!", mention_author=False)

    @duel.command(name="use")
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def duel_use(self, ctx: commands.Context, idx: int):
        """Use a move in duel"""
        battle: Battle = self.get_battle(ctx.author.id)
        if battle is None:
            return await ctx.reply("You are not in a battle!", mention_author=False)

        if 1 > idx > 4:
            return await ctx.reply("Invalid move index!", mention_author=False)

        if battle.used.__len__() != 2:
            battle.used.add(ctx.author.id)
            battle.last_modified = datetime.datetime.utcnow()
            await battle.run_move(
                battle._get_trainer_by_id(ctx.author.id).get_moves[idx - 1],
                ctx.author.id,
            )

            if battle.battle_engine.value == 1 and battle.used.__len__() < 2 and battle.bot.user not in battle.used:
                o = battle._get_another_trainer(ctx.author.id)

                await battle.run_move(random.choice(o.get_moves), battle.bot.user.id)
                battle.used.add(battle.bot.user.id)

                await battle.send_move_result()

            if battle.used.__len__() == 2:
                await battle.send_move_result()

    @commands.command()
    async def duelai(self, ctx: commands.Context):
        """Duel with our battling AI"""
        if self.get_battle(ctx.author.id) is not None:
            return await ctx.reply("Sorry, you are already in a battle!", mention_author=False)

        pk1: models.Pokemon = await self.bot.manager.fetch_selected_pokemon(ctx.author.id)
        if pk1 is None:
            return await ctx.reply(f"{ctx.author.mention}, please select a pokemon!", mention_author=False)

        pk2sp = random.choice(data.pokemon_data[:898])
        pk2: models.Pokemon = models.Pokemon.get_random(
            owner_id=None,
            species_id=pk2sp["species_id"],
            level=random.randint(15, 70),
            idx=1,
            xp=0,
        )

        moves: list = data.get_pokemon_moves(pk2.species_id)
        if len(moves) == 0:
            moves: list = data.get_pokemon_moves(pk2.specie["dex_number"])

        move_ids: list = [m["move_id"] for m in moves]

        pk2.moves = move_ids[:4]
        trainer1: Trainer = Trainer(ctx.author, [pk1], 0, pk1, False)
        trainer2: Trainer = Trainer(self.bot.user, [pk2], 0, pk2, True)

        msg: discord.Message = await ctx.reply("Battle is being loaded...", mention_author=False)

        with ctx.typing():
            battle: Battle = Battle(self.bot, ctx, [trainer1, trainer2], BattleType.oneVone, BattleEngine.AI)
            self.bot.battles.append(battle)

            await battle.send_battle()
            await msg.delete()

    async def get_weakness(self, ctx: commands.Context, specie: str) -> discord.Embed:
        sp = await SpeciesConverter().convert(ctx, specie)

        weak: set = set()
        normal: set = set()
        ressist: set = set()
        immune: set = set()

        sp_types = [TYPES[i] for i in sp["types"]]

        for idx, typ_name in enumerate(TYPES[1:-2], start=1):
            x: int = 1
            for typ in sp["types"]:
                x *= TYPE_EFFICACY[idx][typ]

            if x > 1:
                weak.add(typ_name)

            elif x == 1:
                normal.add(typ_name)

            elif x == 0:
                immune.add(typ_name)

            else:
                ressist.add(typ_name)

        embed = self.bot.Embed(title=f"#{sp['species_id']} - {sp['names']['9']} (" + "/".join(sp_types) + ")")

        embed.set_thumbnail(url=sp["sprites"].__getitem__("normal"))
        l = locals()

        attrs: typing.Iterable[str] = ("weak", "normal", "ressist", "immune")

        for attr in attrs:
            val = l[attr]
            if val:
                embed.add_field(
                    name=attr.capitalize(),
                    value=", ".join(_type if _type not in sp_types else f"**{_type}**" for _type in val),
                    inline=False,
                )

        return embed

    @commands.command(name="weak")
    @has_started()
    async def weak(self, ctx: commands.Context, *, specie: str):
        """See the weakness of a pokemon"""
        emb: discord.Embed = await self.get_weakness(ctx, specie)
        await ctx.reply(embed=emb, mention_author=False)

    @tasks.loop(seconds=5)
    async def check_unmodified_battles(self):
        for battle in self.bot.battles:
            if (datetime.datetime.utcnow() - battle.last_modified).seconds > 120:
                with suppress(Exception):
                    await battle.ctx.send("Battle timed out! Failed to use move.")
                self.bot.battles.remove(battle)

    @check_unmodified_battles.before_loop
    async def before_check_unmodified_battles(self):
        await self.bot.wait_until_ready()


def setup(bot: PokeBest) -> None:
    bot.add_cog(Dueling(bot))
