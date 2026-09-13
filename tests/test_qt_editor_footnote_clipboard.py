from __future__ import annotations

import os
from dataclasses import replace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QByteArray, QMimeData, Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from bloggen.markdown.rich_text_model import (
    BULLET_LIST,
    LIST_ITEM,
    PARAGRAPH,
    Block,
    InlineRun,
)
from bloggen.markdown.rich_text_export import blocks_to_markdown
from bloggen.markdown.typography import NBSP
from bloggen.ui.qt_editor.clipboard_fragment import (
    MEROPE_FRAGMENT_MIME,
    decode_markdown_fragment,
    encode_selection_as_markdown,
)
from bloggen.ui.qt_editor.document_adapter import extract_blocks, populate_document
from bloggen.ui.qt_editor.footnote_selection import (
    expand_selection_to_footnotes,
    merope_footnote_at_position,
)
from bloggen.ui.qt_editor.text_edit import MeropeTextEdit


@pytest.fixture(scope="module")
def qapplication():
    app = QApplication.instance() or QApplication([])
    yield app
    app.clipboard().clear()


@pytest.fixture(autouse=True)
def clean_clipboard(qapplication):
    qapplication.clipboard().clear()
    yield
    qapplication.clipboard().clear()


def _editor(blocks: list[Block] | None = None) -> MeropeTextEdit:
    editor = MeropeTextEdit()
    populate_document(editor.document(), blocks or [])
    editor.document().setModified(False)
    return editor


def _select(editor: MeropeTextEdit, start: int, end: int) -> None:
    cursor = QTextCursor(editor.document())
    cursor.setPosition(start)
    cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
    editor.setTextCursor(cursor)


def _select_all(editor: MeropeTextEdit) -> None:
    _select(editor, 0, editor.document().characterCount() - 1)


def _set_cursor(editor: MeropeTextEdit, position: int) -> None:
    cursor = QTextCursor(editor.document())
    cursor.setPosition(position)
    editor.setTextCursor(cursor)


def _footnote_targets(editor: MeropeTextEdit):
    targets = {}
    for position in range(editor.document().characterCount() - 1):
        target = merope_footnote_at_position(editor.document(), position)
        if target is not None:
            targets[target.start] = target
    return list(targets.values())


def _clipboard_mime() -> QMimeData:
    mime = QApplication.clipboard().mimeData()
    assert mime is not None
    return mime


def test_real_clipboard_copy_paste_of_one_reference_preserves_semantics():
    original = [
        Block(kind=PARAGRAPH, runs=[InlineRun(footnote_ref="1")]),
    ]
    editor = _editor(original)
    target = _footnote_targets(editor)[0]
    editor.setTextCursor(target.cursor(editor.document()))
    assert expand_selection_to_footnotes(editor.textCursor())[1]
    assert decode_markdown_fragment(
        encode_selection_as_markdown(editor.textCursor())
    ) == original
    refused = []
    editor.clipboardRefused.connect(refused.append)

    editor.copy()

    assert not refused
    mime = _clipboard_mime()
    assert mime.hasFormat(MEROPE_FRAGMENT_MIME)
    assert mime.hasText() and mime.text() == "[1]"
    assert mime.hasHtml()
    assert decode_markdown_fragment(mime.data(MEROPE_FRAGMENT_MIME)) == original
    _set_cursor(editor, editor.document().characterCount() - 1)
    editor.paste()

    assert extract_blocks(editor.document()) == [
        Block(
            kind=PARAGRAPH,
            runs=[InlineRun(footnote_ref="1"), InlineRun(footnote_ref="1")],
        )
    ]


def test_internal_fragment_reopens_exported_brackets_and_parenthesized_targets():
    blocks = [
        Block(
            kind=PARAGRAPH,
            runs=[
                InlineRun(
                    text="a]b",
                    underline=True,
                    link_href="https://example.org/a_(b)",
                ),
                InlineRun(text=" "),
                InlineRun(
                    image_src="assets/image_(1).png",
                    image_alt="a]b",
                ),
            ],
        )
    ]

    decoded = decode_markdown_fragment(
        QByteArray(blocks_to_markdown(blocks).encode("utf-8"))
    )

    assert decoded == blocks


