from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor, QTextDocument, QTextTable, QTextTableFormat
from PySide6.QtTest import QTest
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
from bloggen.ui.qt_editor.constants import MEROPE_TABLE_PROPERTY
from bloggen.ui.qt_editor.document_adapter import (
    UnsupportedBlockError,
    cursor_table_context,
    extract_blocks,
    populate_document,
    is_caption_block,
)
from bloggen.ui.qt_editor.table_structure import (
    insert_empty_table,
    insert_table_column,
    insert_table_row,
    remove_table,
    remove_table_column,
    remove_table_row,
)
from bloggen.ui.qt_editor.text_edit import MeropeTextEdit


_OPEN_WIDGETS: list[MeropeTextEdit] = []


@pytest.fixture(scope="module", autouse=True)
def qapplication():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(autouse=True)
def close_widgets(qapplication):
    yield
    for widget in _OPEN_WIDGETS:
        widget.hide()
        widget.deleteLater()
    _OPEN_WIDGETS.clear()
    qapplication.processEvents()


def _cell(*runs: InlineRun) -> Block:
    return Block(kind=TABLE_CELL, runs=list(runs) or [InlineRun(text="")])


def _row(*cells: Block) -> Block:
    return Block(kind=TABLE_ROW, children=list(cells))


def _table(rows: list[list[list[InlineRun] | str]]) -> Block:
    return Block(
        kind=TABLE,
        children=[
            _row(
                *[
                    _cell(
                        *(value if isinstance(value, list) else [InlineRun(text=value)])
                    )
                    for value in row
                ]
            )
            for row in rows
        ],
    )


def _empty_table(rows: int, columns: int) -> Block:
    return _table([["" for _column in range(columns)] for _row in range(rows)])


def _paragraph(text: str) -> Block:
    return Block(kind=PARAGRAPH, runs=[InlineRun(text=text)])


def _document(blocks: list[Block]) -> QTextDocument:
    document = QTextDocument()
    populate_document(document, blocks)
    return document


def _editor(blocks: list[Block]) -> MeropeTextEdit:
    editor = MeropeTextEdit()
    _OPEN_WIDGETS.append(editor)
    populate_document(editor.document(), blocks)
    editor.show()
    editor.activateWindow()
    editor.setFocus()
    QApplication.processEvents()
    assert editor.hasFocus()
    return editor


def _tables(document: QTextDocument) -> list[QTextTable]:
    return [
        frame
        for frame in document.rootFrame().childFrames()
        if isinstance(frame, QTextTable)
    ]


def _all_blocks(document: QTextDocument):
    block = document.begin()
    while block.isValid():
        yield block
        block = block.next()


def _cell_cursor(
    document: QTextDocument,
    row: int,
    column: int,
    *,
    table_index: int = 0,
) -> QTextCursor:
    return _tables(document)[table_index].cellAt(row, column).firstCursorPosition()


def _selection(document: QTextDocument, start: int, end: int) -> QTextCursor:
    cursor = QTextCursor(document)
    cursor.setPosition(start)
    cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
    return cursor


def _assert_table_caret(cursor: QTextCursor, row: int, column: int) -> None:
    context = cursor_table_context(cursor)
    assert context is not None
    _table_frame, cell = context
    assert (cell.row(), cell.column()) == (row, column)
    assert cursor.position() == cell.firstPosition()


def _assert_single_undo_cycle(
    document: QTextDocument,
    before: list[Block],
    after: list[Block],
) -> None:
    assert extract_blocks(document) == after
    assert document.isModified()
    assert document.isUndoAvailable()
    document.undo()
    assert extract_blocks(document) == before
    assert not document.isUndoAvailable()
    assert document.isRedoAvailable()
    document.redo()
    assert extract_blocks(document) == after


@pytest.mark.parametrize(
    ("initial", "position", "expected"),
    [
        ([], 0, [_empty_table(2, 2)]),
        ([_paragraph("Après")], 0, [_empty_table(2, 2), _paragraph("Après")]),
        (
            [_paragraph("AvantAprès")],
            len("Avant"),
            [_paragraph("Avant"), _empty_table(2, 2), _paragraph("Après")],
        ),
        (
            [_paragraph("Avant")],
            len("Avant"),
            [_paragraph("Avant"), _empty_table(2, 2)],
        ),
    ],
)
def test_insert_empty_table_in_document_flow(initial, position, expected):
    document = _document(initial)
    cursor = QTextCursor(document)
    cursor.setPosition(position)

    target = insert_empty_table(cursor, 2, 2)

    _assert_table_caret(target, 0, 0)
    table = _tables(document)[0]
    assert table.format().property(MEROPE_TABLE_PROPERTY)
    assert table.format().headerRowCount() == 1
    _assert_single_undo_cycle(document, initial, expected)


