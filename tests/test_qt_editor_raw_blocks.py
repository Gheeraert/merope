from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QMimeData, Qt
from PySide6.QtGui import QImage, QTextCursor, QTextDocument
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from bloggen.content.footnotes import footnote_reference_order
from bloggen.content.writer import write_content_file
from bloggen.markdown.front_matter import parse_front_matter
from bloggen.markdown.rich_text_export import blocks_to_markdown
from bloggen.markdown.rich_text_import import markdown_to_blocks
from bloggen.markdown.rich_text_model import (
    HEADING,
    FOOTNOTE_DEFINITION,
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
from bloggen.ui.qt_editor.constants import (
    RAW_BLOCK_GROUP_PROPERTY,
    RAW_BLOCK_KIND_PROPERTY,
)
from bloggen.ui.qt_editor.clipboard_fragment import MEROPE_FRAGMENT_MIME
from bloggen.ui.qt_editor.document_adapter import (
    UnsupportedBlockError,
    UnsupportedInlineError,
    extract_blocks,
    insert_footnote_reference,
    insert_blocks,
    populate_document,
    renumber_footnote_references,
    selection_block_identities,
    selection_crosses_raw_boundary,
    validate_blocks,
)
from bloggen.ui.qt_editor.formatting import (
    set_alignment,
    set_blockquote,
    set_heading,
    set_link,
    set_list,
    toggle_bold,
    toggle_italic,
    toggle_strikethrough,
    toggle_superscript,
)
from bloggen.ui.qt_editor.recovery import build_recovery_draft, prepare_recovery_draft
from bloggen.ui.qt_editor.text_edit import MeropeTextEdit
from bloggen.ui.qt_editor.window import QtEditorWindow


@pytest.fixture(scope="module", autouse=True)
def qapplication():
    app = QApplication.instance() or QApplication([])
    yield app
    app.clipboard().clear()


def _table(*, note_id: str | None = None) -> Block:
    value_runs = [InlineRun(text="C")]
    if note_id is not None:
        value_runs.append(InlineRun(footnote_ref=note_id))
    return Block(
        kind=TABLE,
        children=[
            Block(
                kind=TABLE_ROW,
                children=[
                    Block(kind=TABLE_CELL, runs=[InlineRun(text="A")]),
                    Block(kind=TABLE_CELL, runs=[InlineRun(text="B", bold=True)]),
                ],
            ),
            Block(
                kind=TABLE_ROW,
                children=[
                    Block(kind=TABLE_CELL, runs=value_runs),
                    Block(
                        kind=TABLE_CELL,
                        runs=[InlineRun(text="D", italic=True, link_href="https://example.org")],
                    ),
                ],
            ),
        ],
    )


def _editor(blocks: list[Block]) -> MeropeTextEdit:
    editor = MeropeTextEdit()
    populate_document(editor.document(), blocks)
    return editor


def _select_block_text(editor: MeropeTextEdit, block_number: int) -> QTextCursor:
    block = editor.document().findBlockByNumber(block_number)
    cursor = QTextCursor(block)
    cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
    editor.setTextCursor(cursor)
    return cursor


def _select_separator(editor: MeropeTextEdit, left_block_number: int) -> QTextCursor:
    left = editor.document().findBlockByNumber(left_block_number)
    right = left.next()
    separator = left.position() + left.length() - 1
    cursor = QTextCursor(editor.document())
    cursor.setPosition(separator)
    cursor.setPosition(right.position(), QTextCursor.MoveMode.KeepAnchor)
    editor.setTextCursor(cursor)
    assert cursor.selectionEnd() == right.position()
    assert "\u2029" in cursor.selectedText()
    return cursor


def test_table_and_verbatim_roundtrip_as_grouped_raw_blocks():
    blocks = [
        Block(kind=PARAGRAPH, runs=[InlineRun(text="Avant")]),
        _table(),
        Block(kind=VERBATIM, raw_text="<section>\n**brut** : oe XXe\n</section>"),
        Block(kind=HEADING, level=2, runs=[InlineRun(text="Après")]),
        Block(
            kind=ORDERED_LIST,
            children=[Block(kind=LIST_ITEM, runs=[InlineRun(text="item")])],
        ),
    ]
    document = QTextDocument()

    populate_document(document, blocks)

    assert extract_blocks(document) == blocks
    raw_blocks = [
        block
        for number in range(document.blockCount())
        if (block := document.findBlockByNumber(number)).blockFormat().hasProperty(
            RAW_BLOCK_KIND_PROPERTY
        )
    ]
    assert raw_blocks
    assert all(block.blockFormat().property(RAW_BLOCK_GROUP_PROPERTY) for block in raw_blocks)


def test_two_adjacent_tables_have_distinct_transient_groups():
    document = QTextDocument()
    populate_document(document, [_table(), _table()])
    groups = []
    block = document.begin()
    while block.isValid():
        group = block.blockFormat().property(RAW_BLOCK_GROUP_PROPERTY)
        if group and group not in groups:
            groups.append(group)
        block = block.next()

    assert len(groups) == 2
    assert extract_blocks(document) == [_table(), _table()]


def test_invalid_edited_table_falls_back_to_verbatim_without_text_loss():
    editor = _editor([_table()])
    separator = _select_block_text(editor, 1)
    separator.insertText("séparateur cassé")
    expected = "\n".join(
        editor.document().findBlockByNumber(index).text()
        for index in range(editor.document().blockCount())
    )

    assert extract_blocks(editor.document()) == [
        Block(kind=VERBATIM, raw_text=expected)
    ]
    assert blocks_to_markdown(extract_blocks(editor.document())).rstrip("\n") == expected


def test_structural_table_insertion_splits_surrounding_paragraph_once():
    editor = _editor([Block(kind=PARAGRAPH, runs=[InlineRun(text="AvantAprès")])])
    cursor = editor.textCursor()
    cursor.setPosition(5)
    inserted = insert_blocks(cursor, [_table()])
    editor.setTextCursor(inserted)

    assert extract_blocks(editor.document()) == [
        Block(kind=PARAGRAPH, runs=[InlineRun(text="Avant")]),
        _table(),
        Block(kind=PARAGRAPH, runs=[InlineRun(text="Après")]),
    ]
    assert editor.document().isUndoAvailable()
    editor.undo()
    assert extract_blocks(editor.document()) == [
        Block(kind=PARAGRAPH, runs=[InlineRun(text="AvantAprès")])
    ]
    editor.redo()
    assert extract_blocks(editor.document()) == [
        Block(kind=PARAGRAPH, runs=[InlineRun(text="Avant")]),
        _table(),
        Block(kind=PARAGRAPH, runs=[InlineRun(text="Après")]),
    ]


def test_raw_typing_and_enter_are_literal_and_keep_group():
    editor = _editor([Block(kind=VERBATIM, raw_text="brut")])
    cursor = editor.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.End)
    editor.setTextCursor(cursor)

    QTest.keyClicks(editor, ' " : ; ! ? oeuvre XXe')
    QTest.keyClick(editor, Qt.Key.Key_Return)
    QTest.keyClicks(editor, "((note))")

    blocks = extract_blocks(editor.document())
    assert blocks == [
        Block(kind=VERBATIM, raw_text='brut " : ; ! ? oeuvre XXe\n((note))')
    ]
    first = editor.document().begin()
    second = first.next()
    assert first.blockFormat().property(RAW_BLOCK_GROUP_PROPERTY) == second.blockFormat().property(
        RAW_BLOCK_GROUP_PROPERTY
    )


