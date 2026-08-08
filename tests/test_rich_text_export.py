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


def test_blockquote():
    blocks = [Block(kind=BLOCKQUOTE, runs=[InlineRun(text="Une citation.")])]
    assert blocks_to_markdown(blocks) == "> Une citation.\n"


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
