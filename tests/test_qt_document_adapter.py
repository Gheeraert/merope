from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtGui import QTextCursor, QTextDocument, QTextImageFormat

from bloggen.markdown.rich_text_export import blocks_to_markdown
from bloggen.markdown.rich_text_import import markdown_to_blocks
from bloggen.markdown.rich_text_model import (
    BLOCKQUOTE,
    BULLET_LIST,
    HEADING,
    LIST_ITEM,
    ORDERED_LIST,
    PARAGRAPH,
    TABLE,
    VERBATIM,
    Block,
    InlineRun,
)
from bloggen.ui.qt_editor.document_adapter import (
    UnsupportedBlockError,
    UnsupportedInlineError,
    extract_blocks,
    make_image_format,
    populate_document,
)
from bloggen.ui.qt_editor.constants import (
    BOLD_PROPERTY,
    IMAGE_ALIGN_PROPERTY,
    IMAGE_ALT_PROPERTY,
    IMAGE_HEIGHT_PROPERTY,
    IMAGE_MARKER_PROPERTY,
    IMAGE_SRC_PROPERTY,
    IMAGE_WIDTH_PROPERTY,
)


def _round_trip(blocks: list[Block]) -> list[Block]:
    document = QTextDocument()
    populate_document(document, blocks)
    return extract_blocks(document)


def _first_image_format(document: QTextDocument) -> QTextImageFormat:
    iterator = document.begin().begin()
    while not iterator.atEnd():
        fragment = iterator.fragment()
        if fragment.isValid() and fragment.charFormat().isImageFormat():
            return QTextImageFormat(fragment.charFormat())
        iterator += 1
    raise AssertionError("Aucun fragment image Qt trouvé")


def test_simple_paragraph_roundtrip():
    blocks = [Block(kind=PARAGRAPH, runs=[InlineRun(text="Un paragraphe simple.")])]

    assert _round_trip(blocks) == blocks


def test_empty_canonical_document_roundtrip():
    document = QTextDocument()

    populate_document(document, [])

    assert document.blockCount() == 1
    assert extract_blocks(document) == []


def test_empty_markdown_complete_roundtrip():
    document = QTextDocument()
    blocks = markdown_to_blocks("")

    populate_document(document, blocks)

    assert blocks == []
    assert extract_blocks(document) == []
    assert blocks_to_markdown(extract_blocks(document)) == ""


@pytest.mark.parametrize("level", [1, 2, 3, 4])
def test_heading_levels_roundtrip(level: int):
    blocks = [Block(kind=HEADING, level=level, runs=[InlineRun(text=f"Titre H{level}")])]

    assert _round_trip(blocks) == blocks


def test_inline_formats_and_combinations_roundtrip():
    blocks = [
        Block(
            kind=PARAGRAPH,
            runs=[
                InlineRun(text="normal "),
                InlineRun(text="gras", bold=True),
                InlineRun(text=" et "),
                InlineRun(text="italique", italic=True),
                InlineRun(text=" les deux", bold=True, italic=True),
                InlineRun(text=" barre", strikethrough=True),
                InlineRun(text=" exp", superscript=True),
                InlineRun(text=" gras exp", bold=True, superscript=True),
            ],
        )
    ]

    assert _round_trip(blocks) == blocks


def test_adjacent_runs_with_same_format_are_semantically_merged():
    blocks = [
        Block(
            kind=PARAGRAPH,
            runs=[InlineRun(text="deux ", italic=True), InlineRun(text="fragments", italic=True)],
        )
    ]

    assert _round_trip(blocks) == [
        Block(kind=PARAGRAPH, runs=[InlineRun(text="deux fragments", italic=True)])
    ]


def test_links_keep_their_combined_formatting():
    blocks = [
        Block(
            kind=PARAGRAPH,
            runs=[
                InlineRun(text="italique", italic=True, link_href="https://example.org/i"),
                InlineRun(text=" et "),
                InlineRun(text="gras", bold=True, link_href="https://example.org/b"),
            ],
        )
    ]

    assert _round_trip(blocks) == blocks


def test_heading_and_italic_are_independent():
    blocks = [
        Block(
            kind=HEADING,
            level=2,
            runs=[InlineRun(text="Titre "), InlineRun(text="italique", italic=True)],
        )
    ]

    assert _round_trip(blocks) == blocks


def test_blockquote_roundtrip():
    blocks = [
        Block(kind=BLOCKQUOTE, runs=[InlineRun(text="Une citation.", italic=True)])
    ]

    assert _round_trip(blocks) == blocks


@pytest.mark.parametrize("kind", [BULLET_LIST, ORDERED_LIST])
def test_simple_native_lists_roundtrip(kind: str):
    blocks = [
        Block(
            kind=kind,
            children=[
                Block(kind=LIST_ITEM, runs=[InlineRun(text="premier")]),
                Block(kind=LIST_ITEM, runs=[InlineRun(text="second", bold=True)]),
            ],
        )
    ]
    document = QTextDocument()

    populate_document(document, blocks)

    assert document.begin().textList() is not None
    assert extract_blocks(document) == blocks