def test_typography_and_rich_formatting_do_not_touch_raw_blocks():
    editor = _editor(
        [
            Block(kind=PARAGRAPH, runs=[InlineRun(text="normal")]),
            Block(kind=VERBATIM, raw_text='" oeuvre :'),
            Block(kind=PARAGRAPH, runs=[InlineRun(text="suite")]),
        ]
    )
    cursor = QTextCursor(editor.document())
    cursor.select(QTextCursor.SelectionType.Document)
    editor.setTextCursor(cursor)

    toggle_bold(editor)
    assert editor.apply_typography_to_selection() is False
    blocks = extract_blocks(editor.document())
    assert blocks[0].runs[0].bold is True
    assert blocks[1] == Block(kind=VERBATIM, raw_text='" oeuvre :')
    assert blocks[2].runs[0].bold is True

    _select_block_text(editor, 1)
    before_undo = editor.document().isUndoAvailable()
    set_heading(editor, 2)
    assert editor.document().isUndoAvailable() == before_undo
    assert extract_blocks(editor.document())[1].kind == VERBATIM


@pytest.mark.parametrize(
    "command,attribute",
    [
        (toggle_superscript, "superscript"),
        (lambda editor: set_link(editor, "https://example.org"), "link_href"),
    ],
)
def test_inline_formatting_crossing_raw_changes_only_normal_text(command, attribute):
    editor = _editor(
        [
            Block(kind=PARAGRAPH, runs=[InlineRun(text="avant")]),
            Block(kind=VERBATIM, raw_text="brut"),
            Block(kind=PARAGRAPH, runs=[InlineRun(text="après")]),
        ]
    )
    cursor = QTextCursor(editor.document())
    cursor.select(QTextCursor.SelectionType.Document)
    editor.setTextCursor(cursor)

    command(editor)

    blocks = extract_blocks(editor.document())
    expected = True if attribute == "superscript" else "https://example.org"
    assert getattr(blocks[0].runs[0], attribute) == expected
    assert blocks[1] == Block(kind=VERBATIM, raw_text="brut")
    assert getattr(blocks[2].runs[0], attribute) == expected


