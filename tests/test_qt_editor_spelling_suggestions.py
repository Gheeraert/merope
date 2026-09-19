"""Context-menu spelling suggestions (MeropeTextEdit.contextMenuEvent /
_add_spelling_suggestions_menu). Suggestions-only: no "ignore"/"add to
dictionary" — see FrenchSpellChecker.suggestions and
bloggen.ui.qt_editor.spellcheck.match_case.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QApplication

from bloggen.markdown.rich_text_model import (
    PARAGRAPH,
    TABLE,
    TABLE_CELL,
    TABLE_ROW,
    VERBATIM,
    Block,
    InlineRun,
)
from bloggen.ui.qt_editor.document_adapter import populate_document
from bloggen.ui.qt_editor.text_edit import MeropeTextEdit

_EDITORS: list[MeropeTextEdit] = []


@pytest.fixture(scope="module", autouse=True)
def qapplication():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(autouse=True)
def close_editors(qapplication):
    yield
    for editor in _EDITORS:
        editor.hide()
        editor.deleteLater()
    _EDITORS.clear()
    qapplication.processEvents()


def _editor(blocks: list[Block]) -> MeropeTextEdit:
    editor = MeropeTextEdit()
    _EDITORS.append(editor)
    editor.resize(400, 200)
    populate_document(editor.document(), blocks)
    editor.show()
    QApplication.processEvents()
    return editor


def _point_at(editor: MeropeTextEdit, position: int):
    cursor = QTextCursor(editor.document())
    cursor.setPosition(position)
    return editor.cursorRect(cursor).center()


def test_menu_lists_suggestions_for_a_misspelled_word_under_the_click():
    editor = _editor([Block(kind=PARAGRAPH, runs=[InlineRun(text="Ceci est un texe.")])])
    point = _point_at(editor, 14)  # inside "texe"

    menu = editor._create_merope_context_menu(point)
    editor._add_spelling_suggestions_menu(menu, point)

    labels = [action.text() for action in menu.actions()]
    assert "texte" in labels


def test_suggestions_appear_before_the_standard_actions():
    editor = _editor([Block(kind=PARAGRAPH, runs=[InlineRun(text="Ceci est un texe.")])])
    point = _point_at(editor, 14)

    menu = editor._create_merope_context_menu(point)
    editor._add_spelling_suggestions_menu(menu, point)

    actions = menu.actions()
    first_suggestion_index = next(
        index for index, action in enumerate(actions) if action.text() == "texte"
    )
    first_standard_index = next(
        index for index, action in enumerate(actions) if "Copy" in action.text()
    )
    assert first_suggestion_index < first_standard_index


def test_selecting_a_suggestion_replaces_the_word_in_place():
    editor = _editor([Block(kind=PARAGRAPH, runs=[InlineRun(text="Ceci est un texe.")])])
    point = _point_at(editor, 14)

    menu = editor._create_merope_context_menu(point)
    editor._add_spelling_suggestions_menu(menu, point)
    action = next(action for action in menu.actions() if action.text() == "texte")
    action.trigger()
    QApplication.processEvents()

    assert editor.document().toPlainText() == "Ceci est un texte."


def test_selecting_a_suggestion_preserves_original_capitalization():
    editor = _editor([Block(kind=PARAGRAPH, runs=[InlineRun(text="Ceci est un Texe.")])])
    point = _point_at(editor, 14)

    menu = editor._create_merope_context_menu(point)
    editor._add_spelling_suggestions_menu(menu, point)
    action = next(action for action in menu.actions() if action.text() == "Texte")
    action.trigger()
    QApplication.processEvents()

    assert editor.document().toPlainText() == "Ceci est un Texte."


def test_no_suggestions_are_added_for_a_correctly_spelled_word():
    editor = _editor([Block(kind=PARAGRAPH, runs=[InlineRun(text="Ceci est correct.")])])
    point = _point_at(editor, 3)

    menu = editor._create_merope_context_menu(point)
    before = [action.text() for action in menu.actions()]
    editor._add_spelling_suggestions_menu(menu, point)

    assert [action.text() for action in menu.actions()] == before


def test_no_suggestions_inside_a_raw_verbatim_block():
    editor = _editor([Block(kind=VERBATIM, raw_text="texe non verifie")])
    point = _point_at(editor, 2)

    menu = editor._create_merope_context_menu(point)
    before = [action.text() for action in menu.actions()]
    editor._add_spelling_suggestions_menu(menu, point)

    assert [action.text() for action in menu.actions()] == before


def test_suggestions_still_work_inside_a_merope_table_cell():
    cell = Block(kind=TABLE_CELL, runs=[InlineRun(text="texe")])
    row = Block(kind=TABLE_ROW, children=[cell])
    table = Block(kind=TABLE, children=[row])
    editor = _editor([table])
    point = _point_at(editor, 1)

    menu = editor._create_merope_context_menu(point)
    editor._add_spelling_suggestions_menu(menu, point)

    assert any(action.text() == "texte" for action in menu.actions())