@pytest.mark.parametrize("alignment", ["left", "center", "right", "justify"])
def test_paragraph_alignment_roundtrip(alignment: str):
    blocks = [
        Block(kind=PARAGRAPH, runs=[InlineRun(text="Texte aligne.")], alignment=alignment)
    ]

    assert _round_trip(blocks) == blocks


def test_nbsp_survives_fragment_based_extraction_exactly():
    blocks = [
        Block(
            kind=PARAGRAPH,
            runs=[InlineRun(text="«\u00a0Bossuet\u00a0»\u00a0: texte\u00a0!")],
        ),
        Block(kind=PARAGRAPH, runs=[InlineRun(text="p.\u00a012")]),
    ]
    document = QTextDocument()

    populate_document(document, blocks)

    assert document.toPlainText() == "« Bossuet » : texte !\np. 12"
    assert extract_blocks(document) == blocks


def test_complete_block_qt_block_roundtrip():
    blocks = [
        Block(kind=HEADING, level=1, runs=[InlineRun(text="Titre", italic=True)]),
        Block(
            kind=PARAGRAPH,
            runs=[
                InlineRun(text="Du "),
                InlineRun(text="texte", bold=True, italic=True),
                InlineRun(text=" et un lien", link_href="https://example.org"),
                InlineRun(text="."),
            ],
            alignment="justify",
        ),
        Block(kind=BLOCKQUOTE, runs=[InlineRun(text="Citation")], alignment="center"),
        Block(
            kind=BULLET_LIST,
            children=[
                Block(kind=LIST_ITEM, runs=[InlineRun(text="A")]),
                Block(kind=LIST_ITEM, runs=[InlineRun(text="B", strikethrough=True)]),
            ],
        ),
        Block(
            kind=ORDERED_LIST,
            children=[Block(kind=LIST_ITEM, runs=[InlineRun(text="Premier")])],
        ),
    ]

    assert _round_trip(blocks) == blocks


@pytest.mark.parametrize(
    "image",
    [
        InlineRun(image_src="images/a.png", image_alt=""),
        InlineRun(image_src="images/a.png", image_alt="Une légende"),
        InlineRun(image_src="images/a.png", image_alt="**Bossuet** à *Meaux*"),
        InlineRun(image_src="images/a.png", image_width="240"),
        InlineRun(image_src="images/a.png", image_height="180"),
        InlineRun(image_src="images/a.png", image_width="420", image_height="280"),
        InlineRun(image_src="images/a.png", image_align="left"),
        InlineRun(image_src="images/a.png", image_align="center"),
        InlineRun(image_src="images/a.png", image_align="right"),
        InlineRun(image_src="images/a.png", image_align=None),
    ],
)
def test_merope_image_roundtrip_preserves_every_semantic_attribute(image: InlineRun):
    blocks = [Block(kind=PARAGRAPH, runs=[image])]
    document = QTextDocument()

    populate_document(document, blocks)

    image_format = _first_image_format(document)
    assert image_format.isImageFormat()
    assert image_format.name() == image.image_src
    assert image_format.property(IMAGE_MARKER_PROPERTY) is True
    assert image_format.property(IMAGE_SRC_PROPERTY) == image.image_src
    assert extract_blocks(document) == blocks


def test_image_none_and_empty_optional_values_remain_distinct():
    image = InlineRun(
        image_src="images/a.png",
        image_alt="",
        image_width="",
        image_height=None,
        image_align=None,
    )
    document = QTextDocument()

    populate_document(document, [Block(kind=PARAGRAPH, runs=[image])])

    image_format = _first_image_format(document)
    assert image_format.hasProperty(IMAGE_ALT_PROPERTY)
    assert image_format.property(IMAGE_ALT_PROPERTY)
    assert image_format.hasProperty(IMAGE_WIDTH_PROPERTY)
    assert image_format.property(IMAGE_WIDTH_PROPERTY)
    assert not image_format.hasProperty(IMAGE_HEIGHT_PROPERTY)
    assert not image_format.hasProperty(IMAGE_ALIGN_PROPERTY)
    assert extract_blocks(document)[0].runs == [image]


def test_only_positive_integer_dimensions_affect_native_qt_rendering():
    semantic_only = InlineRun(
        image_src="images/a.png",
        image_width="50%",
        image_height="auto",
    )
    pixels = InlineRun(
        image_src="images/b.png",
        image_width="240",
        image_height="180",
    )
    document = QTextDocument()
    blocks = [Block(kind=PARAGRAPH, runs=[semantic_only, pixels])]

    populate_document(document, blocks)

    formats = []
    iterator = document.begin().begin()
    while not iterator.atEnd():
        fragment = iterator.fragment()
        if fragment.isValid() and fragment.charFormat().isImageFormat():
            formats.append(QTextImageFormat(fragment.charFormat()))
        iterator += 1
    assert formats[0].width() == 0
    assert formats[0].height() == 0
    assert formats[1].width() == 240
    assert formats[1].height() == 180
    assert extract_blocks(document) == blocks


