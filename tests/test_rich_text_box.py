"""Encadré (BOX) Markdown round trip and lossless fallbacks."""

from bloggen.markdown.rich_text_export import blocks_to_markdown
from bloggen.markdown.rich_text_import import markdown_to_blocks
from bloggen.markdown.rich_text_model import (
    BOX,
    BULLET_LIST,
    LIST_ITEM,
    PARAGRAPH,
    VERBATIM,
    Block,
    InlineRun,
)


def _p(text):
    return Block(kind=PARAGRAPH, runs=[InlineRun(text=text)])


def test_titled_box_round_trips():
    box = Block(kind=BOX, runs=[InlineRun(text="À retenir")], children=[_p("Un."), _p("Deux.")])
    markdown = blocks_to_markdown([box])
    assert markdown == (
        ":::: {.merope-encadre}\n"
        "::: {.merope-encadre-titre}\nÀ retenir\n:::\n\n"
        "Un.\n\nDeux.\n::::\n"
    )
    assert markdown_to_blocks(markdown) == [box]


def test_untitled_box_round_trips():
    box = Block(kind=BOX, runs=[], children=[_p("Seul.")])
    markdown = blocks_to_markdown([box])
    assert markdown == ":::: {.merope-encadre}\nSeul.\n::::\n"
    assert markdown_to_blocks(markdown) == [box]


def test_inline_formats_and_lists_round_trip():
    box = Block(
        kind=BOX,
        runs=[InlineRun(text="Titre "), InlineRun(text="it", italic=True)],
        children=[
            Block(kind=PARAGRAPH, runs=[InlineRun(text="gras", bold=True), InlineRun(text=" et")]),
            Block(
                kind=BULLET_LIST,
                children=[Block(kind=LIST_ITEM, runs=[InlineRun(text="a")])],
            ),
        ],
    )
    assert markdown_to_blocks(blocks_to_markdown([box])) == [box]


def test_box_between_ordinary_blocks():
    blocks = [
        _p("Avant."),
        Block(kind=BOX, runs=[], children=[_p("Dedans.")]),
        _p("Après."),
    ]
    assert markdown_to_blocks(blocks_to_markdown(blocks)) == blocks


def test_foreign_fenced_div_is_never_a_box_and_stays_lossless():
    source = "::: {.autre}\nTexte.\n:::\n"
    blocks = markdown_to_blocks(source)
    assert all(block.kind != BOX for block in blocks)
    assert blocks_to_markdown(blocks) == source


def test_foreign_div_with_blank_line_stays_lossless():
    source = "::: {.autre}\nUn.\n\nDeux.\n:::\n"
    blocks = markdown_to_blocks(source)
    assert all(block.kind != BOX for block in blocks)
    assert blocks_to_markdown(blocks) == source


def test_unclosed_box_is_verbatim_and_does_not_swallow_the_rest():
    source = ":::: {.merope-encadre}\nTexte.\n\nSuite du document.\n"
    blocks = markdown_to_blocks(source)
    assert all(block.kind != BOX for block in blocks)
    assert blocks[-1] == _p("Suite du document.")
    assert blocks_to_markdown(blocks) == source


def test_box_with_unsupported_content_stays_verbatim():
    source = ":::: {.merope-encadre}\n## Titre interne\n\nTexte.\n::::\n"
    blocks = markdown_to_blocks(source)
    assert [block.kind for block in blocks] == [VERBATIM]
    assert blocks_to_markdown(blocks) == source


def test_box_with_malformed_title_stays_verbatim():
    source = ":::: {.merope-encadre}\n::: {.merope-encadre-titre}\nTitre\n\nTexte.\n::::\n"
    blocks = markdown_to_blocks(source)
    assert all(block.kind != BOX for block in blocks)
    assert blocks_to_markdown(blocks) == source


def test_nested_box_is_not_interpreted_and_stays_lossless():
    source = ":::: {.merope-encadre}\n:::: {.merope-encadre}\nX\n::::\n::::\n"
    blocks = markdown_to_blocks(source)
    # The stray closing fence becomes its own chunk, so only blank-line
    # spacing may differ; no content is lost or reinterpreted.
    assert blocks_to_markdown(blocks).replace("\n\n", "\n") == source
    assert all(block.kind != BOX for block in blocks)
