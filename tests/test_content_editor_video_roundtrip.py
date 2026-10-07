"""The legacy Tk editor must keep an embedded video created with Qt intact."""

from __future__ import annotations

import pytest

from bloggen.markdown.rich_text_export import blocks_to_markdown
from bloggen.markdown.rich_text_import import markdown_to_blocks
from bloggen.markdown.video_syntax import format_video_block
from bloggen.ui.content_editor import ContentEditorWindow

VALID_ID = "dQw4w9WgXcQ"

BODY = (
    "Avant.\n\n"
    + format_video_block(VALID_ID, "Une légende.")
    + "\n\n"
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


def test_tk_open_then_save_keeps_the_video_byte_for_byte(editor):
    editor._populate_from_blocks(markdown_to_blocks(BODY))

    assert blocks_to_markdown(editor.extract_blocks()) == BODY


def test_tk_shows_the_video_as_protected_source_not_as_lost_content(editor):
    editor._populate_from_blocks(markdown_to_blocks(BODY))

    shown = editor.text.get("1.0", "end")
    assert f'data-video-id="{VALID_ID}"' in shown
    assert "Une légende." in shown
