from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QByteArray, QMimeData, Qt
from PySide6.QtGui import QTextCursor, QTextDocument, QTextTable
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from bloggen.markdown.rich_text_model import (
    BLOCKQUOTE,
    BULLET_LIST,
    HEADING,
    ORDERED_LIST,
    PARAGRAPH,
    TABLE,
    TABLE_CELL,
    TABLE_ROW,
    Block,
    InlineRun,
)
from bloggen.markdown.rich_text_export import blocks_to_markdown
from bloggen.markdown.typography import NBSP
from bloggen.ui.qt_editor.clipboard_fragment import MEROPE_FRAGMENT_MIME
from bloggen.ui.qt_editor.document_adapter import extract_blocks, populate_document
from bloggen.ui.qt_editor.formatting import (
    set_alignment,
    set_blockquote,
    set_heading,
    set_link,
    set_list,
    set_paragraph,
    toggle_bold,
    toggle_italic,
    toggle_justify,
    toggle_strikethrough,
    toggle_superscript,
    toggle_underline,
)
from bloggen.ui.qt_editor.text_edit import MeropeTextEdit
from bloggen.ui.qt_editor.window import QtEditorWindow


_OPEN_WIDGETS = []


@pytest.fixture(scope="module", autouse=True)
def qapplication():
    app = QApplication.instance() or QApplication([])
    yield app
    app.clipboard().clear()


@pytest.fixture(autouse=True)
def close_widgets(qapplication):
    yield
    qapplication.clipboard().clear()
    for widget in _OPEN_WIDGETS:
        widget.hide()
        widget.deleteLater()
    _OPEN_WIDGETS.clear()
    qapplication.processEvents()


def _cell(*runs: InlineRun) -> Block:
    return Block(kind=TABLE_CELL, runs=list(runs) or [InlineRun(text="")])


def _table() -> Block:
    return Block(
        kind=TABLE,
        children=[
            Block(
                kind=TABLE_ROW,
                children=[
                    _cell(InlineRun(text="A")),
                    _cell(InlineRun(text="B")),
                ],
            ),
            Block(
                kind=TABLE_ROW,
                children=[
                    _cell(InlineRun(text="C")),
                    _cell(InlineRun(text="D")),
                ],
            ),
        ],
    )


def _single_cell_table(*runs: InlineRun) -> Block:
    return Block(
        kind=TABLE,
        children=[Block(kind=TABLE_ROW, children=[_cell(*runs)])],
    )


def _editor(blocks: list[Block]) -> MeropeTextEdit:
    editor = MeropeTextEdit()
    _OPEN_WIDGETS.append(editor)
    populate_document(editor.document(), blocks)
    editor.document().setModified(False)
    editor.show()
    editor.activateWindow()
    editor.setFocus()
    QApplication.processEvents()
    assert editor.hasFocus()
    return editor


def _window(blocks: list[Block]) -> QtEditorWindow:
    window = QtEditorWindow()
    _OPEN_WIDGETS.append(window)
    populate_document(window.editor.document(), blocks)
    window.editor.document().setModified(False)
    window.show()
    window.activateWindow()
    window.editor.setFocus()
    QApplication.processEvents()
    assert window.editor.hasFocus()
    return window


def _table_frame(document: QTextDocument, index: int = 0) -> QTextTable:
    tables = [
        frame
        for frame in document.rootFrame().childFrames()
        if isinstance(frame, QTextTable)
    ]
    return tables[index]


def _place_in_cell(
    editor: MeropeTextEdit,
    row: int,
    column: int,
    *,
    offset: int = 0,
) -> None:
    table = _table_frame(editor.document())
    cursor = table.cellAt(row, column).firstCursorPosition()
    cursor.setPosition(cursor.position() + offset)
    editor.setTextCursor(cursor)


def _select(
    editor: MeropeTextEdit,
    start: int,
    end: int,
) -> None:
    cursor = QTextCursor(editor.document())
    cursor.setPosition(start)
    cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
    editor.setTextCursor(cursor)


def _select_cell_text(
    editor: MeropeTextEdit,
    row: int,
    column: int,
) -> None:
    table = _table_frame(editor.document())
    cell = table.cellAt(row, column)
    _select(editor, cell.firstPosition(), cell.lastPosition())


