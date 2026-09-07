"""The custom _undo_stack/_redo_stack tracked alongside Tk's own undo
mechanism (see content_editor.py's _on_text_modified/_push_format_undo)
previously grew without any bound for the length of an editing session.
Both are now capped, and Tk's own native undo history is capped the same
way via -maxundo.
"""

from __future__ import annotations

import pytest

from bloggen.ui import content_editor as content_editor_module
from bloggen.ui.content_editor import ContentEditorWindow


@pytest.fixture
def editor(tk_root, tmp_path, monkeypatch):
    # A much smaller cap than production's 500 keeps this test fast while
    # still exercising the real trimming logic — the Text widget reads
    # the module constant at construction time, so this must be patched
    # before the window is built.
    monkeypatch.setattr(content_editor_module, "_MAX_UNDO_HISTORY", 20)

    pages_dir = tmp_path / "content" / "pages"
    posts_dir = tmp_path / "content" / "posts"
    images_dir = tmp_path / "assets" / "images"
    pages_dir.mkdir(parents=True)
    posts_dir.mkdir(parents=True)

    window = ContentEditorWindow(
        tk_root, pages_dir=pages_dir, posts_dir=posts_dir, images_dir=images_dir, slugify_mode="ascii"
    )
    yield window
    window.destroy()


def test_text_widget_native_undo_history_is_capped(editor):
    assert int(editor.text.cget("maxundo")) == content_editor_module._MAX_UNDO_HISTORY


def test_undo_stack_never_exceeds_the_cap_across_many_edits(editor):
    cap = content_editor_module._MAX_UNDO_HISTORY
    # Each iteration alternates insert/delete, which is what makes
    # _on_text_modified start a NEW "text" marker every time (consecutive
    # edits of the SAME kind are coalesced into one) — this is the
    # fastest way to actually grow the stack, not just poke at it.
    for i in range(cap * 3):
        editor.text.insert("insert", "x")
        editor.update()
        editor.text.delete("insert-1c", "insert")
        editor.update()

    assert len(editor._undo_stack) <= cap


def test_redo_stack_never_exceeds_the_cap_after_many_undos(editor):
    cap = content_editor_module._MAX_UNDO_HISTORY
    for i in range(cap * 3):
        editor.text.insert("insert", "x")
        editor.update()
        editor.text.delete("insert-1c", "insert")
        editor.update()

    for _ in range(len(editor._undo_stack)):
        editor._perform_undo()

    assert len(editor._redo_stack) <= cap


def test_push_format_undo_also_respects_the_cap(editor):
    cap = content_editor_module._MAX_UNDO_HISTORY
    for _ in range(cap * 3):
        editor._push_format_undo(lambda: None, lambda: None)

    assert len(editor._undo_stack) <= cap
