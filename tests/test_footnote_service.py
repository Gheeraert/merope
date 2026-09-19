from __future__ import annotations

from dataclasses import replace

from bloggen.content.footnotes import (
    footnote_definition_blocks,
    footnote_reference_counts,
    footnote_reference_order,
    next_footnote_id,
    ordered_footnote_ids,
    plan_footnote_renumbering,
    register_footnote,
    remove_footnote,
    separate_footnote_definitions,
)
from bloggen.markdown.rich_text_export import blocks_to_markdown
from bloggen.markdown.rich_text_import import markdown_to_blocks
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


def test_ordered_footnote_ids_sorts_numeric_orphans_historically():
    definitions = {"10": [InlineRun(text="ten")], "2": [InlineRun(text="two")]}

    assert ordered_footnote_ids(definitions, []) == ["2", "10"]


def test_ordered_footnote_ids_accepts_non_numeric_orphan_without_raising():
    definitions = {"note": [InlineRun(text="alphabetic orphan")]}

    assert ordered_footnote_ids(definitions, []) == ["note"]


def test_ordered_footnote_ids_orders_numeric_orphans_before_non_numeric_ones():
    definitions = {
        "10": [InlineRun(text="ten")],
        "foo": [InlineRun(text="foo")],
        "2": [InlineRun(text="two")],
        "bar": [InlineRun(text="bar")],
    }

    assert ordered_footnote_ids(definitions, []) == ["2", "10", "foo", "bar"]


def test_ordered_footnote_ids_references_take_priority_over_alphabetic_orphans():
    definitions = {
        "foo": [InlineRun(text="foo")],
        "2": [InlineRun(text="two")],
        "bar": [InlineRun(text="bar")],
    }

    assert ordered_footnote_ids(definitions, ["bar", "foo"]) == ["bar", "foo", "2"]


def test_ordered_footnote_ids_keeps_a_reference_with_no_matching_definition():
    definitions = {"foo": [InlineRun(text="foo")]}

    assert ordered_footnote_ids(definitions, ["missing", "foo"]) == ["missing", "foo"]


def test_plan_renumbering_handles_a_full_mixed_alphanumeric_set():
    bar_runs = [InlineRun(text="bar content")]
    foo_runs = [InlineRun(text="foo content")]
    two_runs = [InlineRun(text="two content")]
    definitions = {"2": two_runs, "foo": foo_runs, "bar": bar_runs}

    result = plan_footnote_renumbering(definitions, ["bar", "foo"])

    assert result.mapping == {"bar": "1", "foo": "2", "2": "3"}
    assert result.definitions["1"] is bar_runs
    assert result.definitions["2"] is foo_runs
    assert result.definitions["3"] is two_runs
    # The original dict passed in must be left untouched.
    assert definitions == {"2": two_runs, "foo": foo_runs, "bar": bar_runs}


def test_plan_renumbering_of_an_alphabetic_orphan_definition_does_not_raise():
    definitions = {"note": [InlineRun(text="orphan definition")]}

    result = plan_footnote_renumbering(definitions, [])

    assert result.changed is True
    assert result.mapping == {"note": "1"}
    assert list(result.definitions) == ["1"]


def _renumber_footnote_refs(block: Block, mapping: dict[str, str]) -> Block:
    runs = [
        replace(run, footnote_ref=mapping.get(run.footnote_ref, run.footnote_ref))
        if run.footnote_ref is not None
        else run
        for run in block.runs
    ]
    children = [_renumber_footnote_refs(child, mapping) for child in block.children]
    return replace(block, runs=runs, children=children)


def test_full_pipeline_renumbers_a_non_numeric_footnote_id_without_exception():
    """markdown_to_blocks -> separate_footnote_definitions ->
    plan_footnote_renumbering -> reference renumbering -> blocks_to_markdown,
    reproducing the real user-facing bug: a Markdown document with a
    Pandoc-style non-numeric footnote id (``[^note]``) must be importable
    and renumberable to the canonical ``1, 2, 3...`` sequence without
    ``ordered_footnote_ids`` raising ``ValueError: invalid literal for
    int()`` on the orphan/reference sort.
    """
    source = "Texte avec une note[^note].\n\n[^note]: Contenu de la note.\n"

    blocks = markdown_to_blocks(source)
    body_blocks, definitions = separate_footnote_definitions(blocks)
    reference_order = footnote_reference_order(body_blocks)

    renumbering = plan_footnote_renumbering(definitions, reference_order)
    assert renumbering.changed is True
    assert renumbering.mapping == {"note": "1"}

    renumbered_body = [_renumber_footnote_refs(block, renumbering.mapping) for block in body_blocks]
    final_blocks = renumbered_body + footnote_definition_blocks(renumbering.definitions)

    assert blocks_to_markdown(final_blocks) == (
        "Texte avec une note[^1].\n\n[^1]: Contenu de la note.\n"
    )
