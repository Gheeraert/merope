from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QByteArray, QMimeData
from PySide6.QtGui import QTextCursor, QTextTable
from PySide6.QtWidgets import QApplication, QMenu

from bloggen.markdown.rich_text_export import blocks_to_markdown
from bloggen.markdown.rich_text_model import (
    PARAGRAPH,
    TABLE,
    TABLE_CELL,
    TABLE_ROW,
    VERBATIM,
    Block,
    InlineRun,
)
from bloggen.ui.qt_editor.clipboard_fragment import (
    MEROPE_FRAGMENT_MIME,
    decode_markdown_fragment,
    encode_blocks_as_markdown,
)
from bloggen.ui.qt_editor.document_adapter import (
    extract_blocks,
    is_caption_block,
    populate_document,
)
from bloggen.ui.qt_editor.table_structure import current_table_block
from bloggen.ui.qt_editor.text_edit import MeropeTextEdit
import bloggen.ui.qt_editor.text_edit as text_edit_module


_EDITORS: list[MeropeTextEdit] = []


@pytest.fixture(scope="module", autouse=True)
def qapplication():
    app = QApplication.instance() or QApplication([])
    yield app
    app.clipboard().clear()


@pytest.fixture(autouse=True)
def close_editors(qapplication):
    qapplication.clipboard().clear()
    yield
    qapplication.clipboard().clear()
    for editor in _EDITORS:
        editor.hide()
        editor.deleteLater()
    _EDITORS.clear()
    qapplication.processEvents()


def _cell(*runs: InlineRun) -> Block:
    return Block(kind=TABLE_CELL, runs=list(runs) or [InlineRun(text="")])


def _row(*cells: Block) -> Block:
    return Block(kind=TABLE_ROW, children=list(cells))


def _table() -> Block:
    return Block(
        kind=TABLE,
        children=[
            _row(
                _cell(
                    InlineRun(text="G", bold=True),
                    InlineRun(text="I", italic=True),
                    InlineRun(text="U", underline=True),
                    InlineRun(text="2", superscript=True),
                    InlineRun(text="Lien", link_href="https://example.org/a_(b)"),
                    InlineRun(text="\u00a0"),
                    InlineRun(footnote_ref="7"),
                ),
                _cell(InlineRun(text="B")),
            ),
            _row(
                _cell(InlineRun(text="C")),
                _cell(InlineRun(text="D")),
            ),
        ],
    )


def _simple_table(label: str = "A") -> Block:
    return Block(
        kind=TABLE,
        children=[
            _row(_cell(InlineRun(text=label))),
            _row(_cell(InlineRun(text=f"{label}2"))),
        ],
    )


def _paragraph(text: str) -> Block:
    return Block(kind=PARAGRAPH, runs=[InlineRun(text=text)])


def _editor(blocks: list[Block]) -> MeropeTextEdit:
    editor = MeropeTextEdit()
    _EDITORS.append(editor)
    populate_document(editor.document(), blocks)
    editor.show()
    editor.activateWindow()
    editor.setFocus()
    QApplication.processEvents()
    assert editor.hasFocus()
    return editor


def _tables(editor: MeropeTextEdit) -> list[QTextTable]:
    return [
        frame
        for frame in editor.document().rootFrame().childFrames()
        if isinstance(frame, QTextTable)
    ]


def _place_in_cell(
    editor: MeropeTextEdit,
    row: int = 0,
    column: int = 0,
    *,
    table_index: int = 0,
) -> None:
    editor.setTextCursor(
        _tables(editor)[table_index]
        .cellAt(row, column)
        .firstCursorPosition()
    )


def _select(editor: MeropeTextEdit, start: int, end: int) -> None:
    cursor = QTextCursor(editor.document())
    cursor.setPosition(start)
    cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
    editor.setTextCursor(cursor)


def _table_menu(editor: MeropeTextEdit) -> tuple[QMenu, QMenu]:
    menu = editor._create_merope_context_menu()
    submenu = next(
        action.menu()
        for action in menu.actions()
        if action.objectName() == "merope-table-menu"
    )
    assert submenu is not None
    return menu, submenu


def _menu_action(menu: QMenu, object_name: str):
    return next(
        action for action in menu.actions() if action.objectName() == object_name
    )


def _mime_for(table: Block) -> QMimeData:
    payload = encode_blocks_as_markdown([table])
    mime = QMimeData()
    mime.setData(MEROPE_FRAGMENT_MIME, QByteArray(payload))
    mime.setText(payload.decode("utf-8"))
    return mime


def _set_table_clipboard(table: Block) -> None:
    QApplication.clipboard().setMimeData(_mime_for(table))
    QApplication.processEvents()


def _all_blocks(editor: MeropeTextEdit):
    block = editor.document().begin()
    while block.isValid():
        yield block
        block = block.next()


