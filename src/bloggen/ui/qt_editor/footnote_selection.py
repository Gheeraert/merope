"""Selection helpers for atomic semantic footnote-reference markers."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtGui import QTextCursor, QTextDocument

from bloggen.ui.qt_editor.document_adapter import (
    footnote_run_from_format,
    has_footnote_properties,
)


@dataclass(frozen=True, slots=True)
class FootnoteTarget:
    start: int
    end: int
    note_id: str

    def cursor(self, document: QTextDocument) -> QTextCursor:
        cursor = QTextCursor(document)
        cursor.setPosition(self.start)
        cursor.setPosition(self.end, QTextCursor.MoveMode.KeepAnchor)
        return cursor


def merope_footnote_at_position(
    document: QTextDocument,
    position: int,
) -> FootnoteTarget | None:
    """Return the complete semantic marker containing one Qt position."""

    if position < 0 or position >= document.characterCount() - 1:
        return None
    block = document.findBlock(position)
    if not block.isValid():
        return None
    iterator = block.begin()
    while not iterator.atEnd():
        fragment = iterator.fragment()
        if fragment.isValid():
            start = fragment.position()
            end = start + fragment.length()
            if start <= position < end:
                char_format = fragment.charFormat()
                if not has_footnote_properties(char_format):
                    return None
                run = footnote_run_from_format(char_format, fragment.text())
                return FootnoteTarget(start, end, run.footnote_ref)
        iterator += 1
    return None


def merope_footnotes_in_selection(cursor: QTextCursor) -> list[FootnoteTarget]:
    """Return semantic markers intersecting the selected half-open range."""

    if not cursor.hasSelection():
        return []
    start = cursor.selectionStart()
    end = cursor.selectionEnd()
    targets: list[FootnoteTarget] = []
    seen: set[tuple[int, int]] = set()
    block = cursor.document().findBlock(start)
    while block.isValid() and block.position() < end:
        iterator = block.begin()
        while not iterator.atEnd():
            fragment = iterator.fragment()
            fragment_start = fragment.position()
            fragment_end = fragment_start + fragment.length()
            if (
                fragment.isValid()
                and fragment_end > start
                and fragment_start < end
                and has_footnote_properties(fragment.charFormat())
            ):
                run = footnote_run_from_format(
                    fragment.charFormat(),
                    fragment.text(),
                )
                key = (fragment_start, fragment_end)
                if key not in seen:
                    targets.append(
                        FootnoteTarget(fragment_start, fragment_end, run.footnote_ref)
                    )
                    seen.add(key)
            iterator += 1
        block = block.next()
    return targets


def footnote_containing_cursor(cursor: QTextCursor) -> FootnoteTarget | None:
    """Return a marker only when a collapsed cursor lies strictly inside it."""

    if cursor.hasSelection():
        return None
    position = cursor.position()
    candidates = {
        target.start: target
        for offset in (position - 1, position)
        if (target := merope_footnote_at_position(cursor.document(), offset))
        is not None
        and target.start < position < target.end
    }
    return next(iter(candidates.values())) if len(candidates) == 1 else None


def expand_selection_to_footnotes(cursor: QTextCursor) -> tuple[QTextCursor, bool]:
    """Return an atomic selection and whether it contains a footnote marker."""

    expanded = QTextCursor(cursor)
    if cursor.hasSelection():
        targets = merope_footnotes_in_selection(cursor)
        if not targets:
            return expanded, False
        start = min(cursor.selectionStart(), *(target.start for target in targets))
        end = max(cursor.selectionEnd(), *(target.end for target in targets))
        expanded.setPosition(start)
        expanded.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
        return expanded, True

    target = footnote_containing_cursor(cursor)
    if target is None:
        return expanded, False
    return target.cursor(cursor.document()), True
