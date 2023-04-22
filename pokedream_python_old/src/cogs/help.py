import typing
from discord.ext import commands
import discord
from config import SUPPORT_SERVER_LINK
from contextlib import suppress


# TODO: REFACTOR THIS SHIT
class HelpDropDown(discord.ui.Select):
    def __init__(self, context: commands.Context):
        self.context: commands.Context = context
        options: typing.List[discord.SelectOption] = [
            discord.SelectOption(
                label="Page 1 | Getting Started",
                description="List of commands to get you started with bot.",
            ),
            discord.SelectOption(
                label="Page 2 | Pokemon Commands",
                description="Some pokemon related commands.",
            ),
            discord.SelectOption(
                label="Page 3 | Shop, Market, Auction and Trading.",
                description="Commands related to shop, market and trading.",
            ),
            discord.SelectOption(
                label="Page 4 | Settings",
                description="Commands related to bot configuration.",
            ),
        ]

        super().__init__(placeholder="Choose a page.", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        emb: discord.Embed = self.context.bot.Embed()
        emb.set_author(name="PokeBest Commands", icon_url=self.context.bot.user.display_avatar)

        if "1" in self._selected_values[0]:
            emb.title = "Getting Started"
            cmds = ["start", "pick", "help"]
            for cmd in cmds:
                command: commands.Command = self.context.bot.get_command(cmd)
                emb.add_field(
                    name=f"{command.qualified_name}",
                    value=command.short_doc if command.short_doc is not None else "No help provided...",
                )

            await interaction.response.send_message(embed=emb, ephemeral=True)

        elif "2" in self._selected_values[0]:
            emb.title = "Pokemon Commands"
            cmds = [c.qualified_name for c in self.context.bot.get_cog("Pokemon").get_commands()]
            cmds += [c.qualified_name for c in self.context.bot.get_cog("MessageHandler").get_commands()]
            cmds += [c.qualified_name for c in self.context.bot.get_cog("Dueling").get_commands()]
            cmds += [c.qualified_name for c in self.context.bot.get_cog("Gambling").get_commands()]

            for cmd in cmds:
                command: commands.Command = self.context.bot.get_command(cmd)
                emb.add_field(
                    name=f"{command.qualified_name}",
                    value=command.short_doc
                    if command.short_doc is not None or len(command.short_doc) != 0
                    else "No help provided...",
                )

            await interaction.response.send_message(embed=emb, ephemeral=True)

        elif "3" in self._selected_values[0]:
            emb.title = "Shop, Market, Auction and Trading"
            cmds = [c.qualified_name for c in self.context.bot.get_cog("Shop").get_commands()]
            cmds += [c.qualified_name for c in self.context.bot.get_cog("Trading").get_commands()]
            cmds += [c.qualified_name for c in self.context.bot.get_cog("Auction").get_commands()]
            cmds += [c.qualified_name for c in self.context.bot.get_cog("Market").get_commands()]

            for cmd in cmds:
                command: commands.Command = self.context.bot.get_command(cmd)
                emb.add_field(
                    name=f"{command.qualified_name}",
                    value=command.short_doc if command.short_doc is not None else "No help provided...",
                )

            await interaction.response.send_message(embed=emb, ephemeral=True)

        elif "4" in self._selected_values[0]:
            emb.title = "Settings"
            cmds = [c.qualified_name for c in self.context.bot.get_cog("Settings").get_commands()]

            for cmd in cmds:
                command: commands.Command = self.context.bot.get_command(cmd)
                emb.add_field(
                    name=f"{command.qualified_name}",
                    value=command.short_doc if command.short_doc is not None else "No help provided...",
                )

            await interaction.response.send_message(embed=emb, ephemeral=True)


class HelpView(discord.ui.View):
    def __init__(self, ctx: commands.Context):
        self.ctx: commands.Context = ctx
        super().__init__(timeout=100)

        self.add_item(HelpDropDown(ctx))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message(
                "Sorry, you can't use this interaction as it is not started by you.",
                ephemeral=True,
            )
            return False
        return True

    async def on_timeout(self) -> None:
        for child in self.children:
            child.disabled = True
        with suppress(discord.NotFound):
            # await self._paginator_obj._context.message.edit(view=None)
            self.stop()


class HelpCommand(commands.HelpCommand):
    def __init__(self) -> None:
        super().__init__(command_attrs={"help": "Show help about the bot, a command, or a category."})

    def get_command_signature(self, command):
        parent = command.full_parent_name
        if len(command.aliases) > 0:
            aliases = "|".join(command.aliases)
            fmt = f"[{command.name}|{aliases}]"
            if parent:
                fmt = f"{parent} {fmt}"
            alias = fmt
        else:
            alias = command.name if not parent else f"{parent} {command.name}"
        return f"{alias} {command.signature}"

    async def send_bot_help(self, mapping):
        emb: discord.Embed = self.context.bot.Embed(
            description=f"Things to remeber - `[]` = Optional Parameter, `<>` = Required Paramter.\nType `{self.context.prefix}help [command]` to see detailed help.\n[Support Server]({SUPPORT_SERVER_LINK}) | [Invite Me]({SUPPORT_SERVER_LINK})"
        )

        emb.set_author(name="PokeBest Commands", icon_url=self.context.bot.user.display_avatar)

        modules: list = [
            "**Page 1**: Getting Started",
            "**Page 2**: Pokemon Commands",
            "**Page 3**: Shop, Market, Auction and Trading",
            "**Page 4**: Settings",
        ]
        emb.add_field(name=f"Modules:", value="\n".join(modules), inline=True)

        if self.context.bot.bot_config.bot_news.__len__() != 0:
            emb.add_field(
                name=f"<:emoji_30:896777950358306857> Latest Bot News",
                value=self.context.bot.bot_config.bot_news,
                inline=True,
            )

        await self.context.reply(embed=emb, view=HelpView(self.context), mention_author=False)

    async def send_cog_help(self, cog):
        txt: str = ""
        for cmd in cog.get_commands()():
            try:
                txt += f"`{cmd.name}` - {cmd.brief}\n"
            except KeyError:
                txt = f"`{cmd.name}` - {cmd.brief}\n"

        emb = self.context.bot.Embed(title=f"{cog.qualified_name}", description=txt).set_author(
            name=self.context.author.name, icon_url=self.context.author.display_avatar
        )

        await self.context.reply(embed=emb, mention_author=False)

    async def send_group_help(self, group):
        embed = self.context.bot.Embed(title=f"{group.name} <subcommand>", description=group.description)
        embed.set_author(name=f"{group.cog_name}", icon_url=self.context.bot.user.display_avatar)

        embed.add_field(
            name="Subcommands",
            value="\n".join(f"`{cmd.name}` - {cmd.short_doc}" for cmd in group.commands),
        )

        await self.context.reply(embed=embed, mention_author=False)

    async def send_command_help(self, command):
        embed: discord.Embed = self.context.bot.Embed()
        embed.set_author(name=f"{command.cog_name}", icon_url=self.context.bot.user.display_avatar)

        _help = f"```\n{self.get_command_signature(command)}\n```\n"
        _help += command.short_doc if len(command.short_doc) > len(command.short_doc) else command.short_doc

        if command.aliases.__len__() != 0:
            _help += f"\n\n**Aliases:**\n"
            _help += f"{', '.join(f'`{c}`' for c in command.aliases)}"

        embed.description = _help
        await self.context.reply(embed=embed, mention_author=False)


class HelpCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.old_help_command = bot.help_command
        bot.help_command = HelpCommand()
        bot.help_command.cog = self

    def cog_unload(self):
        self.bot.help_command = self.old_help_command


def setup(bot):
    bot.add_cog(HelpCog(bot))
