from __future__ import annotations
from discord.enums import ButtonStyle

from discord.ext import commands
import discord
import typing
import time

from discord.mentions import AllowedMentions
from discord.permissions import Permissions
from discord.ui.button import button
from core.views import CustomButton, CustomButtonView
from utils.emojis import emojis

if typing.TYPE_CHECKING:
    from core.bot import PokeBest
    from cogs.trading import Trading

from config import OWNERS
from utils.time import human_timedelta
import psutil
from models import models
import pickle
import config


class General(commands.Cog):
    def __init__(self, bot: PokeBest) -> None:
        self.bot: PokeBest = bot

        self.cd: commands.CooldownMapping = commands.CooldownMapping.from_cooldown(1, 2, commands.BucketType.user)

    async def bot_check(self, ctx: commands.Context) -> bool:
        if ctx.invoked_with.lower() == "help":
            return True

        bucket = self.cd.get_bucket(ctx.message)
        if retry_after := bucket.update_rate_limit():
            raise commands.CommandOnCooldown(bucket, retry_after)

        return True

    async def bot_check(self, ctx: commands.Context) -> bool:
        trade_cog: "Trading" = self.bot.get_cog("Trading")
        if trade_cog.is_in_trade(ctx.author) and ctx.command.qualified_name not in (
            "info",
            "pokemon",
            "pk",
            "p",
            "bal",
            "balance",
            "trade",
            "trade add",
            "trade remove",
            "trade addall",
            "trade removeall",
            "trade cancel",
        ):
            await ctx.reply("You can't use this command while in trade.")
            return False
        return True

    @commands.command()
    async def ping(self, ctx: commands.Context):
        """Shows the latency of bot"""
        ping_at: float = time.monotonic()
        message: discord.Message = await ctx.reply("Pinging...", mention_author=False)
        diff = "%.2f" % (1000 * (time.monotonic() - ping_at))

        emb: discord.Embed = self.bot.Embed()
        emb.add_field(name=f"{emojis.typing} | Typing", value=f"`{diff} ms`")
        emb.add_field(name="🔌 | Websocket", value=f"`{round(self.bot.latency*1000, 2)} ms`")

        emb.add_field(
            name=f"{emojis.database} | Database",
            value=f"`{await self.bot.db_latency()}`",
        )

        await message.edit(content=None, embed=emb, allowed_mentions=AllowedMentions.none())

    @commands.command()
    async def stats(self, ctx: commands.Context):
        """How's the bot doing?"""
        emb: discord.Embed = self.bot.Embed()
        emb.set_author(name=f"{self.bot.user.name} Stats", icon_url=self.bot.user.display_avatar)

        emb.add_field(name="👪 Servers", value=f"┕`{len(self.bot.guilds)}`")
        emb.add_field(name=":ping_pong: Ping", value=f"┕`{self.bot.latency:.2f}ms`")
        emb.add_field(name="⏳ Memory Usage", value=f"┕`{psutil.virtual_memory().percent}%`")
        emb.add_field(name="⏳ CPU Usage", value=f"┕`{psutil.cpu_percent()}%`")
        emb.add_field(name="📂 Trainers", value=f"┕`{len(await models.Member.all())}`")
        emb.add_field(name="⏱ Uptime", value=f"┕`{human_timedelta(self.bot.boot_time)}`")

        emb.add_field(name="🤖 Shards", value=f"┕`{self.bot.shard_count}`")
        emb.add_field(
            name="🤝 Support Server",
            value=f"┕[`Click Here`]({config.SUPPORT_SERVER_LINK})",
        )
        emb.add_field(name="👑 Owners", value=f"┕`Scypher#9996`, `LemoN#1226`, `Valentín#1080`")

        await ctx.reply(embed=emb, mention_author=False)

    @commands.command()
    async def invite(self, ctx: commands.Context):
        """Invite bot to your server"""
        emb: discord.Embed = self.bot.Embed(
            title="Invite Me!",
            description=f"To invite me, either [click here]({discord.utils.oauth_url(self.bot.user.id, permissions=Permissions.all())}) or click the button below!",
        )

        buttons: typing.List[CustomButton] = [
            discord.ui.Button(
                style=ButtonStyle.link,
                label="Invite",
                url=discord.utils.oauth_url(
                    self.bot.user.id,
                    permissions=Permissions.all(),
                    scopes=("applications.commands",),
                ),
            )
        ]

        view: CustomButtonView = CustomButtonView(ctx, buttons, disable_button=False)

        await ctx.reply(embed=emb, view=view, mention_author=False)

    @commands.command()
    async def support(self, ctx: commands.Context):
        """Join our support server"""
        emb: discord.Embed = self.bot.Embed(
            title="Support Server!",
            description=f"To join support server, either [click here]({config.SUPPORT_SERVER_LINK}) or click the button below!",
        )

        buttons: typing.List[CustomButton] = [
            discord.ui.Button(
                style=ButtonStyle.link,
                label="Support Server",
                url=config.SUPPORT_SERVER_LINK,
            )
        ]

        view: CustomButtonView = CustomButtonView(ctx, buttons, disable_button=False)

        await ctx.reply(embed=emb, view=view, mention_author=False)

    @commands.command()
    async def donate(self, ctx: commands.Context):
        """Donate to the bot"""
        # scy: discord.User = self.bot.get_user(766553763569336340) or await self.bot.fetch_user(766553763569336340)
        # lemon: discord.User = self.bot.get_user(839891608774508575) or await self.bot.fetch_user(839891608774508575)

        txt: str = (
            f"To donate to the bot, you can go to following links [Website Store](https://www.pokebest.net/store/inr-usd) | [Patreon](https://www.patreon.com/Pokebest?fan_landing=true) | [Ko-fi](https://ko-fi.com/pokebest/shop) or click the button below!"
            # + f"\n\n**Instructions:**\n> - After donating, you can claim your perks by dming `{scy}` or `{lemon}` by sending the screeshot of the donation.\n> - Join our [support server]({config.SUPPORT_SERVER_LINK}) for more info."
        )

        buttons: typing.List[CustomButton] = [
            discord.ui.Button(
                style=ButtonStyle.link,
                label="Website",
                url="https://www.pokebest.net/store/inr-usd",
            ),
            discord.ui.Button(
                style=ButtonStyle.link,
                label="Patreon",
                url="https://www.patreon.com/Pokebest?fan_landing=true",
            ),
            discord.ui.Button(
                style=ButtonStyle.link,
                label="Ko-Fi",
                url="https://ko-fi.com/pokebest/shop",
            ),
        ]

        view: CustomButtonView = CustomButtonView(ctx, buttons, disable_button=False)

        await ctx.reply(
            embed=self.bot.Embed(title="Donate us 😄", description=txt),
            view=view,
            mention_author=False,
        )


def setup(bot: PokeBest) -> None:
    bot.add_cog(General(bot))
