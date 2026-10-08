"""Embedded video in the Qt editor: structural insertion, boundary guards,
dialog URL validation, and round trip through the document adapter."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor, QTextDocument
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from bloggen.markdown.rich_text_model import PARAGRAPH, VERBATIM, Block, InlineRun
from bloggen.markdown.video_syntax import (
    ParsedVideoBlock,
    format_video_block,
    parse_video_block,
)
from bloggen.ui.qt_editor.box_structure import can_insert_box, insert_empty_box
from bloggen.ui.qt_editor.document_adapter import (
    UnsupportedDocumentError,
    extract_blocks,
    populate_document,
    raw_block_identity,
)
from bloggen.ui.qt_editor.text_edit import MeropeTextEdit
from bloggen.ui.qt_editor.video_dialog import VideoInsertDialog
from bloggen.ui.qt_editor.video_structure import (
    can_insert_video,
    insert_video,
    replace_video,
    video_block_at_cursor,
)

VALID_ID = "dQw4w9WgXcQ"
VALID_URL = f"https://www.youtube.com/watch?v={VALID_ID}"


@pytest.fixture(scope="module", autouse=True)
def qapplication():
    app = QApplication.instance() or QApplication([])
    yield app


def _p(text: str) -> Block:
    return Block(kind=PARAGRAPH, runs=[InlineRun(text=text)])


def _video_block(caption: str = "") -> Block:
    return Block(kind=VERBATIM, raw_text=format_video_block(VALID_ID, caption))


def _document(blocks: list[Block]) -> QTextDocument:
    document = QTextDocument()
    populate_document(document, blocks)
    return document


def test_can_insert_video_in_ordinary_text():
    document = _document([_p("")])
    cursor = QTextCursor(document)
    assert can_insert_video(cursor) is True


def test_cannot_insert_video_inside_an_encadre():
    document = _document([_p("Avant.")])
    cursor = insert_empty_box(QTextCursor(document), "Titre")
    assert can_insert_video(cursor) is False
    with pytest.raises(UnsupportedDocumentError):
        insert_video(cursor, VALID_ID, "")


def test_insert_video_round_trips_through_extract_blocks():
    document = _document([_p("Avant."), _p("Après.")])
    text_cursor = QTextCursor(document)
    text_cursor.setPosition(document.findBlockByNumber(0).position())
    insert_video(text_cursor, VALID_ID, "Une légende.")

    blocks = extract_blocks(document)
    assert _video_block("Une légende.") in blocks


def test_video_between_ordinary_blocks_round_trips():
    blocks = [_p("Avant."), _video_block("Légende."), _p("Après.")]
    document = _document(blocks)
    assert extract_blocks(document) == blocks


def test_video_dialog_rejects_invalid_url_without_closing():
    dialog = VideoInsertDialog()
    dialog.url_edit.setText("https://example.com/not-a-video")
    dialog._validate_and_accept()
    assert dialog.result() != dialog.DialogCode.Accepted
    assert not dialog.error_label.isHidden()


def test_video_dialog_accepts_valid_url_and_caption():
    dialog = VideoInsertDialog()
    dialog.url_edit.setText(VALID_URL + "&t=5s")
    dialog.caption_edit.setText("  Une   légende  ")
    dialog._validate_and_accept()
    assert dialog.video_id() == VALID_ID
    assert dialog.caption() == "Une légende"


# --- Width: insertion, default, detection, replacement --------------------


def test_video_dialog_defaults_to_100_percent():
    dialog = VideoInsertDialog()
    assert dialog.width() == 100


def test_insert_video_at_75_percent_round_trips():
    document = _document([_p("")])
    cursor = QTextCursor(document)
    insert_video(cursor, VALID_ID, "Légende.", 75)

    blocks = extract_blocks(document)
    assert blocks == [
        Block(kind=VERBATIM, raw_text=format_video_block(VALID_ID, "Légende.", width=75))
    ]


def test_video_block_at_cursor_detects_an_existing_video():
    document = _document([_p("Avant."), _video_block("Légende."), _p("Après.")])
    cursor = document.findBlockByNumber(1).position()
    text_cursor = QTextCursor(document)
    text_cursor.setPosition(cursor)

    parsed = video_block_at_cursor(text_cursor)
    assert parsed == ParsedVideoBlock(
        provider="youtube",
        video_id=VALID_ID,
        caption="Légende.",
        caption_source="Légende\\.",
        width=100,
    )


def test_video_block_at_cursor_is_none_outside_a_video():
    document = _document([_p("Avant.")])
    cursor = QTextCursor(document)
    assert video_block_at_cursor(cursor) is None


def test_video_dialog_prefilled_for_editing():
    dialog = VideoInsertDialog(video_id=VALID_ID, caption="Légende.", width=75)
    assert dialog.url_edit.text() == VALID_URL
    assert dialog.caption_edit.text() == "Légende."
    assert dialog.width_spin.value() == 75
    assert dialog.windowTitle() == "Modifier la vidéo"


def test_replace_video_from_100_to_50_keeps_id_and_caption():
    document = _document([_p("Avant."), _video_block("Légende."), _p("Après.")])
    text_cursor = QTextCursor(document)
    text_cursor.setPosition(document.findBlockByNumber(1).position())

    replace_video(text_cursor, VALID_ID, "Légende.", 50)

    blocks = extract_blocks(document)
    assert blocks == [
        _p("Avant."),
        Block(kind=VERBATIM, raw_text=format_video_block(VALID_ID, "Légende.", width=50)),
        _p("Après."),
    ]


def test_replace_video_from_75_to_50():
    raw = format_video_block(VALID_ID, "Légende.", width=75)
    document = _document([Block(kind=VERBATIM, raw_text=raw)])
    text_cursor = QTextCursor(document)
    text_cursor.setPosition(document.findBlockByNumber(0).position())

    replace_video(text_cursor, VALID_ID, "Légende.", 50)

    blocks = extract_blocks(document)
    assert blocks == [
        Block(kind=VERBATIM, raw_text=format_video_block(VALID_ID, "Légende.", width=50))
    ]


def test_cannot_replace_a_non_video_verbatim_block():
    other_raw = Block(kind=VERBATIM, raw_text="une\nsource\nbrute\nquelconque")
    document = _document([other_raw])
    text_cursor = QTextCursor(document)
    text_cursor.setPosition(document.findBlockByNumber(0).position())

    assert video_block_at_cursor(text_cursor) is None
    with pytest.raises(UnsupportedDocumentError):
        replace_video(text_cursor, VALID_ID, "Légende.", 50)

    assert extract_blocks(document) == [other_raw]


# --- P1: a caption the user did not touch is preserved byte-for-byte ------


@pytest.mark.parametrize(
    "caption_line",
    ["*gras*", "<em>gras</em>", "Texte   avec   plusieurs   espaces"],
    ids=["manual-markdown-emphasis", "manual-html", "multiple-spaces"],
)
def test_replace_video_without_touching_the_caption_preserves_its_source(caption_line):
    raw = (
        f':::: {{.merope-video data-provider="youtube" data-video-id="{VALID_ID}"}}\n'
        f'{caption_line}\n::::'
    )
    document = _document([Block(kind=VERBATIM, raw_text=raw)])
    text_cursor = QTextCursor(document)
    text_cursor.setPosition(document.findBlockByNumber(0).position())

    existing = video_block_at_cursor(text_cursor)
    assert existing is not None

    # Mirrors the window.py "edit" flow: width changed, caption field left
    # exactly as prefilled, so caption_source is passed through unchanged.
    replace_video(text_cursor, VALID_ID, width=75, caption_source=existing.caption_source)

    blocks = extract_blocks(document)
    assert len(blocks) == 1
    assert blocks[0].raw_text == (
        f':::: {{.merope-video data-provider="youtube" data-video-id="{VALID_ID}" '
        f'data-width="75"}}\n{caption_line}\n::::'
    )


def test_replace_video_with_an_actually_edited_caption_is_escaped_as_plain_text():
    raw = (
        f':::: {{.merope-video data-provider="youtube" data-video-id="{VALID_ID}"}}\n'
        '*gras*\n::::'
    )
    document = _document([Block(kind=VERBATIM, raw_text=raw)])
    text_cursor = QTextCursor(document)
    text_cursor.setPosition(document.findBlockByNumber(0).position())

    # The caller determined the caption field WAS edited (no caption_source
    # passed): the new text must go through the same plain-text escaping
    # as a fresh insertion, never be interpreted as Markdown.
    replace_video(text_cursor, VALID_ID, "# Nouvelle légende", 75)

    blocks = extract_blocks(document)
    assert len(blocks) == 1
    parsed = parse_video_block(blocks[0].raw_text)
    assert parsed is not None
    assert parsed.caption == "# Nouvelle légende"
    assert parsed.caption_source == "\\# Nouvelle légende"


def test_dialog_caption_changed_is_false_when_untouched_despite_internal_spacing():
    dialog = VideoInsertDialog(
        video_id=VALID_ID, caption="Texte   avec   plusieurs   espaces", width=100
    )
    assert dialog.caption_changed() is False


def test_dialog_caption_changed_is_true_after_editing():
    dialog = VideoInsertDialog(video_id=VALID_ID, caption="Légende.", width=100)
    dialog.caption_edit.setText("Autre légende.")
    assert dialog.caption_changed() is True


def test_dialog_caption_changed_is_true_for_a_fresh_insertion_with_text():
    dialog = VideoInsertDialog()
    dialog.caption_edit.setText("Une légende.")
    assert dialog.caption_changed() is True


# --- P3: a selection must never enable "Modifier la vidéo…" ---------------


def _select(document: QTextDocument, start: int, end: int) -> QTextCursor:
    cursor = QTextCursor(document)
    cursor.setPosition(start)
    cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
    return cursor


def test_video_block_at_cursor_detects_the_first_line_with_a_plain_caret():
    document = _document([_video_block("Légende.")])
    cursor = QTextCursor(document)
    cursor.setPosition(document.findBlockByNumber(0).position())
    assert video_block_at_cursor(cursor) is not None


def test_video_block_at_cursor_detects_the_caption_line_with_a_plain_caret():
    document = _document([_video_block("Légende.")])
    cursor = QTextCursor(document)
    cursor.setPosition(document.findBlockByNumber(1).position())
    assert video_block_at_cursor(cursor) is not None


def test_video_block_at_cursor_detects_the_last_line_with_a_plain_caret():
    document = _document([_video_block("Légende.")])
    cursor = QTextCursor(document)
    cursor.setPosition(document.findBlockByNumber(2).position())
    assert video_block_at_cursor(cursor) is not None


def test_video_block_at_cursor_is_none_for_a_selection_entirely_inside_the_video():
    document = _document([_video_block("Légende.")])
    start = document.findBlockByNumber(0).position()
    end = document.findBlockByNumber(2).position() + 1
    cursor = _select(document, start, end)
    assert video_block_at_cursor(cursor) is None


def test_video_block_at_cursor_is_none_for_a_selection_from_paragraph_into_the_video():
    document = _document([_p("Avant."), _video_block("Légende.")])
    start = document.findBlockByNumber(0).position()
    end = document.findBlockByNumber(2).position() + 1
    cursor = _select(document, start, end)
    assert video_block_at_cursor(cursor) is None


def test_video_block_at_cursor_is_none_for_a_selection_from_the_video_into_a_paragraph():
    document = _document([_video_block("Légende."), _p("Après.")])
    start = document.findBlockByNumber(0).position()
    end = document.findBlockByNumber(3).position() + 1
    cursor = _select(document, start, end)
    assert video_block_at_cursor(cursor) is None


# --- Manually erasing the raw block leaves no grey ghost behind -----------


def _editor(blocks: list[Block]) -> MeropeTextEdit:
    editor = MeropeTextEdit()
    populate_document(editor.document(), blocks)
    return editor


def test_deleting_an_entire_video_block_leaves_no_raw_ghost():
    editor = _editor([_video_block("Légende.")])
    cursor = QTextCursor(editor.document())
    cursor.select(QTextCursor.SelectionType.Document)
    editor.setTextCursor(cursor)

    QTest.keyClick(editor, Qt.Key.Key_Delete)

    assert editor.document().blockCount() == 1
    block = editor.document().begin()
    assert raw_block_identity(block) is None
    assert block.blockFormat().background().style() == Qt.BrushStyle.NoBrush
    assert extract_blocks(editor.document()) == [
        Block(kind=PARAGRAPH, runs=[InlineRun(text="")], alignment="justify")
    ]
    assert video_block_at_cursor(editor.textCursor()) is None

    QTest.keyClicks(editor, "Bonjour")
    assert extract_blocks(editor.document()) == [
        Block(kind=PARAGRAPH, runs=[InlineRun(text="Bonjour")], alignment="justify")
    ]

    editor.undo()  # undoes the typed text
    editor.undo()  # undoes the deletion: the video must come back intact
    assert extract_blocks(editor.document()) == [_video_block("Légende.")]
    assert raw_block_identity(editor.document().begin()) is not None
    assert (
        editor.document().begin().blockFormat().background().style()
        != Qt.BrushStyle.NoBrush
    )
