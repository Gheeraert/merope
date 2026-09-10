from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtGui import QFont, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import QApplication, QTextEdit

from bloggen.markdown.rich_text_model import (
    BLOCKQUOTE,
    BULLET_LIST,
    HEADING,
    LIST_ITEM,
    ORDERED_LIST,
    PARAGRAPH,
    Block,
    InlineRun,
)
from bloggen.ui.qt_editor.constants import (
    BODY_POINT_SIZE,
    HEADING_LEVEL_PROPERTY,
)
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
    toggle_strikethrough,
    toggle_superscript,
)


@pytest.fixture(scope="module", autouse=True)
def qapplication():
    app = QApplication.instance() or QApplication([])
    yield app


def _editor(blocks: list[Block]) -> QTextEdit:
    editor = QTextEdit()
    populate_document(editor.document(), blocks)
    editor.document().setModified(False)
    return editor


def _select_document(editor: QTextEdit) -> None:
    cursor = editor.textCursor()
    cursor.select(QTextCursor.SelectionType.Document)
    editor.setTextCursor(cursor)


def _select_block(editor: QTextEdit, index: int) -> None:
    block = editor.document().begin()
    for _ in range(index):
        block = block.next()
    cursor = QTextCursor(block)
    cursor.movePosition(
        QTextCursor.MoveOperation.EndOfBlock,
        QTextCursor.MoveMode.KeepAnchor,
    )
    editor.setTextCursor(cursor)


def _assert_no_heading_residue(editor: QTextEdit, block_index: int = 0) -> None:
    block = editor.document().begin()
    for _ in range(block_index):
        block = block.next()
    block_format = block.blockFormat()
    assert not block_format.hasProperty(HEADING_LEVEL_PROPERTY)
    assert block_format.headingLevel() == 0
    assert block.begin().fragment().charFormat().fontPointSize() == BODY_POINT_SIZE


def test_paragraph_heading_paragraph_clears_heading_state():
    editor = _editor([Block(kind=PARAGRAPH, runs=[InlineRun(text="Texte")])])

    set_heading(editor, 2)
    assert extract_blocks(editor.document())[0].kind == HEADING
    set_paragraph(editor)

    assert extract_blocks(editor.document()) == [
        Block(kind=PARAGRAPH, runs=[InlineRun(text="Texte")])
    ]
    _assert_no_heading_residue(editor)


def test_heading_to_blockquote_cleans_heading_and_sets_quote_margin():
    editor = _editor([Block(kind=HEADING, level=3, runs=[InlineRun(text="Titre")])])

    set_blockquote(editor)

    assert extract_blocks(editor.document()) == [
        Block(kind=BLOCKQUOTE, runs=[InlineRun(text="Titre")])
    ]
    _assert_no_heading_residue(editor)
    assert editor.document().begin().blockFormat().leftMargin() > 0


@pytest.mark.parametrize("list_kind", [BULLET_LIST, ORDERED_LIST])
def test_heading_to_list_cleans_all_heading_state(list_kind: str):
    editor = _editor([Block(kind=HEADING, level=1, runs=[InlineRun(text="Titre")])])

    set_list(editor, list_kind)

    assert extract_blocks(editor.document()) == [
        Block(
            kind=list_kind,
            children=[Block(kind=LIST_ITEM, runs=[InlineRun(text="Titre")])],
        )
    ]
    _assert_no_heading_residue(editor)
    assert editor.document().begin().blockFormat().leftMargin() == 0


def test_blockquote_to_heading_clears_quote_margin():
    editor = _editor([Block(kind=BLOCKQUOTE, runs=[InlineRun(text="Citation")])])

    set_heading(editor, 2)

    assert extract_blocks(editor.document()) == [
        Block(kind=HEADING, level=2, runs=[InlineRun(text="Citation")])
    ]
    assert editor.document().begin().blockFormat().leftMargin() == 0


