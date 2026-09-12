"""Enter must always leave an ordinary, body-sized paragraph behind it."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCharFormat, QTextCursor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from bloggen.markdown.rich_text_model import (
    BLOCKQUOTE,
    BULLET_LIST,
    HEADING,
    LIST_ITEM,
    PARAGRAPH,
    Block,
    InlineRun,
)
from bloggen.ui.qt_editor.constants import BODY_POINT_SIZE, HEADING_POINT_SIZES
from bloggen.ui.qt_editor.document_adapter import extract_blocks, populate_document
from bloggen.ui.qt_editor.text_edit import MeropeTextEdit


@pytest.fixture(scope="module", autouse=True)
def qapplication():
    yield QApplication.instance() or QApplication([])


def _editor(blocks: list[Block]) -> MeropeTextEdit:
    editor = MeropeTextEdit()
    populate_document(editor.document(), blocks)
    editor.show()
    QApplication.processEvents()
    return editor


def _caret(editor: MeropeTextEdit, position: int | None = None) -> None:
    cursor = QTextCursor(editor.document())
    if position is None:
        cursor.movePosition(QTextCursor.MoveOperation.End)
    else:
        cursor.setPosition(position)
    editor.setTextCursor(cursor)


def _typed_size(editor: MeropeTextEdit) -> float:
    block = editor.textCursor().block()
    return block.begin().fragment().charFormat().fontPointSize()


def test_enter_after_a_heading_opens_a_body_paragraph():
    editor = _editor([Block(kind=HEADING, level=1, runs=[InlineRun(text="Titre")])])
    _caret(editor)

    QTest.keyClick(editor, Qt.Key.Key_Return)
    QTest.keyClicks(editor, "Texte")

    assert _typed_size(editor) == BODY_POINT_SIZE
    assert extract_blocks(editor.document()) == [
        Block(kind=HEADING, level=1, runs=[InlineRun(text="Titre")]),
        Block(kind=PARAGRAPH, runs=[InlineRun(text="Texte")], alignment="justify"),
    ]
    editor.undo()
    editor.undo()
    assert extract_blocks(editor.document()) == [
        Block(kind=HEADING, level=1, runs=[InlineRun(text="Titre")])
    ]
    editor.close()


def test_enter_inside_a_heading_splits_it_into_two_headings():
    editor = _editor([Block(kind=HEADING, level=2, runs=[InlineRun(text="Titre")])])
    _caret(editor, 2)

    QTest.keyClick(editor, Qt.Key.Key_Return)

    assert [(block.kind, block.level) for block in extract_blocks(editor.document())] == [
        (HEADING, 2),
        (HEADING, 2),
    ]
    assert _typed_size(editor) == HEADING_POINT_SIZES[2]
    editor.close()


def test_leaving_a_list_with_a_second_enter_gives_a_body_paragraph():
    editor = _editor(
        [Block(kind=BULLET_LIST, children=[Block(kind=LIST_ITEM, runs=[InlineRun(text="un")])])]
    )
    _caret(editor)

    QTest.keyClick(editor, Qt.Key.Key_Return)
    QTest.keyClick(editor, Qt.Key.Key_Return)
    QTest.keyClicks(editor, "Suite")

    assert _typed_size(editor) == BODY_POINT_SIZE
    blocks = extract_blocks(editor.document())
    assert [block.kind for block in blocks] == [BULLET_LIST, PARAGRAPH]
    assert blocks[1].runs == [InlineRun(text="Suite")]
    editor.close()


@pytest.mark.parametrize(
    "block",
    [
        Block(kind=PARAGRAPH, runs=[InlineRun(text="Texte", bold=True)]),
        Block(kind=BLOCKQUOTE, runs=[InlineRun(text="Citation")]),
    ],
)
def test_enter_keeps_body_size_after_paragraphs_and_quotes(block):
    editor = _editor([block])
    _caret(editor)

    QTest.keyClick(editor, Qt.Key.Key_Return)
    QTest.keyClicks(editor, "abc")

    assert _typed_size(editor) == BODY_POINT_SIZE
    assert extract_blocks(editor.document())[1].kind == block.kind
    editor.close()


def test_typing_into_an_empty_document_uses_body_size():
    editor = _editor([])

    QTest.keyClicks(editor, "abc")

    assert _typed_size(editor) == BODY_POINT_SIZE
    editor.close()


def test_unsized_text_is_zoomed_like_body_text():
    editor = _editor([Block(kind=PARAGRAPH, runs=[InlineRun(text="Texte")])])
    cursor = QTextCursor(editor.document())
    cursor.movePosition(QTextCursor.MoveOperation.End)
    cursor.insertText(" nu", QTextCharFormat())  # no explicit size at all

    editor.adjust_zoom(5)

    overlay = [
        item.format.fontPointSize()
        for item in editor.document().begin().layout().formats()
    ]
    assert overlay and all(size == BODY_POINT_SIZE * 1.5 for size in overlay)
    assert editor.document().defaultFont().pointSizeF() == BODY_POINT_SIZE
    editor.close()