def _assert_clean_unchanged(editor: MeropeTextEdit, model: list[Block]) -> None:
    assert extract_blocks(editor.document()) == model
    assert not editor.document().isModified()
    assert not editor.document().isUndoAvailable()


def test_return_in_table_cell_is_a_clean_no_op():
    model = [_table()]
    editor = _editor(model)
    _place_in_cell(editor, 1, 0, offset=1)
    block_count = editor.document().blockCount()

    QTest.keyClick(editor, Qt.Key.Key_Return)
    QApplication.processEvents()

    assert editor.document().blockCount() == block_count
    assert extract_blocks(editor.document()) == model
    assert not editor.document().isModified()
    assert not editor.document().isUndoAvailable()


def test_tab_navigates_without_inserting_text_or_creating_undo():
    model = [_table()]
    editor = _editor(model)
    _place_in_cell(editor, 0, 0, offset=1)

    QTest.keyClick(editor, Qt.Key.Key_Tab)
    QApplication.processEvents()

    table = _table_frame(editor.document())
    assert table.cellAt(editor.textCursor()).row() == 0
    assert table.cellAt(editor.textCursor()).column() == 1
    assert editor.textCursor().position() == table.cellAt(0, 1).firstPosition()
    assert extract_blocks(editor.document()) == model
    assert not editor.document().isModified()
    assert not editor.document().isUndoAvailable()


def test_delete_selection_crossing_paragraph_and_table_is_refused():
    model = [
        Block(kind=PARAGRAPH, runs=[InlineRun(text="Avant")]),
        _table(),
        Block(kind=PARAGRAPH, runs=[InlineRun(text="Après")]),
    ]
    editor = _editor(model)
    table = _table_frame(editor.document())
    before = editor.document().begin()
    _select(
        editor,
        before.position() + before.length() - 1,
        table.cellAt(0, 0).firstPosition() + 1,
    )

    QTest.keyClick(editor, Qt.Key.Key_Delete)
    QApplication.processEvents()

    assert extract_blocks(editor.document()) == model
    assert not editor.document().isModified()
    assert not editor.document().isUndoAvailable()


def test_delete_selection_crossing_multiple_cells_is_refused():
    model = [_table()]
    editor = _editor(model)
    table = _table_frame(editor.document())
    _select(
        editor,
        table.cellAt(0, 0).firstPosition(),
        table.cellAt(0, 1).lastPosition(),
    )

    QTest.keyClick(editor, Qt.Key.Key_Delete)
    QApplication.processEvents()

    assert extract_blocks(editor.document()) == model
    assert not editor.document().isModified()
    assert not editor.document().isUndoAvailable()


@pytest.mark.parametrize(
    ("row", "column", "offset", "select_text"),
    [
        (0, 0, 0, False),
        (0, 1, 1, False),
        (1, 0, 0, True),
        (1, 1, 1, False),
    ],
)
def test_return_is_refused_everywhere_in_a_cell(row, column, offset, select_text):
    model = [_table()]
    editor = _editor(model)
    if select_text:
        _select_cell_text(editor, row, column)
    else:
        _place_in_cell(editor, row, column, offset=offset)

    QTest.keyClick(editor, Qt.Key.Key_Return)

    _assert_clean_unchanged(editor, model)


def test_return_in_empty_cell_is_a_clean_no_op():
    model = [_single_cell_table()]
    editor = _editor(model)
    _place_in_cell(editor, 0, 0)

    QTest.keyClick(editor, Qt.Key.Key_Enter)

    _assert_clean_unchanged(editor, model)


def test_tab_and_backtab_navigate_row_major_with_safe_edge_noops():
    model = [_table()]
    editor = _editor(model)
    table = _table_frame(editor.document())

    _place_in_cell(editor, 0, 0, offset=1)
    QTest.keyClick(editor, Qt.Key.Key_Backtab)
    assert editor.textCursor().position() == table.cellAt(0, 0).firstPosition() + 1

    QTest.keyClick(editor, Qt.Key.Key_Tab)
    assert table.cellAt(editor.textCursor()).column() == 1
    QTest.keyClick(editor, Qt.Key.Key_Tab)
    assert table.cellAt(editor.textCursor()).row() == 1
    assert table.cellAt(editor.textCursor()).column() == 0
    QTest.keyClick(editor, Qt.Key.Key_Tab)
    QTest.keyClick(editor, Qt.Key.Key_Tab)
    assert editor.textCursor().position() == table.cellAt(1, 1).firstPosition()

    _assert_clean_unchanged(editor, model)


