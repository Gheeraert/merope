"""Headless tests for two notes-panel bugs:

- deleting a note from the panel (:meth:`ContentEditorWindow._delete_footnote`)
  used to be undone immediately by ``_refresh_notes_panel``'s own sync step,
  most visibly on an empty note.
- footnote ids drift out of the text's reading order as a human editor adds
  or removes footnote markers; :meth:`ContentEditorWindow._renumber_footnotes`
  (run at save time) must put them back in order 1, 2, 3, ...

Footnotes are inserted here the way the "Note..." dialog does it
(:meth:`ContentEditorWindow._register_new_footnote` +
:meth:`ContentEditorWindow._insert_footnote_marker`) rather than via the
"((note))" shorthand, which no longer converts live — see
:mod:`bloggen.markdown.note_shortcuts`.
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


def _insert_note(editor: ContentEditorWindow, text: str, note_text: str) -> None:
    """Insert ``text`` at the cursor, followed by a real footnote marker
    referencing a freshly-registered note containing ``note_text`` — the
    same effect the "Note..." dialog has, but without the modal prompt.
    """
    editor.text.insert("insert", text)
    note_id = editor._register_new_footnote(note_text)
    editor._insert_footnote_marker(editor.text.index("insert"), note_id)


def test_deleting_an_empty_note_actually_removes_it(editor):
    editor._insert_footnote_marker(editor.text.index("insert"), editor._register_new_footnote(""))
    editor._refresh_notes_panel()
    assert "1" in editor.footnote_definitions

    editor._delete_footnote("1")

    assert "1" not in editor.footnote_definitions


def test_deleting_a_note_with_text_actually_removes_it(editor):
    _insert_note(editor, "mot ", "une remarque")
    assert "1" in editor.footnote_definitions

    editor._delete_footnote("1")

    assert "1" not in editor.footnote_definitions


def test_renumber_reorders_notes_to_match_text_order(editor):
    # Register note "2" before note "1" is referenced later in the text,
    # simulating ids that drifted out of reading order.
    id_b = editor._register_new_footnote("second in text, registered first")
    editor._insert_footnote_marker(editor.text.index("insert"), id_b)
    editor.text.insert("insert", " puis ")
    id_a = editor._register_new_footnote("first in text, registered second")
    editor._insert_footnote_marker(editor.text.index("insert"), id_a)

    editor._renumber_footnotes()

    assert editor.text.get("1.0", "end-1c") == "[1] puis [2]"
    assert editor.footnote_definitions["1"] == [InlineRun(text="second in text, registered first")]
    assert editor.footnote_definitions["2"] == [InlineRun(text="first in text, registered second")]


def test_renumber_keeps_an_unreferenced_note_after_referenced_ones(editor):
    _insert_note(editor, "texte ", "note visible")
    orphan_id = editor._register_new_footnote("plus de renvoi dans le texte")

    editor._renumber_footnotes()

    assert editor.footnote_definitions["1"] == [InlineRun(text="note visible")]
    assert editor.footnote_definitions["2"] == [InlineRun(text="plus de renvoi dans le texte")]
    assert orphan_id not in editor.footnote_definitions or orphan_id == "2"


def test_renumber_is_noop_when_already_in_order(editor):
    _insert_note(editor, "un ", "premier")
    editor.text.insert("insert", " deux ")
    _insert_note(editor, "", "second")
    before_text = editor.text.get("1.0", "end-1c")

    editor._renumber_footnotes()

    assert editor.text.get("1.0", "end-1c") == before_text
    assert list(editor.footnote_definitions) == ["1", "2"]
