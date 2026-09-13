from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor, QTextDocument, QTextLength, QTextTable
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from bloggen.markdown.rich_text_export import blocks_to_markdown
from bloggen.markdown.rich_text_model import (
    TABLE,
    TABLE_CELL,
    TABLE_ROW,
    Block,
    InlineRun,
)
from bloggen.ui.qt_editor.constants import (
    MEROPE_TABLE_PROPERTY,
    TABLE_BLOCK_MARGINS,
    TABLE_BORDER_WIDTH,
    TABLE_CELL_PADDING,
    TABLE_CELL_SPACING,
    TABLE_HEADER_BACKGROUND,
)
from bloggen.ui.qt_editor.document_adapter import extract_blocks, populate_document
from bloggen.ui.qt_editor.table_structure import (
    insert_table_column,
    insert_table_row,
    remove_table_column,
    remove_table_row,
)
from bloggen.ui.qt_editor.text_edit import MeropeTextEdit


@pytest.fixture(scope="module", autouse=True)
def qapplication():
    app = QApplication.instance() or QApplication([])
    yield app


def _cell(*runs: InlineRun) -> Block:
    return Block(kind=TABLE_CELL, runs=list(runs) or [InlineRun(text="")])


def _table(rows: int, columns: int) -> Block:
    return Block(
        kind=TABLE,
        children=[
            Block(
                kind=TABLE_ROW,
                children=[
                    _cell(InlineRun(text=f"L{row + 1}C{column + 1}"))
                    for column in range(columns)
                ],
            )
            for row in range(rows)
        ],
    )


def _rich_table() -> Block:
    return Block(
        kind=TABLE,
        children=[
            Block(
                kind=TABLE_ROW,
                children=[
                    _cell(InlineRun(text="Normal")),
                    _cell(InlineRun(text="Gras", bold=True)),
                ],
            ),
            Block(
                kind=TABLE_ROW,
                children=[
                    _cell(InlineRun(text="Valeur", italic=True)),
                    _cell(InlineRun(text="Lien", link_href="https://example.org")),
                ],
            ),
        ],
    )


def _only_table(document: QTextDocument) -> QTextTable:
    tables = [
        frame
        for frame in document.rootFrame().childFrames()
        if isinstance(frame, QTextTable)
    ]
    assert len(tables) == 1
    return tables[0]


def _document(model: Block) -> QTextDocument:
    document = QTextDocument()
    populate_document(document, [model])
    return document


def _cell_cursor(table: QTextTable, row: int, column: int) -> QTextCursor:
    return table.cellAt(row, column).firstCursorPosition()


def _width_values(table: QTextTable) -> list[float]:
    constraints = table.format().columnWidthConstraints()
    assert all(
        item.type() == QTextLength.Type.PercentageLength for item in constraints
    )
    return [item.rawValue() for item in constraints]


def _assert_equal_widths(table: QTextTable, columns: int) -> None:
    values = _width_values(table)
    assert len(values) == columns
    assert sum(values) == pytest.approx(100.0)
    assert values == pytest.approx([100.0 / columns] * columns)


def _background_name(table: QTextTable, row: int, column: int = 0) -> str:
    return table.cellAt(row, column).format().background().color().name()


@pytest.mark.parametrize("columns", [1, 2, 3, 5])
def test_population_applies_equal_percentage_widths_without_semantic_changes(columns):
    model = _table(2, columns)
    document = _document(model)
    table = _only_table(document)

    assert table.format().property(MEROPE_TABLE_PROPERTY) is True
    assert table.format().headerRowCount() == 1
    assert table.format().width().type() == QTextLength.Type.PercentageLength
    assert table.format().width().rawValue() == pytest.approx(100.0)
    assert table.format().border() == pytest.approx(TABLE_BORDER_WIDTH)
    assert table.format().cellPadding() == pytest.approx(TABLE_CELL_PADDING)
    assert table.format().cellSpacing() == pytest.approx(TABLE_CELL_SPACING)
    assert table.format().topMargin() == pytest.approx(TABLE_BLOCK_MARGINS[0])
    assert table.format().bottomMargin() == pytest.approx(TABLE_BLOCK_MARGINS[1])
    _assert_equal_widths(table, columns)
    assert extract_blocks(document) == [model]
    assert not document.isModified()
    assert not document.isUndoAvailable()


def test_header_background_is_visual_only_and_preserves_explicit_bold():
    model = _rich_table()
    markdown = blocks_to_markdown([model])
    document = _document(model)
    table = _only_table(document)

    assert _background_name(table, 0) == TABLE_HEADER_BACKGROUND
    assert (
        table.cellAt(1, 0).format().background().style()
        == Qt.BrushStyle.NoBrush
    )
    assert extract_blocks(document) == [model]
    assert blocks_to_markdown(extract_blocks(document)) == markdown
    assert extract_blocks(document)[0].children[0].children[0].runs[0].bold is False
    assert extract_blocks(document)[0].children[0].children[1].runs[0].bold is True