def test_rich_clipboard_pastes_only_plain_text_inside_raw_block():
    editor = _editor([Block(kind=VERBATIM, raw_text="Avant")])
    cursor = editor.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.End)
    editor.setTextCursor(cursor)
    mime = QMimeData()
    mime.setHtml("<p><strong>Riche</strong></p>")
    mime.setText("\nRiche")

    editor.insertFromMimeData(mime)

    assert extract_blocks(editor.document()) == [
        Block(kind=VERBATIM, raw_text="Avant\nRiche")
    ]


def test_image_only_clipboard_is_refused_inside_raw_block_without_mutation():
    editor = _editor([Block(kind=VERBATIM, raw_text="intact")])
    mime = QMimeData()
    mime.setImageData(QImage(2, 2, QImage.Format.Format_ARGB32))
    refused = []
    editor.pasteRefused.connect(refused.append)

    editor.insertFromMimeData(mime)

    assert extract_blocks(editor.document()) == [
        Block(kind=VERBATIM, raw_text="intact")
    ]
    assert refused
    assert not editor.document().isUndoAvailable()


def test_semantic_images_and_footnotes_cannot_be_inserted_into_raw_block():
    editor = _editor([Block(kind=VERBATIM, raw_text="intact")])
    cursor = editor.textCursor()

    with pytest.raises(UnsupportedBlockError, match="bloc brut"):
        insert_blocks(
            cursor,
            [Block(kind=PARAGRAPH, runs=[InlineRun(image_src="image.png")])],
        )
    with pytest.raises(UnsupportedInlineError, match="bloc brut"):
        insert_footnote_reference(cursor, "1")

    assert extract_blocks(editor.document()) == [
        Block(kind=VERBATIM, raw_text="intact")
    ]


def test_delete_and_backspace_refuse_raw_normal_boundaries():
    editor = _editor(
        [
            Block(kind=VERBATIM, raw_text="brut"),
            Block(kind=PARAGRAPH, runs=[InlineRun(text="normal")]),
        ]
    )
    raw = editor.document().begin()
    cursor = QTextCursor(raw)
    cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock)
    editor.setTextCursor(cursor)
    QTest.keyClick(editor, Qt.Key.Key_Delete)
    normal = raw.next()
    cursor = QTextCursor(normal)
    editor.setTextCursor(cursor)
    QTest.keyClick(editor, Qt.Key.Key_Backspace)

    assert extract_blocks(editor.document()) == [
        Block(kind=VERBATIM, raw_text="brut"),
        Block(kind=PARAGRAPH, runs=[InlineRun(text="normal")]),
    ]


@pytest.mark.parametrize("operation", ["delete", "type", "cut", "paste", "insert"])
def test_selected_normal_to_raw_separator_is_protected(operation):
    original = [
        Block(kind=PARAGRAPH, runs=[InlineRun(text="normal")]),
        Block(kind=VERBATIM, raw_text="brut"),
    ]
    editor = _editor(original)
    cursor = _select_separator(editor, 0)
    assert selection_crosses_raw_boundary(cursor)
    identities = selection_block_identities(cursor)
    assert None in identities
    assert len(identities) == 2

    if operation == "delete":
        QTest.keyClick(editor, Qt.Key.Key_Delete)
    elif operation == "type":
        QTest.keyClicks(editor, "x")
    elif operation == "cut":
        refused = []
        editor.clipboardRefused.connect(refused.append)
        editor.cut()
        assert refused
    elif operation == "paste":
        refused = []
        editor.pasteRefused.connect(refused.append)
        QApplication.clipboard().setText("collé")
        editor.paste()
        assert refused
    else:
        with pytest.raises(UnsupportedBlockError, match="frontière"):
            insert_blocks(cursor, [_table()])

    assert extract_blocks(editor.document()) == original
    assert not editor.document().isUndoAvailable()


