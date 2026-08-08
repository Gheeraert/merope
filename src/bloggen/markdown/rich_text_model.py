"""Pivot data model between the Tkinter rich-text editor and Markdown.

``Block``/``InlineRun`` are the intermediate representation used by both
directions of conversion (:mod:`bloggen.markdown.rich_text_export` and
:mod:`bloggen.markdown.rich_text_import`), so that neither direction needs
to know about the Tkinter ``Text`` widget, and neither the widget-facing UI
code needs to know about Markdown syntax.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Block-level kinds.
PARAGRAPH = "paragraph"
HEADING = "heading"
BLOCKQUOTE = "blockquote"
BULLET_LIST = "bullet_list"
ORDERED_LIST = "ordered_list"
LIST_ITEM = "list_item"
TABLE = "table"
TABLE_ROW = "table_row"
TABLE_CELL = "table_cell"
FOOTNOTE_DEFINITION = "footnote_definition"
VERBATIM = "verbatim"


@dataclass(slots=True)
class InlineRun:
    """A run of text sharing the same inline formatting, or an inline leaf."""

    text: str = ""
    bold: bool = False
    italic: bool = False
    strikethrough: bool = False
    link_href: str | None = None
    image_src: str | None = None
    image_alt: str | None = None
    footnote_ref: str | None = None


@dataclass(slots=True)
class Block:
    """A block-level node.

    ``runs`` holds inline content for leaf blocks (paragraph, heading,
    blockquote, list_item, table_cell). ``children`` holds nested blocks:
    - BULLET_LIST/ORDERED_LIST -> list of LIST_ITEM
    - LIST_ITEM -> list of nested blocks (usually a single paragraph), or
      plain ``runs`` when the item has no block-level content of its own
    - TABLE -> list of TABLE_ROW, first row is the header row
    - TABLE_ROW -> list of TABLE_CELL
    """

    kind: str
    level: int | None = None  # heading level 1-4
    runs: list[InlineRun] = field(default_factory=list)
    children: list["Block"] = field(default_factory=list)
    footnote_id: str | None = None  # for FOOTNOTE_DEFINITION blocks
    raw_text: str | None = None  # for VERBATIM blocks: reproduced as-is


def plain_text(runs: list[InlineRun]) -> str:
    """Concatenate the raw text of a list of runs, ignoring formatting."""
    return "".join(run.text for run in runs)
