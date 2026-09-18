"""Inactive settings stay in site.json without taking space in the GUI."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from tkinter import Misc, ttk

import pytest

from bloggen.config.defaults import build_default_config
from bloggen.config.io import load_config, save_config
from bloggen.ui.main_window import MainWindow


_HIDDEN_VALUES = {
    ("content", "source_format"): "legacy-value",
    ("content", "use_front_matter"): False,
    ("home", "layout"): "legacy-home",
    ("render", "theme_name"): "legacy-theme",
    ("render", "pretty_print_html"): False,
    ("render", "lightbox_engine"): "legacy-engine",
    ("media_handling", "strategy"): "legacy-strategy",
    ("build", "fail_on_invalid_config"): False,
}


@pytest.fixture(scope="module")
def window() -> Iterator[MainWindow]:
    main_window = MainWindow()
    main_window.withdraw()
    yield main_window
    main_window.destroy()


def _control_texts(parent: Misc) -> set[str]:
    children = parent.winfo_children()
    texts = {
        child.cget("text")
        for child in children
        if isinstance(child, (ttk.Label, ttk.Checkbutton))
    }
    for child in children:
        texts.update(_control_texts(child))
    return texts


def test_inactive_controls_are_not_rendered(window: MainWindow) -> None:
    hidden_by_tab = {
        window.content_tab: {"Format source", "Utiliser front matter"},
        window.home_tab: {"Layout accueil"},
        window.render_tab: {"Nom thème", "HTML lisible", "Moteur lightbox"},
        window.media_panel: {"Stratégie"},
        window.build_tab: {"Échouer si config invalide"},
    }
    for tab, hidden_labels in hidden_by_tab.items():
        assert _control_texts(tab).isdisjoint(hidden_labels)

    assert "Origine markdown" in _control_texts(window.content_tab)
    assert "Source accueil" in _control_texts(window.home_tab)
    assert "Template page" in _control_texts(window.render_tab)
    assert "Dossier images" in _control_texts(window.media_panel)
    assert "Commande pandoc" in _control_texts(window.build_tab)


def test_hidden_values_survive_json_gui_json_round_trip(
    window: MainWindow, tmp_path: Path
) -> None:
    config = build_default_config()
    for (section, key), value in _HIDDEN_VALUES.items():
        setattr(getattr(config, section), key, value)

    config_path = tmp_path / "site.json"
    save_config(config, config_path)
    window._load_into_form(load_config(config_path))
    collected = window._collect_from_form()
    save_config(collected, config_path)
    saved = json.loads(config_path.read_text(encoding="utf-8"))

    for (section, key), value in _HIDDEN_VALUES.items():
        assert getattr(getattr(collected, section), key) == value
        assert saved[section][key] == value


def test_new_config_restores_dataclass_defaults_for_hidden_values(window: MainWindow) -> None:
    config = build_default_config()
    for (section, key), value in _HIDDEN_VALUES.items():
        setattr(getattr(config, section), key, value)
    window._load_into_form(config)

    window.new_config()

    collected = window._collect_from_form()
    defaults = build_default_config()
    for section, key in _HIDDEN_VALUES:
        assert getattr(getattr(collected, section), key) == getattr(getattr(defaults, section), key)