@pytest.mark.parametrize("operation", ["delete", "cut", "paste"])
def test_selected_raw_to_normal_separator_is_protected(operation):
    original = [
        Block(kind=VERBATIM, raw_text="brut"),
        Block(kind=PARAGRAPH, runs=[InlineRun(text="normal")]),
    ]
    editor = _editor(original)
    cursor = _select_separator(editor, 0)
    assert selection_crosses_raw_boundary(cursor)

    if operation == "delete":
        QTest.keyClick(editor, Qt.Key.Key_Delete)
    elif operation == "cut":
        refused = []
        editor.clipboardRefused.connect(refused.append)
        editor.cut()
        assert refused
    else:
        refused = []
        editor.pasteRefused.connect(refused.append)
        QApplication.clipboard().setText("collé")
        editor.paste()
        assert refused

    assert extract_blocks(editor.document()) == original
    assert not editor.document().isUndoAvailable()


@pytest.mark.parametrize("mime_kind", ["plain", "html", "merope", "image"])
def test_every_paste_representation_is_refused_before_replacing_raw_boundary(
    mime_kind,
):
    original = [
        Block(kind=PARAGRAPH, runs=[InlineRun(text="normal")]),
        Block(kind=VERBATIM, raw_text="brut"),
    ]
    editor = _editor(original)
    _select_separator(editor, 0)
    mime = QMimeData()
    if mime_kind == "plain":
        mime.setText("texte")
    elif mime_kind == "html":
        mime.setHtml("<p><strong>riche</strong></p>")
        mime.setText("riche")
    elif mime_kind == "merope":
        mime.setData(MEROPE_FRAGMENT_MIME, b"**fragment**")
    else:
        mime.setImageData(QImage(2, 2, QImage.Format.Format_ARGB32))
    refused = []
    editor.pasteRefused.connect(refused.append)

    editor.insertFromMimeData(mime)

    assert refused
    assert extract_blocks(editor.document()) == original
    assert not editor.document().isUndoAvailable()


@pytest.mark.parametrize("operation", ["delete", "type", "cut"])
def test_selected_separator_between_distinct_raw_groups_is_protected(operation):
    original = [
        Block(kind=VERBATIM, raw_text="groupe A"),
        Block(kind=VERBATIM, raw_text="groupe B"),
    ]
    editor = _editor(original)
    cursor = _select_separator(editor, 0)
    assert selection_crosses_raw_boundary(cursor)

    if operation == "delete":
        QTest.keyClick(editor, Qt.Key.Key_Delete)
    elif operation == "type":
        QTest.keyClicks(editor, '"')
    else:
        refused = []
        editor.clipboardRefused.connect(refused.append)
        editor.cut()
        assert refused

    assert extract_blocks(editor.document()) == original
    assert not editor.document().isUndoAvailable()


def test_selected_separator_inside_same_raw_group_can_merge_and_undo():
    editor = _editor([Block(kind=VERBATIM, raw_text="ligne 1\nligne 2")])
    first = editor.document().begin()
    original_group = first.blockFormat().property(RAW_BLOCK_GROUP_PROPERTY)
    cursor = _select_separator(editor, 0)
    assert not selection_crosses_raw_boundary(cursor)
    assert selection_block_identities(cursor) == {(VERBATIM, original_group)}

    QTest.keyClick(editor, Qt.Key.Key_Delete)

    assert editor.document().blockCount() == 1
    assert extract_blocks(editor.document()) == [
        Block(kind=VERBATIM, raw_text="ligne 1ligne 2")
    ]
    assert editor.document().begin().blockFormat().property(
        RAW_BLOCK_GROUP_PROPERTY
    ) == original_group
    editor.undo()
    assert extract_blocks(editor.document()) == [
        Block(kind=VERBATIM, raw_text="ligne 1\nligne 2")
    ]
    assert editor.document().begin().blockFormat().property(
        RAW_BLOCK_GROUP_PROPERTY
    ) == original_group


