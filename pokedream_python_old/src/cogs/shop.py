import asyncio
from models.helpers import ArrayAppend
from utils.exceptions import PokeBestError, NoSelectedPokemon
import models
from typing import Dict, List, Optional, Union
import discord
from discord.ext import commands
import config

from core.bot import PokeBest
from core.views import GiftView, ShopMenuView
from core.paginator import SimplePaginator

from utils.constants import SHOP_FORMS, NATURES
from utils.checks import has_started
from utils.time import human_timedelta
from utils.converters import PokemonConverter, SpeciesConverter
from utils.emojis import emojis

from data import data
from datetime import datetime, timedelta
import random
import pickle


async def not_enough_balance(ctx: commands.Context):
    await ctx.reply("You don't have enough balance to buy this item!", mention_author=False)


class Shop(commands.Cog):
    def __init__(self, bot: PokeBest) -> None:
        self.bot: PokeBest = bot

    @commands.command()
    @has_started()
    async def shop(self, ctx: commands.Context, *, args: Optional[str] = None):
        """Browse some items to buy for your needs"""
        if args is None:
            _shop_emb: discord.Embed = self.bot.Embed(
                title="Welcome to PokeBest shop!",
                description="Use the given dropdown to go to your desired page to shop items!",
            )

            _shop_fields: dict = {
                "Page 1 : XP Boosters & Rare Candies": "> Get the list of items like XP Boosters and Rare Candies!",
                "Page 2 : Rare Stones & Evolution Items": "> Get the list of items like stones and evolution items to evolve your pokemon!",
                "Page 3 : Nature Modifiers": "> Get the list of items like nature modifiers to change the nature of your pokemon!",
                "Page 4 : Held Items": "> Get the list of items to hold for your pokemon!",
                "Page 5 : Mega Evolutions": "> Get the list of items which will allow your pokemon to mega evolve!",
                "Page 6 : 🔒Forms": "> Get the list of forms of pokemons which you can buy to evolve your pokemon!",
                f"Page 7 : {'⭐' if self.bot.config.CHRISTMAS_MODE else ''} Shard Shop": "> Get the list of items which you can buy using shards!",
                # "Page 8 : Miscellaneous": "> Some miscellaneous and exclusive items which you can buy!",
            }

            for name, value in _shop_fields.items():
                _shop_emb.add_field(name=name, value=value, inline=True)

            await ctx.send(embed=_shop_emb, view=ShopMenuView(ctx))

        elif args.lower().startswith("forms "):
            pokemon_name: str = args.replace("forms ", "")

            with ctx.typing():
                member: models.Member = await self.bot.manager.fetch_member_info(ctx.author.id)

                try:
                    _form_data: dict = SHOP_FORMS.__getitem__(pokemon_name)
                except KeyError:
                    # return await ctx.send(f"No forms found for `{pokemon_name}`!")
                    raise PokeBestError(
                        f"Hey, I don't think there are any forms for `{pokemon_name}` available in the shop! You can find the list of pokemons for which the forms are available in the shop with `{ctx.prefix}shop` command and select the Page 7 there."
                    )

                embed: discord.Embed = self.bot.Embed(
                    title=f"{pokemon_name.title()} Forms",
                    description=f"Some pokémon have different forms, you can buy them here to allow them to transform.\n\n*All {pokemon_name} forms cost **{_form_data.__getitem__('cost')} credits**!*",
                )

                embed.set_author(
                    name=f"Balance: {member.balance} | Shards: {member.shards}",
                    icon_url=ctx.author.avatar.url,
                )

                count: int = 1  # I am making it in paginator for future purposes
                embeds: List[discord.Embed] = []

                for form in _form_data.__getitem__("forms"):
                    embed.add_field(
                        name=f"{form.title()} Form",
                        value=f"{ctx.prefix}buy form {form}",
                        inline=True,
                    )
                    count += 1

                    if count % 25 == 0:
                        embeds.append(embed)

                        embed = self.bot.Embed(
                            title=f"{pokemon_name.title()} Forms",
                            description=f"Some pokémon have different forms, you can buy them here to allow them to transform.\n\n*All {pokemon_name} forms cost **{_form_data.__getitem__('cost')} credits**!*",
                        )

                        embed.set_author(
                            name=f"Balance: {member.balance} | Shards: {member.shards}",
                            icon_url=ctx.author.avatar.url,
                        )

                embeds.append(embed)

            if embeds.__len__() == 1:
                await ctx.send(embed=embeds[0])
            else:
                _paginator = SimplePaginator(ctx, embeds)
                await _paginator.paginate(ctx)

        else:
            return

    @commands.command()
    @has_started()
    async def buy(self, ctx: commands.Context, *, args: str):
        """Buy any item from shop!"""
        member: models.Member = await self.bot.manager.fetch_member_info(ctx.author.id)
        args: str = args.lower()

        if args in [str(i + 1) for i in range(4)]:
            if member.boost_expires is not None:
                return await ctx.reply(
                    "You already have a XP Booster active! Wait till it finishes.",
                    mention_author=False,
                )

            boost_item_id: int = int(args) - 1
            item = data.item_by_name(f"xp booster {boost_item_id}")

            if int(item["cost"]) > member.balance:
                return await not_enough_balance(ctx)

            minutes: int = int(item["action"].replace("xpboost_", ""))
            boost_date = datetime.utcnow() + timedelta(minutes=minutes)

            await self.bot.manager.update_member(ctx.author.id, boost_expires=boost_date)

            time_str: Dict[int, str] = {
                30: "30 Minutes",
                60: "1 Hour",
                120: "2 Hours",
                180: "3 Hours",
            }
            return await ctx.reply(
                f"Your XP gain will be doubled for the next {time_str.__getitem__(minutes)}",
                mention_author=False,
            )

        elif args.lower().startswith("candy"):
            amount_str: str = args.replace("candy ", "")

            try:
                amount: int = int(amount_str)
            except BaseException:
                amount: int = 1

            if amount < 0:
                return await ctx.reply("Amount cannot be negative!", mention_author=False)

            item = data.item_by_name("Rare Candy")
            price: int = int(item["cost"]) * amount

            if member.balance < price:
                return await not_enough_balance(ctx)

            pokemon: Optional[models.Pokemon] = await self.bot.manager.fetch_selected_pokemon(ctx.author.id)

            if pokemon is None:
                raise NoSelectedPokemon(ctx)

            species: dict = data.species_by_num(pokemon.species_id)

            if pokemon.level + amount > 100:
                return await ctx.reply("Your pokemon can't cross level 100!", mention_author=False)

            member.balance -= price
            pokemon.level += amount

            embed: discord.Embed = self.bot.Embed(title="⬆️ Level up!")
            embed.description = (
                f"Congratulations {ctx.author.display_name}! Your {pokemon:n} is now **level {pokemon.level}**!"
            )

            if pokemon.held_item != 13001 and (evo := pokemon.get_next_evolution()) is not None:
                specie: dict = data.species_by_num(evo)
                embed.add_field(
                    name=f"Woah! Your {pokemon:n} is evolving!",
                    value=f"Your {pokemon:n} turned into a **{specie['names']['9']}**!",
                )

                embed.set_thumbnail(url=specie["sprites"].__getitem__("normal"))

                pokemon.species_id = specie["species_id"]

            await member.save()

            await pokemon.save()

            return await ctx.reply(embed=embed, mention_author=False)

        elif args.startswith("nature"):
            nature: str = args.replace("nature ", "").title()

            if nature not in NATURES:
                return await ctx.reply(
                    f"There is no nature available like `{nature}`!",
                    mention_author=False,
                )

            pokemon: models.Pokemon = await self.bot.manager.fetch_selected_pokemon(ctx.author.id)

            if pokemon is None:
                raise NoSelectedPokemon(ctx)

            if pokemon.nature.lower() == nature.lower():
                return await ctx.reply("Your pokemon is already having that nature!", mention_author=False)

            if member.balance < 50:
                return not_enough_balance(ctx)

            member.balance -= 50
            pokemon.nature = nature

            await member.save()
            await pokemon.save()

            return await ctx.reply(
                f"Successfully changed the nature of your selected pokemon to {nature}!",
                mention_author=False,
            )

        elif args.startswith("mega"):
            choice: str = args.replace("mega", "").replace(" ", "")

            pokemon: models.Pokemon = await self.bot.manager.fetch_selected_pokemon(ctx.author.id)
            if pokemon is None:
                raise NoSelectedPokemon(ctx)

            species: dict = data.species_by_num(pokemon.species_id)

            if choice == "":
                attr: str = "mega"
                item_id: int = 12001
            elif choice == "x":
                attr: str = "mega_x"
                item_id: int = 12002
            elif choice == "y":
                attr: str = "mega_y"
                item_id: int = 12003

            else:
                return await ctx.reply("That mega item doesn't seem to exist!", mention_author=False)

            if species.__getitem__(f"{attr}_id") is None:
                return await ctx.reply(
                    "Your pokemon doesn't have such evolution type.",
                    mention_author=False,
                )

            item = data.item_by_id(item_id)

            if member.balance < int(item["cost"]):
                return await not_enough_balance(ctx)

            member.balance -= int(item["cost"])
            pokemon.mega_items = ArrayAppend("mega_items", item.__getitem__("id"))

            await member.save()
            await pokemon.save()

            return await ctx.reply(
                f"You can now evolve your pokemon using `{ctx.prefix}{attr.replace('_', ' ')}`",
                mention_author=False,
            )

        elif args.startswith("item"):
            item_name: str = args.replace("item ", "")
            item = data.item_by_name(item_name)

            if item is None or item.__getitem__("page") != 4:
                raise PokeBestError(
                    f"Hey, I guess `{item_name}` is not a valid held item. To see the list of held items use `{ctx.prefix}shop` command and select Page 4 - Held items."
                )

            if item["cost"] > member.balance:
                return await not_enough_balance(ctx)

            pokemon: models.Pokemon = await self.bot.manager.fetch_selected_pokemon(ctx.author.id)

            if pokemon is None:
                raise NoSelectedPokemon(ctx)

            await self.bot.manager.update_pokemon(pokemon.id, held_item=item["id"])
            await self.bot.manager.update_member(ctx.author.id, balance=member.balance - item["cost"])

            return await ctx.reply(
                f"You bought a `{item['name']}` for your {pokemon:l} to hold!",
                mention_author=False,
            )

        elif args.lower().startswith("stone ") or args.lower() == "friendship bracelet":
            if args.startswith("stone "):
                _ritem_name: list = args.split(" ")
                _ritem_name.reverse()
                item_name: str = " ".join(_ritem_name)
            else:
                item_name: str = args

            item: dict = data.item_by_name(item_name)

            if item["page"] != 2 or item is None:
                raise PokeBestError(
                    f"Hey, I guess `{item_name}` is not a valid stone or friendship bracelet. To see the list of held items use `{ctx.prefix}shop` command and select Page 2 - Rare Stones & Evolution items."
                )

            pokemon: models.Pokemon = await self.bot.manager.fetch_selected_pokemon(ctx.author.id)

            if pokemon is None:
                raise NoSelectedPokemon(ctx)

            if not pokemon.specie.__getitem__("evolution_to"):
                return await ctx.reply(
                    "Your pokemon can't evolve with this item. Please try selecting a valid one.",
                    mention_author=False,
                )

            try:
                evdata: dict = data.pokemon_evolution_data(pokemon.specie["evolution_to"][0])
                if evdata.__getitem__("trigger_item_id") == item["id"]:
                    evoto: int = pokemon.specie["evolution_to"].__getitem__(0)

                else:
                    return await ctx.reply("Your pokemon doesn't evolve this way.", mention_author=False)

            except:
                return await ctx.reply("Internal error :/ Please try again later.", mention_author=False)

            if member.balance < item.__getitem__("cost"):
                return await not_enough_balance(ctx)

            evo_species: dict = data.species_by_num(evoto)
            member.balance -= item.__getitem__("cost")
            pokemon.species_id = evo_species.__getitem__("species_id")

            await member.save()
            await pokemon.save()

            return await ctx.reply(
                f"Your pokemon evolved to {self.bot.sprites.get(pokemon.specie['dex_number'], pokemon.shiny)} {pokemon}!",
                mention_author=False,
            )

        elif args.lower().startswith("form"):
            _mem: models.Member = await self.bot.manager.fetch_member_info(ctx.author.id)
            
            if _mem.vote_total >= 100 or _mem.vote_streak >= 100:
                name: str = args.replace("form ", "")
                species: dict = data.species_by_name(name)

                if species is None:
                    raise PokeBestError(
                        f"Hey, I guess `{name}` is not a valid form. To see the list of forms use `{ctx.prefix}shop` command and select Page 6 - Forms."
                    )

                pokemon: models.Pokemon = await self.bot.manager.fetch_selected_pokemon(ctx.author.id)

                if pokemon is None:
                    raise NoSelectedPokemon(ctx)

                try:
                    form_data: dict = SHOP_FORMS[pokemon.specie["names"]["9"].lower()]
                except KeyError:
                    raise PokeBestError(
                        f"Looks like this form isn't compatible for your selected pokemon. Try selecting any other using `{ctx.prefix}select` command and to see your pokemon collection use `{ctx.prefix}pokemon` command."
                    )

                cost: int = form_data.__getitem__("cost")
                all_forms: List[str] = form_data.__getitem__("forms")

                if pokemon.species_id == species["species_id"] or name not in all_forms:
                    raise PokeBestError(
                        f"Looks like this form isn't compatible for your selected pokemon. Try selecting any other using `{ctx.prefix}select` command and to see your pokemon collection use `{ctx.prefix}pokemon` command."
                    )

                if member.balance < cost:
                    return await not_enough_balance(ctx)

                await self.bot.manager.update_member(ctx.author.id, balance=member.balance - cost)
                await self.bot.manager.update_pokemon(pokemon.id, species_id=species["species_id"])

                return await ctx.reply(
                    f"Your {pokemon:l} evolved into a {species['names']['9'].title()}!",
                    mention_author=False,
                )
            else:
                return await ctx.reply("Sorry, the items here are out of stock.", mention_author=False)

        elif args.lower() == "shiny charm":
            item: dict = data.item_by_name(args.lower())

            if member.shiny_charm is not None:
                return await ctx.reply(
                    "You already have a shiny charm activated on your profile!",
                    mention_author=False,
                )

            if member.shards < item["cost"]:
                return await not_enough_balance(ctx)

            await self.bot.manager.update_member(
                ctx.author.id,
                shiny_charm=datetime.utcnow() + timedelta(days=7),
                shards=member.shards - item["cost"],
            )

            return await ctx.reply(
                "Your shiny chance has been increased by **20%** for **1 week**!",
                mention_author=False,
            )

        elif args.lower() == "spawn boost":
            item: dict = data.item_by_name(args.lower())
            guild: models.Guild = await self.bot.manager.fetch_guild(ctx.guild.id)

            if guild.spawn_boost is not None:
                return await ctx.reply(
                    "This server already has one spawn boost active!",
                    mention_author=False,
                )

            if member.shards < item["cost"]:
                return await not_enough_balance(ctx)

            await self.bot.manager.update_guild(ctx.guild.id, spawn_boost=datetime.utcnow() + timedelta(hours=24))

            await self.bot.manager.update_member(ctx.author.id, shards=member.shards - item["cost"])

            return await ctx.reply(
                "Spawns are now boosted from next **24 hours**!",
                mention_author=False,
            )

        elif args.lower().startswith("redeem"):
            __str_amount: str = args.replace("redeem ", "")
            try:
                amount: int = int(__str_amount)
            except BaseException:
                return await ctx.reply("Please provide a valid number.", mention_author=False)

            if amount < 1:
                return await ctx.reply("Amount must be positive number!", mention_author=False)

            item: dict = data.item_by_name("redeem")

            if member.shards < item["cost"] * amount:
                return await not_enough_balance(ctx)

            await self.bot.manager.update_member(
                ctx.author.id,
                shards=member.shards - (item["cost"] * amount),
                redeems=member.redeems + amount,
            )

            return await ctx.reply(f"Successfully purchased {amount} redeem(s)!", mention_author=False)

        elif args.lower().startswith("tm"):
            tm_name: str = args.replace("tm ", "")
            try:
                machine: dict = data.machine_by_number(int(tm_name) - 1)
            except (BaseException,):
                raise PokeBestError(
                    f"Looks like any technical machine like `{tm_name}` doesn't exists. To see the full list of TMs available, use `{ctx.prefix}tms` command!"
                )

            if machine is None:
                raise PokeBestError(
                    f"Looks like any technical machine like `{tm_name}` doesn't exists. To see the full list of TMs available, use `{ctx.prefix}tms` command!"
                )

            if int(machine["machine_numer"]) in member.technical_machines:
                return await ctx.reply("You already own this TM!", mention_author=False)

            if member.balance < int(machine["cost"]):
                return await not_enough_balance(ctx)

            await self.bot.manager.update_member(
                ctx.author.id,
                balance=member.balance - int(machine["cost"]),
                technical_machines=ArrayAppend(int(machine.__getitem__("machine_number"))),
            )

            return await ctx.reply(f"Successfully purchased `{tm_name}` TM!", mention_author=False)

        elif args.lower() == "gift":
            # Hardcoded the price for a bit
            if member.shards < 50:
                return await not_enough_balance(ctx)

            member.shards -= 50
            member.gift += 1
            await member.save()

            return await ctx.reply(f"Successfully purchased a gift {emojis.gift}!", mention_author=False)

        elif args.lower() == "christmas bundle" and config.CHRISTMAS_MODE:
            if member.shards < 500:
                return await not_enough_balance(ctx)

            member.redeems += 1
            member.gift += 2

            pk: models.Pokemon = models.Pokemon.get_random(
                species_id=10394,
                level=random.randint(10, 40),
                xp=0,
                timestamp=datetime.utcnow(),
                owner_id=ctx.author.id,
                shiny=False,
                idx=member.next_idx,
            )

            member.next_idx += 1
            member.shards -= 500

            await member.save()

            await pk.save()

            return await ctx.reply(
                f"You received `1 redeem`, `2 gifts` and a `{pk:l}`! 🎅 Merry Christmas!",
                mention_author=False,
            )

        elif args.lower() == "santa pikachu" and config.CHRISTMAS_MODE:
            if member.shards < 10000:
                return await not_enough_balance(ctx)

            pk: models.Pokemon = models.Pokemon.get_random(
                species_id=10393,
                level=random.randint(10, 40),
                xp=0,
                timestamp=datetime.utcnow(),
                owner_id=ctx.author.id,
                shiny=True,
                idx=member.next_idx,
            )

            member.next_idx += 1
            member.shards -= 10000

            await member.save()

            await pk.save()

            return await ctx.reply(f"You received a *{pk:l}*! 🎅 Merry Christmas!", mention_author=False)

        elif args.lower() == "heart magikarp" and config.VALENTINES_MODE:
            if member.shards < 5000:
                return await not_enough_balance(ctx)

            pk: models.Pokemon = models.Pokemon.get_random(
                species_id=10397,
                level=random.randint(10, 40),
                xp=0,
                timestamp=datetime.utcnow(),
                owner_id=ctx.author.id,
                shiny=True,
                idx=member.next_idx,
            )

            member.next_idx += 1
            member.shards -= 5000

            await member.save()

            await pk.save()

            return await ctx.reply(
                f"You received a *{pk:l}*! 💝 Happy Valentines Day!",
                mention_author=False,
            )
        
        elif args.lower() == "starter eevee":
            if member.shards < 10000:
                return await not_enough_balance(ctx)
            
            pk: models.Pokemon = models.Pokemon.get_random(
                species_id=10159,
                level=random.randint(10, 40),
                xp=0,
                timestamp=datetime.utcnow(),
                owner_id=ctx.author.id,
                shiny=True,
                idx=member.next_idx,
            )

            member.next_idx += 1
            member.shards -= 10000

            await member.save()

            await pk.save()

            return await ctx.reply(f"You received a *{pk:l}*!", mention_author=False)

        elif args.lower() == "incense":
            if member.shards < 25:
                return await not_enough_balance(ctx)

            if await self.bot.redis.hexists("db:incense", ctx.author.id):
                return await ctx.reply("You already have an active incense!", mention_author=False)

            await self.bot.redis.hset("db:incense", ctx.author.id, 100)
            self.bot.cache.incense_timestamps[f"{ctx.author.id}"] = datetime.utcnow()

            member.shards -= 25
            await member.save()

            return await ctx.reply("You bought an incense!", mention_author=False)

        else:
            raise PokeBestError(
                f"That item doesn't seems to exist! Use `{ctx.prefix}shop` command to view the items available in the shop."
            )

    @commands.command(aliases=("bal",))
    @has_started()
    async def balance(self, ctx: commands.Context):
        """Check your balance"""
        member: models.Member = await self.bot.manager.fetch_member_info(ctx.author.id)

        _embed: discord.Embed = self.bot.Embed(
            title="💰 Your Balance:",
            description=f"```fix\n{member.balance} credit(s) | {member.shards} shard(s) | {member.redeems} redeem(s)\n```\n**Want some more credits?**\nVote for our bot [here]({config.TOP_GG_VOTE_LINK}) and get awesome rewards!",
        )

        _embed.set_author(name=ctx.author.__str__(), icon_url=ctx.author.avatar.url)

        await ctx.reply(embed=_embed, mention_author=False)

    ####################### TODO: MAKE REDEEMABLE CREDITS CUSTOM WITH OWNER COMMANDS ##########################
    @commands.command(aliases=("redeem",))
    @has_started()
    async def redeems(self, ctx: commands.Context, *, args: Optional[str] = None):  # sourcery no-metrics
        """Redeem any pokemon or get some credits"""
        member: models.Member = await self.bot.manager.fetch_member_info(ctx.author.id)
        if args is None:

            _emb: discord.Embed = self.bot.Embed(
                title=f"Your Redeems: {member.redeems}",
                description="Redeems are type of currencies which you can use to get a pokemon or even you can redeem `15000` credits!\n\n**Note:** Only normal and catchable pokemons are redeemable!",
            )

            _emb.add_field(
                name=f"{ctx.prefix}{ctx.command.qualified_name} <pokemon>",
                value="Redeem a pokemon directly in your account.",
                inline=True,
            )
            _emb.add_field(
                name=f"{ctx.prefix}{ctx.command.qualified_name} spawn <pokemon>",
                value="Spawn a pokemon in this channel.",
                inline=True,
            )
            _emb.add_field(
                name=f"{ctx.prefix}{ctx.command.qualified_name} credits",
                value="Instanty get 15000 credits.",
                inline=True,
            )

            return await ctx.reply(embed=_emb, mention_author=False)

        elif args is not None and args.lower().strip().split(" ")[0] not in [
            "spawn",
            "credits",
        ]:
            if member.redeems == 0:
                return await ctx.reply("You don't have redeems!", mention_author=False)

            species: dict = await SpeciesConverter().convert(ctx, args)

            if species["catchable"] is False:
                return await ctx.reply(
                    "Sorry, but this pokemon can't be obtained by using redeems.",
                    mention_author=False,
                )

            _next_idx: int = await self.bot.manager.get_next_idx(ctx.author.id)

            pokemon_res: models.Pokemon = models.Pokemon.get_random(
                species_id=species.__getitem__("species_id"),
                owner_id=ctx.author.id,
                level=random.randint(5, 40),
                xp=0,
                timestamp=datetime.now(),
                idx=_next_idx,
            )

            await pokemon_res.save()
            await self.bot.manager.update_idx(ctx.author.id)

            member.redeems -= 1
            await member.save()

            return await ctx.reply(f"You redeemed a `{pokemon_res:l}`!", mention_author=False)

        elif args is not None and "spawn" in args.lower().strip():
            if member.redeems == 0:
                return await ctx.reply("You don't have redeems!", mention_author=False)

            pokemon: dict = await SpeciesConverter().convert(ctx, args.replace("spawn ", ""))
            if pokemon is None:
                return await ctx.reply(
                    f"Any pokemon like `{args}` doesn't seems to exist. Maybe you spelled wrong.",
                    mention_author=False,
                )

            if pokemon["catchable"] is False:
                return await ctx.reply(
                    "Sorry, but this pokemon can't be obtained by using redeems.",
                    mention_author=False,
                )

            self.bot.spawn_cache[ctx.channel.id]["species_id"] = pokemon.__getitem__("species_id")

            member.redeems -= 1
            await member.save()

            self.bot.dispatch("spawn", ctx.channel, pokemon.__getitem__("species_id"), True)

        elif args is not None and args.lower().strip() == "credits":
            if member.redeems == 0:
                return await ctx.reply("You don't have redeems!", mention_author=False)

            member.balance += 15000

            member.redeems -= 1
            await member.save()

            return await ctx.reply(
                "Successfully added `15,000` credits to your account!",
                mention_author=False,
            )

        else:
            return

    @commands.command()
    @has_started()
    async def mega(self, ctx: commands.Context, args: str = ""):
        """Mega/unmega your pokemon"""
        _form_type: str = args.lower()
        if _form_type not in ("", "x", "y"):
            raise PokeBestError(
                f"That's not a valid mega item! To see the list of mega items use `{ctx.prefix}shop` command and select Page 5 - Mega Items."
            )

        _mem: models.Member = await self.bot.manager.fetch_member_info(ctx.author.id)
        if _mem.selected_id is None:
            raise NoSelectedPokemon(ctx)

        pokemon: Optional[models.Pokemon] = await models.Pokemon.filter(
            owner_id=ctx.author.id, idx=_mem.selected_id
        ).first()

        if args == "":
            attr: str = "mega"
            item_id: int = 12001
        elif args == "x":
            attr: str = "mega_x"
            item_id: int = 12002
        elif args == "y":
            attr: str = "mega_y"
            item_id: int = 12003

        if item_id not in pokemon.mega_items:
            raise PokeBestError(
                f"You don't have this mega item! To buy one use `{ctx.prefix}shop` command and select Page 5 - Mega Items."
            )

        current_specie: dict = pokemon.specie
        if not current_specie["names"]["9"].lower().startswith("mega "):
            specie: Optional[dict] = data.species_by_num(current_specie.__getitem__(f"{attr}_id"))

        else:
            specie: Optional[dict] = data.species_by_num(current_specie["dex_number"])

        if specie is None:
            return await ctx.reply("Your pokemon doesn't evolve this way!", mention_author=False)

        if not specie["names"]["9"].lower().startswith("mega "):
            msg: str = f"Your {pokemon} devolved back into **{specie['names']['9']}**!"
        else:
            msg: str = f"Your {pokemon} evolved into **{specie['names']['9']}**!"

        await self.bot.manager.update_pokemon(pokemon.id, species_id=specie["species_id"])

        await ctx.reply(msg, mention_author=False)

    @commands.command()
    @has_started()
    async def gift(self, ctx: commands.Context):
        """Open or give gift to a user"""
        mem: models.Member = await self.bot.manager.fetch_member_info(ctx.author.id)

        emb: discord.Embed = self.bot.Embed(
            title="Your Gifts:",
            description=f"{emojis.gift} You currently have *{mem.gift} gifts*!\n\n"
            + "**Instructions:**\nYou can use the `give` button to send this gift to someone or you can `open` it yourself using open button",
        )

        emb.set_author(name=f"{ctx.author}", icon_url=ctx.author.display_avatar)

        view: GiftView = GiftView(ctx)
        await ctx.reply(embed=emb, view=view, mention_author=False)

    # @commands.command()
    # @has_started()
    # async def tms(self, ctx: commands.Context, *, pokemon: SpeciesConverter):
    #     """Displays technical machines"""
    #     if not pokemon:
    #         available_tms = sorted()


def setup(bot: PokeBest) -> None:
    bot.add_cog(Shop(bot))
