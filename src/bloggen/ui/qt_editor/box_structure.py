"""Insertion of an empty encadré through the validated document adapter."""

from __future__ import annotations

from PySide6.QtGui import QTextCursor, QTextFrame

from bloggen.markdown.rich_text_model import BOX, PARAGRAPH, Block, InlineRun
from bloggen.ui.qt_editor.document_adapter import (
    UnsupportedBlockError,
    UnsupportedDocumentError,
    insert_blocks,
    is_merope_box_frame,
    validate_block_insertion,
)


def _empty_box_block(title: str = "") -> Block:
    title = " ".join(title.split())
    return Block(
        kind=BOX,
        runs=[InlineRun(text=title)] if title else [],
        children=[Block(kind=PARAGRAPH, runs=[InlineRun(text="")])],
    )


def _root_boxes(cursor: QTextCursor) -> list[QTextFrame]:
    return [
        frame
        for frame in cursor.document().rootFrame().childFrames()
        if is_merope_box_frame(frame)
    ]


def can_insert_box(cursor: QTextCursor) -> bool:
    """Whether an empty encadré can be inserted at ``cursor`` without mutation.

    Like a table, it replaces an ordinary text selection; a selection that
    crosses any structural boundary is refused.
    """

    try:
        validate_block_insertion(cursor, [_empty_box_block()])
    except UnsupportedDocumentError:
        return False
    return True


def insert_empty_box(cursor: QTextCursor, title: str = "") -> QTextCursor:
    """Insert an empty encadré and return a caret in its first body paragraph.

    Refused (nothing changes) at any location that cannot preserve it:
    caption, raw block, table cell, another encadré, or a selection
    crossing a structural boundary.
    """

    existing = {frame.objectIndex() for frame in _root_boxes(cursor)}
    insert_blocks(cursor, [_empty_box_block(title)])

    created = [
        frame for frame in _root_boxes(cursor) if frame.objectIndex() not in existing
    ]
    if len(created) != 1:  # Defensive: insertion itself is already validated.
        raise UnsupportedBlockError(
            "L’encadré inséré ne peut pas être identifié sans ambiguïté"
        )
    return created[0].lastCursorPosition()