def test_selected_separator_between_normal_blocks_keeps_native_qt_behavior():
    editor = _editor(
        [
            Block(kind=PARAGRAPH, runs=[InlineRun(text="A")]),
            Block(kind=PARAGRAPH, runs=[InlineRun(text="B")]),
        ]
    )
    cursor = _select_separator(editor, 0)
    assert not selection_crosses_raw_boundary(cursor)

    QTest.keyClick(editor, Qt.Key.Key_Delete)

    assert extract_blocks(editor.document()) == [
        Block(kind=PARAGRAPH, runs=[InlineRun(text="AB")])
    ]


def test_renumbering_updates_parsed_table_notes_but_not_verbatim_text():
    document = QTextDocument()
    populate_document(
        document,
        [_table(note_id="7"), Block(kind=VERBATIM, raw_text="littéral [^7]")],
    )

    assert footnote_reference_order(extract_blocks(document)) == ["7"]
    assert renumber_footnote_references(document, {"7": "1"}) is True
    blocks = extract_blocks(document)
    assert footnote_reference_order(blocks) == ["1"]
    assert blocks[1].raw_text == "littéral [^7]"
    document.undo()
    assert footnote_reference_order(extract_blocks(document)) == ["7"]


def test_internal_clipboard_preserves_full_table_and_partial_table_text():
    source = _editor([_table()])
    cursor = QTextCursor(source.document())
    cursor.select(QTextCursor.SelectionType.Document)
    source.setTextCursor(cursor)
    source.copy()
    target = _editor([])
    target.paste()
    assert extract_blocks(target.document()) == [_table()]

    _select_block_text(source, 0)
    source.copy()
    partial = _editor([])
    partial.paste()
    assert extract_blocks(partial.document()) == [
        Block(kind=VERBATIM, raw_text=source.document().begin().text())
    ]


def test_internal_clipboard_preserves_complete_verbatim_block():
    source_block = Block(kind=VERBATIM, raw_text="<section>\n**brut**\n</section>")
    source = _editor([source_block])
    cursor = QTextCursor(source.document())
    cursor.select(QTextCursor.SelectionType.Document)
    source.setTextCursor(cursor)

    source.copy()
    target = _editor([])
    target.paste()

    assert extract_blocks(target.document()) == [source_block]


def test_recovery_roundtrip_accepts_table_and_verbatim(tmp_path):
    document = QTextDocument()
    blocks = [_table(), Block(kind=VERBATIM, raw_text="<section>\nbrut\n</section>")]
    populate_document(document, blocks)

    draft = build_recovery_draft(
        document,
        {},
        {"title": "Raw"},
        project_root=tmp_path,
        current_path=None,
        current_kind="page",
    )
    prepared = prepare_recovery_draft(tmp_path, draft)

    assert prepared.body_blocks == blocks


def test_preview_snapshot_contains_raw_blocks_without_mutating_document(tmp_path, monkeypatch):
    source = tmp_path / "page.md"
    source.write_text("disque", encoding="utf-8")
    window = QtEditorWindow()
    window.current_path = source
    window.current_kind = "page"
    window.metadata = {"title": "Raw", "slug": "raw", "type": "page"}
    populate_document(
        window.editor.document(),
        [_table(), Block(kind=VERBATIM, raw_text="<section>brut</section>")],
    )
    window.editor.document().setModified(True)
    monkeypatch.setattr(window, "request_live_config", lambda: 17)

    window._request_html_preview()

    snapshot = window._pending_preview_snapshots[17]
    parsed = markdown_to_blocks(snapshot.body_markdown)
    assert parsed == [_table(), Block(kind=VERBATIM, raw_text="<section>brut</section>")]
    assert window.editor.document().isModified() is True
    window.autosave_timer.stop()
    window.deleteLater()


def test_table_action_builds_model_and_leaves_normal_paragraph():
    window = QtEditorWindow()

    table = window.insert_table(3, 2)

    blocks = extract_blocks(window.editor.document())
    assert blocks[0] == table
    assert blocks[1] == Block(kind=PARAGRAPH, runs=[InlineRun(text="")])
    assert window.editor.textCursor().block().blockFormat().property(
        RAW_BLOCK_KIND_PROPERTY
    ) in (None, "")
    window.autosave_timer.stop()
    window.deleteLater()


