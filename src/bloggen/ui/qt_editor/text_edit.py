"""QTextEdit adaptations for Merope's editing interactions."""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Callable

from PySide6.QtCore import QMimeData, Signal
from PySide6.QtGui import QFont, QKeyEvent, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import QTextEdit

from bloggen.markdown.html_paste_import import (
    UnsupportedHtmlStructureError,
    html_to_blocks,
)
from bloggen.markdown.typography import (
    CENTURY_RE,
    CLOSING_GUILLEMET,
    COMMON_CENTURY_ORDINAL_TYPED_RE,
    CURLY_CLOSING_QUOTE,
    CURLY_OPENING_QUOTE,
    DOUBLE_PUNCTUATION,
    NBSP,
    OE_LIGATURE_TYPED_RE,
    OPENING_GUILLEMET,
    PAGE_ABBREVIATION_TYPED_RE,
    SPACE_BEFORE_PERIOD_TYPED_RE,
    convert_curly_quotes_to_guillemets,
    convert_straight_quotes_stateful,
    fix_double_punctuation_spacing,
    fix_guillemet_spacing,
    fix_page_number_spacing,
    fix_period_spacing,
    is_valid_century_ordinal,
    oe_ligature_replacement,
)
from bloggen.ui.qt_editor.constants import (
    BOLD_PROPERTY,
    ITALIC_PROPERTY,
    STRIKETHROUGH_PROPERTY,
    SUPERSCRIPT_PROPERTY,
)
from bloggen.ui.qt_editor.document_adapter import (
    UnsupportedDocumentError,
    inline_format_enabled,
    insert_blocks,
)


_OE_PAIR_RE = re.compile("oe", re.IGNORECASE)
_REJECTED_RICH_PASTE_TAGS = frozenset(
    {"img", "pre", "table", "v:imagedata", "v:shape"}
)


