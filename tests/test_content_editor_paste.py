"""Headless tests for ContentEditorWindow's asynchronous HTML paste
(see ContentEditorWindow._start_async_html_paste).

Uses the same technique as tests/test_menu_link_dialog.py: instantiate
real Tk widgets, drive them directly (bypassing user interaction), and
pump the event loop with root.update() to let the background worker
thread and its polling callback (self.after) actually run.
"""

from __future__ import annotations

import time
import tkinter as tk

import pytest

import bloggen.ui.content_editor.paste as content_editor_module
from bloggen.ui.content_editor import ContentEditorWindow


@pytest.fixture(scope="module")
def root(tk_root):
    # See tests/conftest.py: one Tk() interpreter shared across the whole
    # test session avoids the flakiness of repeated create/destroy churn.
    return tk_root


@pytest.fixture
def editor(root, tmp_path):
    pages_dir = tmp_path / "content" / "pages"
    posts_dir = tmp_path / "content" / "posts"
    images_dir = tmp_path / "assets" / "images"
    pages_dir.mkdir(parents=True)
    posts_dir.mkdir(parents=True)

    window = ContentEditorWindow(
        root, pages_dir=pages_dir, posts_dir=posts_dir, images_dir=images_dir, slugify_mode="ascii"
    )
    yield window
    window.destroy()


def _pump_until(root: tk.Tk, predicate, *, timeout: float = 3.0) -> None:
    deadline = time.time() + timeout
    while not predicate() and time.time() < deadline:
        root.update()
        time.sleep(0.01)
    assert predicate(), "condition never became true within the timeout"


def test_async_html_paste_inserts_content_without_blocking(root, editor, monkeypatch):
    editor._start_async_html_paste("<p>Bonjour <b>monde</b></p>")
    _pump_until(root, lambda: editor.text.get("1.0", "end-1c").strip() != "")
    assert editor.text.get("1.0", "end-1c") == "Bonjour monde"
    assert editor.text.tag_ranges("bold")


def test_async_html_paste_shows_a_busy_cursor_while_running_then_resets(root, editor, monkeypatch):
    # Wrap (rather than replace outright) so the real parser still runs
    # after the artificial delay, keeping the test meaningful.
    real = content_editor_module.html_to_blocks

    def delayed(html, **kwargs):
        time.sleep(0.3)
        return real(html, **kwargs)

    monkeypatch.setattr(content_editor_module, "html_to_blocks", delayed)

    assert editor.text.cget("cursor") != "watch"
    editor._start_async_html_paste("<p>Retarde</p>")
    assert editor.text.cget("cursor") == "watch"

    _pump_until(root, lambda: "Retarde" in editor.text.get("1.0", "end-1c"))
    assert editor.text.cget("cursor") != "watch"


def test_async_html_paste_lands_at_the_original_cursor_even_if_user_keeps_typing(root, editor, monkeypatch):
    real = content_editor_module.html_to_blocks

    def delayed(html, **kwargs):
        time.sleep(0.3)
        return real(html, **kwargs)

    monkeypatch.setattr(content_editor_module, "html_to_blocks", delayed)

    editor.text.insert("1.0", "AABB")
    editor.text.mark_set("insert", "1.2")  # between "AA" and "BB"

    editor._start_async_html_paste("<p>X</p>")

    # While the paste is still in flight, the user types elsewhere.
    root.update()
    editor.text.mark_set("insert", "end-1c")
    editor.text.insert("insert", "ZZ")

    _pump_until(root, lambda: "X" in editor.text.get("1.0", "end-1c"))
    assert editor.text.get("1.0", "end-1c") == "AAXBBZZ"


def test_async_html_paste_falls_back_to_plain_clipboard_text_on_parse_failure(root, editor, monkeypatch):
    def failing(html, **kwargs):
        raise RuntimeError("malformed html")

    monkeypatch.setattr(content_editor_module, "html_to_blocks", failing)

    editor.clipboard_clear()
    editor.clipboard_append("texte de secours")

    editor._start_async_html_paste("<p>peu importe</p>")
    _pump_until(root, lambda: editor.text.get("1.0", "end-1c").strip() != "")
    assert editor.text.get("1.0", "end-1c") == "texte de secours"
