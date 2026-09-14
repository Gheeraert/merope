from __future__ import annotations

import pytest

from bloggen.markdown.rich_text_export import blocks_to_markdown
from bloggen.markdown.rich_text_import import markdown_to_blocks
from bloggen.markdown.rich_text_model import (
    BLOCKQUOTE,
    BULLET_LIST,
    FOOTNOTE_DEFINITION,
    HEADING,
    ORDERED_LIST,
    PARAGRAPH,
    VERBATIM,
    Block,
)


@pytest.mark.parametrize(
    ("source", "expected_markdown"),
    [
        ("Bonjour \n", "Bonjour\n"),
        ("Bonjour  \n", "Bonjour\n"),
        ("Bonjour   \n", "Bonjour\n"),
        ("Bonjour le monde  \n", "Bonjour le monde\n"),
        ("{{align=justify}}Bonjour le monde  \n", "{{align=justify}}Bonjour le monde\n"),
        ("**Bonjour**  \n", "**Bonjour**\n"),
        ("*Bonjour*  \n", "*Bonjour*\n"),
        ("[Bonjour](https://example.org)  \n", "[Bonjour](https://example.org)\n"),
    ],
)
def test_terminal_spaces_do_not_turn_supported_paragraphs_into_verbatim(
    source, expected_markdown
):
    blocks = markdown_to_blocks(source)

    assert len(blocks) == 1
    assert blocks[0].kind == PARAGRAPH
    assert blocks_to_markdown(blocks) == expected_markdown


def test_terminal_spaces_before_a_blank_line_are_canonicalized():
    source = "Premier paragraphe  \n\nDeuxième paragraphe\n"

    blocks = markdown_to_blocks(source)

    assert [block.kind for block in blocks] == [PARAGRAPH, PARAGRAPH]
    assert blocks_to_markdown(blocks) == "Premier paragraphe\n\nDeuxième paragraphe\n"


@pytest.mark.parametrize("terminal", ["\t", "\u00a0"])
def test_terminal_canonicalization_does_not_remove_tabs_or_nbsp(terminal):
    source = f"Bonjour{terminal}\n"

    blocks = markdown_to_blocks(source)

    assert len(blocks) == 1
    assert blocks[0].kind == PARAGRAPH
    assert blocks[0].runs[0].text == f"Bonjour{terminal}"
    assert blocks_to_markdown(blocks) == source


@pytest.mark.parametrize(
    ("source", "kind", "expected_markdown"),
    [
        ("# Titre  \n", HEADING, "# Titre\n"),
        ("> Citation  \n", BLOCKQUOTE, "> Citation\n"),
        ("- élément  \n", BULLET_LIST, "- élément\n"),
        ("1. élément  \n", ORDERED_LIST, "1. élément\n"),
        ("[^1]: note  \n", FOOTNOTE_DEFINITION, "[^1]: note\n"),
    ],
)
def test_terminal_spaces_are_canonicalized_for_supported_structures(
    source, kind, expected_markdown
):
    blocks = markdown_to_blocks(source)

    assert len(blocks) == 1
    assert blocks[0].kind == kind
    assert blocks_to_markdown(blocks) == expected_markdown


@pytest.mark.parametrize(
    ("source", "width", "alignment", "expected_markdown"),
    [
        ("![x](img.jpg)  \n", None, None, "![x](img.jpg)\n"),
        (
            "![x](img.jpg){width=25%}  \n",
            "25%",
            None,
            "![x](img.jpg){width=25%}\n",
        ),
        (
            "![x](img.jpg){align=center}  \n",
            None,
            "center",
            "![x](img.jpg){align=center}\n",
        ),
        (
            "![x](img.jpg){width=25% align=center}  \n",
            "25%",
            "center",
            "![x](img.jpg){width=25% align=center}\n",
        ),
    ],
)
def test_modern_figures_ignore_only_useless_terminal_spaces(
    source, width, alignment, expected_markdown
):
    blocks = markdown_to_blocks(source)

    assert len(blocks) == 1
    assert blocks[0].kind == PARAGRAPH
    image = blocks[0].runs[0]
    assert image.image_width == width
    assert image.image_align == alignment
    assert blocks_to_markdown(blocks) == expected_markdown


@pytest.mark.parametrize(
    ("alignment", "width"),
    [
        ("left", "18"),
        ("center", "25%"),
        ("right", "38%"),
    ],
)
def test_legacy_figures_with_terminal_spaces_migrate_to_image_alignment(
    alignment, width
):
    source = f"{{{{align={alignment}}}}}![x](img.jpg){{width={width}}}  \n"

    blocks = markdown_to_blocks(source)

    assert len(blocks) == 1
    assert blocks[0].kind == PARAGRAPH
    assert blocks[0].alignment == "left"
    image = blocks[0].runs[0]
    assert image.image_width == width
    assert image.image_align == alignment
    assert blocks_to_markdown(blocks) == (
        f"![x](img.jpg){{width={width} align={alignment}}}\n"
    )


@pytest.mark.parametrize(
    "source",
    [
        "Première ligne  \nseconde ligne\n",
        "Première ligne  \nseconde ligne  \n",
    ],
)
def test_internal_hard_break_remains_exact_verbatim(source):
    blocks = markdown_to_blocks(source)

    assert blocks == [Block(kind=VERBATIM, raw_text=source.rstrip("\n"))]
    assert blocks_to_markdown(blocks) == source


@pytest.mark.parametrize(
    "source",
    [
        "{{align=justify}}![x](img.jpg){width=25%}  \n",
        "{{align=center}}![x](img.jpg){align=right}  \n",
        "[élément][ref]  \n",
        "[élément][ref]\t\n",
        "[élément][ref]\u00a0\n",
    ],
)
def test_unsupported_chunks_keep_original_terminal_whitespace(source):
    blocks = markdown_to_blocks(source)

    assert blocks == [Block(kind=VERBATIM, raw_text=source.rstrip("\n"))]
    assert blocks_to_markdown(blocks) == source


def test_real_legacy_figure_corpus_is_imported_without_verbatim():
    source = (
        "{{align=center}}![Page de titre de l'édition originale]"
        "(../../assets/images/collage-5ef64351.jpg){width=25%}  \n\n"
        "{{align=center}}![Ann Hughes, \\*The Causes of the English Civil War\\*, "
        "seconde édition, Palgrave McMillan, 1998.]"
        "(../../assets/images/collage-51bbf9a6.jpg){width=18%}  \n\n"
        "{{align=center}}![Reuben Bussey (1818-1893), \\*Charles I Raising His "
        "Standard at Nottingham Castle\\*. University of Nottingham]"
        "(../../assets/images/collage-e23570e0.jpg){width=38%}  \n"
    )

    blocks = markdown_to_blocks(source)

    assert len(blocks) == 3
    assert all(block.kind == PARAGRAPH for block in blocks)
    assert all(block.alignment == "left" for block in blocks)
    assert [block.runs[0].image_align for block in blocks] == ["center"] * 3
    assert [block.runs[0].image_width for block in blocks] == ["25%", "18%", "38%"]
    assert [block.runs[0].image_alt for block in blocks] == [
        "Page de titre de l'édition originale",
        (
            "Ann Hughes, *The Causes of the English Civil War*, seconde édition, "
            "Palgrave McMillan, 1998."
        ),
        (
            "Reuben Bussey (1818-1893), *Charles I Raising His Standard at "
            "Nottingham Castle*. University of Nottingham"
        ),
    ]
    assert "{{align=" not in blocks_to_markdown(blocks)
    assert not any(line.endswith("  ") for line in blocks_to_markdown(blocks).splitlines())
