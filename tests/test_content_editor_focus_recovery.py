"""Regression test for the "disparition aleatoire du curseur" bug: every
stdlib dialog this editor opens (simpledialog.askstring, messagebox,
filedialog, ContentMetadataDialog) is built on tkinter.simpledialog.Dialog,
whose cancel()/ok() hand keyboard focus back to ``self.parent`` when the
dialog closes. Every call site here passes ``parent=self`` (the
ContentEditorWindow), never the text widget itself, so without the fix in
ContentEditorWindow._on_toplevel_focus_in the insertion caret simply stops
being drawn anywhere after any dialog use, until the user clicks back into
the editor by hand.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from bloggen.ui.content_editor import ContentEditorWindow


@pytest.fixture(scope="module")
def root(tk_root):
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


def test_dialog_handing_focus_to_the_window_redirects_it_to_the_text_widget(editor, monkeypatch):
    # This is exactly what tkinter.simpledialog.Dialog.cancel() does when
    # any of this editor's dialogs (insert link/image/footnote, metadata,
    # an error popup...) closes: "put focus back to the parent window".
    focus_calls = []
    monkeypatch.setattr(editor.text, "focus_set", lambda: focus_calls.append(True))

    editor._on_toplevel_focus_in(SimpleNamespace(widget=editor))

    assert focus_calls == [True]


def test_note_link_dialog_returns_focus_to_the_note_editor_not_the_main_text(root, editor, monkeypatch):
    # Real window-manager focus across several Toplevels in one test run
    # is too environment-dependent to assert on directly (see the sibling
    # test above, which checks it the one place it's actually reliable:
    # a single window's own internal focus redirect). Spy on focus_set()
    # instead: what matters here is which widget the note-link flow asks
    # Tk to focus, once the dialog it opened has already handed focus
    # back to the main window (simulated the same way as above).
    editor.footnote_definitions["1"] = [__import__(
        "bloggen.markdown.rich_text_model", fromlist=["InlineRun"]
    ).InlineRun(text="une note")]
    editor._refresh_notes_panel()
    root.update()

    note_widget = editor._footnote_text_widgets["1"]
    note_widget.tag_add("sel", "1.0", "1.3")

    monkeypatch.setattr(
        "bloggen.ui.content_editor.notes.simpledialog.askstring",
        lambda *a, **k: (editor.focus_set(), "https://example.org")[1],
    )
    focus_calls = []
    monkeypatch.setattr(note_widget, "focus_set", lambda: focus_calls.append(True))

    editor._insert_note_link(note_widget, "1")
    root.update()

    assert focus_calls, "note_widget.focus_set() was never called"