@pytest.mark.parametrize(
    ("key", "at_end"),
    [(Qt.Key.Key_Backspace, False), (Qt.Key.Key_Delete, True)],
)
@pytest.mark.parametrize(("row", "column"), [(0, 0), (1, 1)])
def test_erase_at_cell_boundaries_is_a_clean_no_op(key, at_end, row, column):
    model = [_table()]
    editor = _editor(model)
    table = _table_frame(editor.document())
    cell = table.cellAt(row, column)
    position = cell.lastPosition() if at_end else cell.firstPosition()
    _place_in_cell(editor, row, column, offset=position - cell.firstPosition())

    QTest.keyClick(editor, key)

    _assert_clean_unchanged(editor, model)


@pytest.mark.parametrize(
    ("key", "offset", "expected"),
    [
        (Qt.Key.Key_Backspace, 2, "AC"),
        (Qt.Key.Key_Delete, 1, "AC"),
    ],
)
def test_erase_inside_cell_is_native_and_undoable(key, offset, expected):
    original = [_single_cell_table(InlineRun(text="ABC"))]
    editor = _editor(original)
    _place_in_cell(editor, 0, 0, offset=offset)

    QTest.keyClick(editor, key)

    changed = [_single_cell_table(InlineRun(text=expected))]
    assert extract_blocks(editor.document()) == changed
    assert editor.document().isUndoAvailable()
    editor.undo()
    assert extract_blocks(editor.document()) == original
    editor.redo()
    assert extract_blocks(editor.document()) == changed


@pytest.mark.parametrize(
    ("key", "modifiers"),
    [
        (Qt.Key.Key_X, Qt.KeyboardModifier.NoModifier),
        (Qt.Key.Key_Backspace, Qt.KeyboardModifier.NoModifier),
        (Qt.Key.Key_Delete, Qt.KeyboardModifier.NoModifier),
        (Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier),
    ],
)
def test_mutating_key_refuses_multicell_selection(key, modifiers):
    model = [_table()]
    editor = _editor(model)
    table = _table_frame(editor.document())
    _select(
        editor,
        table.cellAt(0, 0).firstPosition(),
        table.cellAt(0, 1).lastPosition(),
    )

    QTest.keyClick(editor, key, modifiers)

    _assert_clean_unchanged(editor, model)


def test_cut_and_paste_refuse_multicell_selection_atomically(qapplication):
    model = [_table()]
    editor = _editor(model)
    table = _table_frame(editor.document())
    _select(
        editor,
        table.cellAt(0, 0).firstPosition(),
        table.cellAt(0, 1).lastPosition(),
    )
    qapplication.clipboard().setText("remplacement")

    QTest.keyClick(editor, Qt.Key.Key_X, Qt.KeyboardModifier.ControlModifier)
    _assert_clean_unchanged(editor, model)
    QTest.keyClick(editor, Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier)
    _assert_clean_unchanged(editor, model)


@pytest.mark.parametrize("towards_table", [True, False])
@pytest.mark.parametrize(
    "key",
    [Qt.Key.Key_X, Qt.Key.Key_Backspace, Qt.Key.Key_Delete, Qt.Key.Key_Return],
)
def test_mutating_key_refuses_table_text_selection(towards_table, key):
    model = [
        Block(kind=PARAGRAPH, runs=[InlineRun(text="Avant")]),
        _table(),
        Block(kind=PARAGRAPH, runs=[InlineRun(text="Après")]),
    ]
    editor = _editor(model)
    table = _table_frame(editor.document())
    if towards_table:
        before = editor.document().begin()
        start = before.position() + before.length() - 1
        end = table.cellAt(0, 0).firstPosition() + 1
    else:
        start = table.cellAt(1, 1).lastPosition() - 1
        end = table.lastPosition() + 2
    _select(editor, start, end)

    QTest.keyClick(editor, key)

    _assert_clean_unchanged(editor, model)


def test_cut_and_paste_refuse_table_text_selection(qapplication):
    model = [
        Block(kind=PARAGRAPH, runs=[InlineRun(text="Avant")]),
        _table(),
    ]
    editor = _editor(model)
    table = _table_frame(editor.document())
    before = editor.document().begin()
    _select(
        editor,
        before.position() + before.length() - 1,
        table.cellAt(0, 0).firstPosition() + 1,
    )
    qapplication.clipboard().setText("remplacement")

    QTest.keyClick(editor, Qt.Key.Key_X, Qt.KeyboardModifier.ControlModifier)
    _assert_clean_unchanged(editor, model)
    QTest.keyClick(editor, Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier)
    _assert_clean_unchanged(editor, model)


