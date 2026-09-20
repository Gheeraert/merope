"""Context-menu spelling suggestions (MeropeTextEdit.contextMenuEvent /
_add_spelling_suggestions_menu): suggestions plus "Ignorer tout" and
"Ajouter au dictionnaire" — see FrenchSpellChecker.suggestions,
SpellingExceptions and bloggen.ui.qt_editor.spellcheck.match_case.
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


def _editor_with_exceptions(tmp_path, text):
    from bloggen.ui.qt_editor.spellcheck import FrenchSpellChecker, SpellingExceptions

    editor = _editor([Block(kind=PARAGRAPH, runs=[InlineRun(text=text)])])
    exceptions = SpellingExceptions(tmp_path / "dico.txt")
    editor._spell_highlighter.checker = FrenchSpellChecker(exceptions)
    editor._spell_highlighter.rehighlight()
    return editor, exceptions


def _underlined(editor):
    from PySide6.QtGui import QTextCharFormat

    block = editor.document().firstBlock()
    return [
        block.text()[f.start : f.start + f.length]
        for f in block.layout().formats()
        if f.format.underlineStyle() == QTextCharFormat.UnderlineStyle.SpellCheckUnderline
    ]


def _trigger(editor, label):
    point = _point_at(editor, 14)
    menu = editor._create_merope_context_menu(point)
    editor._add_spelling_suggestions_menu(menu, point)
    next(a for a in menu.actions() if a.text() == label).trigger()


def test_ignore_all_stops_underlining_every_occurrence_without_saving(tmp_path):
    editor, exceptions = _editor_with_exceptions(tmp_path, "Ceci est un texe et un texe.")
    assert _underlined(editor) == ["texe", "texe"]

    _trigger(editor, "Ignorer tout")

    assert _underlined(editor) == []
    assert not (tmp_path / "dico.txt").exists()
    assert not editor.document().isModified()


def test_add_to_dictionary_persists_across_checkers(tmp_path):
    from bloggen.ui.qt_editor.spellcheck import SpellingExceptions

    editor, _exceptions = _editor_with_exceptions(tmp_path, "Ceci est un texe.")

    _trigger(editor, "Ajouter au dictionnaire")

    assert _underlined(editor) == []
    assert SpellingExceptions(tmp_path / "dico.txt").contains("texe")
    assert not editor.document().isModified()


def test_add_to_dictionary_keeps_underline_state_under_zoom(tmp_path):
    editor, _exceptions = _editor_with_exceptions(tmp_path, "Ceci est un texe et un tixe.")
    editor.adjust_zoom(2)

    _trigger(editor, "Ignorer tout")

    assert _underlined(editor) == ["tixe"]
