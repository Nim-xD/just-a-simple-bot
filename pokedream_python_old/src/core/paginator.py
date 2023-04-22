from discord.enums import ButtonStyle
from discord.ui import View, Button, button
from discord.ext import commands, menus
from typing import List, Any, Optional, Dict
from contextlib import suppress
from discord import Interaction
import asyncio
import discord
import math


class SimplePaginator:
    def __init__(
        self,
        ctx: commands.Context,
        pages: List[discord.Embed],
        _per_page: int = 1,
        _title: str = None,
        _embed_template: discord.Embed = discord.Embed(),
        inline: bool = False,
        use_fields: bool = False,
    ):
        self._pages: List[discord.Embed] = pages
        self._per_page: int = _per_page
        self._title = _title
        self._embed_template = _embed_template
        self._inline: bool = inline
        self._use_fields: bool = use_fields
        self._context: commands.Context = ctx

        self._current_page: int = 0
        self._total_pages: int = math.ceil(pages.__len__() / _per_page)

    async def paginate(self, ctx: commands.Context):
        view: View = SimplePaginatorView(self, timeout=120)
        await ctx.send(embed=self._pages[self._current_page], view=view)


class SimplePaginatorView(View):
    def __init__(self, _paginator: SimplePaginator, timeout: int = 100):
        self._paginator_obj: SimplePaginator = _paginator
        super().__init__(timeout=timeout)

    def build_embed(self, data: List[Any], per_page: int = 20):
        _embed = self._paginator_obj._embed_template.description = "\n".join(data)
        return _embed

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self._paginator_obj._context.author.id:
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

    @button(emoji="⏮️")
    async def _backward(self, button: Button, interaction: Interaction):
        first_page = self._paginator_obj._pages[0]
        self._paginator_obj._current_page = 0
        await interaction.message.edit(embed=first_page)

    @button(emoji="◀️")
    async def _back(self, button: Button, interaction: Interaction):
        try:
            page = self._paginator_obj._pages[self._paginator_obj._current_page - 1]
        except IndexError:
            return
        self._paginator_obj._current_page = self._paginator_obj._current_page - 1
        if self._paginator_obj._current_page < 0:
            return
        await interaction.message.edit(embed=page)

    @button(emoji="⏹️")
    async def _stop(self, button: Button, interaction: Interaction):
        await interaction.message.edit(view=None)
        self.stop()

    @button(emoji="▶️")
    async def _next(self, button: Button, interaction: Interaction):
        try:
            page = self._paginator_obj._pages[self._paginator_obj._current_page + 1]
        except IndexError:
            return
        self._paginator_obj._current_page = self._paginator_obj._current_page + 1
        if self._paginator_obj._current_page > self._paginator_obj._total_pages:
            return
        await interaction.message.edit(embed=page)

    @button(emoji="⏭️")
    async def _forward(self, button: Button, interaction: Interaction):
        last_page = self._paginator_obj._pages[self._paginator_obj._total_pages - 1]
        self._paginator_obj._current_page = self._paginator_obj._total_pages - 1
        await interaction.message.edit(embed=last_page)


class AsyncListPaginator:
    def __init__(self, ctx: commands.Context, get_page, total_pages: int):
        self.get_page = get_page
        self._context: commands.Context = ctx
        self.total_pages: int = total_pages

        self._current_page: int = 0

    async def paginate(self, ctx: commands.Context):
        view: View = AsyncPaginatorView(self, timeout=120)
        await ctx.send(embed=self.get_page(0), view=view)