def test_encode_blocks_and_current_table_block_round_trip_exactly():
    table = _table()
    editor = _editor([_paragraph("Avant"), table, _paragraph("Après")])
    _place_in_cell(editor, 1, 1)

    extracted = current_table_block(editor.textCursor())
    payload = encode_blocks_as_markdown([extracted])

    assert extracted == table
    assert decode_markdown_fragment(payload) == [table]
    assert payload.decode("utf-8") == blocks_to_markdown([table])


def test_context_copy_table_writes_canonical_and_plain_mime_without_mutation():
    table = _table()
    editor = _editor([table])
    _place_in_cell(editor, 0, 0)
    menu, submenu = _table_menu(editor)

    _menu_action(submenu, "table-copy").trigger()
    QApplication.processEvents()

    mime = QApplication.clipboard().mimeData()
    assert mime.hasFormat(MEROPE_FRAGMENT_MIME)
    assert decode_markdown_fragment(mime.data(MEROPE_FRAGMENT_MIME)) == [table]
    assert mime.text() == blocks_to_markdown([table])
    assert extract_blocks(editor.document()) == [table]
    assert not editor.document().isModified()
    assert not editor.document().isUndoAvailable()
    assert editor.hasFocus()
    menu.deleteLater()


def test_context_cut_table_copies_before_one_undoable_removal():
    table = _table()
    before = [_paragraph("Avant"), table, _paragraph("Après")]
    after = [_paragraph("Avant"), _paragraph("Après")]
    editor = _editor(before)
    _place_in_cell(editor, 0, 0)
    menu, submenu = _table_menu(editor)

    _menu_action(submenu, "table-cut").trigger()
    QApplication.processEvents()

    mime = QApplication.clipboard().mimeData()
    assert decode_markdown_fragment(mime.data(MEROPE_FRAGMENT_MIME)) == [table]
    assert extract_blocks(editor.document()) == after
    assert editor.hasFocus()
    editor.undo()
    assert extract_blocks(editor.document()) == before
    assert not editor.document().isUndoAvailable()
    editor.redo()
    assert extract_blocks(editor.document()) == after
    menu.deleteLater()


def test_cut_does_not_delete_or_replace_clipboard_when_encoding_fails(monkeypatch):
    table = _simple_table()
    editor = _editor([table])
    _place_in_cell(editor)
    QApplication.clipboard().setText("sentinel")
    refused: list[str] = []
    editor.clipboardRefused.connect(refused.append)
    monkeypatch.setattr(
        text_edit_module,
        "encode_blocks_as_markdown",
        lambda _blocks: (_ for _ in ()).throw(ValueError("échec injecté")),
    )

    assert not editor.cut_current_table()

    assert QApplication.clipboard().text() == "sentinel"
    assert extract_blocks(editor.document()) == [table]
    assert not editor.document().isModified()
    assert not editor.document().isUndoAvailable()
    assert refused and "échec injecté" in refused[0]


@pytest.mark.parametrize(
    "target",
    ["empty", "middle", "between", "before-table", "after-table"],
)
def test_internal_table_fragment_pastes_through_existing_body_pipeline(target):
    copied = _simple_table("Copié")
    existing = _simple_table("Existant")
    if target == "empty":
        before = []
        expected = [copied]
    elif target == "middle":
        before = [_paragraph("AvantAprès")]
        expected = [_paragraph("Avant"), copied, _paragraph("Après")]
    elif target == "between":
        before = [_paragraph("Avant"), _paragraph("Après")]
        expected = [_paragraph("Avant"), copied, _paragraph("Après")]
    elif target == "before-table":
        before = [_paragraph("Avant"), existing, _paragraph("Après")]
        expected = [_paragraph("Avant"), copied, existing, _paragraph("Après")]
    else:
        before = [_paragraph("Avant"), existing, _paragraph("Après")]
        expected = [_paragraph("Avant"), existing, copied, _paragraph("Après")]
    editor = _editor(before)
    cursor = QTextCursor(editor.document())
    if target == "middle":
        cursor.setPosition(len("Avant"))
    elif target in {"between", "after-table"}:
        cursor = QTextCursor(editor.document().lastBlock())
    elif target == "before-table":
        cursor = QTextCursor(editor.document().begin())
        cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock)
    editor.setTextCursor(cursor)
    _set_table_clipboard(copied)

    editor.paste()

    assert extract_blocks(editor.document()) == expected
    assert all(table.format().headerRowCount() == 1 for table in _tables(editor))
    editor.undo()
    assert extract_blocks(editor.document()) == before
    assert not editor.document().isUndoAvailable()
    editor.redo()
    assert extract_blocks(editor.document()) == expected


def test_copy_then_paste_table_in_same_document_keeps_original():
    table = _simple_table()
    before = [table, _paragraph("Après")]
    editor = _editor(before)
    _place_in_cell(editor)
    assert editor.copy_current_table()
    editor.setTextCursor(QTextCursor(editor.document().lastBlock()))

    editor.paste()

    assert extract_blocks(editor.document()) == [table, table, _paragraph("Après")]
    assert len(_tables(editor)) == 2


