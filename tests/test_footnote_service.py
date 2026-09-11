from __future__ import annotations

from bloggen.content.footnotes import (
    footnote_reference_counts,
    footnote_reference_order,
    next_footnote_id,
    ordered_footnote_ids,
    plan_footnote_renumbering,
    register_footnote,
    remove_footnote,
)
from bloggen.markdown.rich_text_model import BULLET_LIST, LIST_ITEM, PARAGRAPH, Block, InlineRun


def test_next_footnote_id_fills_first_numeric_gap():
    definitions = {
        "1": [InlineRun(text="one")],
        "3": [InlineRun(text="three")],
    }

    assert next_footnote_id(definitions) == "2"


def test_register_footnote_accepts_text_runs_and_empty_content():
    definitions = {}
    first = register_footnote(definitions, "texte")
    supplied_runs = [InlineRun(text="lien", link_href="https://example.org")]
    second = register_footnote(definitions, supplied_runs)
    third = register_footnote(definitions, [])

    assert (first, second, third) == ("1", "2", "3")
    assert definitions["1"] == [InlineRun(text="texte")]
    assert definitions["2"] is supplied_runs
    assert definitions["3"] == [InlineRun(text="")]


def test_remove_footnote_reports_if_definition_existed():
    definitions = {"1": [InlineRun(text="note")]}

    assert remove_footnote(definitions, "1") is True
    assert remove_footnote(definitions, "1") is False
    assert definitions == {}


def test_ordered_footnote_ids_deduplicates_references_then_appends_orphans():
    definitions = {
        "1": [InlineRun(text="orphan one")],
        "2": [InlineRun(text="second")],
        "4": [InlineRun(text="orphan four")],
    }

    result = ordered_footnote_ids(definitions, ["2", "2", "7"])

    assert result == ["2", "7", "1", "4"]


def test_plan_renumbering_returns_mapping_and_renamed_definitions():
    first_runs = [InlineRun(text="created first, referenced second")]
    second_runs = [InlineRun(text="created second, referenced first")]
    definitions = {"1": first_runs, "2": second_runs}

    result = plan_footnote_renumbering(definitions, ["2", "1"])

    assert result.changed is True
    assert result.mapping == {"2": "1", "1": "2"}
    # Keep the historical dictionary insertion order while changing keys;
    # GUI adapters sort ids for display themselves.
    assert list(result.definitions) == ["2", "1"]
    assert result.definitions["1"] is second_runs
    assert result.definitions["2"] is first_runs
    assert definitions == {"1": first_runs, "2": second_runs}


def test_plan_renumbering_is_noop_when_ids_already_follow_reference_order():
    definitions = {
        "1": [InlineRun(text="one")],
        "2": [InlineRun(text="two")],
    }

    result = plan_footnote_renumbering(definitions, ["1", "2"])

    assert result.changed is False
    assert result.mapping == {"1": "1", "2": "2"}
    assert result.definitions == definitions


def test_reference_order_and_counts_follow_nested_block_model_semantics():
    blocks = [
        Block(
            kind=PARAGRAPH,
            runs=[InlineRun(footnote_ref="3"), InlineRun(footnote_ref="3")],
        ),
        Block(
            kind=BULLET_LIST,
            children=[
                Block(kind=LIST_ITEM, runs=[InlineRun(footnote_ref="12")]),
            ],
        ),
    ]

    assert footnote_reference_order(blocks) == ["3", "3", "12"]
    assert footnote_reference_counts(blocks) == {"3": 2, "12": 1}
