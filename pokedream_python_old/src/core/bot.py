from pathlib import Path
from cogs.sprites import SpriteManager
import models
from discord.ext import commands
import discord
import jishaku
import asyncio
import aiohttp
import logging
import asyncpg
import aioredis

from typing import Any, Counter, List, Optional
from tortoise import Tortoise
import config
from cogs import __loadable__, __ready_cogs__
from cogs.database import Database
from utils.psqlclient import PostgresClient
from utils.cache import CacheManager
from utils.exceptions import SuspendedUser
from datetime import datetime
from ._logging import init_logging
from .rpc import RPCMixin
from aioredis_lock import RedisLock, LockTimeoutError

from rich.progress import track
from rich.table import Table
from rich.console import Console
import os
import time

console: Console = Console()

log = logging.getLogger(__name__)

os.environ["JISHAKU_HIDE"] = "True"
os.environ["JISHAKU_NO_UNDERSCORE"] = "True"
os.environ["JISHAKU_NO_DM_TRACEBACK"] = "True"
os.environ["OMP_THREAD_LIMIT"] = "1"

CONCURRENCY_LIMITED_COMMANDS: set = {
    "auction",
    "market",
    "evolve",
    "favorite",
    "nickall",
    "nickname",
    "reindex",
    "release",
    "select",
    "unfavorite",
    "mega",
    "buy",
    "dropitem",
    "moveitem",
    "redeems",
    "redeem",
    "trade",
    "gamble",
    "bet",
}


async def is_suspended(ctx: commands.Context):
    user: models.Member = await ctx.bot.manager.fetch_member_info(ctx.author.id)

    if not user:
        return True

    if user.suspended and ctx.author.id not in config.OWNERS:
        raise SuspendedUser(user.suspended_reason)

    return True


# ================================================================================================================================================================


