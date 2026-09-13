"""Losslessness contracts for Merope's deliberately small Markdown importer."""

from __future__ import annotations

import pytest

from bloggen.markdown.rich_text_export import blocks_to_markdown
from bloggen.markdown.rich_text_import import markdown_to_blocks
from bloggen.markdown.rich_text_model import (
    BLOCKQUOTE,
    BULLET_LIST,
    FOOTNOTE_DEFINITION,
    HEADING,
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


@pytest.mark.parametrize(
    "source",
    [
        "```python\nx = 1\ny = 2\n```\n",
        "~~~text\nligne 1\nligne 2\n~~~\n",
        "```\nligne 1\n\nligne 2\n```\n",
        "```python\nx = 1\n\ny = 2\n",
        "    ligne 1\n    ligne 2\n",
        "ligne 1  \nligne 2\n",
        "ligne 1\\\nligne 2\n",
        "Titre\n=====\n",
        "Titre\n-----\n",
        "---\n",
        "* * *\n",
        "_ _ _\n",
        "[^1]: Première ligne.\n    Deuxième ligne.\n",
        "[^1]: Premier paragraphe.\n\n    Deuxième paragraphe.\n",
    ],
)
def test_non_representable_markdown_is_preserved_as_one_verbatim_block(source):
    expected_raw = source.removesuffix("\n")

    blocks = markdown_to_blocks(source)

    assert blocks == [Block(kind=VERBATIM, raw_text=expected_raw)]
    assert blocks_to_markdown(blocks) == source


def test_unclosed_fence_preserves_everything_that_follows():
    source = "Avant.\n\n```python\nx = 1\n\nAprès encore dans la fence.\n"

    blocks = markdown_to_blocks(source)

    assert blocks == [
        Block(kind=PARAGRAPH, runs=[InlineRun(text="Avant.")]),
        Block(
            kind=VERBATIM,
            raw_text="```python\nx = 1\n\nAprès encore dans la fence.",
        ),
    ]
    assert blocks_to_markdown(blocks) == source


def test_ordinary_soft_wrapped_paragraph_remains_supported():
    assert markdown_to_blocks("Un paragraphe\nsimplement replié.\n") == [
        Block(
            kind=PARAGRAPH,
            runs=[InlineRun(text="Un paragraphe simplement replié.")],
        )
    ]


def test_existing_structured_multiline_forms_remain_supported():
    source = (
        "# Titre\n\n"
        "> Citation\n> sur deux lignes\n\n"
        "- un\n- deux\n\n"
        "1. premier\n2. second\n\n"
        "| A | B |\n| --- | --- |\n| C | D |\n"
    )

    assert [block.kind for block in markdown_to_blocks(source)] == [
        HEADING,
        BLOCKQUOTE,
        BULLET_LIST,
        ORDERED_LIST,
        TABLE,
    ]


def test_noncanonical_ordered_list_numbering_is_preserved_verbatim():
    source = "3. troisième\n4. quatrième\n"

    assert markdown_to_blocks(source) == [
        Block(kind=VERBATIM, raw_text=source.removesuffix("\n"))
    ]
    assert blocks_to_markdown(markdown_to_blocks(source)) == source


def test_blockquote_with_hard_break_is_not_flattened():
    source = "> ligne 1  \n> ligne 2\n"

    assert markdown_to_blocks(source) == [
        Block(kind=VERBATIM, raw_text=source.removesuffix("\n"))
    ]
    assert blocks_to_markdown(markdown_to_blocks(source)) == source


def test_unknown_image_attributes_are_preserved_as_literal_suffix():
    source = "![Alt](image.png){width=300 custom=value}\n"

    blocks = markdown_to_blocks(source)

    assert blocks == [
        Block(
            kind=PARAGRAPH,
            runs=[
                InlineRun(image_src="image.png", image_alt="Alt"),
                InlineRun(text="{width=300 custom=value}"),
            ],
        )
    ]
    assert blocks_to_markdown(blocks) == source


@pytest.mark.parametrize(
    "source",
    [
        "| A | B |\n| :--- | ---: |\n| C | D |\n",
        "Voir [la référence][ref].\n\n[ref]: https://example.org\n",
        "Un [span]{#identifiant} Pandoc.\n",
    ],
)
def test_valid_but_unsupported_markdown_is_not_guessed_or_flattened(source):
    blocks = markdown_to_blocks(source)

    assert all(block.kind == VERBATIM for block in blocks)
    assert blocks_to_markdown(blocks) == source


@pytest.mark.parametrize(
    "inline",
    ["[élément][ref]", "[élément]{.classe}"],
)
@pytest.mark.parametrize(
    "container",
    [
        lambda value: value,
        lambda value: f"# {value}",
        lambda value: f"> {value}",
        lambda value: f"- {value}",
        lambda value: f"1. {value}",
        lambda value: f"[^1]: {value}",
        lambda value: f"| {value} |\n| ------------------------------ |",
    ],
    ids=[
        "paragraph",
        "heading",
        "blockquote",
        "bullet-list",
        "ordered-list",
        "footnote-definition",
        "table-cell",
    ],
)
def test_unsupported_inline_syntax_makes_the_whole_container_verbatim(
    inline,
    container,
):
    source = container(inline) + "\n"
    if inline == "[élément][ref]":
        source += "\n[ref]: https://example.org\n"

    blocks = markdown_to_blocks(source)

    assert all(block.kind == VERBATIM for block in blocks)
    assert blocks_to_markdown(blocks) == source


def test_reference_link_in_heading_and_definition_are_both_preserved():
    source = "# [Titre][ref]\n\n[ref]: https://example.org\n"

    assert markdown_to_blocks(source) == [
        Block(kind=VERBATIM, raw_text="# [Titre][ref]"),
        Block(kind=VERBATIM, raw_text="[ref]: https://example.org"),
    ]
    assert blocks_to_markdown(markdown_to_blocks(source)) == source


@pytest.mark.parametrize(
    "source",
    [
        "# [Titre]{#identifiant}\n",
        "- [élément]{.classe}\n",
    ],
)
def test_pandoc_attributes_in_supported_containers_are_preserved(source):
    assert markdown_to_blocks(source) == [
        Block(kind=VERBATIM, raw_text=source.removesuffix("\n"))
    ]
    assert blocks_to_markdown(markdown_to_blocks(source)) == source


@pytest.mark.parametrize(
    ("run", "expected_markdown"),
    [
        (
            InlineRun(text="a]b", link_href="https://example.org"),
            "[a\\]b](https://example.org)\n",
        ),
        (
            InlineRun(text="[a]", link_href="https://example.org/a_(b)"),
            "[\\[a\\]](https://example.org/a_(b))\n",
        ),
        (
            InlineRun(
                image_src="assets/image_(1).png",
                image_alt="a]b",
                image_width="50%",
                image_align="center",
            ),
            "![a\\]b](assets/image_(1).png){width=50% align=center}\n",
        ),
        (
            InlineRun(
                text="a]b",
                bold=True,
                italic=True,
                underline=True,
                link_href="https://example.org/a_(b)",
            ),
            "[[***a\\]b***](https://example.org/a_(b))]{.underline}\n",
        ),
    ],
)
def test_links_images_and_underlined_links_scan_escaped_brackets_and_parentheses(
    run,
    expected_markdown,
):
    expected = [Block(kind=PARAGRAPH, runs=[run])]

    markdown = blocks_to_markdown(expected)

    assert markdown == expected_markdown
    assert markdown_to_blocks(markdown) == expected


@pytest.mark.parametrize(
    "text",
    [r"a\b", "a*b", "a_b", "a^b", "[a]", "a]b"],
)
def test_exported_escapes_roundtrip_inside_links(text):
    expected = [
        Block(
            kind=PARAGRAPH,
            runs=[InlineRun(text=text, link_href="https://example.org/a_(b)")],
        )
    ]

    assert markdown_to_blocks(blocks_to_markdown(expected)) == expected


def test_inline_scanner_is_shared_by_tables_and_footnote_definitions():
    linked = InlineRun(text="a]b", link_href="https://example.org/a_(b)")
    expected = [
        Block(
            kind=TABLE,
            children=[
                Block(
                    kind=TABLE_ROW,
                    children=[Block(kind=TABLE_CELL, runs=[linked])],
                ),
                Block(
                    kind=TABLE_ROW,
                    children=[
                        Block(
                            kind=TABLE_CELL,
                            runs=[InlineRun(text="Valeur")],
                        )
                    ],
                ),
            ],
        ),
        Block(
            kind=FOOTNOTE_DEFINITION,
            footnote_id="1",
            runs=[InlineRun(text="[sic]", underline=True)],
        ),
    ]

    markdown = blocks_to_markdown(expected)

    assert markdown_to_blocks(markdown) == expected
    assert blocks_to_markdown(markdown_to_blocks(markdown)) == markdown


def test_complete_representable_model_reopens_exactly():
    expected = [
        Block(
            kind=PARAGRAPH,
            runs=[
                InlineRun(text=r"simple a\b "),
                InlineRun(text="gras", bold=True),
                InlineRun(text=" "),
                InlineRun(text="italique", italic=True),
                InlineRun(text=" "),
                InlineRun(text="barré", strikethrough=True),
                InlineRun(text=" "),
                InlineRun(text="exposant", superscript=True),
                InlineRun(text=" "),
                InlineRun(text="souligné [sic]", underline=True),
                InlineRun(text=" "),
                InlineRun(
                    text="lien a]b",
                    bold=True,
                    underline=True,
                    link_href="https://example.org/a_(b)",
                ),
                InlineRun(text=" "),
                InlineRun(
                    image_src="assets/image_(1).png",
                    image_alt="a]b",
                    image_width="320",
                    image_height="180",
                    image_align="right",
                ),
                InlineRun(footnote_ref="7"),
            ],
            alignment="justify",
        ),
        Block(
            kind=TABLE,
            children=[
                Block(
                    kind=TABLE_ROW,
                    children=[
                        Block(
                            kind=TABLE_CELL,
                            runs=[
                                InlineRun(
                                    text="a]b",
                                    link_href="https://example.org/a_(b)",
                                )
                            ],
                        )
                    ],
                ),
                Block(
                    kind=TABLE_ROW,
                    children=[
                        Block(kind=TABLE_CELL, runs=[InlineRun(text="Valeur")])
                    ],
                ),
            ],
        ),
        Block(
            kind=FOOTNOTE_DEFINITION,
            footnote_id="7",
            runs=[InlineRun(text="Note [sic]", italic=True, underline=True)],
        ),
    ]

    markdown = blocks_to_markdown(expected)

    assert markdown_to_blocks(markdown) == expected
