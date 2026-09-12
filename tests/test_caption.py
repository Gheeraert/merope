from __future__ import annotations

import pytest

from bloggen.markdown.caption import (
    caption_markdown,
    caption_runs,
    flatten_caption_text,
    normalize_caption_runs,
)
from bloggen.markdown.rich_text_model import InlineRun


def test_markers_become_bold_and_italic_runs():
    assert caption_runs("**Bossuet** à *Meaux*, ***1698***") == [
        InlineRun(text="Bossuet", bold=True),
        InlineRun(text=" à "),
        InlineRun(text="Meaux", italic=True),
        InlineRun(text=", "),
        InlineRun(text="1698", bold=True, italic=True),
    ]


@pytest.mark.parametrize("literal", ["5 * 3 * 2", "note*", "** pas gras **", "*", ""])
def test_unflanked_asterisks_stay_literal(literal):
    runs = caption_runs(literal)
    assert all(not run.bold and not run.italic for run in runs)
    assert "".join(run.text for run in runs) == literal


def test_none_and_empty_have_no_runs():
    assert caption_runs(None) == []
    assert caption_runs("") == []


@pytest.mark.parametrize(
    "caption",
    [
        "**Bossuet** à *Meaux*",
        "Portrait, ***1698***, huile sur toile",
        "Simple légende",
        "5 * 3",
        "*Italique* au début et **gras** à la fin",
    ],
)
def test_round_trip_is_exact_for_ordinary_captions(caption):
    assert caption_markdown(caption_runs(caption)) == caption


def test_edge_spaces_move_outside_markers_and_other_formats_are_dropped():
    runs = [
        InlineRun(text="Vue de "),
        InlineRun(text=" Rouen ", italic=True),
        InlineRun(text="lien", underline=True, link_href="https://x"),
        InlineRun(image_src="a.png"),
        InlineRun(footnote_ref="1"),
    ]

    assert caption_markdown(runs) == "Vue de  *Rouen* lien"


def test_normalization_merges_neighbours_with_same_emphasis():
    runs = [InlineRun(text="a", bold=True), InlineRun(text="b", bold=True), InlineRun(text="c")]

    assert normalize_caption_runs(runs) == [
        InlineRun(text="ab", bold=True),
        InlineRun(text="c"),
    ]


def test_captions_are_flattened_to_one_line():
    assert flatten_caption_text("ligne 1\nligne 2\r\n\tfin") == "ligne 1 ligne 2 fin"