def test_insert_empty_table_replaces_ordinary_selection_transactionally():
    before = [_paragraph("Avant supprimer Après")]
    document = _document(before)
    start = len("Avant ")
    cursor = _selection(document, start, start + len("supprimer "))
    after = [_paragraph("Avant "), _empty_table(1, 3), _paragraph("Après")]

    target = insert_empty_table(cursor, 1, 3)

    _assert_table_caret(target, 0, 0)
    _assert_single_undo_cycle(document, before, after)


def test_insert_empty_table_between_and_beside_existing_tables():
    first = _table([["A"], ["B"]])
    before = [_paragraph("Avant"), first, _paragraph("Après")]
    document = _document(before)
    after_block = document.lastBlock()
    target = insert_empty_table(QTextCursor(after_block), 1, 1)

    expected = [_paragraph("Avant"), first, _empty_table(1, 1), _paragraph("Après")]
    assert extract_blocks(document) == expected
    assert len(_tables(document)) == 2
    _assert_table_caret(target, 0, 0)


def test_insert_empty_table_immediately_before_existing_table():
    existing = _table([["A"], ["B"]])
    before = [_paragraph("Avant"), existing, _paragraph("Après")]
    document = _document(before)
    cursor = QTextCursor(document.begin())
    cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock)

    target = insert_empty_table(cursor, 1, 2)

    assert extract_blocks(document) == [
        _paragraph("Avant"),
        _empty_table(1, 2),
        existing,
        _paragraph("Après"),
    ]
    assert len(_tables(document)) == 2
    _assert_table_caret(target, 0, 0)


@pytest.mark.parametrize(("rows", "columns"), [(0, 1), (1, 0), (-1, 2)])
def test_insert_empty_table_rejects_invalid_dimensions(rows, columns):
    before = [_paragraph("Texte")]
    document = _document(before)

    with pytest.raises(ValueError, match="au moins une ligne et une colonne"):
        insert_empty_table(QTextCursor(document), rows, columns)

    assert extract_blocks(document) == before
    assert not document.isModified()
    assert not document.isUndoAvailable()


@pytest.mark.parametrize("raw_text", ["brut", "ligne 1\nligne 2"])
def test_insert_empty_table_refuses_raw_context(raw_text):
    before = [Block(kind=VERBATIM, raw_text=raw_text)]
    document = _document(before)
    cursor = QTextCursor(document)

    with pytest.raises(UnsupportedBlockError):
        insert_empty_table(cursor, 2, 2)

    assert extract_blocks(document) == before
    assert not document.isModified()
    assert not document.isUndoAvailable()


def test_insert_empty_table_refuses_existing_cell_and_cross_table_selection():
    before = [_paragraph("Avant"), _table([["A", "B"], ["C", "D"]])]
    document = _document(before)

    with pytest.raises(UnsupportedBlockError):
        insert_empty_table(_cell_cursor(document, 0, 0), 2, 2)

    first = _cell_cursor(document, 0, 0)
    last = _tables(document)[0].cellAt(0, 1).lastCursorPosition()
    with pytest.raises(UnsupportedBlockError):
        insert_empty_table(
            _selection(document, first.position(), last.position()), 2, 2
        )

    assert extract_blocks(document) == before
    assert not document.isModified()
    assert not document.isUndoAvailable()


def test_insert_empty_table_refuses_caption_and_caption_boundary():
    figure = InlineRun(image_src="missing.png", image_alt="Légende")
    before = [
        _paragraph("Avant"),
        Block(kind=PARAGRAPH, runs=[figure]),
        _paragraph("Après"),
    ]
    document = _document(before)
    caption = next(
        block
        for block in _all_blocks(document)
        if is_caption_block(block)
    )

    inside = QTextCursor(caption)
    inside.setPosition(caption.position() + 1)
    with pytest.raises(UnsupportedBlockError):
        insert_empty_table(inside, 2, 2)

    following = caption.next()
    boundary = _selection(
        document,
        caption.position() + caption.length() - 1,
        following.position(),
    )
    with pytest.raises(UnsupportedBlockError):
        insert_empty_table(boundary, 2, 2)

    assert extract_blocks(document) == before
    assert not document.isModified()
    assert not document.isUndoAvailable()


