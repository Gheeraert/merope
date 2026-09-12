from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtGui import QTextCursor, QTextDocument
from PySide6.QtWidgets import QApplication, QTextEdit

from bloggen.content.writer import write_content_file
from bloggen.markdown.rich_text_export import blocks_to_markdown
from bloggen.markdown.rich_text_model import HEADING, PARAGRAPH, Block, InlineRun
from bloggen.ui.qt_editor.constants import HEADING_MARGINS, IMAGE_BLOCK_MARGINS
from bloggen.ui.qt_editor.document_adapter import (
    block_is_image_only,
    extract_blocks,
    insert_blocks,
    populate_document,
)
from bloggen.ui.qt_editor.file_io import load_content_document, save_content_document
from bloggen.ui.qt_editor.formatting import set_heading, set_paragraph
from bloggen.ui.qt_editor.image_selection import (
    replace_merope_image,
    targeted_merope_image,
)


@pytest.fixture(scope="module", autouse=True)
def qapplication():
    app = QApplication.instance() or QApplication([])
    yield app


def _blocks(document: QTextDocument):
    block = document.begin()
    while block.isValid():
        yield block
        block = block.next()


def _margins(block) -> tuple[float, float]:
    block_format = block.blockFormat()
    return block_format.topMargin(), block_format.bottomMargin()


def test_heading_margins_are_hierarchical_and_semantically_neutral():
    original = []
    for level in range(1, 5):
        original.extend(
            [
                Block(kind=PARAGRAPH, runs=[InlineRun(text=f"Avant H{level}")]),
                Block(kind=HEADING, level=level, runs=[InlineRun(text=f"Titre {level}")]),
            ]
        )
    original.append(Block(kind=PARAGRAPH, runs=[InlineRun(text="Après")]))
    document = QTextDocument()

    populate_document(document, original)

    qt_blocks = list(_blocks(document))
    heading_margins = [_margins(qt_blocks[index]) for index in (1, 3, 5, 7)]
    assert heading_margins == [HEADING_MARGINS[level] for level in range(1, 5)]
    assert all(
        heading_margins[index][0] > heading_margins[index + 1][0]
        for index in range(3)
    )
    assert all(
        heading_margins[index][1] >= heading_margins[index + 1][1]
        for index in range(3)
    )
    assert all(_margins(qt_blocks[index]) == (0.0, 0.0) for index in (0, 2, 4, 6, 8))
    assert extract_blocks(document) == original
    assert document.isModified() is False
    assert document.isUndoAvailable() is False


def test_heading_conversions_replace_margins_and_undo_redo_together():
    editor = QTextEdit()
    populate_document(
        editor.document(),
        [Block(kind=PARAGRAPH, runs=[InlineRun(text="Titre")])],
    )

    set_heading(editor, 1)
    assert _margins(editor.document().begin()) == HEADING_MARGINS[1]
    assert extract_blocks(editor.document())[0].level == 1

    set_paragraph(editor)
    assert _margins(editor.document().begin()) == (0.0, 0.0)
    assert extract_blocks(editor.document())[0].kind == PARAGRAPH

    set_heading(editor, 1)
    set_heading(editor, 3)
    assert _margins(editor.document().begin()) == HEADING_MARGINS[3]
    assert extract_blocks(editor.document())[0].level == 3

    set_heading(editor, 2)
    assert _margins(editor.document().begin()) == HEADING_MARGINS[2]
    editor.document().undo()
    assert _margins(editor.document().begin()) == HEADING_MARGINS[3]
    assert extract_blocks(editor.document())[0].level == 3
    editor.document().redo()
    assert _margins(editor.document().begin()) == HEADING_MARGINS[2]
    assert extract_blocks(editor.document())[0].level == 2