def test_image_between_text_runs_roundtrips_without_fragment_loss():
    blocks = [
        Block(
            kind=PARAGRAPH,
            runs=[
                InlineRun(text="Avant ", italic=True),
                InlineRun(image_src="images/a.png", image_alt="Légende"),
                InlineRun(text=" après", bold=True),
            ],
        )
    ]

    assert _round_trip(blocks) == blocks


def test_image_inside_simple_list_item_roundtrips():
    blocks = [
        Block(
            kind=BULLET_LIST,
            children=[
                Block(
                    kind=LIST_ITEM,
                    runs=[
                        InlineRun(text="Voir "),
                        InlineRun(image_src="images/a.png", image_alt="A"),
                    ],
                )
            ],
        )
    ]

    assert _round_trip(blocks) == blocks


def test_markdown_block_qt_block_markdown_roundtrip():
    source_blocks = [
        Block(kind=HEADING, level=2, runs=[InlineRun(text="Titre", italic=True)]),
        Block(
            kind=PARAGRAPH,
            runs=[
                InlineRun(text="«\u00a0Texte\u00a0» et "),
                InlineRun(text="lien", bold=True, link_href="https://example.org"),
                InlineRun(text=" puis "),
                InlineRun(text="exposant", bold=True, superscript=True),
            ],
            alignment="right",
        ),
        Block(kind=BLOCKQUOTE, runs=[InlineRun(text="Citation", italic=True)]),
        Block(
            kind=ORDERED_LIST,
            children=[
                Block(kind=LIST_ITEM, runs=[InlineRun(text="un")]),
                Block(kind=LIST_ITEM, runs=[InlineRun(text="deux", bold=True)]),
            ],
        ),
    ]
    markdown = blocks_to_markdown(source_blocks)
    imported_blocks = markdown_to_blocks(markdown)
    document = QTextDocument()

    populate_document(document, imported_blocks)
    rebuilt_markdown = blocks_to_markdown(extract_blocks(document))

    assert rebuilt_markdown == markdown


@pytest.mark.parametrize(
    "unsupported",
    [
        Block(kind=TABLE),
        Block(kind=VERBATIM, raw_text="<section>brut</section>"),
    ],
)
def test_unsupported_block_is_never_silently_lost(unsupported: Block):
    document = QTextDocument()
    original = [Block(kind=PARAGRAPH, runs=[InlineRun(text="Document intact")])]
    populate_document(document, original)

    with pytest.raises(UnsupportedBlockError, match="non pris en charge"):
        populate_document(document, [unsupported])

    assert extract_blocks(document) == original


@pytest.mark.parametrize(
    "run",
    [InlineRun(footnote_ref="1")],
)
def test_unsupported_inline_leaf_is_never_silently_lost(run: InlineRun):
    document = QTextDocument()

    with pytest.raises(UnsupportedInlineError):
        populate_document(document, [Block(kind=PARAGRAPH, runs=[run])])


@pytest.mark.parametrize(
    "run",
    [
        InlineRun(image_src=""),
        InlineRun(image_alt="sans source"),
        InlineRun(image_src="a.png", image_width=240),
        InlineRun(image_src="a.png", image_height=180),
        InlineRun(image_src="a.png", image_align="justify"),
        InlineRun(image_src="a.png", text="texte"),
        InlineRun(image_src="a.png", footnote_ref="1"),
        InlineRun(image_src="a.png", bold=True),
        InlineRun(image_src="a.png", link_href="https://example.org"),
    ],
)
def test_invalid_image_model_is_explicitly_rejected(run: InlineRun):
    document = QTextDocument()

    with pytest.raises(UnsupportedInlineError):
        populate_document(document, [Block(kind=PARAGRAPH, runs=[run])])


def test_empty_list_is_explicitly_rejected():
    document = QTextDocument()

    with pytest.raises(UnsupportedBlockError, match="listes vides"):
        populate_document(document, [Block(kind=BULLET_LIST)])


def test_qt_table_is_not_flattened_during_extraction():
    document = QTextDocument()
    cursor = QTextCursor(document)
    cursor.insertTable(1, 1)

    with pytest.raises(UnsupportedBlockError, match="tableaux"):
        extract_blocks(document)


def test_foreign_qt_image_without_merope_metadata_is_rejected():
    document = QTextDocument()
    cursor = QTextCursor(document)
    cursor.insertImage("missing-development-image.png")

    with pytest.raises(UnsupportedInlineError, match="etrangere"):
        extract_blocks(document)


def test_merope_image_with_incompatible_qt_text_format_is_rejected():
    document = QTextDocument()
    cursor = QTextCursor(document)
    image_format = make_image_format(InlineRun(image_src="image.png"))
    image_format.setProperty(BOLD_PROPERTY, True)
    cursor.insertImage(image_format)

    with pytest.raises(UnsupportedInlineError, match="format de texte incompatible"):
        extract_blocks(document)
