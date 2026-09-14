from __future__ import annotations

from types import SimpleNamespace
from tkinter import ttk

from bloggen.config.models import HomeConfig
from bloggen.ui import main_window as main_window_module
from bloggen.ui.main_window import MainWindow


def test_recent_posts_excerpt_field_defaults_to_2000_and_has_body_tooltip(
    tk_root, monkeypatch
):
    tooltips: list[str] = []
    monkeypatch.setattr(
        main_window_module,
        "add_tooltip",
        lambda _widget, text: tooltips.append(text),
    )
    notebook = ttk.Notebook(tk_root)
    host = SimpleNamespace(notebook=notebook, _on_home_mode_changed=lambda: None)

    MainWindow._build_home_tab(host)

    assert host.home_vars["recent_posts_excerpt_length"].get() == "2000"
    excerpt_tooltip = next(text for text in tooltips if "Lire la suite" in text)
    assert "corps de chaque billet" in excerpt_tooltip
    assert "description" not in excerpt_tooltip
    notebook.destroy()


def test_recent_posts_excerpt_field_keeps_loaded_explicit_value(tk_root):
    notebook = ttk.Notebook(tk_root)
    host = SimpleNamespace(notebook=notebook, _on_home_mode_changed=lambda: None)
    MainWindow._build_home_tab(host)

    main_window_module._set_vars(
        host.home_vars,
        HomeConfig(recent_posts_excerpt_length=750),
    )

    assert host.home_vars["recent_posts_excerpt_length"].get() == "750"
    notebook.destroy()