class AsyncPaginatorView(View):
    def __init__(self, _paginator: AsyncListPaginator, timeout: int = 100):
        self._paginator_obj: AsyncListPaginator = _paginator
        super().__init__(timeout=timeout)

        if self._paginator_obj.total_pages == 1:
            for b in self.children:
                if b.label != "⏹️":
                    b.disabled = True

    def build_embed(self, data: List[Any], per_page: int = 20):
        _embed = self._paginator_obj._embed_template.description = "\n".join(data)
        return _embed

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self._paginator_obj._context.author.id:
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

    @button(emoji="⏮️")
    async def _backward(self, button: Button, interaction: Interaction):
        first_page = self._paginator_obj.get_page(0)
        self._paginator_obj._current_page = 0
        await interaction.message.edit(embed=first_page)

    @button(emoji="◀️")
    async def _back(self, button: Button, interaction: Interaction):
        if self._paginator_obj._current_page == 0 or self._paginator_obj._current_page < 1:
            return
        self._paginator_obj._current_page = self._paginator_obj._current_page - 1
        page = self._paginator_obj.get_page(self._paginator_obj._current_page)
        if self._paginator_obj._current_page < 0:
            return
        await interaction.message.edit(embed=page)

    @button(emoji="⏹️")
    async def _stop(self, button: Button, interaction: Interaction):
        await interaction.message.edit(view=None)
        self.stop()

    @button(emoji="▶️")
    async def _next(self, button: Button, interaction: Interaction):
        if self._paginator_obj._current_page == self._paginator_obj.total_pages - 1:
            return
        self._paginator_obj._current_page = self._paginator_obj._current_page + 1
        page = self._paginator_obj.get_page(self._paginator_obj._current_page)
        if self._paginator_obj._current_page > self._paginator_obj.total_pages:
            return
        await interaction.message.edit(embed=page)

    @button(emoji="⏭️")
    async def _forward(self, button: Button, interaction: Interaction):
        last_page = self._paginator_obj.get_page(self._paginator_obj.total_pages - 1)
        self._paginator_obj._current_page = self._paginator_obj.total_pages - 1
        await interaction.message.edit(embed=last_page)


