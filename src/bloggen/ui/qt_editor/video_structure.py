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
    """The parsed video block the cursor sits on, or ``None``.

    ``None`` covers both "not on a raw block at all" and "on a raw block
    that is not a well-formed, currently-valid Mérope video block" (e.g. a
    table, an encadré's own raw fallback, or a hand-edited block with a
    malformed ``data-width``) — in every such case there is nothing to
    prefill an edit dialog with.
    """

    raw_text = raw_block_group_text(cursor.block())
    if raw_text is None:
        return None
    return parse_video_block(raw_text)


def replace_video(
    cursor: QTextCursor, video_id: str, caption: str = "", width: int = DEFAULT_WIDTH
) -> QTextCursor:
    """Atomically replace the video block group ``cursor`` sits on.

    Raises ``UnsupportedDocumentError`` if the cursor is not positioned on
    a well-formed Mérope video block specifically — never on some other
    raw block (a table's source, an encadré's raw fallback, an
    unrecognized construct): this must not be a generic "overwrite
    whatever raw block is here" operation.
    """

    if video_block_at_cursor(cursor) is None:
        raise UnsupportedDocumentError(
            "Le curseur ne se trouve pas sur un bloc vidéo Mérope"
        )
    return replace_raw_block_group(cursor, _video_block(video_id, caption, width))