def test_cut_inside_one_cell_remains_atomic_and_undoable(qapplication):
    original = [_table()]
    editor = _editor(original)
    _select_cell_text(editor, 0, 1)

    QTest.keyClick(editor, Qt.Key.Key_X, Qt.KeyboardModifier.ControlModifier)

    assert qapplication.clipboard().text() == "B"
    changed = _table()
    changed.children[0].children[1] = _cell()
    assert extract_blocks(editor.document()) == [changed]
    editor.undo()
    assert extract_blocks(editor.document()) == original


@pytest.mark.parametrize("plain", ["ligne 1\nligne 2", "a\rb", "a\u2028b", "a\u2029b"])
def test_multiline_plain_paste_in_cell_is_refused(plain):
    model = [_table()]
    editor = _editor(model)
    _place_in_cell(editor, 1, 1, offset=1)

    assert editor.paste_plain_text(plain) is False

    _assert_clean_unchanged(editor, model)


def test_single_line_plain_paste_in_cell_is_inline_and_undoable():
    original = [_table()]
    editor = _editor(original)
    _select_cell_text(editor, 1, 1)

    assert editor.paste_plain_text("texte") is True

    changed = _table()
    changed.children[1].children[1] = _cell(InlineRun(text="texte"))
    assert extract_blocks(editor.document()) == [changed]
    editor.undo()
    assert extract_blocks(editor.document()) == original


def test_real_plain_clipboard_paste_stays_in_one_cell(qapplication):
    original = [_table()]
    editor = _editor(original)
    _select_cell_text(editor, 1, 1)
    qapplication.clipboard().setText("collé")

    QTest.keyClick(editor, Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier)

    assert extract_blocks(editor.document())[0].children[1].children[1].runs == [
        InlineRun(text="collé")
    ]
    editor.undo()
    assert extract_blocks(editor.document()) == original


def test_internal_inline_fragment_pastes_but_structure_is_refused(qapplication):
    original = [_table()]
    editor = _editor(original)
    _select_cell_text(editor, 1, 1)
    inline = Block(
        kind=PARAGRAPH,
        runs=[InlineRun(text="riche", bold=True), InlineRun(footnote_ref="7")],
    )
    mime = QMimeData()
    mime.setData(
        MEROPE_FRAGMENT_MIME,
        QByteArray(blocks_to_markdown([inline]).encode("utf-8")),
    )
    qapplication.clipboard().setMimeData(mime)

    QTest.keyClick(editor, Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier)
    assert extract_blocks(editor.document())[0].children[1].children[1].runs == inline.runs
    editor.undo()
    assert extract_blocks(editor.document()) == original

    structural = QMimeData()
    structural.setData(
        MEROPE_FRAGMENT_MIME,
        QByteArray(blocks_to_markdown([_table()]).encode("utf-8")),
    )
    qapplication.clipboard().setMimeData(structural)
    _select_cell_text(editor, 1, 1)
    QTest.keyClick(editor, Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier)
    _assert_clean_unchanged(editor, original)


@pytest.mark.parametrize(
    "structural",
    [
        Block(kind=HEADING, level=2, runs=[InlineRun(text="Titre")]),
        Block(
            kind=BULLET_LIST,
            children=[
                Block(kind="list_item", runs=[InlineRun(text="Élément")])
            ],
        ),
        Block(kind=BLOCKQUOTE, runs=[InlineRun(text="Citation")]),
        Block(
            kind=PARAGRAPH,
            runs=[InlineRun(image_src="image.png", image_alt="Image")],
        ),
    ],
)
def test_internal_structural_fragments_are_refused_in_cell(structural):
    model = [_table()]
    editor = _editor(model)
    _select_cell_text(editor, 1, 1)
    mime = QMimeData()
    mime.setData(
        MEROPE_FRAGMENT_MIME,
        QByteArray(blocks_to_markdown([structural]).encode("utf-8")),
    )

    editor.insertFromMimeData(mime)

    _assert_clean_unchanged(editor, model)


