from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QMimeData, Qt
from PySide6.QtGui import QFont, QTextCharFormat, QTextCursor, QTextDocument
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from bloggen.content.footnotes import (
    footnote_definition_blocks,
    separate_footnote_definitions,
)
from bloggen.content.writer import read_content_file, write_content_file
from bloggen.markdown.rich_text_import import markdown_to_blocks
from bloggen.markdown.rich_text_model import (
    BULLET_LIST,
    FOOTNOTE_DEFINITION,
    LIST_ITEM,
    PARAGRAPH,
    Block,
    InlineRun,
)
from bloggen.ui.qt_editor.constants import (
    BOLD_PROPERTY,
    FOOTNOTE_ID_PROPERTY,
    FOOTNOTE_INSTANCE_PROPERTY,
    FOOTNOTE_MARKER_PROPERTY,
    ITALIC_PROPERTY,
)
from bloggen.ui.qt_editor.document_adapter import (
    UnsupportedInlineError,
    extract_blocks,
    inline_format_enabled,
    make_footnote_format,
    populate_document,
)
from bloggen.ui.qt_editor.file_io import (
    load_content_document,
    save_content_document,
)
from bloggen.ui.qt_editor.footnote_selection import merope_footnote_at_position
from bloggen.ui.qt_editor.formatting import (
    set_link,
    toggle_bold,
    toggle_italic,
    toggle_strikethrough,
    toggle_superscript,
)
from bloggen.ui.qt_editor.text_edit import MeropeTextEdit
from bloggen.ui.qt_editor.window import QtEditorWindow


@pytest.fixture(scope="module", autouse=True)
def qapplication():
    app = QApplication.instance() or QApplication([])
    yield app


def _select(editor: MeropeTextEdit, start: int, end: int | None = None) -> None:
    cursor = QTextCursor(editor.document())
    cursor.setPosition(start)
    if end is not None:
        cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
    editor.setTextCursor(cursor)


def _editor(blocks: list[Block]) -> MeropeTextEdit:
    editor = MeropeTextEdit()
    populate_document(editor.document(), blocks)
    editor.document().setModified(False)
    return editor


def _first_footnote_target(document: QTextDocument):
    for position in range(document.characterCount() - 1):
        target = merope_footnote_at_position(document, position)
        if target is not None:
            return target
    raise AssertionError("Aucun appel de note Qt")


def _body_with_note(note_id: str = "1") -> list[Block]:
    return [
        Block(
            kind=PARAGRAPH,
            runs=[
                InlineRun(text="Avant "),
                InlineRun(footnote_ref=note_id),
                InlineRun(text=" après."),
            ],
        )
    ]


def test_simple_reference_is_native_visible_text_and_semantic_run():
    blocks = _body_with_note("12")
    editor = _editor(blocks)
    target = _first_footnote_target(editor.document())

    assert editor.document().begin().text() == "Avant [12] après."
    assert target.note_id == "12"
    assert target.end - target.start == len("[12]")
    assert extract_blocks(editor.document()) == blocks


def test_literal_bracketed_number_without_properties_remains_text():
    document = QTextDocument()
    cursor = QTextCursor(document)
    cursor.insertText("Texte [12]")

    assert extract_blocks(document) == [
        Block(kind=PARAGRAPH, runs=[InlineRun(text="Texte [12]")])
    ]


def test_reference_inside_simple_list_roundtrips():
    blocks = [
        Block(
            kind=BULLET_LIST,
            children=[
                Block(
                    kind=LIST_ITEM,
                    runs=[InlineRun(text="Item"), InlineRun(footnote_ref="1")],
                )
            ],
        )
    ]
    editor = _editor(blocks)

    assert extract_blocks(editor.document()) == blocks


def test_two_references_with_same_id_remain_distinct_semantic_runs():
    blocks = [
        Block(
            kind=PARAGRAPH,
            runs=[InlineRun(footnote_ref="1"), InlineRun(footnote_ref="1")],
        )
    ]
    editor = _editor(blocks)

    assert editor.document().begin().text() == "[1][1]"
    assert extract_blocks(editor.document()) == blocks