@pytest.mark.parametrize(
    ("row", "before_flag", "expected_row", "expected"),
    [
        (0, True, 0, [["", ""], ["A", "B"], ["C", "D"]]),
        (0, False, 1, [["A", "B"], ["", ""], ["C", "D"]]),
        (1, False, 2, [["A", "B"], ["C", "D"], ["", ""]]),
    ],
)
def test_insert_table_row_above_and_below(row, before_flag, expected_row, expected):
    before = [_table([["A", "B"], ["C", "D"]])]
    document = _document(before)

    target = insert_table_row(
        _cell_cursor(document, row, 1), before=before_flag
    )

    after = [_table(expected)]
    _assert_table_caret(target, expected_row, 1)
    assert _tables(document)[0].format().headerRowCount() == 1
    _assert_single_undo_cycle(document, before, after)


@pytest.mark.parametrize(
    ("column", "before_flag", "expected_column", "expected"),
    [
        (0, True, 0, [["", "A", "B"], ["", "C", "D"]]),
        (0, False, 1, [["A", "", "B"], ["C", "", "D"]]),
        (1, False, 2, [["A", "B", ""], ["C", "D", ""]]),
    ],
)
def test_insert_table_column_left_and_right(
    column, before_flag, expected_column, expected
):
    before = [_table([["A", "B"], ["C", "D"]])]
    document = _document(before)

    target = insert_table_column(
        _cell_cursor(document, 1, column), before=before_flag
    )

    after = [_table(expected)]
    _assert_table_caret(target, 1, expected_column)
    _assert_single_undo_cycle(document, before, after)


@pytest.mark.parametrize(
    ("row", "expected_row", "expected"),
    [
        (0, 0, [["C", "D"]]),
        (1, 0, [["A", "B"]]),
        (1, 1, [["A", "B"], ["E", "F"]]),
    ],
)
def test_remove_table_row_keeps_nearest_row(row, expected_row, expected):
    source = [["A", "B"], ["C", "D"]]
    if len(expected) == 2:
        source.append(["E", "F"])
    before = [_table(source)]
    document = _document(before)

    target = remove_table_row(_cell_cursor(document, row, 1))

    after = [_table(expected)]
    _assert_table_caret(target, expected_row, 1)
    assert _tables(document)[0].format().headerRowCount() == 1
    _assert_single_undo_cycle(document, before, after)


@pytest.mark.parametrize(
    ("column", "expected_column", "expected"),
    [
        (0, 0, [["B"], ["D"]]),
        (1, 0, [["A"], ["C"]]),
        (1, 1, [["A", "C"], ["D", "F"]]),
    ],
)
def test_remove_table_column_keeps_nearest_column(column, expected_column, expected):
    source = [["A", "B"], ["C", "D"]]
    if len(expected[0]) == 2 and column == 1:
        source = [["A", "B", "C"], ["D", "E", "F"]]
    before = [_table(source)]
    document = _document(before)

    target = remove_table_column(_cell_cursor(document, 1, column))

    after = [_table(expected)]
    _assert_table_caret(target, 1, expected_column)
    _assert_single_undo_cycle(document, before, after)


@pytest.mark.parametrize(
    ("model", "operation"),
    [
        ([_table([["A", "B"]])], remove_table_row),
        ([_table([["A"], ["B"]])], remove_table_column),
    ],
)
def test_remove_last_row_or_column_is_refused(model, operation):
    document = _document(model)

    with pytest.raises(UnsupportedBlockError):
        operation(_cell_cursor(document, 0, 0))

    assert extract_blocks(document) == model
    assert not document.isModified()
    assert not document.isUndoAvailable()


@pytest.mark.parametrize(
    "before",
    [
        [_table([["A"], ["B"]])],
        [_paragraph("Avant"), _table([["A"], ["B"]]), _paragraph("Après")],
        [_table([["A"], ["B"]]), _paragraph("Après")],
        [_paragraph("Avant"), _table([["A"], ["B"]])],
        [_table([["A"], ["B"]]), _table([["C"], ["D"]])],
    ],
)
def test_remove_table_exactly_and_undo_redo(before):
    document = _document(before)
    model_index = next(index for index, block in enumerate(before) if block.kind == TABLE)
    after = list(before)
    del after[model_index]

    target = remove_table(_cell_cursor(document, 0, 0))

    assert not target.currentTable()
    _assert_single_undo_cycle(document, before, after)


@pytest.mark.parametrize(
    ("before", "expected_text"),
    [
        ([_paragraph("Avant"), _table([["A"]]), _paragraph("Après")], "Après"),
        ([_table([["A"]]), _paragraph("Après")], "Après"),
        ([_paragraph("Avant"), _table([["A"]])], "Avant"),
        ([_table([["A"]])], ""),
    ],
)
def test_remove_table_places_caret_in_nearest_paragraph(before, expected_text):
    document = _document(before)

    target = remove_table(_cell_cursor(document, 0, 0))

    assert not target.currentTable()
    assert target.block().text() == expected_text