def test_native_image_mime_is_refused_before_cell_mutation():
    from PySide6.QtGui import QImage

    model = [_table()]
    editor = _editor(model)
    _select_cell_text(editor, 1, 1)
    mime = QMimeData()
    mime.setImageData(QImage(2, 2, QImage.Format.Format_ARGB32))

    editor.insertFromMimeData(mime)

    _assert_clean_unchanged(editor, model)


def test_html_inline_pastes_but_html_table_is_refused(qapplication):
    original = [_table()]
    editor = _editor(original)
    _select_cell_text(editor, 1, 1)
    mime = QMimeData()
    mime.setHtml("<p><strong>riche</strong></p>")
    mime.setText("riche")
    qapplication.clipboard().setMimeData(mime)

    QTest.keyClick(editor, Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier)
    assert extract_blocks(editor.document())[0].children[1].children[1].runs == [
        InlineRun(text="riche", bold=True)
    ]
    editor.undo()
    assert extract_blocks(editor.document()) == original

    refused = QMimeData()
    refused.setHtml("<table><tr><td>perdu</td></tr></table>")
    refused.setText("perdu")
    qapplication.clipboard().setMimeData(refused)
    _select_cell_text(editor, 1, 1)
    QTest.keyClick(editor, Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier)
    _assert_clean_unchanged(editor, original)


@pytest.mark.parametrize(
    ("key", "before_table"),
    [
        (Qt.Key.Key_Delete, True),
        (Qt.Key.Key_Backspace, False),
    ],
)
def test_erase_from_adjacent_paragraph_never_consumes_table(key, before_table):
    model = [
        Block(kind=PARAGRAPH, runs=[InlineRun(text="Avant")]),
        _table(),
        Block(kind=PARAGRAPH, runs=[InlineRun(text="Après")]),
    ]
    editor = _editor(model)
    table = _table_frame(editor.document())
    if before_table:
        block = editor.document().begin()
        position = block.position() + block.length() - 1
    else:
        position = table.lastPosition() + 1
    cursor = QTextCursor(editor.document())
    cursor.setPosition(position)
    editor.setTextCursor(cursor)

    QTest.keyClick(editor, key)

    _assert_clean_unchanged(editor, model)


@pytest.mark.parametrize("table_first", [True, False])
def test_document_edge_never_lets_erase_consume_table(table_first):
    paragraph = Block(kind=PARAGRAPH, runs=[InlineRun(text="Texte")])
    model = [_table(), paragraph] if table_first else [paragraph, _table()]
    editor = _editor(model)
    table = _table_frame(editor.document())
    if table_first:
        position = table.lastPosition() + 1
        key = Qt.Key.Key_Backspace
    else:
        before = editor.document().begin()
        position = before.position() + before.length() - 1
        key = Qt.Key.Key_Delete
    cursor = QTextCursor(editor.document())
    cursor.setPosition(position)
    editor.setTextCursor(cursor)

    QTest.keyClick(editor, key)

    _assert_clean_unchanged(editor, model)


def test_two_adjacent_tables_keep_their_frame_boundary():
    model = [_table(), _table()]
    editor = _editor(model)
    first, second = [
        frame
        for frame in editor.document().rootFrame().childFrames()
        if isinstance(frame, QTextTable)
    ]
    cursor = QTextCursor(editor.document())
    cursor.setPosition(first.lastPosition() + 1)
    editor.setTextCursor(cursor)

    QTest.keyClick(editor, Qt.Key.Key_Delete)
    QTest.keyClick(editor, Qt.Key.Key_Backspace)

    assert extract_blocks(editor.document()) == model
    assert second.rows() == 2
    assert not editor.document().isModified()


def test_typography_and_nbsp_stay_inside_current_cell():
    original = [_single_cell_table()]
    editor = _editor(original)
    _place_in_cell(editor, 0, 0)

    QTest.keyClicks(editor, '"mot" : XVIIe oeuvre')
    assert editor.insert_nbsp() is True

    (cell,) = extract_blocks(editor.document())[0].children[0].children
    assert "«\u00a0mot\u00a0»\u00a0:" in "".join(run.text for run in cell.runs)
    assert "œuvre" in "".join(run.text for run in cell.runs)
    assert cell.runs[-1].text.endswith(NBSP)
    assert any(run.text == "e" and run.superscript for run in cell.runs)