@pytest.mark.parametrize(
    ("visible", "configure"),
    [
        (
            "[1]",
            lambda fmt: fmt.setProperty(FOOTNOTE_ID_PROPERTY, "1"),
        ),
        (
            "[1]",
            lambda fmt: fmt.setProperty(FOOTNOTE_MARKER_PROPERTY, True),
        ),
        (
            "[1]",
            lambda fmt: fmt.setProperty(FOOTNOTE_INSTANCE_PROPERTY, 0),
        ),
        (
            "[1]",
            lambda fmt: (
                fmt.setProperty(FOOTNOTE_MARKER_PROPERTY, True),
                fmt.setProperty(FOOTNOTE_ID_PROPERTY, "12"),
            ),
        ),
    ],
)
def test_incomplete_or_incoherent_qt_marker_is_refused(visible, configure):
    document = QTextDocument()
    char_format = QTextCharFormat()
    configure(char_format)
    QTextCursor(document).insertText(visible, char_format)

    with pytest.raises(UnsupportedInlineError):
        extract_blocks(document)


def test_semantic_text_format_on_footnote_marker_is_refused():
    document = QTextDocument()
    char_format = make_footnote_format(InlineRun(footnote_ref="1"))
    char_format.setProperty(BOLD_PROPERTY, True)
    char_format.setFontWeight(QFont.Weight.Bold.value)
    QTextCursor(document).insertText("[1]", char_format)

    with pytest.raises(UnsupportedInlineError, match="format de texte"):
        extract_blocks(document)


@pytest.mark.parametrize(
    ("command", "field", "value"),
    [
        (toggle_bold, "bold", True),
        (toggle_italic, "italic", True),
        (toggle_strikethrough, "strikethrough", True),
        (toggle_superscript, "superscript", True),
        (lambda editor: set_link(editor, "https://example.org"), "link_href", "https://example.org"),
    ],
)
def test_text_format_across_reference_changes_only_text(command, field, value):
    original = _body_with_note()
    editor = _editor(original)
    _select(editor, 0, editor.document().characterCount() - 1)

    command(editor)

    runs = extract_blocks(editor.document())[0].runs
    assert getattr(runs[0], field) == value
    assert runs[1] == InlineRun(footnote_ref="1")
    assert getattr(runs[2], field) == value
    editor.undo()
    assert extract_blocks(editor.document()) == original


@pytest.mark.parametrize(
    "command",
    [
        toggle_bold,
        toggle_italic,
        toggle_strikethrough,
        toggle_superscript,
        lambda editor: set_link(editor, "https://example.org"),
    ],
)
def test_text_format_on_reference_only_is_clean_noop(command):
    original = _body_with_note()
    editor = _editor(original)
    target = _first_footnote_target(editor.document())
    editor.setTextCursor(target.cursor(editor.document()))

    command(editor)

    assert extract_blocks(editor.document()) == original
    assert not editor.document().isModified()
    assert not editor.document().isUndoAvailable()


