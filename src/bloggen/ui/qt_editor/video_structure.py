"""Insertion/modification of an embedded-video block through the validated
document adapter.

Unlike the encadré (:mod:`bloggen.ui.qt_editor.box_structure`), a video has
no internal structure to keep editable in the Qt document: it is a single
protected ``VERBATIM`` block (its reserved Markdown fenced-div text, see
:mod:`bloggen.markdown.video_syntax`), rendered the same way any other raw
block (a table's source, an unrecognized construct) already is. This
module therefore only wraps the generic
:func:`bloggen.ui.qt_editor.document_adapter.insert_blocks`/
``validate_block_insertion``/``replace_raw_block_group`` with the one
block shape a video ever is.
"""

from __future__ import annotations

from PySide6.QtGui import QTextCursor

from bloggen.markdown.rich_text_model import VERBATIM, Block
from bloggen.markdown.video_syntax import (
    DEFAULT_WIDTH,
    ParsedVideoBlock,
    compose_video_block,
    format_video_block,
    parse_video_block,
)
from bloggen.ui.qt_editor.document_adapter import (
    UnsupportedDocumentError,
    insert_blocks,
    raw_block_group_text,
    replace_raw_block_group,
    validate_block_insertion,
)


def _video_block(video_id: str, caption: str = "", width: int = DEFAULT_WIDTH) -> Block:
    return Block(kind=VERBATIM, raw_text=format_video_block(video_id, caption, width=width))


def _video_block_with_caption_source(
    video_id: str, caption_source: str, width: int = DEFAULT_WIDTH
) -> Block:
    """Like :func:`_video_block`, but the caption line is taken verbatim —
    never re-escaped — from an existing block's untouched
    ``ParsedVideoBlock.caption_source``."""

    return Block(
        kind=VERBATIM,
        raw_text=compose_video_block(video_id, width=width, caption_source=caption_source),
    )


def can_insert_video(cursor: QTextCursor) -> bool:
    """Whether a video block can be inserted at ``cursor`` without mutation.

    Like a table or an encadré, it replaces an ordinary text selection; a
    selection crossing any structural boundary (table cell, caption,
    encadré, another raw block) is refused.
    """

    try:
        # A placeholder id only used to shape-check the insertion point;
        # its value never reaches any output in this validation-only call.
        validate_block_insertion(cursor, [_video_block("dQw4w9WgXcQ")])
    except UnsupportedDocumentError:
        return False
    return True


def insert_video(
    cursor: QTextCursor, video_id: str, caption: str = "", width: int = DEFAULT_WIDTH
) -> QTextCursor:
    """Insert the reserved video block and return a caret right after it.

    Refused (nothing changes) at any location that cannot preserve it:
    caption, raw block, table cell, encadré, or a selection crossing a
    structural boundary.
    """

    return insert_blocks(cursor, [_video_block(video_id, caption, width)])


def video_block_at_cursor(cursor: QTextCursor) -> ParsedVideoBlock | None:
    """The parsed video block a plain caret (no selection) sits on, or
    ``None``.

    ``None`` covers "there is a selection" (whatever it spans — the edit
    dialog must only ever open for an unambiguous caret position, never
    because a selection happens to end or start inside a video block),
    "not on a raw block at all", and "on a raw block that is not a
    well-formed, currently-valid Mérope video block" (e.g. a table, an
    encadré's own raw fallback, or a hand-edited block with a malformed
    attribute) — in every such case there is nothing to prefill an edit
    dialog with.
    """

    if cursor.hasSelection():
        return None
    raw_text = raw_block_group_text(cursor.block())
    if raw_text is None:
        return None
    return parse_video_block(raw_text)


def replace_video(
    cursor: QTextCursor,
    video_id: str,
    caption: str = "",
    width: int = DEFAULT_WIDTH,
    *,
    caption_source: str | None = None,
) -> QTextCursor:
    """Atomically replace the video block group ``cursor`` sits on.

    ``caption_source`` is the exact, untouched Markdown caption line to
    write back verbatim — the caller's signal that the edit dialog's
    caption field came back unchanged from what it was prefilled with, so
    the original source (not necessarily anything
    :func:`format_video_block`'s own escaping ever produced) must be
    preserved byte-for-byte rather than re-derived from the displayable
    ``caption`` text. Leave it ``None`` (the default) for a new or
    actually-edited caption, which is then escaped as plain text exactly
    like a fresh insertion.

    Raises ``UnsupportedDocumentError`` if the cursor (with no selection)
    is not positioned on a well-formed Mérope video block specifically —
    never on some other raw block (a table's source, an encadré's raw
    fallback, an unrecognized construct): this must not be a generic
    "overwrite whatever raw block is here" operation.
    """

    if video_block_at_cursor(cursor) is None:
        raise UnsupportedDocumentError(
            "Le curseur ne se trouve pas sur un bloc vidéo Mérope"
        )
    if caption_source is not None:
        block = _video_block_with_caption_source(video_id, caption_source, width)
    else:
        block = _video_block(video_id, caption, width)
    return replace_raw_block_group(cursor, block)
