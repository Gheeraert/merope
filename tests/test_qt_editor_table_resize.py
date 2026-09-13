from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QTextCursor, QTextTable
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
from bloggen.ui.qt_editor.document_adapter import extract_blocks, populate_document
from bloggen.ui.qt_editor.table_resize import (
    TABLE_COLUMN_MIN_WIDTH_PIXELS,
    resized_column_percentages,
    table_boundary_at,
    table_column_boundaries,
    table_viewport_rect,
)
from bloggen.ui.qt_editor.table_visuals import table_column_percentages
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


def _table(rows: int = 2, columns: int = 2) -> Block:
    return Block(
        kind=TABLE,
        children=[
            Block(
                kind=TABLE_ROW,
                children=[
                    Block(
                        kind=TABLE_CELL,
                        runs=[InlineRun(text=f"L{row + 1}C{column + 1}")],
                    )
                    for column in range(columns)
                ],
            )
            for row in range(rows)
        ],
    )


def _editor(model: Block, *, width: int = 600, height: int = 260) -> MeropeTextEdit:
    editor = MeropeTextEdit()
    _EDITORS.append(editor)
    editor.resize(width, height)
    populate_document(editor.document(), [model])
    editor.show()
    editor.activateWindow()
    editor.setFocus()
    QApplication.processEvents()
    assert editor.hasFocus()
    return editor


def _only_table(editor: MeropeTextEdit) -> QTextTable:
    tables = [
        frame
        for frame in editor.document().rootFrame().childFrames()
        if isinstance(frame, QTextTable)
    ]
    assert len(tables) == 1
    return tables[0]


def _boundary_point(editor: MeropeTextEdit, boundary_index: int) -> QPoint:
    table = _only_table(editor)
    rect = table_viewport_rect(editor, table)
    visible_top = max(1.0, rect.top() + 2.0)
    visible_bottom = min(float(editor.viewport().height() - 2), rect.bottom() - 2.0)
    assert visible_top <= visible_bottom
    x = table_column_boundaries(editor, table)[boundary_index]
    return QPoint(round(x), round((visible_top + visible_bottom) / 2.0))


