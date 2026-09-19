"""GUI configuration controls and JSON round-trips."""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import fields as dataclass_fields
from pathlib import Path
from tkinter import Misc, Variable, ttk

import pytest

from bloggen.config.defaults import build_default_config
from bloggen.config.io import load_config, save_config, serialize_config
from bloggen.config.models import NotesRenderingConfig
from bloggen.ui.main_window import MainWindow


def _base_raw() -> dict:
    return json.loads(serialize_config(build_default_config()))


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


def _publishing_checkboxes(window: MainWindow) -> list[tuple[ttk.Checkbutton, Variable]]:
    fields = (
        (window.blog_tab, window.blog_vars, "generate_rss_feed", "Générer le flux RSS"),
        (window.build_tab, window.build_vars, "generate_sitemap", "Générer sitemap.xml"),
        (window.build_tab, window.build_vars, "generate_robots_txt", "Générer robots.txt"),
    )
    result = []
    for tab, vars_map, key, label in fields:
        matches = [
            child
            for child in tab.winfo_children()
            if isinstance(child, ttk.Checkbutton) and child.cget("text") == label
        ]
        assert len(matches) == 1
        assert str(matches[0].cget("variable")) == str(vars_map[key])
        result.append((matches[0], vars_map[key]))
    return result


def test_publishing_controls_are_visible_and_bound_to_model_vars(window: MainWindow) -> None:
    assert len(_publishing_checkboxes(window)) == 3


def test_disabled_publishing_flags_survive_json_gui_json_and_can_be_enabled(
    window: MainWindow, tmp_path: Path
) -> None:
    config = build_default_config()
    config.blog.generate_rss_feed = False
    config.build.generate_sitemap = False
    config.build.generate_robots_txt = False
    config_path = tmp_path / "site.json"
    save_config(config, config_path)

    window._load_into_form(load_config(config_path))
    checkboxes = _publishing_checkboxes(window)
    assert all(variable.get() is False for _, variable in checkboxes)

    collected = window._collect_from_form()
    save_config(collected, config_path)
    saved = json.loads(config_path.read_text(encoding="utf-8"))
    assert saved["blog"]["generate_rss_feed"] is False
    assert saved["build"]["generate_sitemap"] is False
    assert saved["build"]["generate_robots_txt"] is False

    for _, variable in checkboxes:
        variable.set(True)
    enabled = window._collect_from_form()
    assert enabled.blog.generate_rss_feed is True
    assert enabled.build.generate_sitemap is True
    assert enabled.build.generate_robots_txt is True


def test_new_config_enables_publishing_flags_by_default(window: MainWindow) -> None:
    window.new_config()
    assert all(variable.get() is True for _, variable in _publishing_checkboxes(window))

    collected = window._collect_from_form()
    defaults = build_default_config()
    assert collected.blog.generate_rss_feed == defaults.blog.generate_rss_feed is True
    assert collected.build.generate_sitemap == defaults.build.generate_sitemap is True
    assert collected.build.generate_robots_txt == defaults.build.generate_robots_txt is True


def test_notes_settings_survive_json_gui_json_and_new_config_uses_defaults(
    window: MainWindow, tmp_path: Path
) -> None:
    config = build_default_config()
    legacy = NotesRenderingConfig(
        mode="legacy-mode",
        enable_margin_notes=True,
        enable_footnotes=False,
        margin_excerpt_words=17,
        margin_excerpt_chars=143,
        prefer_words_over_chars=False,
        footnotes_location="legacy-location",
    )
    config.notes_rendering = legacy
    config_path = tmp_path / "site.json"
    save_config(config, config_path)

    window._load_into_form(load_config(config_path))
    collected = window._collect_from_form()
    save_config(collected, config_path)

    assert collected.notes_rendering == legacy
    saved = json.loads(config_path.read_text(encoding="utf-8"))
    expected = {
        f.name: getattr(legacy, f.name)
        for f in dataclass_fields(legacy)
        if f.name != "unknown_data"
    }
    assert saved["notes_rendering"] == expected

    window.new_config()
    assert window._collect_from_form().notes_rendering == NotesRenderingConfig()


