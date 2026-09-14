from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtGui import QTextCursor, QTextTable
from PySide6.QtWidgets import QApplication

from bloggen.markdown.rich_text_model import (
    BLOCKQUOTE,
    BULLET_LIST,
    HEADING,
    LIST_ITEM,
    ORDERED_LIST,
    PARAGRAPH,
    TABLE,
    TABLE_CELL,
    TABLE_ROW,
    VERBATIM,
    Block,
    InlineRun,
)
from bloggen.ui.qt_editor.constants import BLOCK_KIND_PROPERTY, HEADING_LEVEL_PROPERTY
from bloggen.ui.qt_editor.document_adapter import (
    extract_blocks,
    is_caption_block,
    is_figure_block,
    populate_document,
)
from bloggen.ui.qt_editor.window import QtEditorWindow


_WINDOWS: list[QtEditorWindow] = []


@pytest.fixture(scope="module", autouse=True)
def qapplication():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(autouse=True)
def close_windows(qapplication):
    yield
    for window in _WINDOWS:
        window.autosave_timer.stop()
        window.editor.document().setModified(False)
        window.hide()
        window.deleteLater()
    _WINDOWS.clear()
    qapplication.processEvents()


def _window(blocks: list[Block]) -> QtEditorWindow:
    window = QtEditorWindow()
    _WINDOWS.append(window)
    populate_document(window.editor.document(), blocks)
    QApplication.processEvents()
    return window


def _block(kind: str, text: str, *, level: int | None = None, **run_kwargs) -> Block:
    return Block(kind=kind, level=level, runs=[InlineRun(text=text, **run_kwargs)])


def _checked_styles(window: QtEditorWindow) -> set[str]:
    return {
        key for key, action in window.block_style_actions.items() if action.isChecked()
    }


def _block_at(document, index: int):
    block = document.begin()
    for _ in range(index):
        block = block.next()
    assert block.isValid()
    return block


def _place_cursor(window: QtEditorWindow, block_index: int, offset: int = 0) -> None:
    block = _block_at(window.editor.document(), block_index)
    cursor = QTextCursor(block)
    cursor.setPosition(min(block.position() + offset, block.position() + block.length() - 1))
    window.editor.setTextCursor(cursor)
    QApplication.processEvents()


def _select_blocks(window: QtEditorWindow, first: int, last: int) -> None:
    first_block = _block_at(window.editor.document(), first)
    last_block = _block_at(window.editor.document(), last)
    cursor = QTextCursor(window.editor.document())
    cursor.setPosition(first_block.position())
    cursor.setPosition(
        last_block.position() + last_block.length() - 1,
        QTextCursor.MoveMode.KeepAnchor,
    )
    window.editor.setTextCursor(cursor)
    QApplication.processEvents()


def _table(*rows: tuple[str, ...]) -> Block:
    return Block(
        kind=TABLE,
        children=[
            Block(
                kind=TABLE_ROW,
                children=[
                    Block(kind=TABLE_CELL, runs=[InlineRun(text=text)]) for text in row
                ],
            )
            for row in rows
        ],
    )


def test_block_actions_are_retained_in_an_exclusive_group():
    window = _window([_block(PARAGRAPH, "Texte")])

    assert window.block_style_group.isExclusive()
    assert list(window.block_style_actions) == [
        "paragraph",
        "h1",
        "h2",
        "h3",
        "h4",
        "blockquote",
    ]
    assert set(window.block_style_group.actions()) == set(
        window.block_style_actions.values()
    )
    assert _checked_styles(window) == {"paragraph"}


def test_cursor_tracks_paragraph_headings_and_blockquote():
    blocks = [
        _block(PARAGRAPH, "Paragraphe"),
        *[_block(HEADING, f"Titre {level}", level=level) for level in range(1, 5)],
        _block(BLOCKQUOTE, "Citation"),
    ]
    window = _window(blocks)

    for index, expected in enumerate(
        ("paragraph", "h1", "h2", "h3", "h4", "blockquote")
    ):
        _place_cursor(window, index, 1)
        assert _checked_styles(window) == {expected}


def test_empty_and_formatted_aligned_paragraphs_remain_paragraphs():
    window = _window(
        [
            Block(kind=PARAGRAPH),
            *[
                Block(
                    kind=PARAGRAPH,
                    alignment=alignment,
                    runs=[InlineRun(text=alignment, bold=True, italic=True)],
                )
                for alignment in ("left", "center", "right", "justify")
            ],
        ]
    )

    for index in range(5):
        _place_cursor(window, index)
        assert _checked_styles(window) == {"paragraph"}


@pytest.mark.parametrize(
    ("blocks", "expected"),
    [
        ([_block(PARAGRAPH, "Un"), _block(PARAGRAPH, "Deux")], "paragraph"),
        (
            [_block(HEADING, "Un", level=2), _block(HEADING, "Deux", level=2)],
            "h2",
        ),
        ([_block(BLOCKQUOTE, "Un"), _block(BLOCKQUOTE, "Deux")], "blockquote"),
    ],
)
def test_homogeneous_multiblock_selection_keeps_one_style(blocks, expected):
    window = _window(blocks)

    _select_blocks(window, 0, 1)

    assert _checked_styles(window) == {expected}


@pytest.mark.parametrize(
    "blocks",
    [
        [_block(PARAGRAPH, "Texte"), _block(HEADING, "Titre", level=2)],
        [_block(HEADING, "H2", level=2), _block(HEADING, "H3", level=3)],
        [
            _block(PARAGRAPH, "Texte"),
            Block(kind=BULLET_LIST, children=[_block(LIST_ITEM, "Élément")]),
        ],
    ],
)
def test_mixed_multiblock_selection_clears_the_group(blocks):
    window = _window(blocks)

    _select_blocks(window, 0, 1)

    assert _checked_styles(window) == set()
    assert window.block_style_group.isExclusive()