class PokeBest(RPCMixin, commands.AutoShardedBot):
    def __init__(self, version):
        self.version = version
        self.log = log

        self.DEBUG = config.DEBUG_MODE
        init_logging(0, Path("logs\\PokeBest-core.log"))

        async def _prefix_manager(bot, message: discord.Message):
            if message.guild is None:
                return [
                    "p!",
                    "P!",
                    self.user.mention + " ",
                    self.user.mention[:2] + "!" + self.user.mention[2:] + " ",
                ]

            try:
                if bot.cache is None:
                    return ["p!", "P!"]
                guild: models.Guild = bot.cache.guilds[f"{message.guild.id}"]
            except KeyError:
                guild = None

            if guild is None:
                return [
                    "p!",
                    "P!",
                    self.user.mention + " ",
                    self.user.mention[:2] + "!" + self.user.mention[2:] + " ",
                ]

            return [
                guild.prefix.lower(),
                guild.prefix.upper(),
                self.user.mention + " ",
                self.user.mention[:2] + "!" + self.user.mention[2:] + " ",
            ]

        self.case_insensitive = True

        super().__init__(
            command_prefix=_prefix_manager,
            case_insenstive=True,
            chunk_guilds_at_startup=False,
            heartbeat_timeout=150.0,
            intents=discord.Intents(
                dm_messages=True,
                dm_reactions=True,
                dm_typing=True,
                emojis=True,
                guild_messages=True,
                guild_reactions=True,
                guilds=True,
                integrations=True,
                invites=True,
                messages=True,
                reactions=True,
                typing=True,
                webhooks=True,
                voice_states=True,
            ),
            slash_commands=True,
            enable_debug_events=True
            # slash_commands_guilds=[856535282458558494]
        )

        self.log.info("Hello, World!")

        # Loading cogs in init because of slash loading
        for _cog in __loadable__:
            self.load_extension(_cog)
            self.log.info("[COG ] Loaded %s" % _cog)

        self.loop = asyncio.get_event_loop()
        self.session = aiohttp.ClientSession(loop=self.loop)

        self.add_check(is_suspended)

        # .. Cache ..
        self.spawn_cache: dict = {}
        self.cache = None
        self.bot_config = None

        # Auto-spam control
        self.spam_control = commands.CooldownMapping.from_cooldown(10, 12.0, commands.BucketType.user)
        self._auto_spam_count = Counter()

        self.owner_id = 766553763569336340
        self.boot_time = datetime.utcnow()

        self.battles: list = []
        self.message_cache: dict = {}

        # self.shard_count = config.TOTAL_SHARDS
        # self.shard_ids = config.SHARDS_TO_USE

    @property
    def config(self) -> config:
        return __import__("config")

    @property
    def manager(self) -> Database:
        return self.get_cog("Database")

    @property
    def sprites(self) -> SpriteManager:
        return self.get_cog("SpriteManager")

    async def _init_bot(self):
        # psql_client: PostgresClient = PostgresClient(config.DATABASE_URI)
        # await psql_client.create_pool()

        await Tortoise.init(**config.TORTOISE_ORM)
        # await Tortoise.init(config=config.TORTOIS_ORM)
        await Tortoise.generate_schemas(safe=True)
        self.pool = Tortoise.get_connection("default")._pool

        self.log.info("[DATABASE ] Connected Successfully!")

        try:
            self.redis = await aioredis.create_redis_pool(address=config.REDIS_URI, password="myrediscluster")
            self.log.info("[REDIS ] Redis connected successfully!")
        except Exception as e:
            print(e)
            self.log.error("[REDIS ] Couldn't connect redis! Exiting...")
            quit()

        self.cache: CacheManager = CacheManager(self)
        await self.cache.fill_cache()
        self.log.info("[CACHE ] Loaded successfully!")

        for _, model in Tortoise.apps.get("models").items():
            model.bot = self

        _bot_configs: List[models.BotConfig] = await models.BotConfig.all()
        if _bot_configs.__len__() == 0:
            _bot_config: models.BotConfig = await models.BotConfig.create()
        else:
            _bot_config: models.BotConfig = _bot_configs[0]
        self.bot_config = _bot_config

        self.log.info("[CORE ] Bot's config loaded successfully!")

        await self.rpc.initialize()

        # Loading jsk here to save it from slash registration
        self.load_extension("jishaku")

        for _cog in __ready_cogs__:
            self.load_extension(_cog)

    class Embed(discord.Embed):
        def __init__(self, **kwargs):
            # color = kwargs.pop("color", 0x02FAFA)
            color = kwargs.pop("color", config.DEFAULT_COLOR)  # Yogi baba jindabad
            super().__init__(**kwargs, color=color)

    async def on_ready(self) -> None:
        await self._init_bot()

        # Show shards info
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Shard ID")
        table.add_column("Latency")
        table.add_column("Connected")

        for _id, shard in self.shards.items():
            table.add_row(str(_id), str(shard.latency), str(not shard.is_closed()))

        console.print(table)

        self.log.info("Bot is running...")

    async def db_latency(self) -> str:
        t1 = time.perf_counter()
        await self.pool.execute("SELECT 1;")
        t2 = time.perf_counter() - t1
        return f"{t2*1000:.2f} ms"

    @discord.utils.cached_property
    def stats_webhook(self) -> discord.Webhook:
        wh_id: int = config.STATS_WEBHOOK_ID
        wh_token: str = config.STATS_WEBHOOK_TOKEN

        return discord.Webhook.partial(id=wh_id, token=wh_token, session=self.session)

    async def log_spammer(
        self,
        ctx: commands.Context,
        message: discord.Message,
        retry_after,
        *,
        autoblock: bool = False,
    ):
        guild_name = getattr(ctx.guild, "name", "No guild (DMs)")
        guild_id = getattr(ctx.guild, "id", None)
        fmt = "User %s (ID %s) in guild %r (ID %s) spamming, retry_after: %.2fs"
        log.warning(fmt, message.author, message.author.id, guild_name, guild_id, retry_after)

        if not autoblock:
            return

        wh = self.stats_webhook
        embed: discord.Embed = self.Embed(title="⛔ Auto-blocked Member", color=0xDDA453)
        embed.add_field(
            name="Member",
            value=f"{message.author} (ID: {message.author.id})",
            inline=False,
        )
        embed.add_field(name="Guild Info", value=f"{guild_name} (ID: {guild_id})", inline=False)
        embed.add_field(
            name="Channel Info",
            value=f"{message.channel} (ID: {message.channel.id})",
            inline=False,
        )
        embed.timestamp = discord.utils.utcnow()

        return await wh.send(embed=embed)

    async def invoke(self, ctx: commands.Context):
        if ctx.command is None:
            return

        if not (
            ctx.command.name in CONCURRENCY_LIMITED_COMMANDS
            or (ctx.command.root_parent and ctx.command.root_parent.name in CONCURRENCY_LIMITED_COMMANDS)
        ):
            return await super().invoke(ctx)

        try:
            async with RedisLock(self.redis, f"command:{ctx.author.id}", 60, 1):
                return await super().invoke(ctx)
        except LockTimeoutError:
            await ctx.reply("You are already engaged in a command, please wait for it to finish.")

    async def process_commands(self, message: discord.Message) -> None:
        if message.author.bot:
            return

        ctx: commands.Context = await self.get_context(message, cls=commands.Context)

        if ctx.command is None:
            return

        bucket = self.spam_control.get_bucket(message)
        current = message.created_at.timestamp()
        retry_after = bucket.update_rate_limit(current)
        author_id = message.author.id

        if retry_after and author_id != self.owner_id:
            self._auto_spam_count[author_id] += 1
            if self._auto_spam_count[author_id] >= 5:
                mem: models.Member = await self.manager.fetch_member_info(author_id)
                mem.suspended = True
                mem.suspended_reason = "Auto-Spam control system blocked you."
                await mem.save()

                del self._auto_spam_count[author_id]
                await self.log_spammer(ctx, message, retry_after, autoblock=True)

            else:
                await self.log_spammer(ctx, message, retry_after)
            return

        else:
            self._auto_spam_count.pop(author_id, None)

        await self.invoke(ctx)

    async def on_guild_join(self, guild: discord.Guild):
        g: models.Guild = await self.manager.fetch_guild(guild.id)

        if g.blacklisted:
            await guild.leave()

    def bootup(self, *args: Any, **kwargs: Any) -> None:
        return super().run(*args, **kwargs)

    async def close(self):
        await self.session.close()
        await self.pool.close()
        self.redis.close()
        await Tortoise.close_connections()
        await super().close()