@pytest.mark.parametrize("target", [PARAGRAPH, HEADING])
def test_list_item_to_leaf_block_removes_list_semantics(target: str):
    editor = _editor(
        [
            Block(
                kind=BULLET_LIST,
                children=[Block(kind=LIST_ITEM, runs=[InlineRun(text="Element")])],
            )
        ]
    )

    if target == PARAGRAPH:
        set_paragraph(editor)
        expected = Block(kind=PARAGRAPH, runs=[InlineRun(text="Element")])
    else:
        set_heading(editor, 3)
        expected = Block(kind=HEADING, level=3, runs=[InlineRun(text="Element")])

    assert editor.document().begin().textList() is None
    assert extract_blocks(editor.document()) == [expected]


@pytest.mark.parametrize(
    ("source", "target"),
    [(BULLET_LIST, ORDERED_LIST), (ORDERED_LIST, BULLET_LIST)],
)
def test_switching_list_kind_replaces_old_list_semantics(source: str, target: str):
    editor = _editor(
        [
            Block(
                kind=source,
                children=[
                    Block(kind=LIST_ITEM, runs=[InlineRun(text="Un")]),
                    Block(kind=LIST_ITEM, runs=[InlineRun(text="Deux")]),
                ],
            )
        ]
    )
    _select_document(editor)

    set_list(editor, target)

    assert extract_blocks(editor.document()) == [
        Block(
            kind=target,
            children=[
                Block(kind=LIST_ITEM, runs=[InlineRun(text="Un")]),
                Block(kind=LIST_ITEM, runs=[InlineRun(text="Deux")]),
            ],
        )
    ]


@pytest.mark.parametrize(
    ("toggle", "field"),
    [
        (toggle_bold, "bold"),
        (toggle_italic, "italic"),
        (toggle_strikethrough, "strikethrough"),
        (toggle_superscript, "superscript"),
    ],
)
def test_mixed_inline_selection_is_applied_then_removed_everywhere(toggle, field: str):
    editor = _editor(
        [
            Block(
                kind=PARAGRAPH,
                runs=[
                    InlineRun(text="deja", **{field: True}),
                    InlineRun(text=" mixte"),
                ],
            )
        ]
    )
    _select_document(editor)

    toggle(editor)
    runs = extract_blocks(editor.document())[0].runs
    assert len(runs) == 1
    assert getattr(runs[0], field) is True

    toggle(editor)
    runs = extract_blocks(editor.document())[0].runs
    assert len(runs) == 1
    assert getattr(runs[0], field) is False

    editor.undo()
    assert getattr(extract_blocks(editor.document())[0].runs[0], field) is True


def test_mixed_selection_falls_back_to_native_qt_format_when_property_is_absent():
    editor = QTextEdit()
    cursor = QTextCursor(editor.document())
    native_bold = QTextCharFormat()
    native_bold.setFontWeight(QFont.Weight.Bold.value)
    cursor.insertText("natif", native_bold)
    cursor.insertText(" mixte", QTextCharFormat())
    _select_document(editor)

    toggle_bold(editor)

    assert extract_blocks(editor.document()) == [
        Block(kind=PARAGRAPH, runs=[InlineRun(text="natif mixte", bold=True)])
    ]


def test_inline_format_across_two_paragraphs():
    editor = _editor(
        [
            Block(kind=PARAGRAPH, runs=[InlineRun(text="Un")]),
            Block(kind=PARAGRAPH, runs=[InlineRun(text="Deux")]),
        ]
    )
    _select_document(editor)

    toggle_italic(editor)

    assert all(block.runs[0].italic for block in extract_blocks(editor.document()))


def test_inline_format_across_paragraph_and_heading_preserves_block_types():
    editor = _editor(
        [
            Block(kind=PARAGRAPH, runs=[InlineRun(text="Corps")]),
            Block(kind=HEADING, level=2, runs=[InlineRun(text="Titre")]),
        ]
    )
    _select_document(editor)

    toggle_bold(editor)

    blocks = extract_blocks(editor.document())
    assert [block.kind for block in blocks] == [PARAGRAPH, HEADING]
    assert blocks[1].level == 2
    assert all(block.runs[0].bold for block in blocks)


