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


def _scrollable_editor(last_block: Block) -> MeropeTextEdit:
    blocks = [
        Block(
            kind=PARAGRAPH,
            runs=[InlineRun(text=f"Paragraphe {index} " + "texte " * 8)],
        )
        for index in range(10)
    ]
    blocks.append(last_block)
    editor = _editor(blocks)
    editor.resize(360, 160)
    editor.activateWindow()
    editor.setFocus()
    QApplication.processEvents()
    assert editor.verticalScrollBar().maximum() > 0
    return editor


def _assert_caret_and_viewport_stable_after_enter(
    editor: MeropeTextEdit,
    *,
    expected_position: int,
    expected_block_number: int,
) -> None:
    cursor = editor.textCursor()
    assert cursor.position() == expected_position
    assert cursor.anchor() == expected_position
    assert cursor.blockNumber() == expected_block_number
    assert editor.hasFocus()
    assert editor.verticalScrollBar().value() > 0

    QApplication.processEvents()

    cursor = editor.textCursor()
    assert cursor.position() == expected_position
    assert cursor.anchor() == expected_position
    assert cursor.blockNumber() == expected_block_number
    assert editor.hasFocus()
    assert editor.verticalScrollBar().value() > 0


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


def test_enter_at_end_of_scrollable_document_keeps_caret_and_viewport_visible():
    editor = _scrollable_editor(
        Block(kind=PARAGRAPH, runs=[InlineRun(text="Dernier paragraphe.")])
    )
    last = editor.document().lastBlock()
    cursor = QTextCursor(last)
    cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock)
    editor.setTextCursor(cursor)
    editor.ensureCursorVisible()
    editor.verticalScrollBar().setValue(editor.verticalScrollBar().maximum())
    QApplication.processEvents()
    before = editor.textCursor()
    before_position = before.position()
    before_block_number = before.blockNumber()
    scroll_before = editor.verticalScrollBar().value()
    assert scroll_before > 0

    QTest.keyClick(editor, Qt.Key.Key_Return)

    _assert_caret_and_viewport_stable_after_enter(
        editor,
        expected_position=before_position + 1,
        expected_block_number=before_block_number + 1,
    )
    assert editor.textCursor().block().text() == ""
    editor.close()


def test_enter_in_middle_of_rich_blockquote_keeps_caret_and_viewport_visible():
    text = "Citation riche en bas du document."
    editor = _scrollable_editor(
        Block(kind=BLOCKQUOTE, runs=[InlineRun(text=text, bold=True)])
    )
    last = editor.document().lastBlock()
    split_offset = len("Citation riche")
    cursor = QTextCursor(last)
    cursor.setPosition(last.position() + split_offset)
    editor.setTextCursor(cursor)
    editor.ensureCursorVisible()
    editor.verticalScrollBar().setValue(editor.verticalScrollBar().maximum())
    QApplication.processEvents()
    before = editor.textCursor()
    before_position = before.position()
    before_block_number = before.blockNumber()
    scroll_before = editor.verticalScrollBar().value()
    assert scroll_before > 0

    QTest.keyClick(editor, Qt.Key.Key_Return)

    _assert_caret_and_viewport_stable_after_enter(
        editor,
        expected_position=before_position + 1,
        expected_block_number=before_block_number + 1,
    )
    assert editor.textCursor().block().text() == text[split_offset:]
    editor.close()
