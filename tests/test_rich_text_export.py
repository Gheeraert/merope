import pytest

from bloggen.markdown.rich_text_export import blocks_to_markdown
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


def test_heading_levels():
    blocks = [Block(kind=HEADING, level=2, runs=[InlineRun(text="Titre")])]
    assert blocks_to_markdown(blocks) == "## Titre\n"


def test_paragraph_inline_formatting():
    blocks = [
        Block(
            kind=PARAGRAPH,
            runs=[
                InlineRun(text="Un "),
                InlineRun(text="gras", bold=True),
                InlineRun(text=" et "),
                InlineRun(text="italique", italic=True),
                InlineRun(text=" et "),
                InlineRun(text="les deux", bold=True, italic=True),
                InlineRun(text=" et "),
                InlineRun(text="barre", strikethrough=True),
                InlineRun(text="."),
            ],
        )
    ]
    assert blocks_to_markdown(blocks) == (
        "Un **gras** et *italique* et ***les deux*** et ~~barre~~.\n"
    )


def test_superscript():
    blocks = [
        Block(
            kind=PARAGRAPH,
            runs=[InlineRun(text="Le XXI"), InlineRun(text="e", superscript=True), InlineRun(text=" siecle.")],
        )
    ]
    assert blocks_to_markdown(blocks) == "Le XXI^e^ siecle.\n"


def test_superscript_combined_with_bold():
    blocks = [Block(kind=PARAGRAPH, runs=[InlineRun(text="exp", bold=True, superscript=True)])]
    assert blocks_to_markdown(blocks) == "**^exp^**\n"


def test_underline_uses_pandoc_span_and_wraps_links_safely():
    blocks = [
        Block(
            kind=PARAGRAPH,
            runs=[
                InlineRun(text="souligne", underline=True),
                InlineRun(text=" et "),
                InlineRun(
                    text="lien gras",
                    bold=True,
                    underline=True,
                    link_href="https://example.org",
                ),
            ],
        )
    ]
    assert blocks_to_markdown(blocks) == (
        "[souligne]{.underline} et "
        "[[**lien gras**](https://example.org)]{.underline}\n"
    )


@pytest.mark.parametrize(
    "href",
    [
        "javascript:alert(1)",
        "data:text/html,<script>alert(1)</script>",
        "vbscript:foo",
        "customscheme:foo",
    ],
)
def test_dangerous_link_href_built_directly_is_never_serialized_as_a_link(href):
    blocks = [Block(kind=PARAGRAPH, runs=[InlineRun(text="important", link_href=href)])]
    md = blocks_to_markdown(blocks)
    assert md == "important\n"
    assert "javascript:" not in md
    assert "data:" not in md
    assert "vbscript:" not in md
    assert "customscheme:" not in md


def test_dangerous_link_href_on_a_bold_run_keeps_the_bold_formatting():
    blocks = [
        Block(
            kind=PARAGRAPH,
            runs=[InlineRun(text="important", bold=True, link_href="javascript:alert(1)")],
        )
    ]
    assert blocks_to_markdown(blocks) == "**important**\n"


def test_dangerous_link_href_on_an_italic_run_keeps_the_italic_formatting():
    blocks = [
        Block(
            kind=PARAGRAPH,
            runs=[InlineRun(text="important", italic=True, link_href="javascript:alert(1)")],
        )
    ]
    assert blocks_to_markdown(blocks) == "*important*\n"


def test_dangerous_link_href_on_an_underlined_run_keeps_the_underline_span_without_a_link():
    blocks = [
        Block(
            kind=PARAGRAPH,
            runs=[InlineRun(text="important", underline=True, link_href="javascript:alert(1)")],
        )
    ]
    assert blocks_to_markdown(blocks) == "[important]{.underline}\n"


def test_dangerous_link_href_on_a_bold_italic_underlined_run_keeps_all_formatting():
    blocks = [
        Block(
            kind=PARAGRAPH,
            runs=[
                InlineRun(
                    text="important",
                    bold=True,
                    italic=True,
                    underline=True,
                    link_href="javascript:alert(1)",
                )
            ],
        )
    ]
    assert blocks_to_markdown(blocks) == "[***important***]{.underline}\n"


def test_caret_in_plain_text_is_escaped():
    blocks = [Block(kind=PARAGRAPH, runs=[InlineRun(text="a^b")])]
    assert blocks_to_markdown(blocks) == "a\\^b\n"


def test_link_and_image_and_footnote_ref():
    blocks = [
        Block(
            kind=PARAGRAPH,
            runs=[
                InlineRun(text="Voir ", link_href=None),
                InlineRun(text="ce lien", link_href="https://example.org"),
                InlineRun(text=" et une image "),
                InlineRun(image_src="assets/images/x.jpg", image_alt="Alt"),
                InlineRun(text=" et une note"),
                InlineRun(footnote_ref="1"),
                InlineRun(text="."),
            ],
        )
    ]
    assert blocks_to_markdown(blocks) == (
        "Voir [ce lien](https://example.org) et une image "
        "![Alt](assets/images/x.jpg) et une note[^1].\n"
    )