def test_partial_selection_uses_its_single_block_style():
    window = _window([_block(HEADING, "Titre partiel", level=3)])
    block = window.editor.document().begin()
    cursor = QTextCursor(block)
    cursor.setPosition(block.position() + 1)
    cursor.setPosition(block.position() + 6, QTextCursor.MoveMode.KeepAnchor)

    window.editor.setTextCursor(cursor)
    QApplication.processEvents()

    assert _checked_styles(window) == {"h3"}


def test_native_heading_level_is_used_as_a_semantic_fallback():
    window = _window([_block(HEADING, "Titre natif", level=4)])
    block = window.editor.document().begin()
    block_format = block.blockFormat()
    block_format.clearProperty(BLOCK_KIND_PROPERTY)
    block_format.clearProperty(HEADING_LEVEL_PROPERTY)
    block_format.setHeadingLevel(4)
    cursor = QTextCursor(block)
    cursor.setBlockFormat(block_format)
    QApplication.processEvents()

    assert _checked_styles(window) == {"h4"}


@pytest.mark.parametrize("list_kind", [BULLET_LIST, ORDERED_LIST])
def test_lists_have_no_active_block_style(list_kind):
    window = _window(
        [Block(kind=list_kind, children=[_block(LIST_ITEM, "Élément")])]
    )

    _place_cursor(window, 0, 1)
    assert _checked_styles(window) == set()


def test_raw_blocks_and_graphical_tables_have_no_active_block_style():
    graphical_table = _table(("En-tête",), ("Cellule",))
    window = _window(
        [
            Block(kind=VERBATIM, raw_text="<section data-x='1'>\nraw\n</section>"),
            graphical_table,
        ]
    )

    _place_cursor(window, 0, 1)
    assert _checked_styles(window) == set()

    table = next(
        frame
        for frame in window.editor.document().rootFrame().childFrames()
        if isinstance(frame, QTextTable)
    )
    window.editor.setTextCursor(table.cellAt(0, 0).firstCursorPosition())
    QApplication.processEvents()
    assert _checked_styles(window) == set()


def test_raw_table_figure_and_caption_have_no_active_block_style():
    raw_table = Block(
        kind=TABLE,
        children=[
            Block(
                kind=TABLE_ROW,
                children=[
                    Block(
                        kind=TABLE_CELL,
                        runs=[InlineRun(image_src="cell.png", image_alt="Image")],
                    )
                ],
            )
        ],
    )
    figure = Block(
        kind=PARAGRAPH,
        runs=[InlineRun(image_src="figure.png", image_alt="Légende")],
    )
    window = _window([raw_table, figure])
    document = window.editor.document()

    block = document.begin()
    cursor = QTextCursor(block)
    cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock)
    window.editor.setTextCursor(cursor)
    QApplication.processEvents()
    assert _checked_styles(window) == set()

    image_block = document.begin()
    while image_block.isValid() and not is_figure_block(image_block):
        image_block = image_block.next()
    assert image_block.isValid()
    window.editor.setTextCursor(QTextCursor(image_block))
    QApplication.processEvents()
    assert _checked_styles(window) == set()

    caption_block = image_block.next()
    assert is_caption_block(caption_block)
    window.editor.setTextCursor(QTextCursor(caption_block))
    QApplication.processEvents()
    assert _checked_styles(window) == set()


@pytest.mark.parametrize(
    ("kind", "level"),
    [("foreign-structure", None), (HEADING, "not-a-level")],
)
def test_foreign_or_malformed_block_has_no_active_block_style(kind, level):
    window = _window([_block(PARAGRAPH, "Texte")])
    block = window.editor.document().begin()
    block_format = block.blockFormat()
    block_format.setProperty(BLOCK_KIND_PROPERTY, kind)
    if level is not None:
        block_format.setProperty(HEADING_LEVEL_PROPERTY, level)
    cursor = QTextCursor(block)
    cursor.setBlockFormat(block_format)
    QApplication.processEvents()

    assert _checked_styles(window) == set()


def test_heading_and_inline_actions_are_synchronized_independently():
    window = _window([_block(HEADING, "Titre", level=2, bold=True)])
    _place_cursor(window, 0, 2)

    assert _checked_styles(window) == {"h2"}
    assert window.bold_action.isChecked()


def test_click_heading_then_undo_redo_resynchronizes_the_group():
    window = _window([_block(PARAGRAPH, "Texte")])
    document = window.editor.document()

    window.block_style_actions["h2"].trigger()
    QApplication.processEvents()
    assert _checked_styles(window) == {"h2"}
    assert extract_blocks(document)[0].kind == HEADING
    assert extract_blocks(document)[0].level == 2

    window.editor.undo()
    QApplication.processEvents()
    assert _checked_styles(window) == {"paragraph"}
    assert extract_blocks(document)[0].kind == PARAGRAPH

    window.editor.redo()
    QApplication.processEvents()
    assert _checked_styles(window) == {"h2"}
    assert extract_blocks(document)[0].kind == HEADING
    assert extract_blocks(document)[0].level == 2


def test_cursor_observation_does_not_modify_model_dirty_or_undo():
    blocks = [
        _block(PARAGRAPH, "Texte"),
        _block(HEADING, "Titre", level=1),
        _block(BLOCKQUOTE, "Citation"),
    ]
    window = _window(blocks)
    document = window.editor.document()
    before = extract_blocks(document)
    assert not document.isModified()
    assert not document.isUndoAvailable()

    for index in range(3):
        _place_cursor(window, index, 1)

    assert extract_blocks(document) == before
    assert not document.isModified()
    assert not document.isUndoAvailable()