@pytest.mark.parametrize(
    "command",
    [
        toggle_bold,
        toggle_italic,
        toggle_strikethrough,
        toggle_superscript,
        lambda editor: set_link(editor, "https://example.org"),
        lambda editor: set_heading(editor, 2),
        set_blockquote,
        lambda editor: set_list(editor, ORDERED_LIST),
        lambda editor: set_alignment(editor, "center"),
    ],
)
def test_all_rich_commands_are_noops_on_raw_only_selection(command):
    editor = _editor([Block(kind=VERBATIM, raw_text="**brut**")])
    _select_block_text(editor, 0)

    command(editor)

    assert extract_blocks(editor.document()) == [
        Block(kind=VERBATIM, raw_text="**brut**")
    ]
    assert not editor.document().isUndoAvailable()


def test_valid_table_edit_save_and_reopen(tmp_path):
    path = write_content_file(
        tmp_path,
        "table.md",
        {"title": "Table", "slug": "table", "type": "page"},
        blocks_to_markdown([_table()]),
    )
    window = QtEditorWindow(path)
    last_row = window.editor.document().findBlockByNumber(2)
    cursor = QTextCursor(last_row)
    position = last_row.text().rfind("D")
    cursor.setPosition(last_row.position() + position)
    cursor.setPosition(cursor.position() + 1, QTextCursor.MoveMode.KeepAnchor)
    cursor.insertText("E")

    assert window.save_document()
    reopened = QtEditorWindow(path)
    saved = extract_blocks(reopened.editor.document())
    assert saved[0].children[1].children[1].runs[0].text == "E"
    window.autosave_timer.stop()
    reopened.autosave_timer.stop()
    window.deleteLater()
    reopened.deleteLater()


def test_invalid_table_save_preserves_every_source_character(tmp_path):
    path = write_content_file(
        tmp_path,
        "broken-table.md",
        {"title": "Table", "slug": "broken-table", "type": "page"},
        blocks_to_markdown([_table()]),
    )
    window = QtEditorWindow(path)
    separator = _select_block_text(window.editor, 1)
    separator.insertText("séparateur cassé")
    raw = "\n".join(
        window.editor.document().findBlockByNumber(index).text()
        for index in range(window.editor.document().blockCount())
    )

    assert window.save_document()
    parsed = parse_front_matter(path.read_text(encoding="utf-8"))
    assert parsed.body.strip("\n") == raw
    reopened = QtEditorWindow(path)
    assert blocks_to_markdown(extract_blocks(reopened.editor.document())).strip("\n") == raw
    window.autosave_timer.stop()
    reopened.autosave_timer.stop()
    window.deleteLater()
    reopened.deleteLater()


def test_save_renumbers_footnote_inside_table_but_not_verbatim(tmp_path):
    body = blocks_to_markdown(
        [
            _table(note_id="7"),
            Block(kind=VERBATIM, raw_text="<section>littéral [^7]</section>"),
            Block(kind=FOOTNOTE_DEFINITION, footnote_id="7", runs=[InlineRun(text="Note")]),
        ]
    )
    path = write_content_file(
        tmp_path,
        "notes-table.md",
        {"title": "Notes", "slug": "notes-table", "type": "page"},
        body,
    )
    window = QtEditorWindow(path)

    assert window.save_document()

    saved_text = path.read_text(encoding="utf-8")
    assert "[^1]" in saved_text
    assert "<section>littéral [^7]</section>" in saved_text
    assert set(window.footnote_store.definitions) == {"1"}
    assert footnote_reference_order(extract_blocks(window.editor.document())) == ["1"]
    assert not window.editor.document().isUndoAvailable()
    window.autosave_timer.stop()
    window.deleteLater()


@pytest.mark.parametrize(
    "invalid",
    [
        Block(kind=TABLE),
        Block(kind=TABLE, runs=[InlineRun(text="x")], children=[Block(kind=TABLE_ROW)]),
        Block(kind=TABLE, children=[Block(kind=PARAGRAPH)]),
        Block(kind=TABLE, children=[Block(kind=TABLE_ROW, children=[Block(kind=PARAGRAPH)])]),
        Block(kind=VERBATIM, raw_text="x", runs=[InlineRun(text="x")]),
    ],
)
def test_invalid_raw_models_are_rejected_transactionally(invalid):
    document = QTextDocument()
    original = [Block(kind=PARAGRAPH, runs=[InlineRun(text="intact")])]
    populate_document(document, original)

    with pytest.raises(UnsupportedBlockError):
        populate_document(document, [invalid])

    assert extract_blocks(document) == original
