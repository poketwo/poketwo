import math

from discord.ext import menus
from discord.ext.menus.views import ViewMenuPages

REMOVE_BUTTONS = [
    "\N{BLACK LEFT-POINTING DOUBLE TRIANGLE WITH VERTICAL BAR}\ufe0f",
    "\N{BLACK RIGHT-POINTING DOUBLE TRIANGLE WITH VERTICAL BAR}\ufe0f",
    "\N{BLACK SQUARE FOR STOP}\ufe0f",
]


class FunctionPageSource(menus.PageSource):
    def __init__(self, num_pages, format_page):
        self.num_pages = num_pages
        self.format_page = format_page.__get__(self)

    def is_paginating(self):
        return self.num_pages > 1

    async def get_page(self, page_number):
        return page_number

    def get_max_pages(self):
        return self.num_pages


class AsyncListPageSource(menus.AsyncIteratorPageSource):
    def __init__(
        self,
        data,
        title=None,
        show_index=False,
        prepare_page=lambda self, items: None,
        format_item=str,
        per_page=20,
        count=None,
    ):
        super().__init__(data, per_page=per_page)
        self.title = title
        self.show_index = show_index
        self.prepare_page = prepare_page.__get__(self)
        self.format_item = format_item.__get__(self)
        self.count = count

    def get_max_pages(self):
        if self.count is None:
            return None
        else:
            return math.ceil(self.count / self.per_page)

    async def format_page(self, menu, entries):
        self.prepare_page(entries)
        lines = [
            f"{i+1}. {self.format_item(x)}" if self.show_index else self.format_item(x)
            for i, x in enumerate(entries, start=menu.current_page * self.per_page)
        ]
        start = menu.current_page * self.per_page

        footer = menu.ctx._(
            "pagination-showing-entries-count" if self.count is not None else "pagination-showing-entries",
            start=start + 1,
            end=start + len(lines),
            total=self.count,
        )
        embed = menu.ctx.bot.Embed(
            title=self.title,
            description=f"\n".join(lines)[:4096],
        )
        embed.set_footer(text=footer)
        return embed


class ContinuablePages(ViewMenuPages):
    def __init__(self, source, allow_last=True, allow_go=True, **kwargs):
        super().__init__(source, **kwargs, timeout=120)
        self.allow_last = allow_last
        self.allow_go = allow_go
        for x in REMOVE_BUTTONS:
            self.remove_button(x)

    async def send_initial_message(self, ctx, channel):
        page = await self._source.get_page(self.current_page)
        kwargs = await self._get_kwargs_from_page(page)
        return await self.send_with_view(channel, **kwargs)

    async def show_checked_page(self, page_number):
        max_pages = self._source.get_max_pages()
        try:
            if max_pages is None:
                await self.show_page(page_number)
            elif page_number < 0 and not self.allow_last:
                await self.ctx.send(ctx._("pagination-last-jumping-unsupported"))
            else:
                await self.show_page(page_number % max_pages)
        except IndexError:
            pass

    async def continue_at(self, ctx, page, *, channel=None, wait=False):
        self.stop()
        max_pages = self._source.get_max_pages()
        if max_pages is None:
            self.current_page = page
        else:
            self.current_page = page % self._source.get_max_pages()
        self.message = None
        await self.start(ctx, channel=channel, wait=wait)
