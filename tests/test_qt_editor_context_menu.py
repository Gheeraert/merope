"""The QTextEdit context menu must never bypass Merope's safety guards."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QByteArray, QMimeData
from PySide6.QtGui import QAction, QTextCursor
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
)
from bloggen.ui.qt_editor.document_adapter import (
    extract_blocks,
    is_caption_block,
    populate_document,
)
from bloggen.ui.qt_editor.footnote_selection import merope_footnote_at_position
from bloggen.ui.qt_editor.text_edit import MeropeTextEdit


_OPEN_EDITORS: list[MeropeTextEdit] = []


@pytest.fixture(scope="module", autouse=True)
def qapplication():
    app = QApplication.instance() or QApplication([])
    yield app
    app.clipboard().clear()


@pytest.fixture(autouse=True)
def clean_clipboard(qapplication):
    qapplication.clipboard().clear()
    yield
    qapplication.clipboard().clear()
    for editor in _OPEN_EDITORS:
        editor.close()
        editor.deleteLater()
    _OPEN_EDITORS.clear()
    qapplication.processEvents()


def _editor(blocks: list[Block]) -> MeropeTextEdit:
    editor = MeropeTextEdit()
    _OPEN_EDITORS.append(editor)
    populate_document(editor.document(), blocks)
    editor.document().setModified(False)
    return editor


def _select(editor: MeropeTextEdit, start: int, end: int) -> None:
    cursor = QTextCursor(editor.document())
    cursor.setPosition(start)
    cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
    editor.setTextCursor(cursor)


def _footnote(editor: MeropeTextEdit):
    targets = {}
    for position in range(editor.document().characterCount() - 1):
        target = merope_footnote_at_position(editor.document(), position)
        if target is not None:
            targets[target.start] = target
    assert len(targets) == 1
    return next(iter(targets.values()))


def _menu_action(editor: MeropeTextEdit, object_name: str) -> tuple[QMenu, QAction]:
    menu = editor._create_merope_context_menu()
    matches = [
        action for action in menu.actions() if action.objectName() == object_name
    ]
    assert len(matches) == 1
    return menu, matches[0]


def _trigger(editor: MeropeTextEdit, object_name: str) -> None:
    menu, action = _menu_action(editor, object_name)
    assert action.isEnabled()
    action.trigger()
    QApplication.processEvents()
    menu.close()
    menu.deleteLater()
    QApplication.processEvents()


def _select_separator(editor: MeropeTextEdit, left_block_number: int) -> None:
    left = editor.document().findBlockByNumber(left_block_number)
    right = left.next()
    separator = left.position() + left.length() - 1
    _select(editor, separator, right.position())
    assert "\u2029" in editor.textCursor().selectedText()


def _table() -> Block:
    return Block(
        kind=TABLE,
        children=[
            Block(
                kind=TABLE_ROW,
                children=[Block(kind=TABLE_CELL, runs=[InlineRun(text="A")])],
            ),
            Block(
                kind=TABLE_ROW,
                children=[Block(kind=TABLE_CELL, runs=[InlineRun(text="B")])],
            ),
        ],
    )


def _figure_blocks() -> list[Block]:
    return [
        Block(kind=PARAGRAPH, runs=[InlineRun(text="Avant")]),
        Block(
            kind=PARAGRAPH,
            runs=[InlineRun(image_src="missing.png", image_alt="Portrait")],
        ),
        Block(kind=PARAGRAPH, runs=[InlineRun(text="Après")]),
    ]


def _qt_blocks(editor: MeropeTextEdit):
    blocks = []
    block = editor.document().begin()
    while block.isValid():
        blocks.append(block)
        block = block.next()
    return blocks


def test_context_copy_whole_footnote_adds_merope_mime():
    original = [Block(kind=PARAGRAPH, runs=[InlineRun(footnote_ref="12")])]
    editor = _editor(original)
    editor.setTextCursor(_footnote(editor).cursor(editor.document()))

    _trigger(editor, "edit-copy")

    mime = QApplication.clipboard().mimeData()
    assert mime.hasFormat(MEROPE_FRAGMENT_MIME)
    assert mime.text() == "[12]"
    assert decode_markdown_fragment(mime.data(MEROPE_FRAGMENT_MIME)) == original
    assert extract_blocks(editor.document()) == original


def test_context_copy_partial_footnote_expands_atomically_without_mutation():
    original = [Block(kind=PARAGRAPH, runs=[InlineRun(footnote_ref="12")])]
    editor = _editor(original)
    target = _footnote(editor)
    _select(editor, target.start + 2, target.start + 3)

    _trigger(editor, "edit-copy")

    mime = QApplication.clipboard().mimeData()
    assert mime.hasFormat(MEROPE_FRAGMENT_MIME)
    assert mime.text() == "[12]"
    assert decode_markdown_fragment(mime.data(MEROPE_FRAGMENT_MIME)) == original
    assert extract_blocks(editor.document()) == original
    assert not editor.document().isModified()


def test_context_cut_uses_the_same_atomic_footnote_path_as_keyboard():
    original = [
        Block(
            kind=PARAGRAPH,
            runs=[
                InlineRun(text="Avant "),
                InlineRun(footnote_ref="12"),
                InlineRun(text=" après"),
            ],
        )
    ]
    editor = _editor(original)
    target = _footnote(editor)
    _select(editor, target.start + 1, target.end - 1)

    _trigger(editor, "edit-cut")

    mime = QApplication.clipboard().mimeData()
    assert mime.hasFormat(MEROPE_FRAGMENT_MIME)
    assert decode_markdown_fragment(mime.data(MEROPE_FRAGMENT_MIME)) == [
        Block(kind=PARAGRAPH, runs=[InlineRun(footnote_ref="12")])
    ]
    assert extract_blocks(editor.document()) == [
        Block(kind=PARAGRAPH, runs=[InlineRun(text="Avant  après")])
    ]
    editor.undo()
    assert extract_blocks(editor.document()) == original


def test_context_delete_partial_footnote_removes_the_whole_marker():
    original = [
        Block(
            kind=PARAGRAPH,
            runs=[
                InlineRun(text="Avant "),
                InlineRun(footnote_ref="12"),
                InlineRun(text=" après"),
            ],
        )
    ]
    editor = _editor(original)
    target = _footnote(editor)
    _select(editor, target.start + 2, target.start + 3)

    _trigger(editor, "edit-delete")

    assert extract_blocks(editor.document()) == [
        Block(kind=PARAGRAPH, runs=[InlineRun(text="Avant  après")])
    ]
    editor.undo()
    assert extract_blocks(editor.document()) == original


@pytest.mark.parametrize("raw", [Block(kind=VERBATIM, raw_text="brut"), _table()])
@pytest.mark.parametrize("action_name", ["edit-cut", "edit-delete"])
def test_context_mutation_refuses_normal_raw_boundaries(raw, action_name):
    original = [
        Block(kind=PARAGRAPH, runs=[InlineRun(text="normal")]),
        raw,
    ]
    editor = _editor(original)
    _select_separator(editor, 0)

    _trigger(editor, action_name)

    assert extract_blocks(editor.document()) == original
    assert not editor.document().isModified()
    assert not editor.document().isUndoAvailable()


@pytest.mark.parametrize("action_name", ["edit-cut", "edit-delete"])
def test_context_mutation_refuses_caption_boundaries(action_name):
    original = _figure_blocks()
    editor = _editor(original)
    caption = next(block for block in _qt_blocks(editor) if is_caption_block(block))
    after = caption.next()
    _select(editor, caption.position() + 2, after.position() + 2)

    _trigger(editor, action_name)
    QApplication.processEvents()

    assert extract_blocks(editor.document()) == original
    assert not editor.document().isModified()
    assert not editor.document().isUndoAvailable()


def test_context_copy_and_cut_image_keep_its_caption_contract():
    original = _figure_blocks()
    editor = _editor(original)
    caption = next(block for block in _qt_blocks(editor) if is_caption_block(block))
    image = caption.previous()
    _select(editor, image.position(), image.position() + 1)

    _trigger(editor, "edit-copy")

    payload = QApplication.clipboard().mimeData().data(MEROPE_FRAGMENT_MIME)
    (copied,) = decode_markdown_fragment(payload)
    assert copied.runs[0].image_alt == "Portrait"
    assert extract_blocks(editor.document()) == original

    _trigger(editor, "edit-cut")
    QApplication.processEvents()
    assert not any(is_caption_block(block) for block in _qt_blocks(editor))
    assert extract_blocks(editor.document()) == [
        Block(kind=PARAGRAPH, runs=[InlineRun(text="Avant")]),
        Block(kind=PARAGRAPH, runs=[InlineRun(text="")]),
        Block(kind=PARAGRAPH, runs=[InlineRun(text="Après")]),
    ]
    editor.undo()
    QApplication.processEvents()
    assert extract_blocks(editor.document()) == original


def test_context_paste_preserves_internal_merope_mime_priority():
    editor = _editor([Block(kind=PARAGRAPH, runs=[InlineRun(text="Début ")])])
    cursor = QTextCursor(editor.document())
    cursor.movePosition(QTextCursor.MoveOperation.End)
    editor.setTextCursor(cursor)
    canonical = [
        Block(kind=PARAGRAPH, runs=[InlineRun(text="Interne", bold=True)])
    ]
    mime = QMimeData()
    mime.setData(
        MEROPE_FRAGMENT_MIME,
        QByteArray(blocks_to_markdown(canonical).encode("utf-8")),
    )
    mime.setHtml("<p><em>HTML</em></p>")
    mime.setText("BRUT")
    QApplication.clipboard().setMimeData(mime)
    QApplication.processEvents()

    _trigger(editor, "edit-paste")

    assert extract_blocks(editor.document()) == [
        Block(
            kind=PARAGRAPH,
            runs=[InlineRun(text="Début "), InlineRun(text="Interne", bold=True)],
        )
    ]


def test_missing_native_action_falls_back_to_an_explicit_safe_menu():
    original = [
        Block(
            kind=PARAGRAPH,
            runs=[
                InlineRun(text="Avant "),
                InlineRun(footnote_ref="12"),
                InlineRun(text=" après"),
            ],
        )
    ]
    editor = _editor(original)
    target = _footnote(editor)
    _select(editor, target.start + 2, target.start + 3)
    unsafe_menu = QMenu(editor)
    unsafe_action = unsafe_menu.addAction("Suppression Qt non protégée")
    unsafe_action.setObjectName("native-delete-without-expected-name")
    unsafe_action.triggered.connect(editor.textCursor().removeSelectedText)
    for object_name in ("edit-copy", "edit-cut", "edit-paste"):
        action = unsafe_menu.addAction(object_name)
        action.setObjectName(object_name)
    editor.createStandardContextMenu = lambda _position=None: unsafe_menu

    menu = editor._create_merope_context_menu()

    assert menu is not unsafe_menu
    assert unsafe_action not in menu.actions()
    assert {
        action.objectName() for action in menu.actions() if not action.isSeparator()
    } == {
        "edit-undo",
        "edit-redo",
        "edit-cut",
        "edit-copy",
        "edit-paste",
        "edit-delete",
        "select-all",
    }
    delete = next(
        action for action in menu.actions() if action.objectName() == "edit-delete"
    )
    delete.trigger()
    assert extract_blocks(editor.document()) == [
        Block(kind=PARAGRAPH, runs=[InlineRun(text="Avant  après")])
    ]
    editor.undo()
    assert extract_blocks(editor.document()) == original
