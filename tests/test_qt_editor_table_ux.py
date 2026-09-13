from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtGui import QTextCursor, QTextDocument, QTextTable, QTextTableFormat
from PySide6.QtWidgets import QApplication, QDialog, QMenu, QMessageBox

from bloggen.markdown.rich_text_model import (
    PARAGRAPH,
    TABLE,
    TABLE_CELL,
    TABLE_ROW,
    VERBATIM,
    Block,
    InlineRun,
)
from bloggen.ui.qt_editor.document_adapter import (
    cursor_table_context,
    extract_blocks,
    is_caption_block,
    populate_document,
)
from bloggen.ui.qt_editor.text_edit import MeropeTextEdit
from bloggen.ui.qt_editor.window import QtEditorWindow
import bloggen.ui.qt_editor.window as window_module


_WIDGETS = []


@pytest.fixture(scope="module", autouse=True)
def qapplication():
    app = QApplication.instance() or QApplication([])
    yield app
    app.clipboard().clear()


@pytest.fixture(autouse=True)
def close_widgets(qapplication):
    yield
    for widget in _WIDGETS:
        if isinstance(widget, QtEditorWindow):
            widget.autosave_timer.stop()
        widget.hide()
        widget.deleteLater()
    _WIDGETS.clear()
    qapplication.processEvents()


def _cell(text: str = "") -> Block:
    return Block(kind=TABLE_CELL, runs=[InlineRun(text=text)])


def _table(rows: list[list[str]]) -> Block:
    return Block(
        kind=TABLE,
        children=[
            Block(
                kind=TABLE_ROW,
                children=[_cell(text) for text in row],
            )
            for row in rows
        ],
    )


def _empty_table(rows: int, columns: int) -> Block:
    return _table([["" for _column in range(columns)] for _row in range(rows)])


def _paragraph(text: str) -> Block:
    return Block(kind=PARAGRAPH, runs=[InlineRun(text=text)])


def _window(blocks: list[Block] | None = None) -> QtEditorWindow:
    window = QtEditorWindow()
    _WIDGETS.append(window)
    if blocks is not None:
        populate_document(window.editor.document(), blocks)
    window.show()
    window.activateWindow()
    window.editor.setFocus()
    QApplication.processEvents()
    return window


def _editor(blocks: list[Block]) -> MeropeTextEdit:
    editor = MeropeTextEdit()
    _WIDGETS.append(editor)
    populate_document(editor.document(), blocks)
    editor.show()
    editor.activateWindow()
    editor.setFocus()
    QApplication.processEvents()
    return editor


def _tables(editor: MeropeTextEdit) -> list[QTextTable]:
    return [
        frame
        for frame in editor.document().rootFrame().childFrames()
        if isinstance(frame, QTextTable)
    ]


def _place_in_cell(
    editor: MeropeTextEdit,
    row: int,
    column: int,
) -> None:
    editor.setTextCursor(_tables(editor)[0].cellAt(row, column).firstCursorPosition())
    QApplication.processEvents()


def _select(editor: MeropeTextEdit, start: int, end: int) -> None:
    cursor = QTextCursor(editor.document())
    cursor.setPosition(start)
    cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
    editor.setTextCursor(cursor)
    QApplication.processEvents()


def _table_menu(editor: MeropeTextEdit) -> tuple[QMenu, QMenu | None]:
    menu = editor._create_merope_context_menu()
    action = next(
        (
            action
            for action in menu.actions()
            if action.objectName() == "merope-table-menu"
        ),
        None,
    )
    return menu, action.menu() if action is not None else None


def _table_action(table_menu: QMenu, object_name: str):
    return next(
        action
        for action in table_menu.actions()
        if action.objectName() == object_name
    )


class _AcceptedTableDialog:
    def __init__(self, _parent=None, *, dimensions=(2, 2)):
        self._dimensions = dimensions

    def exec(self):
        return QDialog.DialogCode.Accepted

    def dimensions(self):
        return self._dimensions


