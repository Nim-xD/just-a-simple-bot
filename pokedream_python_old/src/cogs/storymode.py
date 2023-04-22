from __future__ import annotations
import typing

if typing.TYPE_CHECKING:
    from core.bot import PokeBest

from discord.ext import commands
from utils.converters import SpeciesConverter, MoveConverter
from utils.constants import JOURNEY_STARTERS, BattleCategory, ROUTE_TRAINERS
from utils.exceptions import PokeBestError
from data import data
import discord
import models
from io import BytesIO
from utils import constants
from utils.checks import has_started_journey
from core.views import MoveLearnView
from cogs.helpers.battles import Trainer, Battle, BattleEngine, BattleType, Reward
import random

# TODO: I guess this cog needs more refactoring


class Journey(commands.Cog):
    def __init__(self, bot: PokeBest) -> None:
        self.bot: PokeBest = bot

        self.route_battles: typing.Dict[int, BattleCategory] = {
            1: BattleCategory.JourneyGrass,
            2: BattleCategory.JourneyGrass,
            3: BattleCategory.JourneyGrass,
            4: BattleCategory.JourneyCave,
            5: BattleCategory.JourneyCave,
            6: BattleCategory.JourneyCave,
            7: BattleCategory.JourneyDesert,
            8: BattleCategory.JourneyDesert,
            9: BattleCategory.JourneyDesert,
            10: BattleCategory.JourneyBadLand,
            11: BattleCategory.JourneyBadLand,
            12: BattleCategory.JourneyBadLand,
            13: BattleCategory.JourneyWild,
            14: BattleCategory.JourneyWild,
            15: BattleCategory.JourneyWild,
        }

        self.route_images: typing.Dict[int, str] = {
            1: "https://cdn.discordapp.com/attachments/890889580021157918/938155571155177523/viridianforest.png",
            2: "https://cdn.discordapp.com/attachments/890889580021157918/938155571155177523/viridianforest.png",
            3: "https://cdn.discordapp.com/attachments/890889580021157918/938155571155177523/viridianforest.png",
            4: "https://cdn.discordapp.com/attachments/890889580021157918/938155843013206046/mtmoon.png",
            5: "https://cdn.discordapp.com/attachments/890889580021157918/938155843013206046/mtmoon.png",
            6: "https://cdn.discordapp.com/attachments/890889580021157918/938155843013206046/mtmoon.png",
            7: "https://cdn.discordapp.com/attachments/890889580021157918/938155990963060736/mtember.png",
            8: "https://cdn.discordapp.com/attachments/890889580021157918/938155990963060736/mtember.png",
            9: "https://cdn.discordapp.com/attachments/890889580021157918/938155990963060736/mtember.png",
            10: "https://media.discordapp.net/attachments/890889580021157918/938157382687678464/powerplant-1.png",
            11: "https://media.discordapp.net/attachments/890889580021157918/938157382687678464/powerplant-1.png",
            12: "https://media.discordapp.net/attachments/890889580021157918/938157382687678464/powerplant-1.png",
            13: "https://media.discordapp.net/attachments/890889580021157918/938157599239593984/safari.png",
            14: "https://media.discordapp.net/attachments/890889580021157918/938157599239593984/safari.png",
            15: "https://media.discordapp.net/attachments/890889580021157918/938157599239593984/safari.png",
        }

    @commands.group(invoke_without_command=True)
    async def journey(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            return await ctx.send_help(ctx.command)

    @journey.command(name="start")
    async def journey_start(self, ctx: commands.Context):
        """Start your PokeBest Journeys storymode"""
        m: models.JourneyMember = await models.JourneyMember.get_or_none(id=ctx.author.id)

        if m is not None:
            return await ctx.reply("You already started your PokeBest Journey.", mention_author=False)

        emb: discord.Embed = self.bot.Embed(title="PokeBest Journeys")
        emb.description = (
            f"Hello {ctx.author.mention}! Welcome to PokeBest Journeys. I'm here to help you get started with your journey. Given below are the basic instructions and some commands to get you started.\n\n"
            + f"> First, you have to pick your starter buddy Pokémon. Below are the three starters given from which you can choose:\n"
            + f"> {self.bot.sprites.get(722)} **Rowlet** | {self.bot.sprites.get(501)} **Oshawott** | {self.bot.sprites.get(155)} **Cyndaquil**\n"
            + f"> Once you made your choice, do `{ctx.prefix}journey pick <pokemon>` to pick your buddy and get started with your PokeBest journey. To get more information about your buddy use `{ctx.prefix}journey buddy` command.\n\n"
            + f"> Now, to get started with your adventure, you need to learn about some routes. So there are total of *15 routes* in PokeBest, you can duel the Pokémon in each route by using `{ctx.prefix}journey route <route_number>` command.\n"
            + f"> By default, you get route 1, 2 and 3 pre-unlocked. You can unlock more by defeating Elite Members.\n\n"
            + f"> To see the list of moves which your buddy can learn use `{ctx.prefix}journey buddy moves` comamnd and to learn moves, use `{ctx.prefix}journey buddy learn` command. To get in battle with a Elite member, use `{ctx.prefix}journey gym` command. Once, you defeat a Elite Member, you can access new routes and get new Elite Members."
        )

        await ctx.reply(embed=emb, mention_author=False)

    @journey.command(name="pick")
    async def journey_pick(self, ctx: commands.Context, *, pokemon: SpeciesConverter):
        """Pick your journey buddy"""
        if pokemon is None:
            return await ctx.reply("There is no pokemon with that name.", mention_author=False)

        m: models.JourneyMember = await models.JourneyMember.get_or_none(id=ctx.author.id)

        if m is not None:
            return await ctx.reply("You already picked your buddy for your journey!", mention_author=False)

        if pokemon["names"]["9"].lower() not in JOURNEY_STARTERS:
            return await ctx.reply(
                f"That's not a valid starter to pick. Please choose between - {self.bot.sprites.get(722)} **Rowlet** | {self.bot.sprites.get(501)} **Oshawott** | {self.bot.sprites.get(155)} **Cyndaquil**",
                mention_author=False,
            )

        ivs = [data.get_random_iv_value() for _ in range(6)]

        journey: models.JourneyMember = models.JourneyMember(
            id=ctx.author.id,
            species_id=pokemon.__getitem__("species_id"),
            level=5,
            xp=0,
            nature=data.random_nature(),
            shiny=False,
            iv_hp=ivs[0],
            iv_atk=ivs[1],
            iv_defn=ivs[2],
            iv_satk=ivs[3],
            iv_sdef=ivs[4],
            iv_spd=ivs[5],
            iv_total=sum(ivs),
        )

        await journey.save()

        emb: discord.Embed = self.bot.Embed(title="PokeBest Journeys")
        emb.description = (
            f"Congratulations {ctx.author.mention}! You have picked your journey buddy {self.bot.sprites.get(pokemon.__getitem__('species_id'))} **{pokemon['names']['9']}**. Nice choice! You can view stats of your buddy by using `{ctx.prefix}journey buddy info` command.\n"
            + f"\nℹ️ **Below are few instructions given to begin your adventure:**\n"
            + f"> Now, to get started with your adventure, you need to learn about some routes. So there are total of *15 routes* in PokeBest, you can duel the Pokémon in each route by using `{ctx.prefix}journey route <route_number>` command.\n"
            + f"> By default, you get route 1, 2 and 3 pre-unlocked. You can unlock more by defeating Elite Members.\n\n"
            + f"> To see the list of moves which your buddy can learn use `{ctx.prefix}journey buddy moves` comamnd and to learn moves, use `{ctx.prefix}journey buddy learn` command. To get in battle with a Elite member, use `{ctx.prefix}journey gym` command. Once, you defeat a Elite Member, you can access new routes and get new Elite Members."
        )

        emb.set_image(url="https://cdn.discordapp.com/attachments/890889580021157918/938155403303354388/Os-47w.gif")

        await ctx.reply(embed=emb, mention_author=False)

    @journey.group(name="buddy")
    async def journey_buddy(self, ctx: commands.Context):
        """Commands related to your buddy"""
        if ctx.invoked_subcommand is None:
            return await ctx.send_help(ctx.command)

    @journey_buddy.command(name="info")
    @has_started_journey()
    async def journey_buddy_info(self, ctx: commands.Context):
        """Shows your buddy's info"""
        mem: models.JourneyMember = await models.JourneyMember.get(id=ctx.author.id)

        async with self.bot.session.get(
            f"{self.bot.config.IMAGE_SERVER_URL}buddyinfo/{mem.iv_hp}/{mem.iv_atk}/{mem.iv_defn}/{mem.iv_spd}/{mem.iv_satk}/{mem.iv_sdef}/{mem.species_id}/{mem.specie['names']['9']}/{mem.level}"
        ) as resp:
            img_bytes: bytes = BytesIO(await resp.read())

            _file: discord.File = discord.File(img_bytes, filename="buddy.png")

            return await ctx.reply(file=_file, mention_author=False)

    @journey.command(name="route")
    @has_started_journey()
    async def jouney_route(self, ctx: commands.Context, route_number: int):
        """Battle a wild pokemon"""
        if 0 > route_number > 15:
            return await ctx.reply("There is no route available with that number.", mention_author=False)

        mem: models.JourneyMember = await models.JourneyMember.get(id=ctx.author.id)

        if mem.routes_unlocked < route_number:
            return await ctx.reply("You haven't unlocked that route yet!", mention_author=False)

        _weights: list = []
        for x in getattr(constants, f"ROUTE_{route_number}"):
            _weights.extend(i.__getitem__("abundance") for _, i in x.items())
        _species: dict = random.choices(getattr(constants, f"ROUTE_{route_number}"), weights=_weights, k=1)[0]

        pk1: models.JourneyMember = mem
        pk1.owner_id = mem.id

        pk2sp = data.species_by_name([*_species][0])
        pk2: models.Pokemon = models.Pokemon.get_random(
            owner_id=None,
            species_id=pk2sp["species_id"],
            level=random.choice(_species[pk2sp["names"]["9"].title()]["level"]),
            idx=1,
            xp=0,
        )

        moves: list = data.get_pokemon_moves(pk2.species_id)
        if not moves:
            moves: list = data.get_pokemon_moves(pk2.specie["dex_number"])

        move_ids: list = [m["move_id"] for m in moves]

        pk2.moves = move_ids[:4]

        trainer1: Trainer = Trainer(ctx.author, [pk1], 0, pk1, False)
        trainer2: Trainer = Trainer(ctx.bot.user, [pk2], 0, pk2, True)

        msg: discord.Message = await ctx.reply(
            embed=self.bot.Embed(
                description=f"You sent your {self.bot.sprites.get(pk1.specie['dex_number'])} **{pk1}**..."
            ).set_image(url=self.route_images[route_number]),
            mention_author=False,
        )

        with ctx.typing():
            battle: Battle = Battle(
                ctx.bot,
                ctx,
                [trainer1, trainer2],
                BattleType.oneVone,
                BattleEngine.AI,
                Reward.Journey,
                self.route_battles[route_number],
            )
            ctx.bot.battles.append(battle)

            await battle.send_battle()
            await msg.delete()

    @journey.command(name="elite")
    @has_started_journey()
    async def journey_elite(self, ctx: commands.Context):
        """Battle a Elite Four Member"""
        journey_member: models.JourneyMember = await models.JourneyMember.get(id=ctx.author.id)
        elite_mem: typing.Optional[str] = constants.ELITE_ROUTES.get(journey_member.routes_unlocked, None)

        elite_data: dict = constants.ELITE_FOUR_DATA[elite_mem]

        if journey_member.level < elite_data["requirement"]:
            return await ctx.reply(
                f"Your buddy doesn't meet the requirement of Level {elite_data['requirement']} to battle this gym.",
                mention_author=False,
            )

        if elite_data is None:
            return await ctx.reply("You already defeated all elite four memebers!", mention_author=False)

        pk1: models.JourneyMember = journey_member
        pk1.owner_id = journey_member.id

        pk2sp = data.species_by_name(elite_data["pokemon"])
        pk2: models.Pokemon = models.Pokemon.get_random(
            owner_id=None,
            species_id=pk2sp["species_id"],
            level=elite_data["level"],
            idx=1,
            xp=0,
        )

        moves: list = data.get_pokemon_moves(pk2.species_id)
        if not moves:
            moves: list = data.get_pokemon_moves(pk2.specie["dex_number"])

        move_ids: list = [m["move_id"] for m in moves]

        pk2.moves = move_ids[:4]

        trainer1: Trainer = Trainer(ctx.author, [pk1], 0, pk1, False)
        trainer2: Trainer = Trainer(ctx.bot.user, [pk2], 0, pk2, True)

        emb: discord.Embed = self.bot.Embed(description=f"{elite_data['description']}")
        emb.set_image(url=elite_data["gif"])
        emb.set_thumbnail(url=elite_data["image"])

        msg: discord.Message = await ctx.reply(embed=emb, mention_author=False)

        with ctx.typing():
            battle: Battle = Battle(
                ctx.bot,
                ctx,
                [trainer1, trainer2],
                BattleType.oneVone,
                BattleEngine.AI,
                Reward.Journey,
                BattleCategory.Gym,
            )
            ctx.bot.battles.append(battle)

            await battle.send_battle()
            await msg.delete()

    @journey_buddy.command(name="moves")
    @has_started_journey()
    async def journey_buddy_moves(self, ctx: commands.Context):
        """Displays all moves that pokemon can learn"""
        pokemon: models.JourneyMember = await models.JourneyMember.get(id=ctx.author.id)

        available_moves: typing.Iterable = []
        _pokemon_moves: list = data.get_pokemon_moves(pokemon.species_id)
        if not _pokemon_moves:
            _pokemon_moves: list = data.get_pokemon_moves(pokemon.specie["dex_number"])

        for mv in _pokemon_moves:
            if mv in available_moves:
                continue

            if mv["move_method_id"] == 1 and mv["level"] <= pokemon.level:
                available_moves.append(mv)

        pk_moves: list = []
        for mv in pokemon.moves:
            move: dict = data.move_by_id(mv)
            pk_moves.append(move["name"])

        while pk_moves.__len__() < 4:
            pk_moves.append("Tackle")

        embed: discord.Embed = self.bot.Embed(
            title=f"{pokemon} Moves:",
            description=f"To learn a move, use the `{ctx.prefix}journey buddy learn <move>` command.",
        )

        current_moves: list = [f"[{idx}] | {move}" for idx, move in enumerate(pk_moves, start=1)]

        _crtxt: str = "```\n"
        _crtxt += "\n".join(current_moves)
        _crtxt += "```"

        embed.add_field(name="Current Moves", value=_crtxt, inline=True)

        avail_moves: list = []
        for mv in available_moves:
            move: dict = data.move_by_id(mv.__getitem__("move_id"))
            if move["name"] in avail_moves:
                continue
            else:
                avail_moves.append(move["name"])

        _mvtxt: str = "```\n"
        _mvtxt += "\n".join(avail_moves)
        _mvtxt += "```"

        embed.add_field(name="Available Moves:", value=_mvtxt)

        await ctx.reply(embed=embed, mention_author=False)

    @journey_buddy.command(name="learn")
    @has_started_journey()
    async def journey_buddy_learn(self, ctx: commands.Context, *, move: MoveConverter):
        """Make your pokemon learn a move"""
        if move is None:
            return await ctx.reply("That move doesn't exists.", mention_author=False)

        with ctx.typing():
            pokemon: models.JourneyMember = await models.JourneyMember.get(id=ctx.author.id)
            can_learn: bool = False

            pmoves: typing.List[dict] = []
            pmove: typing.Optional[dict] = None

            pokemon_moves: list = data.get_pokemon_moves(pokemon.species_id)
            if not pokemon_moves:
                pokemon_moves: list = data.get_pokemon_moves(pokemon.specie["dex_number"])

            for mv in pokemon_moves:
                if mv["move_id"] == move["id"]:
                    pmoves.append(mv)

            if len(pmoves) != 0:
                for pmove in pmoves:
                    if pmove["move_method_id"] == 1 and pmove["level"] <= pokemon.level:
                        can_learn = True
                        break

            if not can_learn:
                raise PokeBestError(
                    f"You cannot learn this move at this moment as your buddy doesn't meets the requirements for it or this move doesn't exists. To see the list of moves your buddy can learn, use `{ctx.prefix}journey buddy moves` command."
                )

            replace_with: typing.Optional[int] = None

            moves: typing.List[dict] = [data.move_by_id(mv) for mv in pokemon.moves]
        if moves and len(moves) >= 4:
            embed: discord.Embed = self.bot.Embed(title=f"{pokemon} Moves:")
            embed.description = f"Select the move you want to replace with `{move['name']}`.\n\n"

            _move_names: typing.List[str] = [mv["name"] for mv in moves]
            _view: MoveLearnView = MoveLearnView(ctx, _move_names)
            msg: discord.Message = await ctx.send(embed=embed, view=_view)

            await _view.wait()

            replace_with = _view.value

            if replace_with is None:
                return await msg.edit(content="Time's up!", embed=None, view=None, allowed_mentions=None)

            omove = moves[replace_with - 1]
            moves[replace_with - 1] = move

            pokemon.moves = [m["id"] for m in moves]
            await pokemon.save()

        return await ctx.reply(
            f"Successfully replaced `{omove['name']}` with `{move['name']}`!",
            mention_author=False,
        )

    async def _prepare_trainer_battle(self, ctx: commands.Context, trainers: list):
        trainer: dict = random.choice(trainers)

        emb: discord.Embed = self.bot.Embed(
            title="You have been challanged!",
            description=(
                f"{trainer['name']} has challenged you to a battle!"
                + "\n**Rewards**:> Winning trainer battles rewards you with *300 JC*!"
                + "\n\nPress the **Fight** button below to accept the challenge!"
            ),
        )

        emb.set_thumbnail(url=trainer["avatar"])
        
        ...

    @commands.Cog.listener()
    async def on_battle_finish(self, battle: Battle, trainer: Trainer, move_emb: discord.Embed):
        if battle.reward != Reward.Journey or battle.category == BattleCategory.Gym:
            return
        __battle_chance: bool = random.randint(1, 100) <= random.randint(1, 50)
        if not __battle_chance:
            return
        
        if (tr := battle._get_trainer_by_id(self.bot.user.id)) is not None:
            _route_number: int = None
            for rid, category in self.route_battles.items():
                if category == battle.category:
                    _route_number = rid

            _route_trainers: typing.Optional[list] = None
            if _route_number is not None:
                for data in ROUTE_TRAINERS:
                    if _route_number in data.__getitem__("route_numbers"):
                        _route_trainers = data["trainers"]

            if _route_trainers:
                await self._prepare_trainer_battle(battle.ctx, _route_trainers)


def setup(bot: PokeBest) -> None:
    bot.add_cog(Journey(bot))