class AdvancedPaginator(discord.ui.View):
    """A custom implementation of RoboDanny's RoboPages"""

    def __init__(
        self,
        get_page,
        total_pages: int,
        *,
        ctx: commands.Context,
        check_embeds: bool = True,
        compact: bool = False,
    ):
        super().__init__()
        self.get_page = get_page
        self.check_embeds: bool = check_embeds
        self.ctx: commands.Context = ctx
        self.message: Optional[discord.Message] = None
        self.current_page: int = 0
        self.compact: bool = compact
        self.input_lock = asyncio.Lock()
        self.clear_items()
        self.fill_items()
        self.total_pages: int = total_pages

    def fill_items(self) -> None:
        if not self.compact:
            self.numbered_page.row = 1
            self.stop_pages.row = 1

        # if self.source.is_paginating():
        if 1 != 0:
            max_pages = self.total_pages
            use_last_and_first = max_pages is not None and max_pages >= 2
            if use_last_and_first:
                self.add_item(self.go_to_first_page)  # type: ignore
            self.add_item(self.go_to_previous_page)  # type: ignore
            if not self.compact:
                self.add_item(self.go_to_current_page)  # type: ignore
            self.add_item(self.go_to_next_page)  # type: ignore
            if use_last_and_first:
                self.add_item(self.go_to_last_page)  # type: ignore
            if not self.compact:
                self.add_item(self.numbered_page)  # type: ignore
            self.add_item(self.stop_pages)  # type: ignore

    async def _get_kwargs_from_page(self, page: int) -> Dict[str, Any]:
        value = await discord.utils.maybe_coroutine(self.get_page, page)
        if isinstance(value, dict):
            return value
        elif isinstance(value, str):
            return {"content": value, "embed": None}
        elif isinstance(value, discord.Embed):
            return {"embed": value, "content": None}
        else:
            return {}

    async def show_page(self, interaction: discord.Interaction, page_number: int) -> None:
        page = await self.get_page(page_number)
        self.current_page = page_number
        kwargs = await self._get_kwargs_from_page(page)
        self._update_labels(page_number)
        if kwargs:
            if interaction.response.is_done():
                if self.message:
                    await self.message.edit(**kwargs, view=self)
            else:
                await interaction.response.edit_message(**kwargs, view=self)

    def _update_labels(self, page_number: int) -> None:
        self.go_to_first_page.disabled = page_number == 0
        if self.compact:
            max_pages = self.total_pages
            self.go_to_last_page.disabled = max_pages is None or (page_number + 1) >= max_pages
            self.go_to_next_page.disabled = max_pages is not None and (page_number + 1) >= max_pages
            self.go_to_previous_page.disabled = page_number == 0
            return

        self.go_to_current_page.label = str(page_number + 1)
        self.go_to_previous_page.label = str(page_number)
        self.go_to_next_page.label = str(page_number + 2)
        self.go_to_next_page.disabled = False
        self.go_to_previous_page.disabled = False
        self.go_to_first_page.disabled = False

        max_pages = self.total_pages
        if max_pages is not None:
            self.go_to_last_page.disabled = (page_number + 1) >= max_pages
            if (page_number + 1) >= max_pages:
                self.go_to_next_page.disabled = True
                self.go_to_next_page.label = "…"
            if page_number == 0:
                self.go_to_previous_page.disabled = True
                self.go_to_previous_page.label = "…"

    async def show_checked_page(self, interaction: discord.Interaction, page_number: int) -> None:
        max_pages = self.total_pages
        try:
            if max_pages is None:
                # If it doesn't give maximum pages, it cannot be checked
                await self.show_page(interaction, page_number)
            elif max_pages > page_number >= 0:
                await self.show_page(interaction, page_number)
        except IndexError:
            # An error happened that can be handled, so ignore it.
            pass

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user and interaction.user.id in (
            self.ctx.bot.owner_id,
            self.ctx.author.id,
        ):
            return True
        await interaction.response.send_message(
            "This pagination menu cannot be controlled by you, sorry!", ephemeral=True
        )
        return False

    async def on_timeout(self) -> None:
        if self.message:
            await self.message.edit(view=None)

    async def on_error(self, error: Exception, item: discord.ui.Item, interaction: discord.Interaction) -> None:
        if interaction.response.is_done():
            await interaction.followup.send("An unknown error occurred, sorry", ephemeral=True)
        else:
            await interaction.response.send_message("An unknown error occurred, sorry", ephemeral=True)

    async def start(self) -> None:
        if self.check_embeds and not self.ctx.channel.permissions_for(self.ctx.me).embed_links:
            await self.ctx.send("Bot does not have embed links permission in this channel.")
            return

        # await self.source._prepare_once()
        page = await self.get_page(0)
        kwargs = await self._get_kwargs_from_page(page)
        self._update_labels(0)
        self.message = await self.ctx.send(**kwargs, view=self)

    @discord.ui.button(label="≪", style=discord.ButtonStyle.grey)
    async def go_to_first_page(self, button: discord.ui.Button, interaction: discord.Interaction):
        """go to the first page"""
        await self.show_page(interaction, 0)

    @discord.ui.button(label="Back", style=discord.ButtonStyle.blurple)
    async def go_to_previous_page(self, button: discord.ui.Button, interaction: discord.Interaction):
        """go to the previous page"""
        await self.show_checked_page(interaction, self.current_page - 1)

    @discord.ui.button(label="Current", style=discord.ButtonStyle.grey, disabled=True)
    async def go_to_current_page(self, button: discord.ui.Button, interaction: discord.Interaction):
        pass

    @discord.ui.button(label="Next", style=discord.ButtonStyle.blurple)
    async def go_to_next_page(self, button: discord.ui.Button, interaction: discord.Interaction):
        """go to the next page"""
        await self.show_checked_page(interaction, self.current_page + 1)

    @discord.ui.button(label="≫", style=discord.ButtonStyle.grey)
    async def go_to_last_page(self, button: discord.ui.Button, interaction: discord.Interaction):
        """go to the last page"""
        # The call here is safe because it's guarded by skip_if
        await self.show_page(interaction, self.total_pages - 1)

    @discord.ui.button(label="Skip to page...", style=discord.ButtonStyle.grey)
    async def numbered_page(self, button: discord.ui.Button, interaction: discord.Interaction):
        """lets you type a page number to go to"""
        if self.input_lock.locked():
            await interaction.response.send_message("Already waiting for your response...", ephemeral=True)
            return

        if self.message is None:
            return

        async with self.input_lock:
            channel = self.message.channel
            author_id = interaction.user and interaction.user.id
            await interaction.response.send_message("What page do you want to go to?", ephemeral=True)

            def message_check(m):
                return m.author.id == author_id and channel == m.channel and m.content.isdigit()

            try:
                msg = await self.ctx.bot.wait_for("message", check=message_check, timeout=30.0)
            except asyncio.TimeoutError:
                await interaction.followup.send("Took too long.", ephemeral=True)
                await asyncio.sleep(5)
            else:
                page = int(msg.content)
                await msg.delete()
                await self.show_checked_page(interaction, page - 1)

    @discord.ui.button(label="Quit", style=discord.ButtonStyle.red)
    async def stop_pages(self, button: discord.ui.Button, interaction: discord.Interaction):
        """stops the pagination session."""
        await interaction.response.defer()
        await interaction.delete_original_message()
        self.stop()
