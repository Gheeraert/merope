from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QApplication, QTextEdit

from bloggen.markdown.rich_text_model import PARAGRAPH, Block, InlineRun
from bloggen.ui.qt_editor.document_adapter import extract_blocks, populate_document
from bloggen.ui.qt_editor.formatting import set_link, toggle_bold


@pytest.fixture(scope="module")
def qapplication():
    app = QApplication.instance() or QApplication([])
    yield app


def test_qt_native_undo_redo_for_text(qapplication):
    editor = QTextEdit()
    populate_document(
        editor.document(),
        [Block(kind=PARAGRAPH, runs=[InlineRun(text="Texte")])],
    )
    cursor = editor.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.End)
    cursor.insertText(" ajoute")

    assert extract_blocks(editor.document())[0].runs[0].text == "Texte ajoute"
    assert editor.document().isUndoAvailable()

    editor.undo()
    assert extract_blocks(editor.document())[0].runs[0].text == "Texte"

    editor.redo()
    assert extract_blocks(editor.document())[0].runs[0].text == "Texte ajoute"


def test_qt_native_undo_redo_for_formatting(qapplication):
    editor = QTextEdit()
    populate_document(
        editor.document(),
        [Block(kind=PARAGRAPH, runs=[InlineRun(text="Texte")])],
    )
    cursor = editor.textCursor()
    cursor.setPosition(0)
    cursor.setPosition(5, QTextCursor.MoveMode.KeepAnchor)
    editor.setTextCursor(cursor)

    toggle_bold(editor)
    assert extract_blocks(editor.document())[0].runs == [InlineRun(text="Texte", bold=True)]

    editor.undo()
    assert extract_blocks(editor.document())[0].runs == [InlineRun(text="Texte")]

    editor.redo()
    assert extract_blocks(editor.document())[0].runs == [InlineRun(text="Texte", bold=True)]


def test_link_command_uses_native_anchor_and_roundtrips(qapplication):
    editor = QTextEdit()
    populate_document(
        editor.document(),
        [Block(kind=PARAGRAPH, runs=[InlineRun(text="Lien")])],
    )
    cursor = editor.textCursor()
    cursor.setPosition(0)
    cursor.setPosition(4, QTextCursor.MoveMode.KeepAnchor)
    editor.setTextCursor(cursor)

    set_link(editor, "https://example.org")

    assert extract_blocks(editor.document())[0].runs == [
        InlineRun(text="Lien", link_href="https://example.org")
    ]