def test_inline_format_across_several_list_items():
    editor = _editor(
        [
            Block(
                kind=ORDERED_LIST,
                children=[
                    Block(kind=LIST_ITEM, runs=[InlineRun(text="Un")]),
                    Block(kind=LIST_ITEM, runs=[InlineRun(text="Deux")]),
                ],
            )
        ]
    )
    _select_document(editor)

    toggle_strikethrough(editor)

    items = extract_blocks(editor.document())[0].children
    assert all(item.runs[0].strikethrough for item in items)


def test_inline_format_across_paragraph_and_list_is_safe():
    editor = _editor(
        [
            Block(kind=PARAGRAPH, runs=[InlineRun(text="Avant")]),
            Block(
                kind=BULLET_LIST,
                children=[Block(kind=LIST_ITEM, runs=[InlineRun(text="Element")])],
            ),
        ]
    )
    _select_document(editor)

    toggle_superscript(editor)

    blocks = extract_blocks(editor.document())
    assert blocks[0].runs[0].superscript
    assert blocks[1].children[0].runs[0].superscript


def test_alignment_across_paragraph_and_list_is_refused_without_changes():
    original = [
        Block(kind=PARAGRAPH, runs=[InlineRun(text="Avant")]),
        Block(
            kind=BULLET_LIST,
            children=[Block(kind=LIST_ITEM, runs=[InlineRun(text="Element")])],
        ),
    ]
    editor = _editor(original)
    _select_document(editor)

    with pytest.raises(ValueError, match="liste"):
        set_alignment(editor, "center")

    assert extract_blocks(editor.document()) == original


def test_two_paragraphs_can_become_headings_in_one_operation():
    editor = _editor(
        [
            Block(kind=PARAGRAPH, runs=[InlineRun(text="Un")]),
            Block(kind=PARAGRAPH, runs=[InlineRun(text="Deux")]),
        ]
    )
    _select_document(editor)

    set_heading(editor, 3)

    assert extract_blocks(editor.document()) == [
        Block(kind=HEADING, level=3, runs=[InlineRun(text="Un")]),
        Block(kind=HEADING, level=3, runs=[InlineRun(text="Deux")]),
    ]


@pytest.mark.parametrize(
    ("command", "field"),
    [
        (toggle_bold, "bold"),
        (toggle_superscript, "superscript"),
    ],
)
def test_inline_format_across_image_only_changes_text(command, field: str):
    image = InlineRun(
        image_src="image.png",
        image_alt="Légende",
        image_width="240",
        image_align="center",
    )
    original = [
        Block(
            kind=PARAGRAPH,
            runs=[InlineRun(text="Avant "), image, InlineRun(text=" après")],
        )
    ]
    editor = _editor(original)
    _select_document(editor)

    command(editor)

    runs = extract_blocks(editor.document())[0].runs
    assert getattr(runs[0], field) is True
    assert runs[1] == image
    assert getattr(runs[2], field) is True
    editor.undo()
    assert extract_blocks(editor.document()) == original


def test_link_across_image_only_changes_text_and_undoes_once():
    image = InlineRun(image_src="image.png", image_alt="Légende")
    original = [
        Block(
            kind=PARAGRAPH,
            runs=[InlineRun(text="Avant "), image, InlineRun(text=" après")],
        )
    ]
    editor = _editor(original)
    _select_document(editor)

    set_link(editor, "https://example.org")

    runs = extract_blocks(editor.document())[0].runs
    assert runs[0].link_href == "https://example.org"
    assert runs[1] == image
    assert runs[2].link_href == "https://example.org"
    editor.undo()
    assert extract_blocks(editor.document()) == original


@pytest.mark.parametrize("command", [toggle_bold, toggle_italic, set_link])
def test_text_format_on_image_only_is_clean_noop(command):
    original = [
        Block(
            kind=PARAGRAPH,
            runs=[InlineRun(image_src="image.png", image_alt="Légende")],
        )
    ]
    editor = _editor(original)
    cursor = QTextCursor(editor.document())
    cursor.setPosition(0)
    cursor.setPosition(1, QTextCursor.MoveMode.KeepAnchor)
    editor.setTextCursor(cursor)

    if command is set_link:
        command(editor, "https://example.org")
    else:
        command(editor)

    assert extract_blocks(editor.document()) == original
    assert editor.document().isModified() is False
    assert editor.document().isUndoAvailable() is False