def test_quote_state_is_local_to_each_table_cell():
    model = [
        Block(
            kind=TABLE,
            children=[
                Block(
                    kind=TABLE_ROW,
                    children=[
                        _cell(InlineRun(text='"')),
                        _cell(InlineRun(text="")),
                    ],
                )
            ],
        )
    ]
    editor = _editor(model)
    _place_in_cell(editor, 0, 1)

    QTest.keyClicks(editor, '"mot"')

    cells = extract_blocks(editor.document())[0].children[0].children
    assert cells[0].runs == [InlineRun(text='"')]
    assert cells[1].runs == [InlineRun(text=f"«{NBSP}mot{NBSP}»")]


def test_inline_formatting_and_link_are_preserved_in_one_cell():
    original = [_single_cell_table(InlineRun(text="texte"))]
    editor = _editor(original)
    _select_cell_text(editor, 0, 0)

    toggle_bold(editor)
    toggle_italic(editor)
    toggle_underline(editor)
    toggle_strikethrough(editor)
    toggle_superscript(editor)
    set_link(editor, "https://example.org")

    assert extract_blocks(editor.document()) == [
        _single_cell_table(
            InlineRun(
                text="texte",
                bold=True,
                italic=True,
                underline=True,
                strikethrough=True,
                superscript=True,
                link_href="https://example.org",
            )
        )
    ]
    editor.undo()
    assert extract_blocks(editor.document())[0].children[0].children[0].runs[0].link_href is None


def test_real_shortcuts_keep_inline_semantics_inside_cell():
    window = _window([_single_cell_table(InlineRun(text="texte"))])
    editor = window.editor
    _select_cell_text(editor, 0, 0)

    QTest.keyClick(editor, Qt.Key.Key_B, Qt.KeyboardModifier.ControlModifier)
    QTest.keyClick(editor, Qt.Key.Key_I, Qt.KeyboardModifier.ControlModifier)
    QTest.keyClick(editor, Qt.Key.Key_U, Qt.KeyboardModifier.ControlModifier)
    QTest.keyClick(
        editor,
        Qt.Key.Key_S,
        Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier,
    )
    QTest.keyClick(
        editor,
        Qt.Key.Key_Equal,
        Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier,
    )

    run = extract_blocks(editor.document())[0].children[0].children[0].runs[0]
    assert (
        run.bold
        and run.italic
        and run.underline
        and run.strikethrough
        and run.superscript
    )

    QTest.keyClick(editor, Qt.Key.Key_G, Qt.KeyboardModifier.ControlModifier)
    assert not extract_blocks(editor.document())[0].children[0].children[0].runs[0].bold
    QTest.keyClick(editor, Qt.Key.Key_G, Qt.KeyboardModifier.ControlModifier)

    cursor = _table_frame(editor.document()).cellAt(0, 0).lastCursorPosition()
    editor.setTextCursor(cursor)
    QTest.keyClick(editor, Qt.Key.Key_Space, Qt.KeyboardModifier.ControlModifier)
    assert extract_blocks(editor.document())[0].children[0].children[0].runs[-1].text.endswith(
        NBSP
    )


@pytest.mark.parametrize(
    "command",
    [
        set_paragraph,
        lambda editor: set_heading(editor, 2),
        set_blockquote,
        lambda editor: set_list(editor, BULLET_LIST),
        lambda editor: set_list(editor, ORDERED_LIST),
        lambda editor: set_alignment(editor, "left"),
        lambda editor: set_alignment(editor, "center"),
        lambda editor: set_alignment(editor, "right"),
        lambda editor: set_alignment(editor, "justify"),
        toggle_justify,
    ],
)
def test_block_commands_are_clean_noops_in_table_cell(command):
    model = [_table()]
    editor = _editor(model)
    _select_cell_text(editor, 0, 0)

    command(editor)

    _assert_clean_unchanged(editor, model)


def test_block_commands_are_clean_noops_at_collapsed_cell_caret():
    model = [_table()]
    editor = _editor(model)
    _place_in_cell(editor, 1, 0, offset=1)

    for command in (
        set_paragraph,
        lambda target: set_heading(target, 2),
        set_blockquote,
        lambda target: set_list(target, BULLET_LIST),
        lambda target: set_alignment(target, "center"),
        toggle_justify,
    ):
        command(editor)
        _assert_clean_unchanged(editor, model)