class _RejectedTableDialog(_AcceptedTableDialog):
    def exec(self):
        return QDialog.DialogCode.Rejected


def test_toolbar_insertion_action_uses_dialog_and_structural_primitive(monkeypatch):
    monkeypatch.setattr(window_module, "TableInsertDialog", _AcceptedTableDialog)
    window = _window()
    action = window.insert_table_action

    assert action.text() == "Insérer un tableau…"
    assert action.isEnabled()
    assert not action.icon().isNull()
    assert action.toolTip()
    action.trigger()
    QApplication.processEvents()

    expected = [_empty_table(2, 2)]
    assert extract_blocks(window.editor.document()) == expected
    context = cursor_table_context(window.editor.textCursor())
    assert context is not None
    _table_frame, cell = context
    assert (cell.row(), cell.column()) == (0, 0)
    assert window.editor.hasFocus()
    assert window.editor.document().isModified()
    window.editor.undo()
    assert extract_blocks(window.editor.document()) == []
    window.editor.redo()
    assert extract_blocks(window.editor.document()) == expected


def test_toolbar_insertion_splits_paragraph_at_caret(monkeypatch):
    monkeypatch.setattr(
        window_module,
        "TableInsertDialog",
        lambda parent: _AcceptedTableDialog(parent, dimensions=(1, 3)),
    )
    window = _window([_paragraph("AvantAprès")])
    cursor = QTextCursor(window.editor.document())
    cursor.setPosition(len("Avant"))
    window.editor.setTextCursor(cursor)

    window.insert_table_action.trigger()

    assert extract_blocks(window.editor.document()) == [
        _paragraph("Avant"),
        _empty_table(1, 3),
        _paragraph("Après"),
    ]


def test_toolbar_insertion_replaces_ordinary_text_selection(monkeypatch):
    monkeypatch.setattr(
        window_module,
        "TableInsertDialog",
        lambda parent: _AcceptedTableDialog(parent, dimensions=(1, 1)),
    )
    window = _window([_paragraph("Avant supprimer Après")])
    _select(window.editor, len("Avant "), len("Avant supprimer "))

    assert window.insert_table_action.isEnabled()
    window.insert_table_action.trigger()

    assert extract_blocks(window.editor.document()) == [
        _paragraph("Avant "),
        _empty_table(1, 1),
        _paragraph("Après"),
    ]


def test_cancelled_table_dialog_does_not_mutate_document(monkeypatch):
    monkeypatch.setattr(window_module, "TableInsertDialog", _RejectedTableDialog)
    before = [_paragraph("Texte")]
    window = _window(before)

    window.insert_table_action.trigger()

    assert extract_blocks(window.editor.document()) == before
    assert not window.editor.document().isModified()
    assert not window.editor.document().isUndoAvailable()
    assert window.editor.hasFocus()


@pytest.mark.parametrize("context", ["table", "raw", "caption", "boundary"])
def test_toolbar_insertion_action_is_disabled_in_protected_contexts(context):
    if context == "table":
        blocks = [_table([["A", "B"], ["C", "D"]])]
    elif context == "raw":
        blocks = [Block(kind=VERBATIM, raw_text="brut")]
    elif context == "caption":
        blocks = [
            Block(
                kind=PARAGRAPH,
                runs=[InlineRun(image_src="missing.png", image_alt="Légende")],
            ),
            _paragraph("Après"),
        ]
    else:
        blocks = [_paragraph("Avant"), Block(kind=VERBATIM, raw_text="brut")]
    window = _window(blocks)

    if context == "table":
        _place_in_cell(window.editor, 0, 0)
    elif context == "caption":
        caption = next(
            block
            for block in _all_blocks(window.editor)
            if is_caption_block(block)
        )
        cursor = QTextCursor(caption)
        cursor.setPosition(caption.position() + 1)
        window.editor.setTextCursor(cursor)
    elif context == "boundary":
        left = window.editor.document().begin()
        right = left.next()
        _select(
            window.editor,
            left.position() + left.length() - 1,
            right.position(),
        )
    QApplication.processEvents()

    assert not window.insert_table_action.isEnabled()


