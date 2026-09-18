from __future__ import annotations

from tkinter import ttk

import pytest

from bloggen.config.models import NotesRenderingConfig
from bloggen.ui.notes_panel import NotesPanel


@pytest.fixture(scope="module")
def root(tk_root):
    # See tests/conftest.py: one Tk() interpreter shared across the whole
    # test session avoids the flakiness of repeated create/destroy churn.
    return tk_root


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


def test_only_footnotes_control_is_visible_and_connected(root):
    panel = NotesPanel(root)
    controls = [child for child in panel.winfo_children() if isinstance(child, ttk.Checkbutton)]
    assert len(controls) == 1
    assert controls[0].cget("text") == "Afficher les notes complètes en fin de page"
    assert str(controls[0].cget("variable")) == str(panel.enable_footnotes_var)

    labels = {
        child.cget("text")
        for child in panel.winfo_children()
        if isinstance(child, (ttk.Label, ttk.Checkbutton))
    }
    assert labels.isdisjoint(
        {
            "Mode",
            "Activer notes marginales (non disponible pour le moment)",
            "Amorce (mots)",
            "Amorce (caractères)",
            "Préférer le comptage en mots",
            "Emplacement notes finales",
        }
    )
    assert not any(isinstance(child, ttk.Entry) for child in panel.winfo_children())

    panel.enable_footnotes_var.set(False)
    assert panel.get_data().enable_footnotes is False
    panel.enable_footnotes_var.set(True)
    assert panel.get_data().enable_footnotes is True


def test_all_notes_settings_round_trip_even_when_six_are_hidden(root):
    panel = NotesPanel(root)
    legacy = NotesRenderingConfig(
        mode="legacy-mode",
        enable_margin_notes=True,
        enable_footnotes=False,
        margin_excerpt_words=17,
        margin_excerpt_chars=143,
        prefer_words_over_chars=False,
        footnotes_location="legacy-location",
    )

    panel.set_data(legacy)

    assert panel.get_data() == legacy