@pytest.mark.parametrize("crosses_text", [False, True])
def test_block_commands_refuse_multicell_and_table_text_selections(crosses_text):
    model = [
        Block(kind=PARAGRAPH, runs=[InlineRun(text="Avant")]),
        _table(),
    ]
    editor = _editor(model)
    table = _table_frame(editor.document())
    start = (
        editor.document().begin().position()
        if crosses_text
        else table.cellAt(0, 0).firstPosition()
    )
    _select(editor, start, table.cellAt(0, 1).lastPosition())

    for command in (
        set_paragraph,
        lambda target: set_heading(target, 2),
        set_blockquote,
        lambda target: set_list(target, BULLET_LIST),
        lambda target: set_alignment(target, "center"),
        toggle_justify,
    ):
        command(editor)
        _assert_clean_unchanged(editor, model)


@pytest.mark.parametrize(
    "command",
    [toggle_bold, toggle_italic, toggle_underline, toggle_strikethrough, toggle_superscript],
)
def test_inline_formatting_refuses_multicell_selection(command):
    model = [_table()]
    editor = _editor(model)
    table = _table_frame(editor.document())
    _select(
        editor,
        table.cellAt(0, 0).firstPosition(),
        table.cellAt(0, 1).lastPosition(),
    )

    command(editor)

    _assert_clean_unchanged(editor, model)


def test_inline_format_at_caret_applies_only_to_new_text_in_cell():
    editor = _editor([_single_cell_table(InlineRun(text="avant"))])
    _place_in_cell(editor, 0, 0, offset=len("avant"))

    toggle_bold(editor)
    QTest.keyClicks(editor, "x")

    assert extract_blocks(editor.document()) == [
        _single_cell_table(
            InlineRun(text="avant"),
            InlineRun(text="x", bold=True),
        )
    ]


@pytest.mark.parametrize(
    ("key", "position_delta"),
    [(Qt.Key.Key_Delete, 0), (Qt.Key.Key_Backspace, len("[12]"))],
)
def test_footnote_erase_in_cell_remains_atomic_and_undoable(key, position_delta):
    original = [
        _single_cell_table(
            InlineRun(text="avant "),
            InlineRun(footnote_ref="12"),
            InlineRun(text=" après"),
        )
    ]
    editor = _editor(original)
    table = _table_frame(editor.document())
    block = table.cellAt(0, 0).firstCursorPosition().block()
    marker_start = block.position() + len("avant ")
    cursor = QTextCursor(editor.document())
    cursor.setPosition(marker_start + position_delta)
    editor.setTextCursor(cursor)

    QTest.keyClick(editor, key)

    assert extract_blocks(editor.document()) == [
        _single_cell_table(InlineRun(text="avant  après"))
    ]
    editor.undo()
    assert extract_blocks(editor.document()) == original


def test_context_menu_delete_cut_and_paste_use_table_guards(qapplication):
    model = [_table()]
    editor = _editor(model)
    table = _table_frame(editor.document())
    _select(
        editor,
        table.cellAt(0, 0).firstPosition(),
        table.cellAt(0, 1).lastPosition(),
    )
    qapplication.clipboard().setText("remplacement")

    for action_name in ("edit-delete", "edit-cut", "edit-paste"):
        menu = editor._create_merope_context_menu()
        action = next(
            item for item in menu.actions() if item.objectName() == action_name
        )
        action.trigger()
        QApplication.processEvents()
        menu.deleteLater()
        _assert_clean_unchanged(editor, model)


@pytest.mark.parametrize(
    "key",
    [
        Qt.Key.Key_Return,
        Qt.Key.Key_Tab,
        Qt.Key.Key_Backspace,
        Qt.Key.Key_Delete,
        Qt.Key.Key_X,
    ],
)
def test_foreign_qtexttable_is_keyboard_fail_closed(key):
    editor = MeropeTextEdit()
    _OPEN_WIDGETS.append(editor)
    table = QTextCursor(editor.document()).insertTable(1, 1)
    editor.setTextCursor(table.cellAt(0, 0).firstCursorPosition())
    editor.document().clearUndoRedoStacks()
    editor.document().setModified(False)
    editor.show()
    editor.setFocus()
    QApplication.processEvents()
    block_count = editor.document().blockCount()

    QTest.keyClick(editor, key)

    assert editor.document().blockCount() == block_count
    assert table.rows() == 1 and table.columns() == 1
    assert not editor.document().isModified()
    assert not editor.document().isUndoAvailable()
