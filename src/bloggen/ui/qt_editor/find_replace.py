"""Safe literal find/replace operations for the Qt editor body."""

from __future__ import annotations

from dataclasses import dataclass
import re

from PySide6.QtGui import QTextCharFormat, QTextCursor, QTextDocument
from PySide6.QtWidgets import QTextEdit

from bloggen.ui.qt_editor.constants import (
    BOLD_PROPERTY,
    ITALIC_PROPERTY,
    STRIKETHROUGH_PROPERTY,
    SUPERSCRIPT_PROPERTY,
)
from bloggen.ui.qt_editor.document_adapter import (
    inline_format_enabled,
    is_semantic_inline_object_format,
)


@dataclass(frozen=True, slots=True)
class FindMatch:
    """One safe, single-block occurrence in QTextDocument UTF-16 positions."""

    start: int
    end: int

    def cursor(self, document: QTextDocument) -> QTextCursor:
        cursor = QTextCursor(document)
        cursor.setPosition(self.start)
        cursor.setPosition(self.end, QTextCursor.MoveMode.KeepAnchor)
        return cursor


def find_replaceable_matches(
    document: QTextDocument,
    pattern: str,
    *,
    case_sensitive: bool = False,
) -> list[FindMatch]:
    """Return literal occurrences safe to replace without crossing semantics."""

    if not pattern or "\n" in pattern or "\r" in pattern or "\u2029" in pattern:
        return []
    flags = 0 if case_sensitive else re.IGNORECASE
    expression = re.compile(re.escape(pattern), flags)
    matches: list[FindMatch] = []
    block = document.begin()
    while block.isValid():
        text = block.text()
        for candidate in expression.finditer(text):
            start = block.position() + _utf16_length(text[: candidate.start()])
            end = block.position() + _utf16_length(text[: candidate.end()])
            if _replacement_format(document, start, end) is not None:
                matches.append(FindMatch(start, end))
        block = block.next()
    return matches


def find_next(
    editor: QTextEdit,
    pattern: str,
    *,
    case_sensitive: bool = False,
) -> FindMatch | None:
    """Select the next safe occurrence, wrapping once to the document start."""

    matches = find_replaceable_matches(
        editor.document(), pattern, case_sensitive=case_sensitive
    )
    if not matches:
        return None
    cursor = editor.textCursor()
    start_position = cursor.selectionEnd() if cursor.hasSelection() else cursor.position()
    match = next(
        (candidate for candidate in matches if candidate.start >= start_position),
        matches[0],
    )
    editor.setTextCursor(match.cursor(editor.document()))
    editor.ensureCursorVisible()
    return match


def selected_replaceable_match(
    editor: QTextEdit,
    pattern: str,
    *,
    case_sensitive: bool = False,
) -> FindMatch | None:
    """Revalidate that the live selection is still the requested safe match."""

    cursor = editor.textCursor()
    if not cursor.hasSelection() or not pattern:
        return None
    selected = cursor.selectedText()
    equal = selected == pattern if case_sensitive else selected.casefold() == pattern.casefold()
    if not equal:
        return None
    start = cursor.selectionStart()
    end = cursor.selectionEnd()
    if _replacement_format(editor.document(), start, end) is None:
        return None
    return FindMatch(start, end)


def replace_current(
    editor: QTextEdit,
    pattern: str,
    replacement: str,
    *,
    case_sensitive: bool = False,
) -> bool:
    """Replace the currently selected safe match in one native undo operation."""

    match = selected_replaceable_match(
        editor, pattern, case_sensitive=case_sensitive
    )
    if match is None:
        return False
    cursor = match.cursor(editor.document())
    if cursor.selectedText() == replacement:
        return False
    char_format = _replacement_format(editor.document(), match.start, match.end)
    if char_format is None:
        return False
    cursor.beginEditBlock()
    try:
        if replacement:
            cursor.insertText(replacement, char_format)
        else:
            cursor.removeSelectedText()
    finally:
        cursor.endEditBlock()
    editor.setTextCursor(cursor)
    return True


def replace_all(
    editor: QTextEdit,
    pattern: str,
    replacement: str,
    *,
    case_sensitive: bool = False,
) -> int:
    """Replace every safe occurrence right-to-left as one native undo step."""

    operations = []
    for match in find_replaceable_matches(
        editor.document(), pattern, case_sensitive=case_sensitive
    ):
        cursor = match.cursor(editor.document())
        if cursor.selectedText() == replacement:
            continue
        char_format = _replacement_format(editor.document(), match.start, match.end)
        if char_format is not None:
            operations.append((match, char_format))
    if not operations:
        return 0

    edit_cursor = QTextCursor(editor.document())
    edit_cursor.beginEditBlock()
    try:
        for match, char_format in reversed(operations):
            cursor = match.cursor(editor.document())
            if replacement:
                cursor.insertText(replacement, char_format)
            else:
                cursor.removeSelectedText()
    finally:
        edit_cursor.endEditBlock()
    return len(operations)


def _replacement_format(
    document: QTextDocument,
    start: int,
    end: int,
) -> QTextCharFormat | None:
    if start >= end:
        return None
    block = document.findBlock(start)
    if not block.isValid() or document.findBlock(end - 1) != block:
        return None

    source_format: QTextCharFormat | None = None
    signature = None
    iterator = block.begin()
    while not iterator.atEnd():
        fragment = iterator.fragment()
        fragment_start = fragment.position()
        fragment_end = fragment_start + fragment.length()
        if fragment.isValid() and fragment_end > start and fragment_start < end:
            char_format = fragment.charFormat()
            if is_semantic_inline_object_format(char_format):
                return None
            current_signature = _semantic_signature(char_format)
            if signature is None:
                signature = current_signature
                source_format = QTextCharFormat(char_format)
            elif current_signature != signature:
                return None
        iterator += 1
    return source_format


def _semantic_signature(char_format: QTextCharFormat) -> tuple[object, ...]:
    return (
        inline_format_enabled(char_format, BOLD_PROPERTY),
        inline_format_enabled(char_format, ITALIC_PROPERTY),
        inline_format_enabled(char_format, STRIKETHROUGH_PROPERTY),
        inline_format_enabled(char_format, SUPERSCRIPT_PROPERTY),
        char_format.anchorHref() if char_format.isAnchor() else None,
    )


def _utf16_length(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2