class MeropeTextEdit(QTextEdit):
    """Qt editing surface with Merope's shared French typography rules.

    The widget owns interaction behaviour only.  ``Block`` / ``InlineRun``
    remain canonical and are still converted by ``document_adapter``.
    """

    pasteRefused = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAcceptRichText(False)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        char = event.text()
        if char == '"' and self.textCursor().hasSelection():
            self._wrap_selection_in_guillemets()
            return

        if len(char) == 1 and self._typing_requires_autoformat(char):
            cursor = self.textCursor()
            cursor.beginEditBlock()
            try:
                cursor.insertText(char)
                self.setTextCursor(cursor)
            finally:
                cursor.endEditBlock()
            self._apply_typing_autoformat(char)
            return

        super().keyPressEvent(event)

    def canInsertFromMimeData(self, source: QMimeData) -> bool:
        """Accept only MIME content that Merope can inspect safely itself."""

        if source.hasHtml() and bool(source.html().strip()):
            return True
        return source.hasText() and bool(source.text())

    def insertFromMimeData(self, source: QMimeData) -> None:
        """Insert clipboard data without letting Qt interpret rich HTML.

        HTML always goes through Merope's canonical ``html_to_blocks``
        importer, then through the validated document adapter.  Unsupported
        semantic structures refuse the entire paste before the selection or
        document is touched.
        """

        if source.hasHtml() and source.html().strip():
            try:
                blocks = html_to_blocks(
                    source.html(),
                    reject_tags=_REJECTED_RICH_PASTE_TAGS,
                )
                if blocks:
                    cursor = insert_blocks(self.textCursor(), blocks)
                    self.setTextCursor(cursor)
                    return
            except (UnsupportedHtmlStructureError, UnsupportedDocumentError) as exc:
                self.pasteRefused.emit(str(exc))
                return
            except Exception as exc:
                self.pasteRefused.emit(f"Le collage HTML n’a pas pu être analysé : {exc}")
                return

        if source.hasText():
            cursor = self.textCursor()
            cursor.beginEditBlock()
            try:
                cursor.insertText(source.text())
            finally:
                cursor.endEditBlock()
            self.setTextCursor(cursor)
            return

        self.pasteRefused.emit(
            "Ce format de presse-papiers n’est pas encore pris en charge par l’éditeur Qt"
        )

    def apply_typography_to_selection(self) -> bool:
        """Apply shared pure typography rules while retaining Qt formats.

        Edits are calculated over the whole selected Unicode text, so quote
        parity continues across QTextFragment boundaries.  Only changed
        ranges are rewritten, from right to left, in one native undo block.
        """

        selection = self.textCursor()
        if not selection.hasSelection():
            return False
        start = selection.selectionStart()
        source = selection.selectedText()
        opening_next = self._opening_quote_at_position(start)

        fixed = convert_curly_quotes_to_guillemets(source)
        fixed, _opening_next = convert_straight_quotes_stateful(
            fixed,
            opening_next=opening_next,
        )
        fixed = fix_guillemet_spacing(fixed)
        fixed = fix_double_punctuation_spacing(fixed)
        fixed = fix_page_number_spacing(fixed)
        fixed = fix_period_spacing(fixed)
        if fixed == source:
            return False

        opcodes = SequenceMatcher(None, source, fixed, autojunk=False).get_opcodes()
        source_positions = _utf16_offsets(source)
        edit_block = QTextCursor(self.document())
        edit_block.beginEditBlock()
        try:
            for tag, source_start, source_end, fixed_start, fixed_end in reversed(opcodes):
                if tag == "equal":
                    continue
                absolute_start = start + source_positions[source_start]
                absolute_end = start + source_positions[source_end]
                replacement = fixed[fixed_start:fixed_end]
                char_format = self._format_for_edit(absolute_start, absolute_end)
                self._replace_range(
                    absolute_start,
                    absolute_end,
                    replacement,
                    char_format,
                )
        finally:
            edit_block.endEditBlock()

        updated = QTextCursor(self.document())
        updated.setPosition(start)
        updated.setPosition(start + _utf16_length(fixed), QTextCursor.MoveMode.KeepAnchor)
        self.setTextCursor(updated)
        return True

    def _apply_typing_autoformat(self, char: str) -> None:
        if char == '"':
            self._replace_last_quote()
        elif char == OPENING_GUILLEMET:
            self._space_after_opening_guillemet()
        elif char == CLOSING_GUILLEMET:
            self._space_before_current_character()
        elif char in DOUBLE_PUNCTUATION:
            self._space_before_current_character()

        self._autoformat_century_phrases()
        if char.isdigit():
            self._autoformat_page_number_space()
        elif char == ".":
            self._autoformat_period_spacing()
        elif char.isalpha():
            self._autoformat_oe_ligature()
            if char == "e":
                self._autoformat_common_century_ordinal()

    def _typing_requires_autoformat(self, char: str) -> bool:
        if char in ('"', OPENING_GUILLEMET, CLOSING_GUILLEMET) or char in DOUBLE_PUNCTUATION:
            return True
        _block, prefix = self._current_block_prefix()
        candidate = prefix + char
        if char.isdigit() and PAGE_ABBREVIATION_TYPED_RE.search(candidate):
            return True
        if char == "." and SPACE_BEFORE_PERIOD_TYPED_RE.search(candidate):
            return True
        if char.isalpha() and OE_LIGATURE_TYPED_RE.search(candidate):
            return True
        if char == "e" and COMMON_CENTURY_ORDINAL_TYPED_RE.search(candidate):
            return True
        return any(
            is_valid_century_ordinal(match.group(1), match.group(2))
            for match in CENTURY_RE.finditer(candidate)
        )

    def _replace_last_quote(self) -> None:
        cursor = self.textCursor()
        quote_position = cursor.position() - 1
        if quote_position < 0:
            return
        opening_next = self._opening_quote_at_position(quote_position)
        replacement, _ = convert_straight_quotes_stateful(
            '"',
            opening_next=opening_next,
        )
        char_format = self._format_for_edit(quote_position, quote_position + 1)
        self._joined_with_previous_edit(
            lambda: self._replace_range(
                quote_position,
                quote_position + 1,
                replacement,
                char_format,
            )
        )

    def _space_after_opening_guillemet(self) -> None:
        position = self.textCursor().position()
        char_format = self._format_for_edit(position - 1, position)
        self._joined_with_previous_edit(
            lambda: self._replace_range(position, position, NBSP, char_format)
        )

    def _space_before_current_character(self) -> None:
        cursor = self.textCursor()
        punctuation_position = cursor.position() - 1
        if punctuation_position < 0:
            return
        block = cursor.block()
        block_text = block.text()
        relative_position = _python_index_for_utf16_offset(
            block_text,
            punctuation_position - block.position(),
        )
        preceding = block_text[relative_position - 1] if relative_position > 0 else ""
        if preceding == NBSP:
            return
        if preceding == " ":
            start = punctuation_position - 1
            char_format = self._format_for_edit(start, punctuation_position)
            end = punctuation_position
        else:
            start = punctuation_position
            end = punctuation_position
            char_format = self._format_for_edit(
                punctuation_position,
                punctuation_position + 1,
            )
        self._joined_with_previous_edit(
            lambda: self._replace_range(start, end, NBSP, char_format)
        )

    def _autoformat_page_number_space(self) -> None:
        block, prefix = self._current_block_prefix()
        match = PAGE_ABBREVIATION_TYPED_RE.search(prefix)
        if match is None:
            return
        space_offset = prefix.rfind(" ", match.start(), match.end())
        if space_offset < 0:
            return
        start = _block_position(block, space_offset)
        char_format = self._format_for_edit(start, start + 1)
        self._joined_with_previous_edit(
            lambda: self._replace_range(start, start + 1, NBSP, char_format)
        )

    def _autoformat_period_spacing(self) -> None:
        block, prefix = self._current_block_prefix()
        match = SPACE_BEFORE_PERIOD_TYPED_RE.search(prefix)
        if match is None:
            return
        start = _block_position(block, match.start())
        period_position = self.textCursor().position() - 1
        self._joined_with_previous_edit(
            lambda: self._replace_range(start, period_position, "", QTextCharFormat())
        )

    def _autoformat_oe_ligature(self) -> None:
        block, prefix = self._current_block_prefix()
        match = OE_LIGATURE_TYPED_RE.search(prefix)
        if match is None:
            return
        word = match.group(1)
        replacement = oe_ligature_replacement(word)
        pair = _OE_PAIR_RE.search(word)
        if replacement == word or pair is None:
            return
        start = _block_position(block, match.start(1) + pair.start())
        ligature = replacement[pair.start()]
        char_format = self._format_for_edit(start, start + 2)
        self._joined_with_previous_edit(
            lambda: self._replace_range(start, start + 2, ligature, char_format)
        )

    def _autoformat_century_phrases(self) -> None:
        block, prefix = self._current_block_prefix()
        ranges: list[tuple[int, int]] = []
        for match in CENTURY_RE.finditer(prefix):
            numeral, suffix = match.group(1), match.group(2)
            if not is_valid_century_ordinal(numeral, suffix):
                continue
            start = _block_position(block, match.start(2))
            end = _block_position(block, match.end(2))
            if not inline_format_enabled(
                self._format_for_edit(start, end),
                SUPERSCRIPT_PROPERTY,
            ):
                ranges.append((start, end))
        if ranges:
            self._joined_with_previous_edit(lambda: self._superscript_ranges(ranges))

    def _autoformat_common_century_ordinal(self) -> None:
        _block, prefix = self._current_block_prefix()
        if COMMON_CENTURY_ORDINAL_TYPED_RE.search(prefix) is None:
            return
        end = self.textCursor().position()
        start = end - 1
        source_format = self._format_for_edit(start, end)
        if inline_format_enabled(source_format, SUPERSCRIPT_PROPERTY):
            return

        def apply() -> None:
            self._superscript_ranges([(start, end)])
            continuation_format = QTextCharFormat(source_format)
            continuation_format.setProperty(SUPERSCRIPT_PROPERTY, False)
            continuation_format.setVerticalAlignment(
                QTextCharFormat.VerticalAlignment.AlignNormal
            )
            self.setCurrentCharFormat(continuation_format)

        self._joined_with_previous_edit(apply)

    def _superscript_ranges(self, ranges: list[tuple[int, int]]) -> None:
        semantic_format = QTextCharFormat()
        semantic_format.setProperty(SUPERSCRIPT_PROPERTY, True)
        semantic_format.setVerticalAlignment(
            QTextCharFormat.VerticalAlignment.AlignSuperScript
        )
        for start, end in ranges:
            cursor = QTextCursor(self.document())
            cursor.setPosition(start)
            cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
            cursor.mergeCharFormat(semantic_format)

    def _wrap_selection_in_guillemets(self) -> None:
        selection = self.textCursor()
        start = selection.selectionStart()
        end = selection.selectionEnd()
        opening, _ = convert_straight_quotes_stateful('"', opening_next=True)
        closing, _ = convert_straight_quotes_stateful('"', opening_next=False)
        opening_format = self._plain_wrapper_format(
            self._format_for_edit(start, min(start + 1, end))
        )
        closing_format = self._plain_wrapper_format(
            self._format_for_edit(max(start, end - 1), end)
        )

        edit_block = QTextCursor(self.document())
        edit_block.beginEditBlock()
        try:
            self._replace_range(end, end, closing, closing_format)
            self._replace_range(start, start, opening, opening_format)
        finally:
            edit_block.endEditBlock()
        cursor = QTextCursor(self.document())
        cursor.setPosition(end + _utf16_length(opening) + _utf16_length(closing))
        self.setTextCursor(cursor)

    def _opening_quote_at_position(self, position: int) -> bool:
        opening_next = True
        block = self.document().begin()
        while block.isValid() and block.position() < position:
            length = _python_index_for_utf16_offset(
                block.text(),
                max(0, position - block.position()),
            )
            for char in block.text()[:length]:
                if char in (OPENING_GUILLEMET, CURLY_OPENING_QUOTE):
                    opening_next = False
                elif char in (CLOSING_GUILLEMET, CURLY_CLOSING_QUOTE):
                    opening_next = True
                elif char == '"':
                    opening_next = not opening_next
            block = block.next()
        return opening_next

    def _current_block_prefix(self):
        cursor = self.textCursor()
        block = cursor.block()
        relative_position = _python_index_for_utf16_offset(
            block.text(),
            max(0, cursor.position() - block.position()),
        )
        return block, block.text()[:relative_position]

    def _joined_with_previous_edit(self, operation: Callable[[], None]) -> None:
        edit_block = QTextCursor(self.document())
        edit_block.joinPreviousEditBlock()
        try:
            operation()
        finally:
            edit_block.endEditBlock()

    def _replace_range(
        self,
        start: int,
        end: int,
        replacement: str,
        char_format: QTextCharFormat,
    ) -> None:
        cursor = QTextCursor(self.document())
        cursor.setPosition(start)
        cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
        if replacement:
            cursor.insertText(replacement, char_format)
        else:
            cursor.removeSelectedText()

    def _format_for_edit(self, start: int, end: int) -> QTextCharFormat:
        document_end = max(0, self.document().characterCount() - 1)
        if start < end and start < document_end:
            cursor = QTextCursor(self.document())
            cursor.setPosition(start)
            cursor.setPosition(min(start + 1, document_end), QTextCursor.MoveMode.KeepAnchor)
            return QTextCharFormat(cursor.charFormat())
        if start < document_end:
            cursor = QTextCursor(self.document())
            cursor.setPosition(start)
            cursor.setPosition(start + 1, QTextCursor.MoveMode.KeepAnchor)
            return QTextCharFormat(cursor.charFormat())
        if start > 0:
            cursor = QTextCursor(self.document())
            cursor.setPosition(start - 1)
            cursor.setPosition(start, QTextCursor.MoveMode.KeepAnchor)
            return QTextCharFormat(cursor.charFormat())
        return QTextCharFormat(self.currentCharFormat())

    @staticmethod
    def _plain_wrapper_format(source: QTextCharFormat) -> QTextCharFormat:
        char_format = QTextCharFormat(source)
        char_format.setProperty(BOLD_PROPERTY, False)
        char_format.setProperty(ITALIC_PROPERTY, False)
        char_format.setProperty(STRIKETHROUGH_PROPERTY, False)
        char_format.setProperty(SUPERSCRIPT_PROPERTY, False)
        char_format.setFontWeight(QFont.Weight.Normal.value)
        char_format.setFontItalic(False)
        char_format.setFontStrikeOut(False)
        char_format.setVerticalAlignment(QTextCharFormat.VerticalAlignment.AlignNormal)
        char_format.setAnchor(False)
        char_format.setAnchorHref("")
        char_format.setFontUnderline(False)
        char_format.clearForeground()
        return char_format


def _block_position(block, python_offset: int) -> int:
    return block.position() + _utf16_length(block.text()[:python_offset])


def _utf16_length(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2


def _utf16_offsets(text: str) -> list[int]:
    offsets = [0]
    total = 0
    for char in text:
        total += 2 if ord(char) > 0xFFFF else 1
        offsets.append(total)
    return offsets


def _python_index_for_utf16_offset(text: str, utf16_offset: int) -> int:
    if utf16_offset <= 0:
        return 0
    consumed = 0
    for index, char in enumerate(text):
        consumed += 2 if ord(char) > 0xFFFF else 1
        if consumed >= utf16_offset:
            return index + 1
    return len(text)
