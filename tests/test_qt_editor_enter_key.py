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


def _place_caret_at_viewport_y(
    editor: MeropeTextEdit,
    cursor: QTextCursor,
    target_y: int,
) -> None:
    editor.setTextCursor(cursor)
    editor.ensureCursorVisible()
    QApplication.processEvents()
    scroll = editor.verticalScrollBar()
    scroll.setValue(scroll.value() + editor.cursorRect().top() - target_y)
    QApplication.processEvents()
    assert abs(editor.cursorRect().top() - target_y) <= 2


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


def _block_with_text(editor: MeropeTextEdit, text: str):
    block = editor.document().begin()
    while block.isValid():
        if block.text() == text:
            return block
        block = block.next()
    raise AssertionError(f"Bloc introuvable : {text!r}")


@pytest.mark.parametrize(
    "case",
    [
        {
            "block": Block(kind=PARAGRAPH, runs=[InlineRun(text="Cible milieu")]),
            "offset": len("Cible"),
            "vertical": "center",
        },
        {
            "block": Block(kind=PARAGRAPH, runs=[InlineRun(text="Cible fin")]),
            "offset": len("Cible fin"),
            "vertical": "center",
        },
        {
            "block": Block(kind=PARAGRAPH, runs=[InlineRun(text="Cible bas")]),
            "offset": len("Cible"),
            "vertical": "bottom",
        },
        {
            "block": Block(kind=PARAGRAPH, runs=[InlineRun(text="Cible haut")]),
            "offset": len("Cible"),
            "vertical": "top",
        },
        {
            "block": Block(
                kind=BLOCKQUOTE,
                runs=[InlineRun(text="Cible citation", bold=True)],
            ),
            "offset": len("Cible"),
            "vertical": "center",
        },
        {
            "block": Block(
                kind=HEADING,
                level=2,
                runs=[InlineRun(text="Cible titre fin")],
            ),
            "offset": len("Cible titre fin"),
            "vertical": "center",
        },
        {
            "block": Block(
                kind=HEADING,
                level=2,
                runs=[InlineRun(text="Cible titre milieu")],
            ),
            "offset": len("Cible titre"),
            "vertical": "center",
        },
        {
            "block": Block(
                kind=BULLET_LIST,
                children=[Block(kind=LIST_ITEM, runs=[InlineRun(text="Cible liste")])],
            ),
            "target_text": "Cible liste",
            "offset": len("Cible liste"),
            "vertical": "center",
        },
        {
            "block": Block(kind=PARAGRAPH, runs=[InlineRun(text="Cible zoom")]),
            "offset": len("Cible"),
            "vertical": "center",
            "zoom_steps": 5,
        },
        {
            "block": Block(kind=PARAGRAPH, runs=[InlineRun(text="Cible figure")]),
            "offset": len("Cible"),
            "vertical": "center",
            "with_figure": True,
        },
    ],
    ids=[
        "paragraph-middle",
        "paragraph-end",
        "near-bottom",
        "near-top",
        "rich-blockquote",
        "heading-end",
        "heading-middle",
        "list",
        "zoom-150",
        "figure-caption-elsewhere",
    ],
)
def test_enter_keeps_visible_caret_near_same_viewport_y(case):
    prefix = [
        Block(
            kind=PARAGRAPH,
            runs=[InlineRun(text=f"Paragraphe {index} " + "texte " * 6)],
        )
        for index in range(12)
    ]
    if case.get("with_figure"):
        prefix.append(
            Block(
                kind=PARAGRAPH,
                runs=[InlineRun(image_src="missing.png", image_alt="Légende")],
            )
        )
    blocks = prefix + [case["block"]] + [
        Block(
            kind=PARAGRAPH,
            runs=[InlineRun(text=f"Suite {index} " + "texte " * 6)],
        )
        for index in range(8)
    ]
    editor = _editor(blocks)
    editor.resize(360, 180)
    editor.activateWindow()
    editor.setFocus()
    QApplication.processEvents()
    if case.get("zoom_steps"):
        editor.adjust_zoom(case["zoom_steps"])
        QApplication.processEvents()
    target_text = case.get("target_text") or "".join(
        run.text for run in case["block"].runs
    )
    block = _block_with_text(editor, target_text)
    cursor = QTextCursor(block)
    cursor.setPosition(block.position() + case["offset"])
    editor.setTextCursor(cursor)
    line_height = editor.cursorRect().height()
    if case["vertical"] == "top":
        target_y = line_height
    elif case["vertical"] == "bottom":
        target_y = editor.viewport().height() - line_height * 2
    else:
        target_y = editor.viewport().height() // 2
    _place_caret_at_viewport_y(editor, cursor, target_y)
    before_position = editor.textCursor().position()
    before_block_number = editor.textCursor().blockNumber()
    before_top = editor.cursorRect().top()
    before_blocks = extract_blocks(editor.document())

    QTest.keyClick(editor, Qt.Key.Key_Return)

    after = editor.textCursor()
    assert after.position() == before_position + 1
    assert after.anchor() == before_position + 1
    assert after.blockNumber() == before_block_number + 1
    assert editor.hasFocus()
    assert 0 <= editor.cursorRect().top()
    assert editor.cursorRect().bottom() <= editor.viewport().height()
    assert abs(editor.cursorRect().top() - before_top) <= line_height * 2

    QApplication.processEvents()

    assert editor.textCursor().position() == before_position + 1
    assert editor.textCursor().blockNumber() == before_block_number + 1
    assert editor.hasFocus()
    assert 0 <= editor.cursorRect().top()
    assert editor.cursorRect().bottom() <= editor.viewport().height()
    assert abs(editor.cursorRect().top() - before_top) <= line_height * 2
    after_blocks = extract_blocks(editor.document())

    editor.undo()
    assert extract_blocks(editor.document()) == before_blocks
    editor.redo()
    assert extract_blocks(editor.document()) == after_blocks
    assert editor.textCursor().position() > 0
    editor.close()
