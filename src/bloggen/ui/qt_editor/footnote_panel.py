"""Read-only Qt rendering of canonical footnote definitions."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtGui import QFont, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import QTextBrowser, QWidget

from bloggen.content.footnotes import FootnoteDefinitions
from bloggen.ui.qt_editor.document_adapter import make_char_format


class FootnotePanel(QTextBrowser):
    """Display definitions without owning or mutating their canonical model."""

    noteSelected = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setReadOnly(True)
        self.setOpenExternalLinks(False)
        self.setObjectName("meropeFootnotePanel")
        self._note_ids_by_block: dict[int, str] = {}
        self.cursorPositionChanged.connect(self._emit_selected_note)

    @property
    def selected_note_id(self) -> str | None:
        return self._note_ids_by_block.get(self.textCursor().blockNumber())

    def set_definitions(self, definitions: FootnoteDefinitions) -> None:
        previous_id = self.selected_note_id
        document = self.document()
        self._note_ids_by_block = {}
        document.clear()
        cursor = QTextCursor(document)
        first = True
        for note_id in sorted(definitions, key=int):
            if not first:
                cursor.insertBlock()
            first = False
            self._note_ids_by_block[cursor.blockNumber()] = note_id
            marker_format = QTextCharFormat()
            marker_format.setFontWeight(QFont.Weight.Bold.value)
            cursor.insertText(f"[{note_id}] ", marker_format)
            for run in definitions[note_id]:
                cursor.insertText(run.text, make_char_format(run))
        cursor.movePosition(QTextCursor.MoveOperation.Start)
        self.setTextCursor(cursor)
        document.clearUndoRedoStacks()
        document.setModified(False)
        preferred_id = (
            previous_id
            if previous_id is not None and previous_id in definitions
            else next(iter(sorted(definitions, key=int)), None)
        )
        if preferred_id is not None:
            self.select_note(preferred_id)
        else:
            self.noteSelected.emit(None)

    def select_note(self, note_id: str) -> bool:
        for block_number, candidate_id in self._note_ids_by_block.items():
            if candidate_id != note_id:
                continue
            block = self.document().findBlockByNumber(block_number)
            cursor = QTextCursor(block)
            self.setTextCursor(cursor)
            self.ensureCursorVisible()
            self.noteSelected.emit(note_id)
            return True
        return False

    def _emit_selected_note(self) -> None:
        self.noteSelected.emit(self.selected_note_id)
