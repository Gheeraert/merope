"""Headless tests for ContentEditorWindow._autoformat_double_paren_note
(the live-typing "((note))" -> real footnote shorthand).

Uses the same technique as tests/test_menu_link_dialog.py: instantiate a
real ContentEditorWindow, drive its Text widget directly, and call the
autoformat method the same way <<KeyRelease>> would.
"""

from __future__ import annotations

import pytest

from bloggen.markdown.rich_text_model import InlineRun
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
    """Insert text at the cursor and run the same autoformat hook a real
    keystroke would trigger, one character at a time (so the "))"-anchored
    regex the method relies on sees it complete mid-stream, exactly as
    while typing)."""
    for char in text:
        editor.text.insert("insert", char)
        if char == ")":
            editor._autoformat_double_paren_note()


def test_plain_note_converts_to_a_footnote_reference(editor):
    _type(editor, "mot ((une remarque)) suite")

    assert editor.text.get("1.0", "end-1c") == "mot [1] suite"
    assert editor.footnote_definitions["1"] == [InlineRun(text="une remarque")]


def test_italic_text_typed_inside_the_note_is_preserved(editor):
    """Regression: formatting (e.g. an italicized title) typed inside
    ((...)) used to be lost — the note was read back as plain text via
    Text.get(), discarding all Tk tags.
    """
    editor.text.insert("insert", "voir ((")
    start = editor.text.index("insert")
    editor.text.insert("insert", "Le Titre")
    end = editor.text.index("insert")
    editor.text.tag_add("italic", start, end)
    editor.text.insert("insert", " pour plus))")
    editor._autoformat_double_paren_note()

    assert editor.text.get("1.0", "end-1c") == "voir [1]"
    note_runs = editor.footnote_definitions["1"]
    assert [(run.text, run.italic) for run in note_runs] == [
        ("Le Titre", True),
        (" pour plus", False),
    ]


def test_note_glued_to_closing_punctuation_converts(editor):
    _type(editor, "Une phrase avec une note((ceci est la note)). Suite.")

    assert editor.text.get("1.0", "end-1c") == "Une phrase avec une note[1]. Suite."
    assert editor.footnote_definitions["1"][0].text == "ceci est la note"


def test_empty_note_is_left_alone(editor):
    _type(editor, "mot (( )) suite")

    assert editor.text.get("1.0", "end-1c") == "mot (( )) suite"
    assert not editor.footnote_definitions