@pytest.mark.parametrize(
    ("row", "column", "selection"),
    [(0, 0, False), (1, 1, False), (0, 1, True), (1, 0, True)],
)
def test_table_fragment_paste_in_graphical_cell_is_refused_atomically(
    row,
    column,
    selection,
):
    table = _table()
    editor = _editor([table])
    target = _tables(editor)[0].cellAt(row, column)
    if selection:
        _select(editor, target.firstPosition(), target.lastPosition())
    else:
        editor.setTextCursor(target.firstCursorPosition())
    refused: list[str] = []
    editor.pasteRefused.connect(refused.append)

    editor.insertFromMimeData(_mime_for(_simple_table("Collé")))

    assert refused
    assert extract_blocks(editor.document()) == [table]
    assert not editor.document().isModified()
    assert not editor.document().isUndoAvailable()


@pytest.mark.parametrize("target", ["raw", "caption", "raw-boundary", "table-boundary"])
def test_table_fragment_paste_in_protected_context_is_refused(target):
    if target == "raw":
        before = [Block(kind=VERBATIM, raw_text="brut")]
    elif target == "caption":
        before = [
            Block(
                kind=PARAGRAPH,
                runs=[InlineRun(image_src="missing.png", image_alt="Légende")],
            ),
            _paragraph("Après"),
        ]
    elif target == "raw-boundary":
        before = [_paragraph("Avant"), Block(kind=VERBATIM, raw_text="brut")]
    else:
        before = [_paragraph("Avant"), _simple_table(), _paragraph("Après")]
    editor = _editor(before)
    if target == "caption":
        caption = next(block for block in _all_blocks(editor) if is_caption_block(block))
        cursor = QTextCursor(caption)
        cursor.setPosition(caption.position() + 1)
        editor.setTextCursor(cursor)
    elif target.endswith("boundary"):
        first = editor.document().begin()
        second = first.next()
        _select(
            editor,
            first.position() + first.length() - 1,
            second.position(),
        )
    refused: list[str] = []
    editor.pasteRefused.connect(refused.append)

    editor.insertFromMimeData(_mime_for(_simple_table("Collé")))

    assert refused
    assert extract_blocks(editor.document()) == before
    assert not editor.document().isModified()
    assert not editor.document().isUndoAvailable()


def test_multi_cell_standard_copy_and_cut_are_refused_without_tsv_semantics():
    table = _simple_table()
    editor = _editor([table])
    frame = _tables(editor)[0]
    _select(
        editor,
        frame.cellAt(0, 0).firstPosition(),
        frame.cellAt(1, 0).lastPosition(),
    )
    QApplication.clipboard().setText("sentinel")
    refused: list[str] = []
    editor.clipboardRefused.connect(refused.append)

    editor.copy()
    editor.cut()

    assert QApplication.clipboard().text() == "sentinel"
    assert len(refused) == 2
    assert extract_blocks(editor.document()) == [table]
    assert not editor.document().isModified()
    assert not editor.document().isUndoAvailable()


def test_single_cell_text_selection_keeps_existing_paragraph_clipboard_contract():
    table = _simple_table()
    editor = _editor([table])
    cell = _tables(editor)[0].cellAt(0, 0)
    _select(editor, cell.firstPosition(), cell.lastPosition())

    editor.copy()

    mime = QApplication.clipboard().mimeData()
    assert decode_markdown_fragment(mime.data(MEROPE_FRAGMENT_MIME)) == [
        _paragraph("A")
    ]


def test_copy_table_action_exists_in_fail_closed_menu(monkeypatch):
    table = _simple_table()
    editor = _editor([table])
    _place_in_cell(editor)
    unsafe_menu = QMenu(editor)
    unsafe = unsafe_menu.addAction("Action native inconnue")
    unsafe.setObjectName("unsafe")
    monkeypatch.setattr(
        editor,
        "createStandardContextMenu",
        lambda _position=None: unsafe_menu,
    )

    menu, submenu = _table_menu(editor)
    _menu_action(submenu, "table-copy").trigger()

    assert menu is not unsafe_menu
    assert unsafe not in menu.actions()
    assert decode_markdown_fragment(
        QApplication.clipboard().mimeData().data(MEROPE_FRAGMENT_MIME)
    ) == [table]
    menu.deleteLater()


def test_raw_table_fallback_has_no_structural_table_clipboard_actions():
    raw_table = Block(
        kind=TABLE,
        children=[
            _row(_cell(InlineRun(image_src="image.png", image_alt="Image"))),
        ],
    )
    editor = _editor([raw_table])

    menu = editor._create_merope_context_menu()

    assert not any(
        action.objectName() == "merope-table-menu" for action in menu.actions()
    )
    menu.deleteLater()
