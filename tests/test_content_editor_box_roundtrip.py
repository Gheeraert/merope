"""The legacy Tk editor must keep an encadré created with Qt intact."""

from __future__ import annotations

import pytest

from bloggen.markdown.rich_text_export import blocks_to_markdown
from bloggen.markdown.rich_text_import import markdown_to_blocks
from bloggen.ui.content_editor import ContentEditorWindow

BODY = (
    "Avant.\n\n"
    ":::: {.merope-encadre}\n"
    "::: {.merope-encadre-titre}\nÀ retenir\n:::\n\n"
    "Premier paragraphe.\n\n"
    "Deuxième **gras**.\n"
    "::::\n\n"
    "Après.\n"
)


@pytest.fixture
def editor(tk_root, tmp_path):
    (tmp_path / "content" / "pages").mkdir(parents=True)
    (tmp_path / "content" / "posts").mkdir(parents=True)
    window = ContentEditorWindow(
        tk_root,
        pages_dir=tmp_path / "content" / "pages",
        posts_dir=tmp_path / "content" / "posts",
        images_dir=tmp_path / "assets" / "images",
        slugify_mode="ascii",
    )
    yield window
    window.destroy()


def test_tk_open_then_save_keeps_the_box_byte_for_byte(editor):
    editor._populate_from_blocks(markdown_to_blocks(BODY))

    assert blocks_to_markdown(editor.extract_blocks()) == BODY


def test_tk_shows_the_box_as_protected_source_not_as_lost_content(editor):
    editor._populate_from_blocks(markdown_to_blocks(BODY))

    shown = editor.text.get("1.0", "end")
    assert ":::: {.merope-encadre}" in shown
    assert "Premier paragraphe." in shown
    assert "Deuxième **gras**." in shown
