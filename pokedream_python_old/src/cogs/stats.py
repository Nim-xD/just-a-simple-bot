from __future__ import annotations

import discord
from discord.ext import commands, tasks
import typing
import asyncio

if typing.TYPE_CHECKING:
    from core.bot import PokeBest

from utils import time
import textwrap
import datetime
import logging
import psutil
import os

log = logging.getLogger(__name__)


class GatewayHandler(logging.Handler):
    def __init__(self, cog):
        self.cog = cog
        super().__init__(logging.INFO)

    def filter(self, record):
        return record.name == "discord.gateway" or "Shard ID" in record.msg or "Websocket closed " in record.msg

    def emit(self, record):
        self.cog.add_record(record)


class BotStats(commands.Cog):
    def __init__(self, bot: PokeBest) -> None:
        self.bot: PokeBest = bot

        self._gateway_queue: asyncio.Queue = asyncio.Queue(loop=self.bot.loop)
        self.gateway_worker.start()
        self.process = psutil.Process()

    def add_record(self, record):
        self._gateway_queue.put_nowait(record)

    async def notify_gateway_status(self, record):
        attributes = {"INFO": "\N{INFORMATION SOURCE}", "WARNING": "\N{WARNING SIGN}"}

        emoji = attributes.get(record.levelname, "\N{CROSS MARK}")
        dt = datetime.datetime.utcfromtimestamp(record.created)
        msg = textwrap.shorten(f"{emoji} [{time.format_dt(dt)}] `{record.message}`", width=1990)
        await self.bot.stats_webhook.send(msg, username="Gateway", avatar_url="https://i.imgur.com/4PnCKB3.png")

    @tasks.loop(seconds=0.0)
    async def gateway_worker(self):
        if self.bot.DEBUG:
            return

        record = await self._gateway_queue.get()
        await self.notify_gateway_status(record)

    @commands.command(hidden=True)
    @commands.is_owner()
    async def bothealth(self, ctx):
        """Various bot health monitoring tools."""

        # This uses a lot of private methods because there is no
        # clean way of doing this otherwise.

        HEALTHY = discord.Colour(value=0x43B581)
        UNHEALTHY = discord.Colour(value=0xF04947)
        WARNING = discord.Colour(value=0xF09E47)
        total_warnings = 0

        embed = discord.Embed(title="Bot Health Report", colour=HEALTHY)

        # Check the connection pool health.
        pool = self.bot.pool
        total_waiting = len(pool._queue._getters)
        current_generation = pool._generation

        description = [
            f"Total `Pool.acquire` Waiters: {total_waiting}",
            f"Current Pool Generation: {current_generation}",
            f"Connections In Use: {len(pool._holders) - pool._queue.qsize()}",
        ]

        questionable_connections = 0
        connection_value = []
        for index, holder in enumerate(pool._holders, start=1):
            generation = holder._generation
            in_use = holder._in_use is not None
            is_closed = holder._con is None or holder._con.is_closed()
            display = f"gen={holder._generation} in_use={in_use} closed={is_closed}"
            questionable_connections += any((in_use, generation != current_generation))
            connection_value.append(f"<Holder i={index} {display}>")

        joined_value = "\n".join(connection_value)
        embed.add_field(name="Connections", value=f"```py\n{joined_value}\n```", inline=False)

        spam_control = self.bot.spam_control
        being_spammed = [str(key) for key, value in spam_control._cache.items() if value._tokens == 0]

        description.append(f'Current Spammers: {", ".join(being_spammed) if being_spammed else "None"}')
        description.append(f"Questionable Connections: {questionable_connections}")

        total_warnings += questionable_connections
        if being_spammed:
            embed.colour = WARNING
            total_warnings += 1

        try:
            task_retriever = asyncio.Task.all_tasks
        except AttributeError:
            # future proofing for 3.9 I guess
            task_retriever = asyncio.all_tasks
        else:
            all_tasks = task_retriever(loop=self.bot.loop)

        event_tasks = [t for t in all_tasks if "Client._run_event" in repr(t) and not t.done()]

        cogs_directory = os.path.dirname(__file__)
        tasks_directory = os.path.join("discord", "ext", "tasks", "__init__.py")
        inner_tasks = [t for t in all_tasks if cogs_directory in repr(t) or tasks_directory in repr(t)]

        bad_inner_tasks = ", ".join(hex(id(t)) for t in inner_tasks if t.done() and t._exception is not None)
        total_warnings += bool(bad_inner_tasks)
        embed.add_field(
            name="Inner Tasks",
            value=f'Total: {len(inner_tasks)}\nFailed: {bad_inner_tasks or "None"}',
        )
        embed.add_field(name="Events Waiting", value=f"Total: {len(event_tasks)}", inline=False)

        # command_waiters = len(self._data_batch)
        # is_locked = self._batch_lock.locked()
        # description.append(f'Commands Waiting: {command_waiters}, Batch Locked: {is_locked}')

        memory_usage = self.process.memory_full_info().uss / 1024 ** 2
        cpu_usage = self.process.cpu_percent() / psutil.cpu_count()
        embed.add_field(
            name="Process",
            value=f"{memory_usage:.2f} MiB\n{cpu_usage:.2f}% CPU",
            inline=False,
        )

        global_rate_limit = not self.bot.http._global_over.is_set()
        description.append(f"Global Rate Limit: {global_rate_limit}")

        # if command_waiters >= 8:
        #     total_warnings += 1
        #     embed.colour = WARNING

        if global_rate_limit or total_warnings >= 9:
            embed.colour = UNHEALTHY

        embed.set_footer(text=f"{total_warnings} warning(s)")
        embed.description = "\n".join(description)
        await ctx.send(embed=embed)


def setup(bot: PokeBest) -> None:
    cog: BotStats = BotStats(bot)
    bot.add_cog(cog)

    bot._stats_cog_gateway_handler = handler = GatewayHandler(cog)
    logging.getLogger().addHandler(handler)