def _all_blocks(editor: MeropeTextEdit):
    block = editor.document().begin()
    while block.isValid():
        yield block
        block = block.next()


def test_table_action_is_grouped_with_insertion_controls():
    window = _window()
    actions = window.toolbar.actions_in_order
    image_index = actions.index(
        next(action for action in actions if action.text() == "Insérer une image...")
    )
    table_index = actions.index(window.insert_table_action)

    assert table_index == image_index + 1


def test_context_table_submenu_visibility_and_enabled_states():
    editor = _editor([_table([["A"]])])
    _place_in_cell(editor, 0, 0)

    menu, table_menu = _table_menu(editor)

    assert table_menu is not None
    assert [
        action.text() for action in table_menu.actions() if not action.isSeparator()
    ] == [
        "Copier le tableau",
        "Couper le tableau",
        "Ajouter une ligne au-dessus",
        "Ajouter une ligne en dessous",
        "Ajouter une colonne à gauche",
        "Ajouter une colonne à droite",
        "Supprimer la ligne",
        "Supprimer la colonne",
        "Supprimer le tableau",
    ]
    assert not _table_action(table_menu, "table-remove-row").isEnabled()
    assert not _table_action(table_menu, "table-remove-column").isEnabled()
    for name in (
        "table-copy",
        "table-cut",
        "table-row-above",
        "table-row-below",
        "table-column-left",
        "table-column-right",
        "table-remove",
    ):
        assert _table_action(table_menu, name).isEnabled()
    menu.deleteLater()


def test_context_delete_row_and_column_are_enabled_in_two_by_two_table():
    editor = _editor([_table([["A", "B"], ["C", "D"]])])
    _place_in_cell(editor, 0, 0)

    menu, table_menu = _table_menu(editor)

    assert table_menu is not None
    assert _table_action(table_menu, "table-remove-row").isEnabled()
    assert _table_action(table_menu, "table-remove-column").isEnabled()
    menu.deleteLater()


@pytest.mark.parametrize(
    ("action_name", "expected", "expected_cell"),
    [
        (
            "table-row-above",
            [["", ""], ["A", "B"], ["C", "D"]],
            (0, 1),
        ),
        (
            "table-row-below",
            [["A", "B"], ["", ""], ["C", "D"]],
            (1, 1),
        ),
        (
            "table-column-left",
            [["A", "", "B"], ["C", "", "D"]],
            (0, 1),
        ),
        (
            "table-column-right",
            [["A", "B", ""], ["C", "D", ""]],
            (0, 2),
        ),
        ("table-remove-row", [["C", "D"]], (0, 1)),
        ("table-remove-column", [["A"], ["C"]], (0, 0)),
    ],
)
def test_context_table_actions_reuse_structural_operations(
    action_name,
    expected,
    expected_cell,
):
    before = [_table([["A", "B"], ["C", "D"]])]
    editor = _editor(before)
    _place_in_cell(editor, 0, 1)
    menu, table_menu = _table_menu(editor)
    assert table_menu is not None

    _table_action(table_menu, action_name).trigger()
    QApplication.processEvents()

    after = [_table(expected)]
    assert extract_blocks(editor.document()) == after
    context = cursor_table_context(editor.textCursor())
    assert context is not None
    _table_frame, cell = context
    assert (cell.row(), cell.column()) == expected_cell
    assert editor.hasFocus()
    editor.undo()
    assert extract_blocks(editor.document()) == before
    assert not editor.document().isUndoAvailable()
    editor.redo()
    assert extract_blocks(editor.document()) == after
    menu.deleteLater()


