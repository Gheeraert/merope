"""Embedded-video Markdown fenced div: round trip as one protected block.

No change was made to rich_text_import.py/rich_text_export.py for this:
the reserved syntax (see bloggen.markdown.video_syntax) has no blank line
between its opening fence, optional caption and closing fence, so the
existing chunker already groups the whole span into a single chunk, and
FENCED_DIV_LINE_RE (any line starting with "::::") already forces that
chunk to VERBATIM rather than guessing at it as a paragraph. These tests
characterize that this still holds.
"""

from __future__ import annotations

from bloggen.markdown.rich_text_export import blocks_to_markdown
from bloggen.markdown.rich_text_import import markdown_to_blocks
from bloggen.markdown.rich_text_model import PARAGRAPH, VERBATIM, Block, InlineRun
from bloggen.markdown.video_syntax import format_video_block

VALID_ID = "dQw4w9WgXcQ"


def _p(text: str) -> Block:
    return Block(kind=PARAGRAPH, runs=[InlineRun(text=text)])


def test_video_without_caption_round_trips_as_one_verbatim_block():
    markdown = format_video_block(VALID_ID) + "\n"
    blocks = markdown_to_blocks(markdown)
    assert blocks == [Block(kind=VERBATIM, raw_text=format_video_block(VALID_ID))]
    assert blocks_to_markdown(blocks) == markdown


def test_video_with_caption_round_trips_as_one_verbatim_block():
    markdown = format_video_block(VALID_ID, "Une légende.") + "\n"
    blocks = markdown_to_blocks(markdown)
    assert blocks == [
        Block(kind=VERBATIM, raw_text=format_video_block(VALID_ID, "Une légende."))
    ]
    assert blocks_to_markdown(blocks) == markdown


def test_video_between_ordinary_paragraphs_round_trips():
    blocks = [
        _p("Avant."),
        Block(kind=VERBATIM, raw_text=format_video_block(VALID_ID, "Légende.")),
        _p("Après."),
    ]
    assert markdown_to_blocks(blocks_to_markdown(blocks)) == blocks


def test_video_caption_is_not_reparsed_as_a_plain_paragraph():
    """The caption line alone, inside the fenced div, must never become an
    editable PARAGRAPH block: that would let ordinary formatting commands
    reach it, defeating the "protected block" guarantee."""

    markdown = format_video_block(VALID_ID, "Texte.") + "\n"
    blocks = markdown_to_blocks(markdown)
    assert len(blocks) == 1
    assert blocks[0].kind == VERBATIM
