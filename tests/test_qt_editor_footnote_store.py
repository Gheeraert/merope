from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from bloggen.markdown.rich_text_model import InlineRun
from bloggen.ui.qt_editor.footnote_store import FootnoteStore, plain_footnote_text


@pytest.fixture(scope="module", autouse=True)
def qapplication():
    yield QApplication.instance() or QApplication([])


def test_load_is_clean_and_mutations_track_against_saved_baseline():
    store = FootnoteStore()
    modified_events = []
    store.modifiedChanged.connect(modified_events.append)

    store.load({"1": [InlineRun(text="Initiale")]})
    assert not store.modified

    assert store.update("1", [InlineRun(text="Modifiée")])
    assert store.modified
    assert modified_events == [True]

    assert store.update("1", [InlineRun(text="Initiale")])
    assert not store.modified
    assert modified_events == [True, False]


def test_register_remove_snapshot_restore_and_mark_clean():
    store = FootnoteStore()
    store.load({"1": [InlineRun(text="Une")]})
    snapshot = store.snapshot()

    assert store.register("Deux") == "2"
    assert store.remove("1")
    assert store.modified
    store.restore(snapshot)
    assert store.definitions == {"1": [InlineRun(text="Une")]}
    assert not store.modified

    store.update("1", [InlineRun(text="Sauvegardée")])
    store.mark_clean()
    assert not store.modified


def test_definitions_property_does_not_allow_untracked_external_mutation():
    store = FootnoteStore()
    store.load({"1": [InlineRun(text="Stable")]})

    exposed = store.definitions
    exposed["1"][0].text = "Mutation externe"
    exposed["2"] = [InlineRun(text="Ajout externe")]

    assert store.definitions == {"1": [InlineRun(text="Stable")]}
    assert not store.modified


@pytest.mark.parametrize(
    "run",
    [
        InlineRun(text="x", bold=True),
        InlineRun(text="x", italic=True),
        InlineRun(text="x", strikethrough=True),
        InlineRun(text="x", superscript=True),
        InlineRun(text="x", link_href="https://example.org"),
        InlineRun(image_src="image.png"),
        InlineRun(footnote_ref="1"),
    ],
)
def test_plain_footnote_text_refuses_every_rich_or_semantic_run(run):
    assert plain_footnote_text([run]) is None


def test_plain_footnote_text_combines_only_plain_runs_without_mutating_them():
    runs = [InlineRun(text="Une "), InlineRun(text="note")]

    assert plain_footnote_text(runs) == "Une note"
    assert runs == [InlineRun(text="Une "), InlineRun(text="note")]