def test_image_with_dimensions_and_alignment():
    blocks = [
        Block(
            kind=PARAGRAPH,
            runs=[
                InlineRun(
                    image_src="assets/images/x.jpg",
                    image_alt="Alt",
                    image_width="300",
                    image_height="200",
                    image_align="left",
                )
            ],
        )
    ]
    assert blocks_to_markdown(blocks) == (
        "![Alt](assets/images/x.jpg){width=300 height=200 align=left}\n"
    )


def test_image_without_dimensions_has_no_attribute_suffix():
    blocks = [Block(kind=PARAGRAPH, runs=[InlineRun(image_src="a.jpg", image_alt="Alt")])]
    assert blocks_to_markdown(blocks) == "![Alt](a.jpg)\n"


def test_blockquote():
    blocks = [Block(kind=BLOCKQUOTE, runs=[InlineRun(text="Une citation.")])]
    assert blocks_to_markdown(blocks) == "> Une citation.\n"


def test_paragraph_alignment_marker():
    blocks = [Block(kind=PARAGRAPH, runs=[InlineRun(text="Centre.")], alignment="center")]
    assert blocks_to_markdown(blocks) == "{{align=center}}Centre.\n"


def test_paragraph_left_alignment_has_no_marker():
    blocks = [Block(kind=PARAGRAPH, runs=[InlineRun(text="Normal.")], alignment="left")]
    assert blocks_to_markdown(blocks) == "Normal.\n"


def test_blockquote_alignment_marker():
    blocks = [Block(kind=BLOCKQUOTE, runs=[InlineRun(text="Citation.")], alignment="right")]
    assert blocks_to_markdown(blocks) == "> {{align=right}}Citation.\n"


def test_bullet_and_ordered_lists():
    bullet = Block(
        kind=BULLET_LIST,
        children=[
            Block(kind=LIST_ITEM, runs=[InlineRun(text="un")]),
            Block(kind=LIST_ITEM, runs=[InlineRun(text="deux", bold=True)]),
        ],
    )
    ordered = Block(
        kind=ORDERED_LIST,
        children=[
            Block(kind=LIST_ITEM, runs=[InlineRun(text="premier")]),
            Block(kind=LIST_ITEM, runs=[InlineRun(text="second")]),
        ],
    )
    assert blocks_to_markdown([bullet]) == "- un\n- **deux**\n"
    assert blocks_to_markdown([ordered]) == "1. premier\n2. second\n"


def _cell(text: str) -> Block:
    return Block(kind=TABLE_CELL, runs=[InlineRun(text=text)])


def test_table():
    table = Block(
        kind=TABLE,
        children=[
            Block(kind=TABLE_ROW, children=[_cell("Élément"), _cell("Valeur")]),
            Block(kind=TABLE_ROW, children=[_cell("A"), _cell("1")]),
            Block(kind=TABLE_ROW, children=[_cell("B"), _cell("2")]),
        ],
    )
    assert blocks_to_markdown([table]) == (
        "| Élément | Valeur |\n| --- | --- |\n| A | 1 |\n| B | 2 |\n"
    )


def test_table_cell_pipe_escaping():
    table = Block(kind=TABLE, children=[Block(kind=TABLE_ROW, children=[_cell("a|b")])])
    assert blocks_to_markdown([table]) == "| a\\|b |\n| --- |\n"


@pytest.mark.parametrize(
    "row_widths",
    [
        (2, 1),
        (1, 2),
        (2, 2, 1, 2),
    ],
)
def test_irregular_table_is_rejected_instead_of_padded(row_widths):
    table = Block(
        kind=TABLE,
        children=[
            Block(
                kind=TABLE_ROW,
                children=[
                    _cell(f"{row_index}-{cell_index}")
                    for cell_index in range(width)
                ],
            )
            for row_index, width in enumerate(row_widths)
        ],
    )

    with pytest.raises(ValueError, match="même nombre de cellules"):
        blocks_to_markdown([table])


def test_footnote_definition():
    blocks = [
        Block(kind=FOOTNOTE_DEFINITION, footnote_id="1", runs=[InlineRun(text="Une note.")]),
    ]
    assert blocks_to_markdown(blocks) == "[^1]: Une note.\n"


def test_verbatim_reproduced_as_is():
    raw = '<div class="weird">contenu html</div>'
    blocks = [Block(kind=VERBATIM, raw_text=raw)]
    assert blocks_to_markdown(blocks) == raw + "\n"


def test_special_characters_are_escaped():
    blocks = [Block(kind=PARAGRAPH, runs=[InlineRun(text="1 * 2 = [deux] et _underscore_")])]
    assert blocks_to_markdown(blocks) == "1 \\* 2 = \\[deux\\] et \\_underscore\\_\n"


def test_multiple_blocks_separated_by_blank_line():
    blocks = [
        Block(kind=HEADING, level=1, runs=[InlineRun(text="Titre")]),
        Block(kind=PARAGRAPH, runs=[InlineRun(text="Corps.")]),
    ]
    assert blocks_to_markdown(blocks) == "# Titre\n\nCorps.\n"


def test_empty_block_list_exports_to_empty_markdown():
    assert blocks_to_markdown([]) == ""
