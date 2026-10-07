"""Insertion of an embedded-video block through the validated document
adapter.

Unlike the encadré (:mod:`bloggen.ui.qt_editor.box_structure`), a video has
no internal structure to keep editable in the Qt document: it is a single
protected ``VERBATIM`` block (its reserved Markdown fenced-div text, see
:mod:`bloggen.markdown.video_syntax`), rendered the same way any other raw
block (a table's source, an unrecognized construct) already is. This
module therefore only wraps the generic
:func:`bloggen.ui.qt_editor.document_adapter.insert_blocks`/
``validate_block_insertion`` with the one block shape a video ever is.
"""

from __future__ import annotations

from PySide6.QtGui import QTextCursor

from bloggen.markdown.rich_text_model import VERBATIM, Block
from bloggen.markdown.video_syntax import format_video_block
from bloggen.ui.qt_editor.document_adapter import (
    UnsupportedDocumentError,
    insert_blocks,
    validate_block_insertion,
)


def _video_block(video_id: str, caption: str = "") -> Block:
    return Block(kind=VERBATIM, raw_text=format_video_block(video_id, caption))


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


def insert_video(cursor: QTextCursor, video_id: str, caption: str = "") -> QTextCursor:
    """Insert the reserved video block and return a caret right after it.

    Refused (nothing changes) at any location that cannot preserve it:
    caption, raw block, table cell, encadré, or a selection crossing a
    structural boundary.
    """

    return insert_blocks(cursor, [_video_block(video_id, caption)])