def test_keyboard_shortcuts_use_internal_copy_and_paste_path():
    original = [Block(kind=PARAGRAPH, runs=[InlineRun(footnote_ref="1")])]
    editor = _editor(original)
    target = _footnote_targets(editor)[0]
    editor.setTextCursor(target.cursor(editor.document()))

    QTest.keyClick(
        editor,
        Qt.Key.Key_C,
        Qt.KeyboardModifier.ControlModifier,
    )
    assert _clipboard_mime().hasFormat(MEROPE_FRAGMENT_MIME)
    _set_cursor(editor, editor.document().characterCount() - 1)
    QTest.keyClick(
        editor,
        Qt.Key.Key_V,
        Qt.KeyboardModifier.ControlModifier,
    )

    assert extract_blocks(editor.document()) == [
        Block(
            kind=PARAGRAPH,
            runs=[InlineRun(footnote_ref="1"), InlineRun(footnote_ref="1")],
        )
    ]


def test_keyboard_cut_shortcut_builds_internal_mime_before_removal():
    original = [
        Block(
            kind=PARAGRAPH,
            runs=[
                InlineRun(text="Avant "),
                InlineRun(footnote_ref="1"),
                InlineRun(text=" après"),
            ],
        )
    ]
    editor = _editor(original)
    target = _footnote_targets(editor)[0]
    editor.setTextCursor(target.cursor(editor.document()))

    QTest.keyClick(
        editor,
        Qt.Key.Key_X,
        Qt.KeyboardModifier.ControlModifier,
    )

    assert _clipboard_mime().hasFormat(MEROPE_FRAGMENT_MIME)
    assert extract_blocks(editor.document()) == [
        Block(kind=PARAGRAPH, runs=[InlineRun(text="Avant  après")])
    ]
    editor.undo()
    assert extract_blocks(editor.document()) == original


def test_real_clipboard_cut_paste_moves_reference_with_native_undo_redo():
    original = [
        Block(
            kind=PARAGRAPH,
            runs=[
                InlineRun(text="Texte A "),
                InlineRun(footnote_ref="1"),
                InlineRun(text=" texte B"),
            ],
        )
    ]
    editor = _editor(original)
    target = _footnote_targets(editor)[0]
    editor.setTextCursor(target.cursor(editor.document()))
    assert expand_selection_to_footnotes(editor.textCursor())[1]

    editor.cut()

    cut_state = [Block(kind=PARAGRAPH, runs=[InlineRun(text="Texte A  texte B")])]
    assert extract_blocks(editor.document()) == cut_state
    cut_mime = _clipboard_mime()
    assert cut_mime.hasFormat(MEROPE_FRAGMENT_MIME)
    assert cut_mime.hasText() and cut_mime.hasHtml()
    _set_cursor(editor, editor.document().characterCount() - 1)
    editor.paste()
    moved = [
        Block(
            kind=PARAGRAPH,
            runs=[InlineRun(text="Texte A  texte B"), InlineRun(footnote_ref="1")],
        )
    ]
    assert extract_blocks(editor.document()) == moved

    editor.undo()
    assert extract_blocks(editor.document()) == cut_state
    editor.undo()
    assert extract_blocks(editor.document()) == original
    editor.redo()
    assert extract_blocks(editor.document()) == cut_state
    editor.redo()
    assert extract_blocks(editor.document()) == moved


@pytest.mark.parametrize("operation", ["copy", "cut"])
def test_partial_reference_selection_is_expanded_before_clipboard_creation(operation):
    original = [Block(kind=PARAGRAPH, runs=[InlineRun(footnote_ref="12")])]
    editor = _editor(original)
    target = _footnote_targets(editor)[0]
    _select(editor, target.start + 1, target.end - 1)

    getattr(editor, operation)()

    mime = _clipboard_mime()
    if operation == "copy":
        assert editor.textCursor().selectionStart() == target.start
        assert editor.textCursor().selectionEnd() == target.end
    else:
        assert not editor.textCursor().hasSelection()
        assert editor.textCursor().position() == target.start
    assert mime.text() == "[12]"
    assert decode_markdown_fragment(mime.data(MEROPE_FRAGMENT_MIME)) == original
    if operation == "cut":
        assert extract_blocks(editor.document()) == [
            Block(kind=PARAGRAPH, runs=[InlineRun(text="")])
        ]
        editor.undo()
        assert extract_blocks(editor.document()) == original


