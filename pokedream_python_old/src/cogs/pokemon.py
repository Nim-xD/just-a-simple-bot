from __future__ import annotations

from discord.ext import commands
import discord
from core.bot import PokeBest
from core.paginator import AsyncListPaginator, SimplePaginator
from core.views import Confirm, PokedexView, FishingView, InfoView
from data import data
import models

import math
import random
from datetime import datetime
from typing import List, Iterable, Optional, Union
from contextlib import suppress
from collections import Counter
import asyncio
import pickle

from utils.constants import STARTERS, TYPES, LANGUAGES, BattleCategory
from utils.converters import PokemonConverter, SpeciesConverter
from utils.checks import has_started
from utils.filters import create_filter
from utils.methods import write_fp
from utils.emojis import emojis
from utils import flags
from utils.exceptions import NoSelectedPokemon, PokeBestError

# from utils import flags
from cogs.helpers.battles import Battle, Reward, get_ai_duel


class Pokemon(commands.Cog):
    def __init__(self, bot: PokeBest) -> None:
        self.bot: PokeBest = bot

    async def prepare_pokedex_pages(self, ctx: commands.Context, page: str, _flags) -> List[discord.Embed]:
        pgstart: int = (int(page) - 1) * 20

        if pgstart >= 898 or pgstart < 0:
            return None

        caught: List[int] = (await models.Member.get(id=ctx.author.id)).pokemons
        pages: List[discord.Embed] = []

        if _flags["caught"] and caught.__len__() == 0:
            return None

        def include(idx: int) -> bool:
            if _flags["legendary"] and idx not in [s["species_id"] for s in data.list_legendary]:
                return False

            elif _flags["mythical"] and idx not in [s["species_id"] for s in data.list_mythical]:
                return False

            elif _flags["ub"] and idx not in [s["species_id"] for s in data.list_ub]:
                return False

            else:
                return True

        to_include = range(0, 898)
        to_include = list(filter(lambda idx: include(idx), to_include))

        if _flags["caught"]:
            for i in to_include:
                if i + 1 not in list(set(caught)):
                    to_include.remove(i)

        if _flags["uncaught"]:
            for i in to_include:
                if i + 1 in list(set(caught)):
                    to_include.remove(i)

        def get_page(pidx: int) -> discord.Embed:
            pgstart: int = pidx * 20
            pgend: int = min(pgstart + 20, 898)

            # use_sprites: bool = self.bot.user.permissions_in(ctx.channel).external_emojis
            use_sprites: bool = True

            page: discord.Embed = self.bot.Embed(
                title="Your pokedex",
                description=f"You have caught {list(set(caught)).__len__()} out of 898 pokemon.",
            )

            for i in to_include[pgstart:pgend]:
                # if i + 1 in caught and not _flags["uncaught"] or i + 1 in caught and _flags["caught"]:
                if i + 1 in caught:
                    occr: int = Counter(caught).__getitem__(i + 1)

                    page.add_field(
                        name=f"{self.bot.sprites.get(i + 1) if use_sprites else ''} {data.species_by_num(i + 1)['names']['9']} #{i + 1}",
                        value=f"{emojis.tick} {occr} caught!",
                    )

                # elif i + 1 not in caught and not _flags["caught"] or i + 1 not in caught and _flags["uncaught"]:
                elif i + 1 not in caught:
                    page.add_field(
                        name=f"{self.bot.sprites.get(i + 1) if use_sprites else ''} {data.species_by_num(i + 1)['names']['9']} #{i + 1}",
                        value=f"{emojis.cross} Not caught yet!",
                    )

            page.set_footer(text=f"Showing {pgstart+1}-{pgend} of 898 pokemon.")

            return page

        total_pages: int = math.ceil(898 / 20)

        for i in range(total_pages):
            page = get_page(i)
            if len(page.fields) == 0:
                continue

            pages.append(page)

        return pages

    @flags.add_flag("page", nargs="*", default="1", type=str)
    @flags.add_flag("--caught", action="store_true")
    @flags.add_flag("--uncaught", action="store_true")
    @flags.add_flag("--legendary", action="store_true")
    @flags.add_flag("--mythical", action="store_true")
    @flags.add_flag("--ub", action="store_true")
    @flags.add_flag("--type", action="store_true")
    @flags.command(aliases=("dex", "d"))
    @has_started()
    async def pokedex(self, ctx: commands.Context, **flags):
        """Show's the pokedex"""
        search_or_page = " ".join(flags["page"])

        if flags["caught"] and flags["uncaught"]:
            return await ctx.reply(
                "You can use either --caught or --uncaught at one time.",
                mention_author=False,
            )

        if flags["mythical"] + flags["legendary"] + flags["ub"] > 1:
            return await ctx.reply("You can't use more than one rarity flag.", mention_author=False)

        if search_or_page is None:
            search_or_page = "1"

        if search_or_page.isdigit():
            pages = await self.prepare_pokedex_pages(ctx, search_or_page, flags)

            if pages is None or len(pages) == 0:
                return await ctx.reply("There is nothing on that page!", mention_author=False)

            if len(pages) > 1:
                paginator: SimplePaginator = SimplePaginator(ctx, pages)
                paginator._current_page = int(search_or_page) - 1
                await paginator.paginate(ctx)
            else:
                await ctx.send(embed=pages[0])
        else:
            is_shiny: bool = False
            pokemon: str = search_or_page

            if "shiny " in pokemon:
                is_shiny = True
                pokemon: str = pokemon.replace("shiny ", "")

            specie = await SpeciesConverter().convert(ctx, pokemon)

            if specie is None:
                return await ctx.reply(
                    f"Any pokemon with name `{pokemon}` doesn't exists.",
                    mention_author=False,
                )

            embed: discord.Embed = self.bot.Embed(
                title=f"#{specie['species_id']} — {specie['names']['9']}",
                description=specie.__getitem__("description"),
                color=int(data.specie_color(specie["dex_number"]), 16),
            )

            names: List[str] = []
            for idx, name in specie["names"].items():
                with suppress(IndexError):
                    names.append(f"{LANGUAGES[int(idx)][2]} {name}")

            embed.add_field(name="Alternative Names", value="\n".join(names), inline=False)

            stats: Iterable[str] = (
                f"**HP**: {specie['base_stats'][0]}",
                f"**Attack**: {specie['base_stats'][1]}",
                f"**Defense**: {specie['base_stats'][2]}",
                f"**Sp. Atk**: {specie['base_stats'][3]}",
                f"**Sp. Def**: {specie['base_stats'][4]}",
                f"**Speed**: {specie['base_stats'][5]}",
            )

            embed.add_field(name="Stats", value="\n".join(stats), inline=True)

            types: List[str] = []
            for type_id in specie["types"]:
                types.append(getattr(emojis, TYPES[type_id].lower(), TYPES[type_id]))

            embed.add_field(name="Types", value=" | ".join(types), inline=True)

            embed.add_field(
                name="Appearance",
                value=f"Height: {int(specie['height'])/10}m\nWeight: {int(specie['weight'])/10}kg",
                inline=True,
            )

            _nos: str = "normal" if not is_shiny else "shiny"

            embed.set_image(url=specie["sprites"].__getitem__(_nos))

            return await ctx.send(
                embed=embed,
                view=PokedexView(self.bot, ctx, specie, is_shiny, embed),
            )

    @commands.command()
    async def start(self, ctx: commands.Context) -> discord.Message:
        """Start your pokemon journey"""
        _starter_menu: self.bot.Embed = self.bot.Embed(
            title="Welcome to the world of Pokemon!",
            description=f"To start the game, choose one of the starter pokemon with `{ctx.prefix}pick <pokemon>` command.",
        )

        for gen, pokemon in STARTERS.items():
            _starter_menu.add_field(name=gen, value=" | ".join(f"`{p}`" for p in pokemon))

        # _starter_menu.set_image(url="https://i.imgur.com/oSHo1IZ.png")
        _starter_menu.set_author(
            name="Professor Oak",
            icon_url="https://media.discordapp.net/attachments/811830543061876757/811848174033305640/Professor_Oak.jpg",
        )

        return await ctx.send(embed=_starter_menu)

    @commands.command()
    async def pick(self, ctx: commands.Context, *, pokemon: SpeciesConverter):
        """Pick a starter pokemon to start your game."""
        member = await models.Member.get_or_none(id=ctx.author.id)

        if member != None:
            return await ctx.send("You already picked a starter pokemon!")

        _starters: List[str] = [name.lower() for x in STARTERS.values() for name in x]

        if pokemon is None or pokemon["names"]["9"].lower() not in _starters:
            return await ctx.send("That's not a valid starter pokemon!")

        pokemon_result: models.Pokemon = models.Pokemon.get_random(
            species_id=pokemon["species_id"],
            owner_id=ctx.author.id,
            level=1,
            xp=0,
            timestamp=datetime.now(),
            idx=1,
        )

        await pokemon_result.save()

        member: models.Member = models.Member(
            id=ctx.author.id,
            joined_at=datetime.now(),
            next_idx=2,
            selected_id=1,
        )

        await member.save()

        emb: discord.Embed = self.bot.Embed(
            title=f"Welcome to {self.bot.user.name}!",
            description=f"{ctx.author.mention}, Welcome to the world of pokémon! Thank you for choosing {self.bot.user.name}.\n\n"
            + f"❓**Quick Question**: Did someone refer you to play {self.bot.user.name}?\n"
            + f"If so, tag them or type their Discord ID below, otherwise type `no`.",
        )

        emb.set_thumbnail(
            url="https://media.discordapp.net/attachments/811830543061876757/811848174033305640/Professor_Oak.jpg"
        )

        emb.set_author(name=ctx.author, icon_url=ctx.author.display_avatar)

        await ctx.reply(embed=emb, mention_author=False)

        _picked_emb: discord.Embed = self.bot.Embed(
            description=f"Great! You choose {self.bot.sprites.get(pokemon_result.specie['dex_number'])} {pokemon['names']['9']} as your starter pokemon.\n\n"
            + f"ℹ️ **Instructions:**\n> - Use `{ctx.prefix}pokemon` command to see your pokemon collection."
            + f"\n> - You can view detailed information about your pokemon using `{ctx.prefix}info` command."
            + f"\n> - To see all the commands and get the help about them, use `{ctx.prefix}help` command."
            + f"\n\n If you face any difficulties, then feel free to join our [support server]({self.bot.config.SUPPORT_SERVER_LINK}) and ask your questions there.",
        )

        _picked_emb.set_footer(text=f"We hope you will have fun! - Team {self.bot.user.name}")

        _picked_emb.set_image(
            url="https://cdn.discordapp.com/attachments/880507623550619678/929683163507212298/tumblr_o1kp5jG72K1u3e4cro1_500.gif"
        )

        _picked_emb.set_author(name=ctx.author, icon_url=ctx.author.display_avatar)

        def _check(msg: discord.Message) -> bool:
            return msg.channel.id == ctx.channel.id and msg.author.id == ctx.author.id

        try:
            referral_msg: discord.Message = await self.bot.wait_for("message", check=_check, timeout=120)
            referrer = None
            # TODO: Make a tutorial class, and just make instance and call it here after referral

            if referral_msg.content.lower() == "no":
                return await ctx.reply(embed=_picked_emb, mention_author=False)

            if referral_msg.mentions.__len__() != 0:
                referrer: Optional[models.Member] = await self.bot.manager.fetch_member_info(referral_msg.mentions[0].id)

            if referral_msg.content.isdigit():
                referrer_id: int = int(referral_msg.content)

                referrer: Optional[models.Member] = await self.bot.manager.fetch_member_info(referrer_id)

            if referrer is None:
                return await ctx.reply(
                    "The user you mentioned maybe didn't started yet or doesn't exist! Anyways,",
                    embed=_picked_emb,
                    mention_author=False,
                )

            if referrer.id == ctx.author.id:
                return await ctx.reply(
                    "You can't be your own referrer. Anyways,",
                    embed=_picked_emb,
                    mention_author=False,
                )

            referrer.gift += 1
            await referrer.save()

            referrer_user: Optional[discord.User] = self.bot.get_user(referrer.id) or await self.bot.fetch_user(
                referrer.id
            )

            if referrer_user is not None:
                with suppress(discord.Forbidden, discord.HTTPException):
                    _referrer_emb: discord.Embed = self.bot.Embed(
                        title="Thank you for referring us!",
                        description=f"Thank you for referring us to `{ctx.author}`! They used your referral code, and u received a {emojis.gift} gift from us. Keep referring!\n\n- Team {self.bot.user.name}",
                    )

                    await referrer_user.send(embed=_referrer_emb)

            self.bot.dispatch("new_player", ctx.author)
            return await ctx.reply(embed=_picked_emb, mention_author=False)

        except asyncio.TimeoutError:
            self.bot.dispatch("new_player", ctx.author)
            return await ctx.reply(embed=_picked_emb, mention_author=False)

    async def create_filters(
        self, ctx: commands.Context, flags: dict, pokemons: List[models.Pokemon]
    ) -> List[models.Pokemon]:
        filtered = []

        if flags["shiny"]:
            filtered += filter(lambda pk: pk.shiny, pokemons)

        for x in ("legendary", "mythical", "ub"):
            if x in flags and flags[x]:
                filtered += filter(lambda pk: pk.species_id in getattr(data, f"{x}_ids"), pokemons)

        for x in ("alola", "galarian"):
            if x in flags and flags[x]:
                filtered += filter(
                    lambda pk: data.species_by_num(pk.species_id)["names"]["9"].lower().startswith(f"{x} "),
                    pokemons,
                )

    async def prepare_pokemon_pages(self, ctx: commands.Context, flags, order_by: str = "number") -> List[discord.Embed]:
        _pokemon_model_list: List[models.Pokemon] = await self.bot.manager.fetch_pokemon_list(member_id=ctx.author.id)
        _pokemon_model_list = await create_filter(flags, ctx, _pokemon_model_list)

        if _pokemon_model_list.__len__() == 0:
            return None

        # TODO: This should be changed in p!order command
        if order_by.lower() == "number":
            _pokemon_model_list.sort(key=lambda k: k.idx)
        else:
            _pokemon_model_list.sort(key=lambda k: k.iv_total, reverse=True)

        pages: List[discord.Embed] = []

        def get_page(pidx):
            pgstart: int = pidx * 15
            pgend: int = max(min(pgstart + 15, _pokemon_model_list.__len__()), 0)
            txt: str = ""

            if pgstart != pgend:
                for pk in _pokemon_model_list[pgstart:pgend]:
                    txt += f"`{'0{0}'.format(pk.idx) if pk.idx < 10 else pk.idx}` | {'✨' if pk.shiny else ''} {self.bot.sprites.get(pk.specie['dex_number'], pk.shiny)} **{pk.specie['names']['9']}** {'💖' if pk.favorite else ''} | Level: {pk.level} | IV: {pk.iv_total/186:.2%} {'| Nickname: {0}'.format(pk.nickname) if pk.nickname is not None else ''}\n"
            else:
                for pk in [_pokemon_model_list[pgstart]]:
                    txt += f"`{'0{0}'.format(pk.idx) if pk.idx < 10 else pk.idx}` | {'✨' if pk.shiny else ''} {self.bot.sprites.get(pk.specie['dex_number'], pk.shiny)} **{pk.specie['names']['9']}** {'💖' if pk.favorite else ''} | Level: {pk.level} | IV: {pk.iv_total/186:.2%} {'| Nickname: {0}'.format(pk.nickname) if pk.nickname is not None else ''}\n"

            return self.bot.Embed(description=txt, title="Your pokemon:").set_footer(
                text=f"Showing {pgstart+1}-{pgend} of {_pokemon_model_list.__len__()} pokemon."
            )

        total_pages: int = math.ceil(_pokemon_model_list.__len__() / 15)

        for i in range(total_pages):
            page = get_page(i)
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
    @flags.command(aliases=("pk", "p"), case_insensitve=True)
    @has_started()
    async def pokemon(self, ctx: commands.Context, **flags):
        """Shows your pokemon collection"""
        mem: models.Member = await self.bot.manager.fetch_member_info(ctx.author.id)

        with ctx.typing():
            pages = await self.prepare_pokemon_pages(ctx, flags, mem.order_by)

        if pages is None:
            return await ctx.reply("No pokemon found matching this search!", mention_author=False)

        if len(pages) > 1:
            paginator: SimplePaginator = SimplePaginator(ctx, pages)
            await paginator.paginate(ctx)
        else:
            await ctx.send(embed=pages[0])

    @commands.command(aliases=("i",), rest_is_raw=True)
    @has_started()
    async def info(self, ctx: commands.Context, *, pokemon: PokemonConverter):
        """Get info about a specific pokemon in your collection."""
        if pokemon is None:
            return await ctx.send("Couldn't find any pokemon!")

        embed: discord.Embed = self.bot.Embed(title=f"{pokemon:l}", color=pokemon.normal_color)
        embed.description = ""

        embed.description += f"**XP:** {pokemon.xp}\n**Nature:** {pokemon.nature}\n\n"
        embed.description += "\n".join(pokemon.get_stats)

        embed.set_thumbnail(url=ctx.author.avatar.url)
        _nos: str = "normal" if pokemon.shiny is False else "shiny"

        async with self.bot.session.get(pokemon.specie["sprites"].__getitem__(_nos)) as resp:
            if resp.status == 200:
                arr = await self.bot.loop.run_in_executor(None, write_fp, await resp.read())
                image: discord.File = discord.File(arr, filename="pokemon.jpg")
                embed.set_image(url="attachment://pokemon.jpg")
            else:
                image = None

        embed.set_footer(
            text=f"Displaying pokemon {pokemon.idx}/{(await self.bot.manager.fetch_pokemon_count(ctx.author.id))}."
        )

        # view: InfoView = InfoView(ctx, pokemon)
        # await ctx.send(embed=embed, file=image, view=view)

        await ctx.reply(embed=embed, file=image, mention_author=False)

    @commands.command(aliases=("nick",))
    @has_started()
    async def nickname(self, ctx: commands.Context, *, nickname: str = None):
        """Set a nickname of your pokemon"""
        pokemon = await PokemonConverter().convert(ctx, "")

        if pokemon is None:
            raise PokeBestError(
                f"Hey, I guess you don't have any pokemon selected. Try selecting a pokemon from your pokemon collection which you can view using `{ctx.prefix}pokemon` command. To select a pokemon use `{ctx.prefix}select <index>` command."
            )

        if pokemon.nickname is None and nickname is None:
            raise PokeBestError(
                "Hey, looks like your pokemon doesn't have any existing nickname and you also didn't provide any nickname too. Try again this command by giving a nickname now, your pokemon's nickname will be changed then!"
            )

        if pokemon.nickname is not None and nickname is None:
            await self.bot.manager.update_pokemon(pokemon_id=pokemon.id, nickname=None)
            return await ctx.reply("Nickname successfully removed!", mention_author=False)

        if pokemon.nickname is None and nickname is not None:
            await self.bot.manager.update_pokemon(pokemon_id=pokemon.id, nickname=nickname)
            return await ctx.reply(f"Nickname successfully updated to `{nickname}`.", mention_author=False)

    @commands.command(aliases=("fav", "favourite"))
    @has_started()
    async def favorite(self, ctx: commands.Context, pokemon: PokemonConverter):
        """Add a pokemon to your favorites"""
        if pokemon is None:
            raise PokeBestError(
                f"Hey, I guess you don't have any pokemon on that number! Use `{ctx.prefix}pokemon` command to view your pokemon collection and enter a correct number this time."
            )

        if pokemon.favorite:
            await self.bot.manager.update_pokemon(pokemon_id=pokemon.id, favorite=False)
            return await ctx.reply(f"Successfully unfavorited your {pokemon:l}!", mention_author=False)

        if not pokemon.favorite:
            await self.bot.manager.update_pokemon(pokemon_id=pokemon.id, favorite=True)
            return await ctx.reply(f"Successfully favorited your {pokemon:l}!", mention_author=False)

    @commands.command(aliases=("s",))
    @has_started()
    async def select(self, ctx: commands.Context, pokemon: PokemonConverter):
        """Select a pokemon"""
        if pokemon is None:
            raise PokeBestError(
                f"Hey, I guess you don't have any pokemon on that number! Use `{ctx.prefix}pokemon` command to view your pokemon collection and enter a correct number this time."
            )

        with ctx.typing():
            member: models.Member = await self.bot.manager.fetch_member_info(ctx.author.id)

            if member.selected_id == pokemon.idx:
                return await ctx.reply("You have already selected this pokemon!", mention_author=False)

            await self.bot.manager.update_member(ctx.author.id, selected_id=pokemon.idx)

            await ctx.reply(f"You selected your {pokemon:l}!", mention_author=False)

    @commands.command(aliases=("r",))
    @has_started()
    async def release(self, ctx: commands.Context, pokemon: commands.Greedy[PokemonConverter]):
        """Release any pokemon from your collection"""
        pks: List[models.Pokemon] = []

        if pokemon.__len__() == 0:
            pk = await PokemonConverter().convert(ctx, "")
            if pk is None:
                return await ctx.reply("That pokemon is not avaialable.", mention_author=False)

            pks.append(pk)

        else:
            for p in pokemon:
                _pk: Optional[models.Pokemon] = await self.bot.manager.fetch_pokemon_by_id(p.id)
                if _pk is None:
                    continue

                pks.append(p)

        if any(pk is None for pk in pks):
            return await ctx.reply("Please provide a valid index of pokemon.", mention_author=False)

        txt: str = "Are you sure you want to **release** following pokemon?\n⚠️ **Note:** The changes are irrversible!\n"

        for p in pks:
            txt += f"\n`{p.idx}` - {p:l}\n"

        _view: Confirm = Confirm(ctx)

        msg: discord.Message = await ctx.reply(txt, view=_view, mention_author=False)

        await _view.wait()

        if _view.value is None:
            return await msg.edit("Time's up!", view=None, allowed_mentions=None)

        elif _view.value:
            with ctx.typing():
                for pk in pks:
                    await pk.delete()

                return await msg.edit("Done!", view=None, allowed_mentions=None)

        elif _view.value is False:
            return await msg.edit("Aborted!", view=None, allowed_mentions=None)

    @commands.command()
    @has_started()
    async def reindex(self, ctx: commands.Context):
        """Fix the indexes of your pokemon collection"""
        pks: List[models.Pokemon] = await self.bot.manager.fetch_pokemon_list(ctx.author.id)
        if not pks:
            return await ctx.reply("You don't have any pokemon!", mention_author=False)

        msg: discord.Message = await ctx.reply(
            "Re-indexing your pokemon collection.\n⚠️**CAUTION**: Don't do anything else until the process is completed!",
            mention_author=False,
        )

        for idx, pk in enumerate(pks, start=1):
            pk.idx = idx

            await pk.save()

        mem: models.Member = await self.bot.manager.fetch_member_info(ctx.author.id)
        mem.selected_id = 1
        mem.next_idx = len(pks) + 1
        await mem.save()

        with suppress(discord.Forbidden, discord.HTTPException):
            return await msg.edit(
                "Successfully re-indexed your pokemon collection!\n*Your selected pokemon may vary after reindex.*",
                allowed_mentions=None,
            )

    # TODO: Fishing rods to be implemented
    @commands.command()
    @commands.cooldown(1, 5, commands.BucketType.user)
    @has_started()
    async def fish(self, ctx: commands.Context):
        """Start fishing"""
        msg: discord.Message = await ctx.reply(
            embed=self.bot.Embed(title="You threw your fishing rod...").set_image(
                url="https://cdn.discordapp.com/attachments/890889580021157918/928700605311119380/e8ef393b431d0a4ce738f13af0e9d022.gif"
            ),
            mention_author=False,
        )

        await asyncio.sleep(5)
        rf: int = random.randint(1, 55)
        if rf >= 1 and rf <= 30:
            with ctx.typing():
                sp: dict = data.get_random_specie_by_type("water", "normal")
                # sp: dict = data.species_by_num(129)

                # Magikarp Event #
                _shiny: bool = False

                if random.randint(1, 4096) == 1:
                    _shiny = True

            embed: discord.Embed = self.bot.Embed(
                description=f"You encountered a {'✨' if _shiny else ''} {self.bot.sprites.get(sp['dex_number'], _shiny)} **{sp['names']['9']}** while fishing!\nChoose what you want to do from below provided actions:"
            )

            async with self.bot.session.get(
                f"{self.bot.config.IMAGE_SERVER_URL}trainer/{sp.__getitem__('species_id')}"
            ) as resp:
                if resp.status != 200:
                    return await ctx.reply(
                        "⚠️ Something went wrong...", mention_author=False
                    )  # TODO: Create a backup API thing for this

                arr = await self.bot.loop.run_in_executor(None, write_fp, await resp.read())
                image: discord.File = discord.File(arr, filename="fish.jpg")
                embed.set_image(url="attachment://fish.jpg")

            with suppress(discord.Forbidden, discord.HTTPException):
                await msg.delete()

            _view: FishingView = FishingView(ctx, sp)
            vmsg: discord.Message = await ctx.reply(embed=embed, file=image, mention_author=False, view=_view)

            await _view.wait()

            if _view.ready is None:
                with suppress(discord.Forbidden, discord.HTTPException):
                    return await vmsg.edit(
                        content="Time's up!",
                        embed=None,
                        attachments=[],
                        view=None,
                        allowed_mentions=None,
                    )

            elif _view.ready:
                with ctx.typing():
                    pk: Optional[models.Pokemon] = await self.bot.manager.fetch_selected_pokemon(ctx.author.id)
                    if pk is None:
                        raise NoSelectedPokemon(ctx)

                    battle: Battle = await get_ai_duel(ctx, sp, pk, Reward.Pokemon, BattleCategory.Water, _shiny)
                    self.bot.battles.append(battle)

                    with suppress(discord.Forbidden, discord.HTTPException):
                        await vmsg.delete()

                    await battle.send_battle()

        elif 31 <= rf and rf <= 55:
            cr: int = random.randint(10, 50)

            with ctx.typing():
                mem: models.Member = await self.bot.manager.fetch_member_info(ctx.author.id)
                mem.balance += cr
                await mem.save()

            with suppress(discord.Forbidden, discord.HTTPException):
                return await msg.edit(content=f"💰 You found **{cr}** credits!", embed=None)

    @commands.command(rest_is_raw=True)
    @has_started()
    async def evolve(self, ctx: commands.Context, args: commands.Greedy[PokemonConverter]):
        """Evolve a pokemon if it reached the required level"""
        if len(args) == 0:
            args.append(await PokemonConverter().convert(ctx, ""))

        if any(pokemon is None for pokemon in args):
            raise PokeBestError(
                f"Hey, I guess you don't have any pokemon on that number! Use `{ctx.prefix}pokemon` command to view your pokemon collection and enter a correct number this time."
            )

        embed: discord.Embed = self.bot.Embed(description="", title=f"Congratulations {ctx.author.display_name}!")

        evolved: list = []

        if len(args) > 10:
            return await ctx.reply("You can't evolve more than 10 pokemon at once!", mention_author=False)

        for pokemon in args:
            name: str = format(pokemon, "n")

            if (evo_id := pokemon.get_next_evolution()) is None:
                return await ctx.reply(f"Your {name} can't be evolved!", mention_author=False)

            if len(args) < 20:
                evo: dict = data.species_by_num(evo_id)

                embed.add_field(
                    name=f"Your {name} is evolving!",
                    value=f"Your {name} evolved into {self.bot.sprites.get(evo['dex_number'], pokemon.shiny)} **{evo['names']['9']}**!",
                    inline=True,
                )

            else:
                embed.description += f"Your {name} evolved into {self.bot.sprites.get(evo['dex_number'], pokemon.shiny)} **{evo['names']['9']}**!\n"

            if len(args) == 1:
                embed.set_thumbnail(url=evo["sprites"]["normal" if not pokemon.shiny else "shiny"])

            evolved.append((pokemon, evo))

        for pokemon, evo in evolved:
            pokemon.species_id = evo["species_id"]
            await pokemon.save()

            self.bot.dispatch("evolve", ctx.message, pokemon)

        return await ctx.reply(embed=embed)

    @commands.command()
    async def order(self, ctx: commands.Context, *, args: str):
        """Change order of your pokemon collection"""
        if args.lower() not in ("number", "iv"):
            return await ctx.reply("Please choose order type either `number` or `iv`.", mention_author=False)

        mem: models.Member = await self.bot.manager.fetch_member_info(ctx.author.id)
        mem.order_by = args.lower()

        await mem.save()
        return await ctx.reply(f"Successfully updated order to `{args.lower()}`!", mention_author=False)

def setup(bot: PokeBest) -> None:
    bot.add_cog(Pokemon(bot))