def _drag_boundary(
    editor: MeropeTextEdit,
    boundary_index: int,
    delta_x: int,
) -> None:
    start = _boundary_point(editor, boundary_index)
    end = QPoint(start.x() + delta_x, start.y())
    QTest.mouseMove(editor.viewport(), start)
    QTest.mousePress(editor.viewport(), Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(editor.viewport(), end)
    QApplication.processEvents()
    QTest.mouseRelease(editor.viewport(), Qt.MouseButton.LeftButton, pos=end)
    QApplication.processEvents()


def test_hover_internal_boundary_uses_horizontal_cursor_and_elsewhere_ibeam():
    editor = _editor(_table())
    boundary = _boundary_point(editor, 0)

    QTest.mouseMove(editor.viewport(), boundary)
    QApplication.processEvents()
    assert editor.viewport().cursor().shape() == Qt.CursorShape.SizeHorCursor

    rect = table_viewport_rect(editor, _only_table(editor))
    outside_boundary = QPoint(round(rect.left() + rect.width() * 0.25), boundary.y())
    QTest.mouseMove(editor.viewport(), outside_boundary)
    QApplication.processEvents()
    assert editor.viewport().cursor().shape() == Qt.CursorShape.IBeamCursor


def test_outer_edges_and_foreign_qtexttable_are_not_resize_handles():
    editor = _editor(_table())
    table = _only_table(editor)
    rect = table_viewport_rect(editor, table)
    y = round(rect.center().y())

    assert table_boundary_at(editor, QPoint(round(rect.left()), y)) is None
    assert table_boundary_at(editor, QPoint(round(rect.right()), y)) is None

    foreign = MeropeTextEdit()
    _EDITORS.append(foreign)
    foreign.resize(600, 260)
    QTextCursor(foreign.document()).insertTable(2, 2)
    foreign.show()
    QApplication.processEvents()
    foreign_table = _only_table(foreign)
    foreign_rect = table_viewport_rect(foreign, foreign_table)
    foreign_point = QPoint(
        round(foreign_rect.center().x()),
        round(foreign_rect.center().y()),
    )
    assert table_boundary_at(foreign, foreign_point) is None


def test_raw_table_fallback_has_no_resize_boundary():
    raw_table = Block(
        kind=TABLE,
        children=[
            Block(
                kind=TABLE_ROW,
                children=[
                    Block(
                        kind=TABLE_CELL,
                        runs=[InlineRun(image_src="missing.png", image_alt="Image")],
                    ),
                ],
            ),
        ],
    )
    editor = _editor(raw_table)
    point = editor.viewport().rect().center()

    assert not any(
        isinstance(frame, QTextTable)
        for frame in editor.document().rootFrame().childFrames()
    )
    assert table_boundary_at(editor, point) is None
    QTest.mouseMove(editor.viewport(), point)
    QApplication.processEvents()
    assert editor.viewport().cursor().shape() == Qt.CursorShape.IBeamCursor


def test_two_column_mouse_drag_is_one_visual_undo_and_semantically_inert():
    model = _table()
    markdown = blocks_to_markdown([model])
    editor = _editor(model)
    original_widths = table_column_percentages(_only_table(editor))

    _drag_boundary(editor, 0, 70)

    resized_widths = table_column_percentages(_only_table(editor))
    assert resized_widths[0] > original_widths[0]
    assert resized_widths[1] < original_widths[1]
    assert sum(resized_widths) == pytest.approx(100.0)
    assert extract_blocks(editor.document()) == [model]
    assert blocks_to_markdown(extract_blocks(editor.document())) == markdown
    assert not editor.document().isModified()
    assert editor.document().isUndoAvailable()

    editor.undo()
    assert table_column_percentages(_only_table(editor)) == pytest.approx(
        original_widths
    )
    assert extract_blocks(editor.document()) == [model]
    editor.redo()
    assert table_column_percentages(_only_table(editor)) == pytest.approx(
        resized_widths
    )
    assert extract_blocks(editor.document()) == [model]

    reopened = _editor(extract_blocks(editor.document())[0])
    assert table_column_percentages(_only_table(reopened)) == pytest.approx(
        (50.0, 50.0)
    )


def test_three_column_drag_changes_only_the_adjacent_pair():
    model = _table(columns=3)
    editor = _editor(model)
    before = table_column_percentages(_only_table(editor))

    _drag_boundary(editor, 0, 50)

    after = table_column_percentages(_only_table(editor))
    assert after[0] > before[0]
    assert after[1] < before[1]
    assert after[2] == pytest.approx(before[2])
    assert after[0] + after[1] == pytest.approx(before[0] + before[1])
    assert sum(after) == pytest.approx(100.0)
    assert extract_blocks(editor.document()) == [model]


def test_click_without_drag_does_not_change_widths_or_undo_state():
    model = _table()
    editor = _editor(model)
    before = table_column_percentages(_only_table(editor))
    point = _boundary_point(editor, 0)

    QTest.mouseClick(editor.viewport(), Qt.MouseButton.LeftButton, pos=point)
    QApplication.processEvents()

    assert table_column_percentages(_only_table(editor)) == before
    assert extract_blocks(editor.document()) == [model]
    assert not editor.document().isModified()
    assert not editor.document().isUndoAvailable()


@pytest.mark.parametrize("columns", [2, 5])
@pytest.mark.parametrize("direction", [-1, 1])
def test_extreme_drag_keeps_adjacent_columns_visible(columns, direction):
    editor = _editor(_table(columns=columns), width=520)
    table = _only_table(editor)
    widths = table_column_percentages(table)
    boundary_index = 0 if direction < 0 else columns - 2
    rect = table_viewport_rect(editor, table)
    proposed = resized_column_percentages(
        editor,
        table,
        widths,
        boundary_index,
        rect.left() - 1000 if direction < 0 else rect.right() + 1000,
    )
    pair_total = widths[boundary_index] + widths[boundary_index + 1]
    pair_pixels = rect.width() * pair_total / 100.0
    expected_minimum = min(
        TABLE_COLUMN_MIN_WIDTH_PIXELS,
        max(1.0, (pair_pixels - 1.0) / 2.0),
    )

    assert sum(proposed) == pytest.approx(100.0)
    assert (
        rect.width() * proposed[boundary_index] / 100.0
        >= expected_minimum - 0.6
    )
    assert (
        rect.width() * proposed[boundary_index + 1] / 100.0
        >= expected_minimum - 0.6
    )


def test_escape_cancels_active_drag_before_any_document_mutation():
    model = _table()
    editor = _editor(model)
    original_widths = table_column_percentages(_only_table(editor))
    start = _boundary_point(editor, 0)
    end = QPoint(start.x() + 80, start.y())

    QTest.mousePress(editor.viewport(), Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(editor.viewport(), end)
    QApplication.processEvents()

    assert editor._table_resize_state is not None
    assert editor._table_resize_state.proposed_widths != original_widths
    assert table_column_percentages(_only_table(editor)) == original_widths
    QTest.keyClick(editor, Qt.Key.Key_Escape)
    QTest.mouseRelease(editor.viewport(), Qt.MouseButton.LeftButton, pos=end)

    assert editor._table_resize_state is None
    assert table_column_percentages(_only_table(editor)) == original_widths
    assert extract_blocks(editor.document()) == [model]
    assert not editor.document().isModified()
    assert not editor.document().isUndoAvailable()


def test_drag_preserves_preexisting_dirty_state():
    model = _table()
    editor = _editor(model)
    table = _only_table(editor)
    cursor = table.cellAt(1, 0).lastCursorPosition()
    editor.setTextCursor(cursor)
    QTest.keyClick(editor, Qt.Key.Key_X)
    assert editor.document().isModified()

    _drag_boundary(editor, 0, 50)

    assert editor.document().isModified()
    assert extract_blocks(editor.document())[0].children[1].children[0].runs[0].text.endswith(
        "x"
    )


@pytest.mark.parametrize("zoom_percent", [50, 200])
def test_hit_testing_and_drag_work_after_zoom_and_vertical_scroll(
    zoom_percent,
    qapplication,
):
    model = _table(rows=40, columns=3)
    editor = _editor(model, width=500, height=180)
    assert editor.adjust_zoom((zoom_percent - 100) // 10)
    table = _only_table(editor)
    editor.setTextCursor(table.cellAt(30, 1).firstCursorPosition())
    editor.ensureCursorVisible()
    qapplication.processEvents()
    assert editor.verticalScrollBar().value() > 0
    before = table_column_percentages(table)
    point = _boundary_point(editor, 1)

    assert table_boundary_at(editor, point) is not None
    _drag_boundary(editor, 1, 30)

    after = table_column_percentages(_only_table(editor))
    assert after != before
    assert sum(after) == pytest.approx(100.0)
    assert extract_blocks(editor.document()) == [model]
    assert not editor.document().isModified()