def test_context_remove_table_preserves_surrounding_paragraphs_and_focus():
    before = [_paragraph("Avant"), _table([["A"], ["B"]]), _paragraph("Après")]
    editor = _editor(before)
    _place_in_cell(editor, 0, 0)
    menu, table_menu = _table_menu(editor)
    assert table_menu is not None

    _table_action(table_menu, "table-remove").trigger()
    QApplication.processEvents()

    after = [_paragraph("Avant"), _paragraph("Après")]
    assert extract_blocks(editor.document()) == after
    assert editor.textCursor().block().text() == "Après"
    assert editor.hasFocus()
    editor.undo()
    assert extract_blocks(editor.document()) == before
    editor.redo()
    assert extract_blocks(editor.document()) == after
    menu.deleteLater()


@pytest.mark.parametrize("context", ["outside", "multi-cell", "boundary", "raw"])
def test_context_table_submenu_is_absent_outside_one_graphical_cell(context):
    if context == "outside":
        editor = _editor([_paragraph("Texte")])
    elif context == "raw":
        editor = _editor(
            [
                Block(
                    kind=TABLE,
                    children=[
                        Block(
                            kind=TABLE_ROW,
                            children=[
                                Block(
                                    kind=TABLE_CELL,
                                    runs=[InlineRun(image_src="image.png")],
                                )
                            ],
                        )
                    ],
                )
            ]
        )
    else:
        editor = _editor(
            [_paragraph("Avant"), _table([["A", "B"], ["C", "D"]])]
        )
        table = _tables(editor)[0]
        if context == "multi-cell":
            _select(
                editor,
                table.cellAt(0, 0).firstPosition(),
                table.cellAt(0, 1).lastPosition(),
            )
        else:
            _select(
                editor,
                editor.document().begin().position(),
                table.cellAt(0, 0).lastPosition(),
            )

    menu, table_menu = _table_menu(editor)

    assert table_menu is None
    menu.deleteLater()


def test_context_table_submenu_is_absent_for_foreign_qtexttable():
    editor = MeropeTextEdit()
    _WIDGETS.append(editor)
    document = QTextDocument(editor)
    editor.setDocument(document)
    cursor = QTextCursor(document)
    table_format = QTextTableFormat()
    table_format.setHeaderRowCount(1)
    foreign = cursor.insertTable(2, 2, table_format)
    editor.setTextCursor(foreign.cellAt(0, 0).firstCursorPosition())

    menu, table_menu = _table_menu(editor)

    assert table_menu is None
    menu.deleteLater()


def test_table_submenu_is_added_to_fail_closed_context_menu(monkeypatch):
    editor = _editor([_table([["A", "B"], ["C", "D"]])])
    _place_in_cell(editor, 0, 0)
    unsafe_menu = QMenu(editor)
    unsafe = unsafe_menu.addAction("Mutation Qt inconnue")
    unsafe.setObjectName("unsafe-native-action")
    monkeypatch.setattr(
        editor,
        "createStandardContextMenu",
        lambda _position=None: unsafe_menu,
    )

    menu, table_menu = _table_menu(editor)

    assert menu is not unsafe_menu
    assert unsafe not in menu.actions()
    assert table_menu is not None
    assert _table_action(table_menu, "table-row-below").isEnabled()
    menu.deleteLater()


def test_stale_context_action_fails_closed_with_visible_warning(monkeypatch):
    before = [_table([["A", "B"], ["C", "D"]]), _paragraph("Après")]
    editor = _editor(before)
    _place_in_cell(editor, 0, 0)
    menu, table_menu = _table_menu(editor)
    assert table_menu is not None
    warnings = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda *args: warnings.append(args),
    )
    editor.setTextCursor(QTextCursor(editor.document().lastBlock()))

    _table_action(table_menu, "table-row-below").trigger()

    assert extract_blocks(editor.document()) == before
    assert not editor.document().isModified()
    assert not editor.document().isUndoAvailable()
    assert warnings
    assert warnings[0][1] == "Modification du tableau impossible"
    menu.deleteLater()
