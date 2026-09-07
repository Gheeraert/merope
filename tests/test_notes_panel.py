from __future__ import annotations

import tkinter as tk

import pytest

from bloggen.config.models import NotesRenderingConfig
from bloggen.ui.notes_panel import NotesPanel


@pytest.fixture(scope="module")
def root():
    # See tests/test_menu_link_dialog.py: one Tk() reused across a module's
    # tests avoids the flakiness of rapid create/destroy churn.
    window = tk.Tk()
    window.withdraw()
    yield window
    window.destroy()


def test_excerpt_fields_round_trip_through_set_and_get_data(root):
    panel = NotesPanel(root)
    panel.set_data(NotesRenderingConfig(margin_excerpt_words=12, margin_excerpt_chars=90))
    data = panel.get_data()
    assert data.margin_excerpt_words == 12
    assert data.margin_excerpt_chars == 90


def test_excerpt_fields_accept_zero_meaning_no_truncation(root):
    panel = NotesPanel(root)
    panel.set_data(NotesRenderingConfig(margin_excerpt_words=0, margin_excerpt_chars=0))
    data = panel.get_data()
    assert data.margin_excerpt_words == 0
    assert data.margin_excerpt_chars == 0


def test_get_data_raises_a_clean_error_on_empty_excerpt_words(root):
    """excerpt_words_var/excerpt_chars_var used to be tk.IntVar: clearing
    the entry raised a raw tkinter.TclError on .get() instead of a
    catchable, friendly message.
    """
    panel = NotesPanel(root)
    panel.excerpt_words_var.set("")
    with pytest.raises(ValueError, match="Amorce"):
        panel.get_data()


def test_get_data_raises_a_clean_error_on_non_numeric_excerpt_chars(root):
    panel = NotesPanel(root)
    panel.excerpt_chars_var.set("beaucoup")
    with pytest.raises(ValueError, match="Amorce"):
        panel.get_data()


def test_get_data_rejects_a_negative_excerpt_length(root):
    panel = NotesPanel(root)
    panel.excerpt_words_var.set("-3")
    with pytest.raises(ValueError, match="supérieur ou égal à 0"):
        panel.get_data()