def test_click_selects_complete_footnote_marker(qapplication):
    editor = _editor(_body_with_note("12"))
    editor.resize(400, 120)
    editor.show()
    qapplication.processEvents()
    target = _first_footnote_target(editor.document())
    start = QTextCursor(editor.document())
    start.setPosition(target.start)
    end = QTextCursor(editor.document())
    end.setPosition(target.end)
    point = editor.cursorRect(start).center()
    point.setX((point.x() + editor.cursorRect(end).center().x()) // 2)

    QTest.mouseClick(editor.viewport(), Qt.MouseButton.LeftButton, pos=point)

    assert editor.textCursor().selectionStart() == target.start
    assert editor.textCursor().selectionEnd() == target.end
    editor.close()


def test_typing_inside_marker_replaces_whole_marker_with_plain_text():
    editor = _editor(_body_with_note("12"))
    target = _first_footnote_target(editor.document())
    _select(editor, target.start + 2)

    QTest.keyClick(editor, Qt.Key.Key_X)

    assert extract_blocks(editor.document()) == [
        Block(kind=PARAGRAPH, runs=[InlineRun(text="Avant x après.")])
    ]
    editor.undo()
    assert extract_blocks(editor.document()) == _body_with_note("12")


@pytest.mark.parametrize("position_name", ["before", "after"])
def test_typing_adjacent_to_marker_does_not_inherit_footnote_semantics(position_name):
    original = [
        Block(
            kind=PARAGRAPH,
            runs=[InlineRun(footnote_ref="12")],
        )
    ]
    editor = _editor(original)
    target = _first_footnote_target(editor.document())
    position = target.start if position_name == "before" else target.end
    _select(editor, position)

    QTest.keyClick(editor, Qt.Key.Key_X)

    expected_runs = (
        [InlineRun(text="x"), InlineRun(footnote_ref="12")]
        if position_name == "before"
        else [InlineRun(footnote_ref="12"), InlineRun(text="x")]
    )
    assert extract_blocks(editor.document()) == [
        Block(kind=PARAGRAPH, runs=expected_runs)
    ]
    editor.undo()
    assert extract_blocks(editor.document()) == original


def test_delete_partial_marker_selection_removes_complete_reference():
    original = _body_with_note("12")
    editor = _editor(original)
    target = _first_footnote_target(editor.document())
    _select(editor, target.start + 1, target.end - 1)

    QTest.keyClick(editor, Qt.Key.Key_Delete)

    assert extract_blocks(editor.document()) == [
        Block(kind=PARAGRAPH, runs=[InlineRun(text="Avant  après.")])
    ]
    editor.undo()
    assert extract_blocks(editor.document()) == original


def test_plain_text_paste_over_partial_marker_replaces_complete_reference():
    original = _body_with_note("12")
    editor = _editor(original)
    target = _first_footnote_target(editor.document())
    _select(editor, target.start + 1, target.end - 1)
    mime = QMimeData()
    mime.setText("collé")

    editor.insertFromMimeData(mime)

    assert extract_blocks(editor.document()) == [
        Block(kind=PARAGRAPH, runs=[InlineRun(text="Avant collé après.")])
    ]
    editor.undo()
    assert extract_blocks(editor.document()) == original


@pytest.mark.parametrize("key", [Qt.Key.Key_Delete, Qt.Key.Key_Backspace])
def test_complete_reference_deletion_undo_redo_preserves_semantic_format(key):
    original = _body_with_note()
    editor = _editor(original)
    target = _first_footnote_target(editor.document())
    editor.setTextCursor(target.cursor(editor.document()))

    QTest.keyClick(editor, key)

    deleted = [Block(kind=PARAGRAPH, runs=[InlineRun(text="Avant  après.")])]
    assert extract_blocks(editor.document()) == deleted
    assert editor.document().isModified()
    editor.undo()
    assert extract_blocks(editor.document()) == original
    editor.redo()
    assert extract_blocks(editor.document()) == deleted


def test_split_and_rebuild_definitions_preserve_order_and_runs():
    first = [InlineRun(text="Première", bold=True)]
    third = [InlineRun(text="Orpheline", italic=True)]
    blocks = [
        Block(kind=PARAGRAPH, runs=[InlineRun(footnote_ref="1")]),
        Block(kind=FOOTNOTE_DEFINITION, footnote_id="1", runs=first),
        Block(kind=FOOTNOTE_DEFINITION, footnote_id="3", runs=third),
    ]

    body, definitions = separate_footnote_definitions(blocks)

    assert body == blocks[:1]
    assert definitions == {"1": first, "3": third}
    assert footnote_definition_blocks(definitions) == blocks[1:]


def test_window_panel_displays_rich_definitions_without_dirtying_body(tmp_path):
    body = (
        "Corps[^1] et suite[^2].\n\n"
        "[^1]: Première **note** avec [lien](https://example.org).\n\n"
        "[^2]: Deuxième *note*.\n"
    )
    path = write_content_file(tmp_path, "notes.md", {"title": "Notes"}, body)
    window = QtEditorWindow(path)

    assert list(window.footnote_definitions) == ["1", "2"]
    assert window.footnote_panel.isReadOnly()
    assert window.footnote_panel.toPlainText() == (
        "[1] Première note avec lien.\n[2] Deuxième note."
    )
    formats = []
    block = window.footnote_panel.document().begin()
    while block.isValid():
        iterator = block.begin()
        while not iterator.atEnd():
            fragment = iterator.fragment()
            if fragment.isValid():
                formats.append((fragment.text(), fragment.charFormat()))
            iterator += 1
        block = block.next()
    assert any(text == "note" and inline_format_enabled(fmt, BOLD_PROPERTY) for text, fmt in formats)
    assert any(
        text == "note" and inline_format_enabled(fmt, ITALIC_PROPERTY)
        for text, fmt in formats
    )
    assert any(text == "lien" and fmt.isAnchor() for text, fmt in formats)
    assert not window.editor.document().isModified()
    window.close()


def test_open_save_reopen_separates_body_and_preserves_front_matter(tmp_path):
    metadata = {"title": "Bossuet", "slug": "bossuet", "type": "page"}
    body = (
        "Bossuet écrit une phrase[^1], puis une autre[^2].\n\n"
        "[^1]: Première **note**.\n\n"
        "[^2]: Deuxième note avec [lien](https://example.org).\n"
    )
    path = write_content_file(tmp_path, "bossuet.md", metadata, body)
    document = QTextDocument()

    loaded = load_content_document(path, document)

    expected = markdown_to_blocks(body)
    expected_body, expected_definitions = separate_footnote_definitions(expected)
    assert extract_blocks(document) == expected_body
    assert loaded.footnote_definitions == expected_definitions
    assert all(block.kind != FOOTNOTE_DEFINITION for block in extract_blocks(document))
    result = save_content_document(
        path,
        loaded.metadata,
        document,
        loaded.footnote_definitions,
    )
    assert markdown_to_blocks(result.markdown_body) == expected
    saved_metadata, _saved_body = read_content_file(path)
    assert saved_metadata == metadata

    reopened = QTextDocument()
    reloaded = load_content_document(path, reopened)
    assert extract_blocks(reopened) == expected_body
    assert reloaded.footnote_definitions == expected_definitions


@pytest.mark.parametrize(
    "body",
    [
        "Texte sans appel.\n\n[^3]: Note orpheline.\n",
        "Référence sans définition[^7].\n",
    ],
)
def test_orphan_definition_and_missing_definition_are_preserved(tmp_path, body):
    path = write_content_file(tmp_path, "orphan.md", {"title": "Notes"}, body)
    document = QTextDocument()
    loaded = load_content_document(path, document)
    expected = markdown_to_blocks(body)

    result = save_content_document(
        path,
        loaded.metadata,
        document,
        loaded.footnote_definitions,
    )

    assert markdown_to_blocks(result.markdown_body) == expected


def test_deleting_reference_keeps_definition_as_orphan_on_disk(tmp_path):
    body = "Texte avec appel[^1].\n\n[^1]: Définition conservée.\n"
    path = write_content_file(tmp_path, "delete.md", {"title": "Notes"}, body)
    window = QtEditorWindow(path)
    target = _first_footnote_target(window.editor.document())
    window.editor.setTextCursor(target.cursor(window.editor.document()))

    QTest.keyClick(window.editor, Qt.Key.Key_Delete)

    assert window.footnote_definitions == {
        "1": [InlineRun(text="Définition conservée.")]
    }
    assert window.save_document()
    _metadata, saved = read_content_file(path)
    assert "[^1]" not in saved.split("\n\n", 1)[0]
    assert "[^1]: Définition conservée." in saved
    window.close()


def test_document_without_notes_keeps_empty_store_and_same_roundtrip(tmp_path):
    body = "Corps sans note.\n"
    path = write_content_file(tmp_path, "plain.md", {"title": "Simple"}, body)
    document = QTextDocument()
    loaded = load_content_document(path, document)

    assert loaded.footnote_definitions == {}
    result = save_content_document(path, loaded.metadata, document, {})
    assert result.markdown_body == body


def test_unsupported_definition_content_is_refused_before_document_change(tmp_path):
    safe = write_content_file(tmp_path, "safe.md", {}, "Texte sûr.\n")
    unsafe = write_content_file(
        tmp_path,
        "unsafe.md",
        {},
        "Texte[^1].\n\n[^1]: ![Image](image.png)\n",
    )
    document = QTextDocument()
    load_content_document(safe, document)
    before = extract_blocks(document)

    with pytest.raises(UnsupportedInlineError, match="images"):
        load_content_document(unsafe, document)

    assert extract_blocks(document) == before