def test_only_standalone_merope_image_paragraph_gets_image_margins():
    image = InlineRun(image_src="missing.png", image_alt="Image")
    original = [
        Block(kind=PARAGRAPH, runs=[InlineRun(text="Avant")]),
        Block(kind=PARAGRAPH, runs=[InlineRun(text="  "), image]),
        Block(
            kind=PARAGRAPH,
            runs=[InlineRun(text="A"), image, InlineRun(text="B")],
        ),
        Block(kind=PARAGRAPH, runs=[InlineRun(text="Après")]),
    ]
    document = QTextDocument()

    populate_document(document, original)

    qt_blocks = list(_blocks(document))
    assert block_is_image_only(qt_blocks[1])
    assert _margins(qt_blocks[1]) == IMAGE_BLOCK_MARGINS
    assert not block_is_image_only(qt_blocks[2])
    assert _margins(qt_blocks[2]) == (0.0, 0.0)
    assert extract_blocks(document) == original


def test_image_insertion_margins_share_the_single_document_undo():
    document = QTextDocument()
    populate_document(document, [])
    image_blocks = [
        Block(
            kind=PARAGRAPH,
            runs=[InlineRun(image_src="missing.png", image_alt="Image")],
        )
    ]

    insert_blocks(QTextCursor(document), image_blocks)

    assert _margins(document.begin()) == IMAGE_BLOCK_MARGINS
    assert extract_blocks(document) == image_blocks
    document.undo()
    assert _margins(document.begin()) == (0.0, 0.0)
    assert document.isUndoAvailable() is False
    document.redo()
    assert _margins(document.begin()) == IMAGE_BLOCK_MARGINS
    assert extract_blocks(document) == image_blocks


def test_replacing_standalone_image_preserves_block_spacing():
    document = QTextDocument()
    original = InlineRun(image_src="old.png", image_alt="Ancienne")
    populate_document(document, [Block(kind=PARAGRAPH, runs=[original])])
    cursor = QTextCursor(document)
    cursor.setPosition(0)
    cursor.setPosition(1, QTextCursor.MoveMode.KeepAnchor)
    target = targeted_merope_image(cursor)
    assert target is not None

    replace_merope_image(
        document,
        target,
        InlineRun(image_src="new.png", image_alt="Ancienne"),
        allow_source_change=True,
    )

    assert _margins(document.begin()) == IMAGE_BLOCK_MARGINS
    assert block_is_image_only(document.begin())


def test_save_reopen_restores_visual_spacing_without_changing_markdown(tmp_path):
    image = InlineRun(image_src="missing.png", image_alt="Image")
    original = [
        Block(kind=HEADING, level=1, runs=[InlineRun(text="Titre")]),
        Block(kind=HEADING, level=2, runs=[InlineRun(text="Sous-titre")]),
        Block(kind=PARAGRAPH, runs=[image]),
        Block(kind=PARAGRAPH, runs=[InlineRun(text="Texte")]),
    ]
    expected_markdown = blocks_to_markdown(original)
    path = write_content_file(
        tmp_path,
        "espacement.md",
        {"title": "Espacement"},
        expected_markdown,
    )
    source_bytes = path.read_bytes()
    document = QTextDocument()

    loaded = load_content_document(path, document)
    assert extract_blocks(document) == original
    assert [_margins(block) for block in _blocks(document)] == [
        HEADING_MARGINS[1],
        HEADING_MARGINS[2],
        IMAGE_BLOCK_MARGINS,
        (0.0, 0.0),
    ]
    assert document.isModified() is False
    assert document.isUndoAvailable() is False

    save_content_document(path, loaded.metadata, document)
    assert path.read_bytes() == source_bytes
    assert blocks_to_markdown(extract_blocks(document)) == expected_markdown

    reopened = QTextDocument()
    load_content_document(path, reopened)
    assert extract_blocks(reopened) == original
    assert [_margins(block) for block in _blocks(reopened)] == [
        HEADING_MARGINS[1],
        HEADING_MARGINS[2],
        IMAGE_BLOCK_MARGINS,
        (0.0, 0.0),
    ]
    assert reopened.isModified() is False
    assert reopened.isUndoAvailable() is False