# -- Lossless round-trip: real MainWindow open -> edit -> save cycle ----------
#
# Reuses the module-scoped `window` fixture above rather than creating a
# second independent MainWindow()/Tk() root in this pytest session — see
# bloggen.config.models.ProjectConfig.unknown_data's docstring for the
# mechanism these exercise end-to-end.


def test_new_config_does_not_inherit_opaque_data_from_a_previous_project(
    window: MainWindow, tmp_path: Path
) -> None:
    raw_a = _base_raw()
    raw_a["future_extension"] = {"from": "A"}
    path_a = tmp_path / "a.json"
    path_a.write_text(json.dumps(raw_a), encoding="utf-8")

    window._load_into_form(load_config(path_a))

    window.new_config()
    path_b = tmp_path / "b.json"
    save_config(window._collect_from_form(), path_b)

    saved_b = json.loads(path_b.read_text(encoding="utf-8"))
    assert "future_extension" not in saved_b


def test_opening_a_second_config_replaces_the_first_ones_opaque_data(
    window: MainWindow, tmp_path: Path
) -> None:
    raw_a = _base_raw()
    raw_a["future_extension"] = {"from": "A"}
    path_a = tmp_path / "a.json"
    path_a.write_text(json.dumps(raw_a), encoding="utf-8")

    raw_b = _base_raw()
    raw_b["future_extension"] = {"from": "B"}
    path_b = tmp_path / "b.json"
    path_b.write_text(json.dumps(raw_b), encoding="utf-8")

    window._load_into_form(load_config(path_a))
    window._load_into_form(load_config(path_b))

    save_config(window._collect_from_form(), path_b)
    saved_b = json.loads(path_b.read_text(encoding="utf-8"))
    assert saved_b["future_extension"] == {"from": "B"}


def test_save_as_preserves_opaque_data_in_the_new_destination(
    window: MainWindow, tmp_path: Path
) -> None:
    raw = _base_raw()
    raw["future_extension"] = {"kept": True}
    path_a = tmp_path / "a.json"
    path_a.write_text(json.dumps(raw), encoding="utf-8")

    window._load_into_form(load_config(path_a))
    collected = window._collect_from_form()
    path_b = tmp_path / "b.json"
    save_config(collected, path_b)

    saved_b = json.loads(path_b.read_text(encoding="utf-8"))
    assert saved_b["future_extension"] == {"kept": True}


def test_loaded_config_version_survives_open_edit_and_collect(
    window: MainWindow, tmp_path: Path
) -> None:
    raw = _base_raw()
    raw["version"] = "2.0"
    config_path = tmp_path / "site.json"
    config_path.write_text(json.dumps(raw), encoding="utf-8")

    window._load_into_form(load_config(config_path))
    collected = window._collect_from_form()

    assert collected.version == "2.0"


def test_loaded_config_version_survives_full_save_round_trip(
    window: MainWindow, tmp_path: Path
) -> None:
    raw = _base_raw()
    raw["version"] = "2.0"
    config_path = tmp_path / "site.json"
    config_path.write_text(json.dumps(raw), encoding="utf-8")

    window._load_into_form(load_config(config_path))
    save_config(window._collect_from_form(), config_path)

    saved = json.loads(config_path.read_text(encoding="utf-8"))
    assert saved["version"] == "2.0"


def test_new_config_still_uses_the_default_version(window: MainWindow) -> None:
    window.new_config()
    collected = window._collect_from_form()
    assert collected.version == "1.0"


def test_successive_loads_each_keep_their_own_version_not_the_previous_one(
    window: MainWindow, tmp_path: Path
) -> None:
    raw_a = _base_raw()
    raw_a["version"] = "2.0"
    path_a = tmp_path / "a.json"
    path_a.write_text(json.dumps(raw_a), encoding="utf-8")

    raw_b = _base_raw()
    raw_b["version"] = "3.0"
    path_b = tmp_path / "b.json"
    path_b.write_text(json.dumps(raw_b), encoding="utf-8")

    window._load_into_form(load_config(path_a))
    window._load_into_form(load_config(path_b))

    collected = window._collect_from_form()
    assert collected.version == "3.0"

    save_config(collected, path_b)
    saved_b = json.loads(path_b.read_text(encoding="utf-8"))
    assert saved_b["version"] == "3.0"
    assert saved_b["version"] != "2.0"