def test_text_and_formatted_runs_around_reference_survive_internal_clipboard():
    blocks = [
        Block(
            kind=PARAGRAPH,
            runs=[
                InlineRun(text="Avant", bold=True),
                InlineRun(text=" "),
                InlineRun(footnote_ref="1"),
                InlineRun(text=" "),
                InlineRun(text="après", italic=True),
            ],
        )
    ]
    source = _editor(blocks)
    destination = _editor()
    _select_all(source)

    source.copy()
    destination.paste()

    # A lone paragraph paste reuses the destination block's own formatting
    # (like ordinary rich-text paste), here the empty document's default
    # justified paragraph rather than ``blocks``' own "left" default.
    assert extract_blocks(destination.document()) == [
        replace(blocks[0], alignment="justify")
    ]


@pytest.mark.parametrize(
    "runs",
    [
        [
            InlineRun(footnote_ref="1"),
            InlineRun(text=" texte "),
            InlineRun(footnote_ref="2"),
        ],
        [InlineRun(footnote_ref="1"), InlineRun(footnote_ref="1")],
    ],
)
def test_multiple_and_adjacent_references_preserve_ids_and_count(runs):
    blocks = [Block(kind=PARAGRAPH, runs=runs)]
    source = _editor(blocks)
    destination = _editor()
    _select_all(source)

    source.copy()
    destination.paste()

    assert extract_blocks(destination.document()) == [
        replace(blocks[0], alignment="justify")
    ]
    assert len(_footnote_targets(destination)) == 2


def test_two_paragraph_fragment_uses_canonical_multiblock_roundtrip():
    blocks = [
        Block(
            kind=PARAGRAPH,
            runs=[InlineRun(text="Premier"), InlineRun(footnote_ref="1")],
        ),
        Block(kind=PARAGRAPH, runs=[InlineRun(text="Second", italic=True)]),
    ]
    source = _editor(blocks)
    destination = _editor()
    _select_all(source)

    source.copy()
    destination.paste()

    assert extract_blocks(destination.document()) == blocks


def test_simple_list_fragment_uses_canonical_multiblock_roundtrip():
    blocks = [
        Block(
            kind=BULLET_LIST,
            children=[
                Block(
                    kind=LIST_ITEM,
                    runs=[InlineRun(text="Premier"), InlineRun(footnote_ref="1")],
                ),
                Block(kind=LIST_ITEM, runs=[InlineRun(text="Second")]),
            ],
        )
    ]
    source = _editor(blocks)
    destination = _editor()
    _select_all(source)

    source.copy()
    destination.paste()

    assert extract_blocks(destination.document()) == blocks


def test_invalid_internal_mime_refuses_without_html_or_text_fallback():
    original = [Block(kind=PARAGRAPH, runs=[InlineRun(text="Document intact")])]
    editor = _editor(original)
    refused = []
    editor.pasteRefused.connect(refused.append)
    mime = QMimeData()
    mime.setData(MEROPE_FRAGMENT_MIME, b"\xff\xfe")
    mime.setHtml("<p>Fallback HTML</p>")
    mime.setText("Fallback texte")
    QApplication.clipboard().setMimeData(mime)

    assert editor.canInsertFromMimeData(mime)
    editor.paste()

    assert extract_blocks(editor.document()) == original
    assert refused and "UTF-8" in refused[0]
    assert not editor.document().isUndoAvailable()


def test_typography_selection_keeps_reference_semantic():
    editor = _editor(
        [
            Block(
                kind=PARAGRAPH,
                runs=[
                    InlineRun(text="Texte "),
                    InlineRun(footnote_ref="1"),
                    InlineRun(text=" : suite"),
                ],
            )
        ]
    )
    _select_all(editor)

    assert editor.apply_typography_to_selection()

    assert extract_blocks(editor.document()) == [
        Block(
            kind=PARAGRAPH,
            runs=[
                InlineRun(text="Texte "),
                InlineRun(footnote_ref="1"),
                InlineRun(text=f"{NBSP}: suite"),
            ],
        )
    ]
