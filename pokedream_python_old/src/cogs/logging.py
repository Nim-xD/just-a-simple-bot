from contextlib import suppress
import discord
from discord.colour import Color
from discord.ext import commands
from discord.ext.commands import flags
from core.bot import PokeBest
import random
from typing import List
import config
from rich.console import Console
import textwrap
import traceback
from discord.ext.flags import ArgumentParsingError
import models
from utils.emojis import Emojis

from utils.exceptions import SuspendedUser
from tortoise.exceptions import MultipleObjectsReturned

console = Console()


class Logging(commands.Cog):
    def __init__(self, bot: PokeBest) -> None:
        self.bot: PokeBest = bot

    @commands.Cog.listener()
    async def on_command_error(self, ctx: commands.Context, error):
        if isinstance(error, commands.CheckFailure) and not isinstance(error, SuspendedUser):
            _replies: List[str] = [
                "Uhh ohh....",
                "Something went wrong",
                "Error",
                "Oops!",
            ]

            _server_replies: List[str] = [
                "Stuck somewhere?",
                "Lost?",
                "Stuck?",
                "Lost somewhere?",
            ]

            try:
                _error_embed: discord.Embed = discord.Embed(
                    title=f"⚠️ | {random.choice(_replies)}",
                    color=discord.Color.red(),
                    description=error.__str__()
                    + f"\n\n**{random.choice(_server_replies)}** Consider joining our [support server]({config.SUPPORT_SERVER_LINK}).",
                )
                return await ctx.reply(embed=_error_embed, mention_author=False)
            except:
                return

        elif isinstance(error, commands.NotOwner):
            return await ctx.reply(
                embed=self.bot.Embed(
                    title="❌ Access Denied.",
                    description="This command can only be used by owners.",
                ),
                mention_author=False,
            )

        elif isinstance(error, commands.CommandNotFound):
            return

        elif isinstance(error, commands.MaxConcurrencyReached):
            return await ctx.reply(
                embed=self.bot.Embed(
                    title="⚠️ Maximum Concurreny Reached",
                    description="This command is already invoked somewhere in your server. Please let that finish then try again.",
                ),
                mention_author=False,
            )

        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.reply(
                f"⚠️ You missed the `{error.param.name}` argument.",
                mention_author=False,
            )
            helper = str(ctx.invoked_subcommand) if ctx.invoked_subcommand else str(ctx.command)
            return await ctx.send_help(helper)

        elif isinstance(error, commands.MissingPermissions):
            permissions = "\n".join(f"> {permission}" for permission in error.missing_perms)

            await ctx.reply(
                embed=self.bot.Embed(
                    title="⚠️ | Lacking Permissions!",
                    description=f"You lack **`{permissions}`** permissions to run this command.",
                ),
                mention_author=False,
            )

        elif isinstance(error, commands.CommandOnCooldown):
            return await ctx.reply(
                embed=self.bot.Embed(
                    title="⌛ | On cooldown!",
                    description=f"This command is on cooldown. Try again after `{error.retry_after:.2f}` second(s)!",
                ),
                mention_author=False,
            )

        elif isinstance(error, commands.MemberNotFound):
            return await ctx.reply(
                embed=self.bot.Embed(
                    title="❌| Member not found!",
                    description="Sorry, I can't find any member of the argument you provided in the comamnd.",
                    color=discord.Color.red(),
                ),
                mention_author=False,
            )

        elif isinstance(error, SuspendedUser):
            emb: discord.Embed = self.bot.Embed(
                title="❌ Account Suspended!",
                description=f"Your account has been suspended from using this bot! If you think there is any fault from our side you can appeal in our [support server]({config.SUPPORT_SERVER_LINK})!",
                color=discord.Color.red(),
            )

            if error.reason is not None:
                emb.add_field(name="Reason:", value=error.reason, inline=False)

            return await ctx.reply(embed=emb, mention_author=False)

        elif isinstance(error, tuple) and any(isinstance(e, MultipleObjectsReturned) for e in error):
            emb: discord.Embed = self.bot.Embed(
                title="ℹ️ Re-index Needed!",
                description=f"Hey there! I guess your pokemon collection has some pokemon in same index due to which this error is showing up. To fix this, use `{ctx.prefix}reindex` command. This will fix the indexes of your collection.",
            )

            return await ctx.reply(embed=emb, mention_author=False)

        elif isinstance(error, discord.Forbidden) or error == discord.Forbidden:
            ...

        elif isinstance(error, commands.CommandInvokeError):
            ...

        elif isinstance(error, ArgumentParsingError):
            emb: discord.Embed = self.bot.Embed(
                title="⚠️ | Invalid Argument!",
                description="Sorry, but you provided an invalid argument. Please try again.",
                color=discord.Color.red(),
            )
            return await ctx.reply(embed=emb, mention_author=False)

        else:
            # raise error
            emb: discord.Embed = self.bot.Embed(
                color=discord.Color.red(),
                title="⚠️ Uncaught Exception!",
                description=f"This command raised an uncaught exception. I *notified* my developers about it. However, you can check out out [support server]({config.SUPPORT_SERVER_LINK}) for more information."
                + f"```py\n{error}\n```",
            )

            with suppress(discord.Forbidden, discord.HTTPException):
                await ctx.reply(embed=emb, mention_author=False)

            # Send the error through hook
            error_hook: discord.Webhook = discord.Webhook.from_url(config.ERROR_LOG_WEBHOOK, session=self.bot.session)

            e: discord.Embed = discord.Embed(title="Command Error", colour=0xCC3366)
            e.add_field(name="Name", value=ctx.command.qualified_name)
            e.add_field(name="Author", value=f"{ctx.author} (ID: {ctx.author.id})")

            fmt = f"Channel: {ctx.channel} (ID: {ctx.channel.id})"
            if ctx.guild:
                fmt = f"{fmt}\nGuild: {ctx.guild} (ID: {ctx.guild.id})"

            e.add_field(name="Location", value=fmt, inline=False)
            e.add_field(name="Content", value=textwrap.shorten(ctx.message.content, width=512))

            exc = "".join(traceback.format_exception(type(error), error, error.__traceback__, chain=False))
            e.description = f"```py\n{exc}\n```"

            self.bot.log.error(exc)

            e.timestamp = discord.utils.utcnow()
            await error_hook.send(embed=e)

    @commands.Cog.listener()
    async def on_command(self, ctx: commands.Context):
        self.bot.log.info(
            f"COMMAND {ctx.command.qualified_name} | GUILD: {ctx.guild.id} USERID: {ctx.author.id} CHANNEL: {ctx.channel.id}"
        )

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if (
            after.guild.id == config.SUPPORT_SERVER_ID
            and before.premium_since is None
            and after.premium_since is not None
        ):
            self.bot.dispatch("support_server_boost", after, "50 shards")

        elif (
            after.guild.id == config.SUPPORT_SERVER_ID
            and before.premium_since is not None
            and after.premium_since is not None
        ):
            self.bot.dispatch("support_server_boost", after, "1 redeem")

    @commands.Cog.listener()
    async def on_support_server_boost(self, member: discord.Member, to_give: str):
        mem: models.Member = await self.bot.manager.fetch_member_info(member.id)

        if to_give == "50 shards":
            mem.shards += 50
        elif to_give == "1 redeem":
            mem.redeems += 1

        with suppress(discord.Forbidden, discord.HTTPException):
            emb: discord.Embed = self.bot.Embed(
                title="💖 Thanks for boosting!",
                description=f"Thanks for {Emojis().booster} boosting our server! As a reward, you have been given *{to_give}*! More perks coming soon.",
                color=0xFA6EF6,
            )

            await member.send(embed=emb)

        await mem.save()

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        guild_log_webhook: discord.Webhook = discord.Webhook.from_url(
            "https://canary.discord.com/api/webhooks/943075833696886824/fFv5Ud_glrSnzsk3jnIe0csEDrrjlk1ZjkWc6sTgi6MlXkzaOj6LbAf6Aw1ce79FIPkz",
            session=self.bot.session,
        )
        emb: discord.Embed = self.bot.Embed(title="Joined a Guild!", color=discord.Color.green())

        emb.add_field(name="Name", value=guild.name)
        emb.add_field(name="ID", value=guild.id)
        emb.add_field(name="Owner", value=guild.owner)
        emb.add_field(name="Owner ID", value=guild.owner_id)
        emb.add_field(name="Timestamp", value=discord.utils.format_dt(discord.utils.utcnow()))

        await guild_log_webhook.send(embed=emb)

    @commands.Cog.listener()
    async def on_guild_leave(self, guild: discord.Guild):
        guild_log_webhook: discord.Webhook = discord.Webhook.from_url(
            "https://canary.discord.com/api/webhooks/943075833696886824/fFv5Ud_glrSnzsk3jnIe0csEDrrjlk1ZjkWc6sTgi6MlXkzaOj6LbAf6Aw1ce79FIPkz",
            session=self.bot.session,
        )

        emb: discord.Embed = self.bot.Embed(title="Left a Guild!", color=discord.Color.red())

        emb.add_field(name="Name", value=guild.name)
        emb.add_field(name="ID", value=guild.id)
        emb.add_field(name="Owner", value=guild.owner)
        emb.add_field(name="Owner ID", value=guild.owner_id)
        emb.add_field(name="Timestamp", value=discord.utils.format_dt(discord.utils.utcnow()))

        await guild_log_webhook.send(embed=emb)

    @commands.Cog.listener()
    async def on_new_player(self, mem: discord.Member):
        start_log_webhook: discord.Webhook = discord.Webhook.from_url(
            "https://canary.discord.com/api/webhooks/943508154942099456/T5GEYz8nowrY0zLLhNSEWJy0wvIMpdGZ5xUyUe3MJ3BLQN8ZeY2NB2CAc6CtqWxX4Z_W",
            session=self.bot.session,
        )

        emb: discord.Embed = self.bot.Embed(title="New Trainer Registered!", color=discord.Color.green())

        emb.add_field(name="Name", value=mem.name)
        emb.add_field(name="ID", value=mem.id)

        emb.add_field(name="Timestamp", value=discord.utils.format_dt(discord.utils.utcnow()))

        await start_log_webhook.send(embed=emb)

    @commands.Cog.listener()
    async def on_catch(self, ctx: commands.Context, pokemon: models.Pokemon):
        if not pokemon.shiny:
            return
        shiny_hook: discord.Webhook = discord.Webhook.from_url(
            "https://canary.discord.com/api/webhooks/942094314538958849/MNf2GLLLjJFfkri8QoeOEJfId3JVw3qJEM5BXBBumsqrtmmbRR9l7RvuL23w91DgaMkh",
            session=self.bot.session,
        )

        emb: discord.Embed = discord.Embed(title="Shiny Caught")
        emb.add_field(name="User", value=ctx.author.name)
        emb.add_field(name="User ID", value=ctx.author.id)
        emb.add_field(name="Guild ID", value=ctx.guild.id)
        emb.add_field(name="Guild name", value=ctx.guild.name)

        await shiny_hook.send(embed=emb)


def setup(bot: PokeBest) -> None:
    bot.add_cog(Logging(bot))
