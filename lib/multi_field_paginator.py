from __future__ import annotations

from dataclasses import dataclass
import math
from typing import TYPE_CHECKING, Callable, List, Optional

from helpers import pagination

if TYPE_CHECKING:
    from bot import ClusterBot


@dataclass
class PaginatedField:
    """Dataclass to easily define fields for MultiFieldPageSource
    along with useful methods and properties.

    Attributes
    ----------
    name : str
        The name of the field.
    entries : List[str]
        The list of all entries of the field to be used as value.
    num_entries : int
        The total number of entries.

    Methods
    -------
    get_entries(current_page: int, *, per_page: int) -> List[str]
        Get entries for the current page.
    get_num_pages(self, per_page: int) -> int
        Get the total number of pages.
    """

    name: str
    entries: List[str]

    def __str__(self) -> str:
        return self.name

    def __repr__(self) -> str:
        return f"<PaginatedField name: {self.name} num_entries: {self.num_entries}"

    @property
    def num_entries(self) -> int:
        """The total number of entries."""

        return len(self.entries)

    def get_entries(self, current_page: int, *, per_page: int) -> List[str]:
        """Get entries for the current page."""

        pgstart = current_page * per_page
        pgend = min(pgstart + per_page, self.num_entries)

        return self.entries[pgstart:pgend]

    def get_num_pages(self, per_page: int) -> int:
        """Get the total number of pages."""

        return math.ceil(self.num_entries / per_page)


class MultiFieldPageSource(pagination.FunctionPageSource):
    """A page source to paginate multiple fields of an embed at once.
    Continues paginating fields until their respective page limits are reached.
    Overall max number of pages is the length of the list of entries that is longest.

    Parameters
    ----------
    fields : List[PaginatedField]
        A dictionary of `field_name: list_of_entries` pairs. This contains all the entries
        of the fields that will be paginated.
    make_embed : Callable[MultiFieldPageSource, [List[PaginatedField]], ClusterBot.Embed]
        The function the page source will call to build the embed.

    per_page : Optional[int]
        The maximum number of entries to show in a field per page. Default is 10.
    """

    def __init__(
        self,
        fields: List[PaginatedField],
        make_embed: Callable[[MultiFieldPageSource, List[PaginatedField]], ClusterBot.Embed],
        per_page: Optional[int] = 10,
    ):
        self.fields = fields
        self.make_embed = make_embed
        self.per_page = per_page

        # Make total number of pages equal to the length of the longest entries list
        self.num_pages = max(fields, key=lambda f: len(f.entries)).get_num_pages(self.per_page)

    def format_page(self, menu: pagination.ContinuablePages, current_page: int) -> ClusterBot.Embed:
        """The method that formats and returns the embed for each page."""

        self.current_page = current_page

        embed = self.make_embed(self, self.fields)
        return embed