def test_column_insert_remove_recalculates_widths_with_exact_undo_redo():
    before = _table(2, 2)
    document = _document(before)

    insert_table_column(_cell_cursor(_only_table(document), 1, 0), before=False)
    after = extract_blocks(document)
    _assert_equal_widths(_only_table(document), 3)

    document.undo()
    assert extract_blocks(document) == [before]
    _assert_equal_widths(_only_table(document), 2)
    document.redo()
    assert extract_blocks(document) == after
    _assert_equal_widths(_only_table(document), 3)

    remove_table_column(_cell_cursor(_only_table(document), 1, 1))
    after_remove = extract_blocks(document)
    _assert_equal_widths(_only_table(document), 2)
    document.undo()
    assert extract_blocks(document) == after
    _assert_equal_widths(_only_table(document), 3)
    document.redo()
    assert extract_blocks(document) == after_remove
    _assert_equal_widths(_only_table(document), 2)


def test_header_visual_migrates_when_first_row_is_inserted_and_removed():
    model = _table(2, 2)
    document = _document(model)
    original_header = TABLE_HEADER_BACKGROUND

    insert_table_row(_cell_cursor(_only_table(document), 0, 0), before=True)
    table = _only_table(document)
    after_insert = extract_blocks(document)
    assert _background_name(table, 0) == original_header
    assert table.cellAt(1, 0).format().background().style() == Qt.BrushStyle.NoBrush

    document.undo()
    assert extract_blocks(document) == [model]
    assert _background_name(_only_table(document), 0) == original_header
    document.redo()
    assert extract_blocks(document) == after_insert
    assert _background_name(_only_table(document), 0) == original_header


def test_new_first_row_becomes_header_after_removing_original_header():
    model = _table(3, 2)
    document = _document(model)

    remove_table_row(_cell_cursor(_only_table(document), 0, 0))
    table = _only_table(document)
    after = extract_blocks(document)
    assert _background_name(table, 0) == TABLE_HEADER_BACKGROUND
    assert table.cellAt(1, 0).format().background().style() == Qt.BrushStyle.NoBrush
    assert table.rows() == 2
    document.undo()
    assert extract_blocks(document) == [model]
    assert _background_name(_only_table(document), 0) == TABLE_HEADER_BACKGROUND
    document.redo()
    assert extract_blocks(document) == after
    assert _background_name(_only_table(document), 0) == TABLE_HEADER_BACKGROUND


@pytest.mark.parametrize("zoom_percent", [50, 100, 200, 300])
def test_zoom_keeps_table_visual_contract_and_canonical_model(
    zoom_percent,
    qapplication,
):
    model = _rich_table()
    editor = MeropeTextEdit()
    populate_document(editor.document(), [model])
    before_widths = _width_values(_only_table(editor.document()))
    before_modified = editor.document().isModified()
    before_undo = editor.document().isUndoAvailable()

    if zoom_percent != 100:
        assert editor.adjust_zoom((zoom_percent - 100) // 10)

    table = _only_table(editor.document())
    assert editor.zoom_percent == zoom_percent
    assert _width_values(table) == pytest.approx(before_widths)
    assert extract_blocks(editor.document()) == [model]
    assert editor.document().isModified() is before_modified
    assert editor.document().isUndoAvailable() is before_undo
    editor.deleteLater()
    qapplication.processEvents()


def test_tab_added_row_keeps_new_cell_and_caret_visible(qapplication):
    model = _table(20, 2)
    editor = MeropeTextEdit()
    editor.resize(360, 180)
    populate_document(editor.document(), [model])
    editor.show()
    editor.activateWindow()
    editor.setFocus()
    table = _only_table(editor.document())
    editor.setTextCursor(table.cellAt(19, 1).firstCursorPosition())
    editor.ensureCursorVisible()
    qapplication.processEvents()

    QTest.keyClick(editor, Qt.Key.Key_Tab)
    qapplication.processEvents()

    table = _only_table(editor.document())
    current = table.cellAt(editor.textCursor())
    cursor_rect = editor.cursorRect()
    assert (current.row(), current.column()) == (20, 0)
    assert 0 <= cursor_rect.top()
    assert cursor_rect.bottom() <= editor.viewport().height()
    assert extract_blocks(editor.document())[0].children[-1] == Block(
        kind=TABLE_ROW,
        children=[_cell(), _cell()],
    )
    editor.deleteLater()
    qapplication.processEvents()
