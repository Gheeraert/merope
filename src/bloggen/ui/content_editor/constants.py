"""Tag names shared by more than one content_editor mixin.

Constants used by only a single mixin are defined locally in that file
instead — this module exists only for the few genuinely cross-cutting
ones, to avoid an arbitrary "owner" file importing into another.
"""

from __future__ import annotations

_BLOCK_LINE_TAGS = {
    "h1",
    "h2",
    "h3",
    "h4",
    "blockquote",
    "bullet_item",
    "ordered_item",
    "table_source",
    "verbatim",
}
