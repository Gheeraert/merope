"""Embedded video in the Qt editor: structural insertion, boundary guards,
dialog URL validation, and round trip through the document adapter."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtGui import QTextCursor, QTextDocument
from PySide6.QtWidgets import QApplication

from bloggen.markdown.rich_text_model import PARAGRAPH, VERBATIM, Block, InlineRun
from bloggen.markdown.video_syntax import ParsedVideoBlock, format_video_block
from bloggen.ui.qt_editor.box_structure import can_insert_box, insert_empty_box
from bloggen.ui.qt_editor.document_adapter import (
    UnsupportedDocumentError,
    extract_blocks,
    populate_document,
)
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
        provider="youtube", video_id=VALID_ID, caption="Légende.", width=100
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
