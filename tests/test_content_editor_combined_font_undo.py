"""formatting._refresh_combined_fonts patches over Tk's inability to merge
overlapping bold/italic/heading font specs (see the _COMBINED_FONT_TAG_PREFIX
comment in formatting.py) by maintaining derived cf_* tags. Those tags must
stay in sync whenever the underlying h1-h4/bold/italic tags change —
including through undo/redo and "remise à zéro" (_set_paragraph_normal),
which don't go through the toolbar commands that originally triggered the
refresh.
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


def _has_combined_font_tag(editor, index: str) -> bool:
    return any(name.startswith("cf_") for name in editor.text.tag_names(index))


def _make_heading_with_partial_italic(editor) -> tuple[str, str]:
    """Types "Titre exemple" as an h2, then italicizes "exemple" — the
    scenario from the reported symptom. Returns the (start, end) range of
    the italicized word.
    """
    editor.text.insert("1.0", "Titre exemple")
    editor.text.mark_set("insert", "1.0")
    editor._toggle_line_tag("h2")

    start, end = "1.6", "1.13"  # "exemple"
    editor.text.tag_add("sel", start, end)
    editor._toggle_char_tag("italic")
    editor.text.tag_remove("sel", "1.0", "end")
    return start, end


def test_partial_italic_in_heading_gets_a_combined_font_tag(editor):
    start, _end = _make_heading_with_partial_italic(editor)
    assert _has_combined_font_tag(editor, start)


def test_undo_of_italic_removes_the_stale_combined_font_tag(editor):
    start, _end = _make_heading_with_partial_italic(editor)
    assert _has_combined_font_tag(editor, start)

    editor._perform_undo()  # undoes the italic toggle (a "format" entry)

    assert "italic" not in editor.text.tag_names(start)
    assert not _has_combined_font_tag(editor, start)


def test_redo_of_italic_restores_the_combined_font_tag(editor):
    start, _end = _make_heading_with_partial_italic(editor)
    editor._perform_undo()
    assert not _has_combined_font_tag(editor, start)

    editor._perform_redo()

    assert "italic" in editor.text.tag_names(start)
    assert _has_combined_font_tag(editor, start)


def test_reset_to_normal_paragraph_clears_the_combined_font_tag(editor):
    start, _end = _make_heading_with_partial_italic(editor)
    assert _has_combined_font_tag(editor, start)

    editor.text.mark_set("insert", start)
    editor._set_paragraph_normal()

    assert "h2" not in editor.text.tag_names(start)
    assert "italic" not in editor.text.tag_names(start)
    assert not _has_combined_font_tag(editor, start)