def test_remove_second_of_two_consecutive_tables():
    first = _table([["A"], ["B"]])
    second = _table([["C"], ["D"]])
    before = [first, second]
    document = _document(before)

    target = remove_table(_cell_cursor(document, 0, 0, table_index=1))

    assert not target.currentTable()
    _assert_single_undo_cycle(document, before, [first])


def test_tab_from_last_cell_adds_one_body_row_in_one_undo_step():
    before = [_table([["A", "B"], ["C", "D"]])]
    editor = _editor(before)
    editor.setTextCursor(_cell_cursor(editor.document(), 1, 1))

    QTest.keyClick(editor, Qt.Key.Key_Tab)

    after = [_table([["A", "B"], ["C", "D"], ["", ""]])]
    _assert_table_caret(editor.textCursor(), 2, 0)
    _assert_single_undo_cycle(editor.document(), before, after)


def test_shift_tab_from_first_cell_remains_a_clean_no_op():
    before = [_table([["A", "B"], ["C", "D"]])]
    editor = _editor(before)
    editor.setTextCursor(_cell_cursor(editor.document(), 0, 0))

    QTest.keyClick(editor, Qt.Key.Key_Backtab)

    _assert_table_caret(editor.textCursor(), 0, 0)
    assert extract_blocks(editor.document()) == before
    assert not editor.document().isModified()
    assert not editor.document().isUndoAvailable()


def test_structure_preserves_rich_cells_and_notes():
    rich = [
        InlineRun(text="G", bold=True),
        InlineRun(text="I", italic=True),
        InlineRun(text="U", underline=True),
        InlineRun(text="X", superscript=True),
        InlineRun(text="Lien", link_href="https://example.org"),
        InlineRun(text="\u00a0"),
        InlineRun(footnote_ref="7"),
    ]
    before = [_table([[rich, "B"], ["C", "D"]])]
    document = _document(before)

    target = insert_table_column(_cell_cursor(document, 1, 0), before=False)
    after_insert = [_table([[rich, "", "B"], ["C", "", "D"]])]
    assert extract_blocks(document) == after_insert

    target = remove_table_column(target)
    assert extract_blocks(document) == before
    assert cursor_table_context(target) is not None


def test_deleting_row_with_note_keeps_remaining_table_extractible():
    before = [
        _table(
            [
                ["En-tête"],
                [[InlineRun(text="Appel "), InlineRun(footnote_ref="12")]],
                ["Suite"],
            ]
        )
    ]
    document = _document(before)

    remove_table_row(_cell_cursor(document, 1, 0))

    assert extract_blocks(document) == [_table([["En-tête"], ["Suite"]])]


def test_structure_commands_accept_selection_inside_one_cell():
    before = [_table([["AB", "C"], ["D", "E"]])]
    document = _document(before)
    cell = _tables(document)[0].cellAt(0, 0)
    cursor = _selection(document, cell.firstPosition(), cell.lastPosition())

    target = insert_table_row(cursor, before=False)

    _assert_table_caret(target, 1, 0)
    assert extract_blocks(document) == [
        _table([["AB", "C"], ["", ""], ["D", "E"]])
    ]


@pytest.mark.parametrize(
    "cursor_factory",
    [
        lambda document: QTextCursor(document),
        lambda document: _selection(
            document,
            _tables(document)[0].cellAt(0, 0).firstPosition(),
            _tables(document)[0].cellAt(0, 1).lastPosition(),
        ),
        lambda document: _selection(
            document,
            document.begin().position(),
            _tables(document)[0].cellAt(0, 0).lastPosition(),
        ),
    ],
)
def test_structure_commands_refuse_no_table_multi_cell_and_cross_boundary(
    cursor_factory,
):
    before = [_paragraph("Avant"), _table([["A", "B"], ["C", "D"]])]
    document = _document(before)
    cursor = cursor_factory(document)

    with pytest.raises(UnsupportedBlockError):
        insert_table_row(cursor, before=False)

    assert extract_blocks(document) == before
    assert not document.isModified()
    assert not document.isUndoAvailable()


def test_structure_commands_refuse_foreign_table():
    document = QTextDocument()
    cursor = QTextCursor(document)
    table_format = QTextTableFormat()
    table_format.setHeaderRowCount(1)
    foreign = cursor.insertTable(2, 2, table_format)
    document.clearUndoRedoStacks()
    document.setModified(False)

    with pytest.raises(UnsupportedBlockError):
        insert_table_column(foreign.cellAt(0, 0).firstCursorPosition(), before=False)

    assert foreign.rows() == 2
    assert foreign.columns() == 2
    assert not document.isModified()
    assert not document.isUndoAvailable()
