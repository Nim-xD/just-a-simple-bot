import asyncio
from tortoise.exceptions import ConfigurationError
from utils.converters import PokemonConverter, SpeciesConverter
from cogs.helpers.battles import Battle, BattleEngine, Trainer
from discord.utils import escape_markdown
from discord.ext import commands, tasks
from models.helpers import ArrayAppend
from utils.checks import has_started
from utils.methods import write_fp
from utils.constants import TYPES, UTC
from core.views import SpawnDuelView, Confirm
from core.views import SpawnFightView
from contextlib import suppress
from typing import List, Optional, Union
from core.bot import PokeBest
from datetime import datetime
from data import data
import discord
import models
import random
import config


class MessageHandler(commands.Cog):
    def __init__(self, bot: PokeBest) -> None:
        self.bot: PokeBest = bot

        self.type_spawn_channels = {
            900784397454802994: "ice",
            896407360367624262: "beach",
            908770331999756318: "desert",
            915151599205236776: "forest",
        }

        self.incense_counter: dict = {}

        # self.clear_expired_incense.start()

    async def increase_xp(self: "MessageHandler", message: discord.Message):
        ctx: commands.Context = await self.bot.get_context(message)
        member: models.Member = await self.bot.manager.fetch_member_info(message.author.id)

        if member is None:
            return

        pokemon: models.Pokemon = await PokemonConverter().convert(ctx, "")
        if pokemon is None:
            return

        if pokemon.held_item == 13002:
            return

        level_increase: int = 0

        if pokemon.xp <= pokemon.max_xp:
            xp_inc: int = random.randint(10, 40)
            if member.boost_expires is not None or ctx.guild.id == config.SUPPORT_SERVER_ID:
                xp_inc *= 2

            if message.author.premium_since is not None and message.guild.id == config.SUPPORT_SERVER_ID:
                xp_inc *= 2

            pokemon.xp += xp_inc

        embed: Union[None, discord.Embed] = None

        if pokemon.xp > pokemon.max_xp and pokemon.level < 100:
            pokemon.level += 1
            level_increase += 1
            pokemon.xp = 0

            embed = self.bot.Embed(
                title="⬆️ Level up!",
                description=f"Congratulations {ctx.author.mention}!\nYour {pokemon:n} is now **Level {pokemon.level}**!",
            )

            embed.set_thumbnail(url=pokemon.normal_image)

            if pokemon.held_item != 13001:
                evo_id: int = pokemon.get_next_evolution()

                if evo_id is not None:
                    evo: dict = data.species_by_num(evo_id)
                    embed.add_field(
                        name=f"Ohh look! Your {pokemon:n} is evolving!",
                        value=f"Your {pokemon:n} turned into a **{evo['names']['9']}**!",
                    )

                    embed.set_thumbnail(url=evo["sprites"].__getitem__("normal"))

                    pokemon.species_id = evo["species_id"]

                    self.bot.dispatch("evolve", message, pokemon)

        if pokemon.level == 100:
            pokemon.xp = pokemon.max_xp

        await pokemon.save()

        if pokemon.level != 100 and embed:
            self.bot.dispatch("levelup", message, pokemon)
            return await ctx.send(embed=embed)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.guild is None:  # This will not allow to spawn and increase xp in dms
            return

        try:
            await self.increase_xp(message)
        except ConfigurationError:
            return

        try:
            _message_count: int = self.bot.spawn_cache[message.channel.id]["messages"]
        except KeyError:
            self.bot.spawn_cache[message.channel.id] = {
                "messages": 0,
                "species_id": None,
                "hint_used": False,
                "is_shiny": False,
                "is_engaged": False,
            }
            _message_count: int = 0

        if message.guild.id == self.bot.config.SUPPORT_SERVER_ID:
            SPAWN_THRESHOLD = 15
        else:
            SPAWN_THRESHOLD = 25

        if _message_count >= SPAWN_THRESHOLD:
            _species = data.random_pokemon()

            _ctx: commands.Context = await self.bot.get_context(message)
            spawn_duel: SpawnDuelView = SpawnDuelView(self.bot, _ctx, message.channel, _species.__getitem__("species_id"))

            self.bot.dispatch(
                "spawn",
                message.channel,
                species_id=_species["species_id"],
                redeemed=False,
                spawn_duel=spawn_duel,
            )

        self.bot.spawn_cache[message.channel.id]["messages"] += 1

        incense_counter: Optional[int] = self.incense_counter.get(message.author.id, None)
        if incense_counter is None and (await self.bot.redis.hexists(f"db:incense", message.author.id)):
            self.incense_counter[message.author.id] = 1
        elif incense_counter is not None:
            self.incense_counter[message.author.id] += 1

            if self.incense_counter[message.author.id] >= 10:
                self.bot.dispatch("spawn_incense", message)
                self.incense_counter[message.author.id] = 0

    @commands.Cog.listener()
    async def on_spawn(
        self,
        channel: discord.TextChannel,
        species_id: int,
        redeemed: bool = False,
        **kwargs,
    ):
        try:
            _redirects: List[int] = self.bot.cache.guilds[f"{channel.guild.id}"].channels
        except (KeyError, AttributeError):
            _redirects = []

        with suppress(KeyError):
            self.bot.spawn_cache[channel.id]["messages"] = 0

        try:
            guild_prefix: str = self.bot.cache.guilds[f"{channel.guild.id}"].prefix
        except (KeyError, AttributeError):
            guild_prefix: str = "p!"

        _spawn_embed: self.bot.Embed = self.bot.Embed(
            title="A wild pokemon has appeared!",
            description=f"Guess the pokemon and type `{guild_prefix}catch <pokemon>` to catch it!",
        )

        _species: dict = data.species_by_num(species_id)
        is_shiny: bool = random.randint(1, 4096) == 1

        try:
            _spawn_embed.color = int(data.specie_color(_species.__getitem__("species_id")), base=16)
        except TypeError:
            _spawn_embed.color = 0x000000

        if is_shiny:
            self.bot.spawn_cache[channel.id]["is_shiny"] = is_shiny

        # _nos: str = "normal" if not is_shiny else "shiny"

        types: List[str] = [TYPES[idx] for idx in _species["types"]]

        if channel.id in self.type_spawn_channels.keys():
            types = [self.type_spawn_channels.get(channel.id)]

        # async with self.bot.session.get(_species["sprites"]["normal"]) as resp:
        #     arr = await self.bot.loop.run_in_executor(None, write_fp, await resp.read())
        #     image: discord.File = discord.File(arr, filename="pokemon.jpg")

        #     _spawn_embed.set_image(url="attachment://pokemon.jpg")

        async with self.bot.session.get(
            f"{self.bot.config.IMAGE_SERVER_URL}spawn/{random.choice(types).lower()}/{_species['species_id']}"
        ) as resp:
            if resp.status == 200:
                arr = await self.bot.loop.run_in_executor(None, write_fp, await resp.read())
                image: discord.File = discord.File(arr, filename="pokemon.jpg")
                _spawn_embed.set_image(url="attachment://pokemon.jpg")

            else:
                async with self.bot.session.get(_species["sprites"]["normal"]) as resp:
                    arr = await self.bot.loop.run_in_executor(None, write_fp, await resp.read())
                    image: discord.File = discord.File(arr, filename="pokemon.jpg")
                    _spawn_embed.set_image(url="attachment://pokemon.jpg")

        if _redirects.__len__() == 0 or redeemed:
            await channel.send(embed=_spawn_embed, file=image)

            try:
                self.bot.spawn_cache[channel.id]["species_id"] = _species["species_id"]
                self.bot.spawn_cache[channel.id]["is_engaged"] = False

            except KeyError:
                self.bot.spawn_cache[channel.id] = {
                    "species_id": _species["species_id"],
                    "is_shiny": is_shiny,
                    "hint_used": False,
                    "messages": 0,
                    "is_engaged": False,
                }

        else:
            if channel.id not in self.bot.bot_config.normal_spawns:
                try:
                    channels: List[discord.TextChannel] = [
                        channel.guild.get_channel(chid) or (await self.bot.fetch_channel(chid)) for chid in _redirects
                    ]
                    channel: discord.TextChannel = random.choice(channels)

                except:
                    return

            try:
                self.bot.spawn_cache[channel.id]["species_id"] = _species["species_id"]
                self.bot.spawn_cache[channel.id]["is_engaged"] = False

            except KeyError:
                self.bot.spawn_cache[channel.id] = {
                    "species_id": _species["species_id"],
                    "is_shiny": is_shiny,
                    "hint_used": False,
                    "messages": 0,
                    "is_engaged": False,
                }

            if channel.id == 837902385946427412:
                _spawn_embed.set_image(url=None)
                _spawn_embed.set_thumbnail(url="attachment://pokemon.jpg")

            spawn_duel_view: Optional[SpawnDuelView] = kwargs.get("spawn_duel", None)
            if spawn_duel_view is not None:
                spawn_duel_view.ctx.channel = channel
                spawn_duel_view.channel = channel

            with suppress(discord.Forbidden, discord.HTTPException):
                await channel.send(embed=_spawn_embed, file=image, view=spawn_duel_view)

        self.bot.log.info(f"POKEMON {_species['names']['9']} IN {channel.id}")

    @commands.Cog.listener()
    async def on_spawn_incense(self, message: discord.Message):
        species: dict = data.random_pokemon()
        _species_id: int = species["species_id"]

        emb: discord.Embed = self.bot.Embed(
            title=f"{message.author.name}, your incense attracted a wild pokemon!",
            description=f"Guess the pokemon and type it's name to catch it.",
            color=0xFF5CF7,
        )

        async with self.bot.session.get(species["sprites"]["normal"]) as resp:
            arr = await self.bot.loop.run_in_executor(None, write_fp, await resp.read())
            image: discord.File = discord.File(arr, filename="pokemon.jpg")

            emb.set_thumbnail(url="attachment://pokemon.jpg")

        def _check(msg: discord.Message):
            guess: str = msg.content.lower()
            _pk: Optional[dict] = data.species_by_name(guess)

            return (
                msg.author.id == message.author.id
                and msg.channel.id == message.channel.id
                and _pk is not None
                and _pk["species_id"] == _species_id
            )

        _remaining_count: int = int(await self.bot.redis.hget("db:incense", message.author.id))
        if _remaining_count <= 1:
            await self.bot.redis.hdel(f"db:incense", message.author.id)
        else:
            await self.bot.redis.hset("db:incense", message.author.id, _remaining_count - 1)

        emb.set_footer(text=f"Incense Remaining: {_remaining_count - 1}")
        _spawn_msg: discord.Message = await message.channel.send(embed=emb, file=image)

        try:
            msg: discord.Message = await self.bot.wait_for("message", check=_check, timeout=200.0)

            if msg:
                emb.title = "Caught!"
                mem: models.Member = await self.bot.manager.fetch_member_info(message.author.id)
                _next_idx: int = mem.next_idx

                if hasattr(mem, "shiny_hunt") and _species_id == mem.shiny_hunt:
                    mem.shiny_streak += 1

                    is_shiny: bool = (mem.shiny_streak * random.randint(1, 4096)) == 1

                else:
                    is_shiny: bool = random.randint(1, 4096) == 1

                pokemon_res: models.Pokemon = models.Pokemon.get_random(
                    species_id=_species_id,
                    owner_id=message.author.id,
                    level=random.randint(5, 40),
                    timestamp=datetime.now(),
                    xp=0,
                    idx=_next_idx,
                    shiny=is_shiny,
                )

                emb.description = f"Congratulations {message.author.mention}! You caught a {self.bot.sprites.get(pokemon_res.species_id, pokemon_res.shiny)} **{pokemon_res:l}!**"

                await pokemon_res.save()

                if pokemon_res.shiny and mem.shiny_hunt == pokemon_res.species_id:
                    mem.shiny_hunt = 0
                    mem.shiny_streak = 0

                mem.next_idx += 1
                ctx: commands.Context = await self.bot.get_context(message)

                _message: str = f"Congratulations {message.author.mention}! You caught a {self.bot.sprites.get(pokemon_res.species_id, pokemon_res.shiny)} **{pokemon_res:l}!**"

                if pokemon_res.species_id not in mem.pokemons:
                    mem.balance += 50
                    _message += " Added to Pokédex! You received 50 credits."
                else:
                    _message += " You received 20 credits."
                    mem.balance += 20

                mem.pokemons = ArrayAppend("pokemons", pokemon_res.species_id)
                if pokemon_res.shiny:
                    _message += "\n\n✨ Oh! The colors on this one seem odd..."

                await mem.save()

                # await message.channel.send(_message, mention_author=False)

                with suppress(discord.Forbidden, discord.HTTPException):
                    await _spawn_msg.edit(embed=emb)

                self.bot.dispatch("catch", ctx, pokemon_res)

        except asyncio.TimeoutError:
            emb.title = "Despawned"
            emb.description = ""

            with suppress(discord.Forbidden, discord.HTTPException):
                await _spawn_msg.edit(embed=emb)

    @commands.command(aliases=("c",))
    @has_started()
    async def catch(self, ctx: commands.Context, *, pokemon: SpeciesConverter):
        """Catch a wild pokemon!"""
        try:
            if self.bot.spawn_cache[ctx.channel.id]["species_id"] is None:
                return await ctx.reply("There is no wild pokemon!", mention_author=False)
        except KeyError:
            return await ctx.reply("There is no wild pokemon!", mention_author=False)

        if self.bot.spawn_cache[ctx.channel.id]["is_engaged"]:
            return await ctx.reply("This pokemon is in duel with another trainer.", mention_author=False)

        if pokemon is None or self.bot.spawn_cache[ctx.channel.id]["species_id"] != pokemon.__getitem__("species_id"):
            return await ctx.reply("That is the wrong pokemon! Try again.", mention_author=False)

        mem: models.Member = await self.bot.manager.fetch_member_info(ctx.author.id)

        species_id: int = self.bot.spawn_cache[ctx.channel.id]["species_id"]
        self.bot.spawn_cache[ctx.channel.id]["species_id"] = None
        _next_idx: int = mem.next_idx

        if hasattr(mem, "shiny_hunt") and species_id == mem.shiny_hunt:
            mem.shiny_streak += 1

            is_shiny: bool = (mem.shiny_streak * random.randint(1, 4096)) == 1

        else:
            is_shiny: bool = random.randint(1, 4096) == 1

        pokemon_res: models.Pokemon = models.Pokemon.get_random(
            species_id=species_id,
            owner_id=ctx.author.id,
            level=random.randint(5, 40),
            timestamp=datetime.now(),
            xp=0,
            idx=_next_idx,
            shiny=is_shiny,
        )

        await pokemon_res.save()

        if pokemon_res.shiny and mem.shiny_hunt == pokemon_res.species_id:
            mem.shiny_hunt = 0
            mem.shiny_streak = 0

        mem.next_idx += 1

        self.bot.spawn_cache[ctx.channel.id]["hint_used"] = False

        message: str = f"Congratulations {ctx.author.mention}! You caught a {self.bot.sprites.get(pokemon_res.species_id, pokemon_res.shiny)} **{pokemon_res:l}!**"

        if pokemon_res.species_id not in mem.pokemons:
            mem.balance += 50
            message += " Added to Pokédex! You received 50 credits."
            # message += "\n\nAdded to Pokédex! You received 50 credits."
        else:
            message += " You received 20 credits."
            mem.balance += 20

        mem.pokemons = ArrayAppend("pokemons", pokemon_res.species_id)
        if pokemon_res.shiny:
            message += "\n\n✨ Oh! The colors on this one seem odd..."

        if self.bot.config.CHRISTMAS_MODE:
            species: dict = data.species_by_num(pokemon_res.species_id)
            if 15 in species["types"]:
                _shards = random.randint(1, 5)
                message += f"\n\n❄️ The wild {pokemon_res} dropped 💎 {_shards} shard(s)!"

                mem.shards += _shards

        await mem.save()

        # message += f"\n**IV:** ||{pokemon_res.iv_total/186:.2%}||"
        # await ctx.reply(embed=self.bot.Embed(description=message).set_footer(text=f"Number: {pokemon_res.idx}"), mention_author=False)
        await ctx.reply(message, mention_author=False)

        self.bot.dispatch("catch", ctx, pokemon_res)

        # Re-initialising cache can save life
        self.bot.spawn_cache[ctx.channel.id] = {
            "messages": 0,
            "species_id": None,
            "hint_used": False,
            "is_shiny": False,
            "is_engaged": False,
        }

    @commands.command(aliases=("h",))
    @has_started()
    async def hint(self, ctx: commands.Context):
        """Get hint for a spawned wild pokemon."""
        try:
            if self.bot.spawn_cache[ctx.channel.id]["species_id"] is None:
                return await ctx.reply("There is no wild pokemon!", mention_author=False)
        except KeyError:
            return await ctx.reply("There is no wild pokemon!", mention_author=False)

        if self.bot.spawn_cache[ctx.channel.id]["hint_used"] is True:
            return await ctx.reply("You can't get more hints!", mention_author=False)

        specie = data.species_by_num(self.bot.spawn_cache[ctx.channel.id]["species_id"])

        inds = [i for i, x in enumerate(specie["names"]["9"]) if x.isalpha()]
        blanks = random.sample(inds, len(inds) // 2)
        hint = "".join("_" if i in blanks else x for i, x in enumerate(specie["names"]["9"]))

        await ctx.reply(f"The wild pokemon is {escape_markdown(hint)}!", mention_author=False)

    @commands.command(aliases=("sh",))
    @has_started()
    async def shinyhunt(self, ctx: commands.Context, species: str = None):
        """Shiny hunt a pokemon"""
        mem: models.Member = await self.bot.manager.fetch_member_info(ctx.author.id)

        if species is None:
            emb: discord.Embed = self.bot.Embed(
                title="✨ Shiny Hunt ✨",
                description="Start shiny hunting a pokemon! More you catch that pokemon, more the shiny catching chance increases.\n\n"
                + f"**To start shiny hunting use**: `{ctx.prefix}shinyhunt <pokemon name>`",
            )

            if mem.shiny_hunt:
                species: dict = data.species_by_num(mem.shiny_hunt)
                emb.add_field(
                    name="Current Hunt:",
                    value=f"**Hunting**: {species['names']['9']} | **Streak**: {mem.shiny_streak}",
                )
                emb.set_thumbnail(url=species["sprites"]["shiny"])

            return await ctx.reply(embed=emb, mention_author=False)

        species: Optional[dict] = await SpeciesConverter().convert(ctx, species)

        if species is None:
            return await ctx.reply("There is no pokemon available like that.", mention_author=False)

        if species["catchable"] is False:
            return await ctx.reply(
                "That pokemon isn't available for hunting as it doesn't spawn!",
                mention_author=False,
            )

        if mem.shiny_hunt != None and mem.shiny_hunt == species["species_id"]:
            return await ctx.reply("You are already hunting this pokemon!")

        _view: Confirm = Confirm(ctx, ctx.author.id)

        await ctx.reply(
            "Are you sure you want to hunt this pokemon?\n⚠ **Caution**: The previous hunting data will be removed!",
            view=_view,
        )

        await _view.wait()

        if _view.value is None:
            return await ctx.reply("Time's up!", mention_author=False)

        if _view.value is False:
            return await ctx.reply("Aborted.", mention_author=False)

        mem.shiny_hunt = species["species_id"]
        mem.shiny_streak = 0

        await mem.save()

        await ctx.reply(
            f"You are now hunting for ✨ `{species['names']['9']}`! All the best.",
            mention_author=False,
        )

    @commands.Cog.listener()
    async def on_catch(self, ctx: commands.Context, pokemon: models.Pokemon):
        if random.randint(1, 50) == 5:
            emb: discord.Embed = self.bot.Embed(
                title="You have been challanged!",
                description=f"{ctx.author.mention}, You have been challenged by Team Rocket for a battle!\n> Beating Team Rocket will give you a chance to catch a {self.bot.sprites.get(150)} Armoured Mewtwo!",
                color=0x000000,
            )

            emb.set_image(
                url="https://media.discordapp.net/attachments/890889580021157918/928993634538360882/20220107_181832.gif"
            )

            emb.set_footer(text="Beating Team Rocket rewards you with Armoured Mewtwo!")

            await ctx.reply(embed=emb, view=SpawnFightView(ctx), mention_author=False)

    @commands.Cog.listener()
    async def on_battle_finish(self, battle: Battle, trainer: Trainer, move_emb: discord.Embed):
        if battle.battle_engine == BattleEngine.AI:
            if (tr := battle._get_trainer_by_id(self.bot.user.id)) is not None:
                if tr.pokemon[0].species_id == 150 and tr.pokemon[0].level == 150:
                    if not trainer.is_bot:
                        mem: models.Member = await self.bot.manager.fetch_member_info(trainer.user.id)

                        pokemon_res: models.Pokemon = models.Pokemon.get_random(
                            species_id=10252,
                            owner_id=mem.id,
                            level=random.randint(5, 40),
                            timestamp=datetime.now(),
                            xp=0,
                            idx=mem.next_idx,
                            shiny=random.randint(1, 4096) == 1,
                        )

                        await pokemon_res.save()

                        mem.next_idx += 1
                        await mem.save()

    # @tasks.loop(seconds=10)
    # async def clear_expired_incense(self):
    #     await self.bot.wait_until_ready()
    #     for id in list(self.bot.cache.incense_timestamps):
    #         if (
    #             datetime.utcnow().replace(tzinfo=UTC) - self.bot.cache.incense_timestamps[id].replace(tzinfo=UTC)
    #         ).seconds >= 3600:
    #             del self.bot.cache.incense_timestamps[id]
    #             del self.incense_counter[int(id)]


def setup(bot: PokeBest) -> None:
    bot.add_cog(MessageHandler(bot))
