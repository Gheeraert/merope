"""Read-only Qt rendering of canonical footnote definitions."""

from __future__ import annotations

from PySide6.QtGui import QFont, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import QTextBrowser, QWidget

from bloggen.content.footnotes import FootnoteDefinitions
from bloggen.ui.qt_editor.document_adapter import make_char_format


class FootnotePanel(QTextBrowser):
    """Display definitions without owning or mutating their canonical model."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setReadOnly(True)
        self.setOpenExternalLinks(False)
        self.setObjectName("meropeFootnotePanel")

    def set_definitions(self, definitions: FootnoteDefinitions) -> None:
        document = self.document()
        document.clear()
        cursor = QTextCursor(document)
        first = True
        for note_id in sorted(definitions, key=int):
            if not first:
                cursor.insertBlock()
            first = False
            marker_format = QTextCharFormat()
            marker_format.setFontWeight(QFont.Weight.Bold.value)
            cursor.insertText(f"[{note_id}] ", marker_format)
            for run in definitions[note_id]:
                cursor.insertText(run.text, make_char_format(run))
        cursor.movePosition(QTextCursor.MoveOperation.Start)
        self.setTextCursor(cursor)
        document.clearUndoRedoStacks()
        document.setModified(False)
