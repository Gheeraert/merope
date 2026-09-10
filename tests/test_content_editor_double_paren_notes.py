"""Headless tests confirming the "((note))" shorthand is now left as
literal text while typing in the editor, instead of being auto-converted
to a footnote reference — see :mod:`bloggen.markdown.note_shortcuts` for
why (formatting options must keep working on the note's text while it is
still being written) and where the conversion now actually happens
(Markdown normalization, at preview/build time).

Uses the same technique as tests/test_menu_link_dialog.py: instantiate a
real ContentEditorWindow and drive its Text widget directly.
"""

from __future__ import annotations

import pytest

from bloggen.ui.content_editor import ContentEditorWindow


@pytest.fixture
def editor(tk_root, tmp_path):
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


def _type(editor: ContentEditorWindow, text: str) -> None:
    """Insert text at the cursor one character at a time, exactly as real
    keystrokes would (whitespace/typography autoformat still applies, just
    not any ((note)) conversion)."""
    for char in text:
        editor.text.insert("insert", char)


def test_note_shorthand_stays_literal_while_typing(editor):
    _type(editor, "mot ((une remarque)) suite")

    assert editor.text.get("1.0", "end-1c") == "mot ((une remarque)) suite"
    assert not editor.footnote_definitions


def test_note_glued_to_closing_punctuation_stays_literal(editor):
    _type(editor, "Une phrase avec une note((ceci est la note)). Suite.")

    assert (
        editor.text.get("1.0", "end-1c")
        == "Une phrase avec une note((ceci est la note)). Suite."
    )
    assert not editor.footnote_definitions


def test_italic_text_typed_inside_a_note_shorthand_keeps_its_formatting(editor):
    """The whole point of leaving the shorthand literal: formatting typed
    inside ((...)) (e.g. an italicized title) is ordinary Tk formatting on
    ordinary text, so it survives untouched — nothing needs to specially
    carry it into a footnote definition anymore.
    """
    editor.text.insert("insert", "voir ((")
    start = editor.text.index("insert")
    editor.text.insert("insert", "Le Titre")
    end = editor.text.index("insert")
    editor.text.tag_add("italic", start, end)
    editor.text.insert("insert", " pour plus))")

    assert editor.text.get("1.0", "end-1c") == "voir ((Le Titre pour plus))"
    assert "italic" in editor.text.tag_names(start)
    assert not editor.footnote_definitions
