"""The Tkinter editor must open, show and save back percentage widths
written by the Qt editor ("50%"), while keeping its own pixel behaviour."""

from __future__ import annotations

import pytest
from PIL import Image

from bloggen.markdown.rich_text_model import PARAGRAPH, Block, InlineRun
from bloggen.ui.content_editor import ContentEditorWindow
from bloggen.ui.image_widget import ImageWidget


@pytest.fixture
def editor(tk_root, tmp_path):
    pages = tmp_path / "content" / "pages"
    posts = tmp_path / "content" / "posts"
    images = tmp_path / "assets" / "images"
    for directory in (pages, posts, images):
        directory.mkdir(parents=True)
    Image.new("RGB", (1400, 700), "navy").save(images / "photo.png")
    window = ContentEditorWindow(
        tk_root,
        pages_dir=pages,
        posts_dir=posts,
        images_dir=images,
        slugify_mode="ascii",
        project_root=tmp_path,
    )
    window.current_path = pages / "article.md"
    yield window
    window.destroy()


def _image_widgets(window) -> list[ImageWidget]:
    return [
        window.text.nametowidget(name)
        for name in window.text.window_names()
        if isinstance(window.text.nametowidget(name), ImageWidget)
    ]


def _load(window, run: InlineRun) -> None:
    window._populate_from_blocks([Block(kind=PARAGRAPH, runs=[run])])


def test_percent_width_is_displayed_and_saved_back_unchanged(editor):
    run = InlineRun(
        image_src="../../assets/images/photo.png",
        image_alt="Légende",
        image_width="50%",
        image_align="center",
    )

    _load(editor, run)

    (widget,) = _image_widgets(editor)
    assert (widget.width, widget.height) == (350, 175)
    assert editor.extract_blocks() == [Block(kind=PARAGRAPH, runs=[run])]


def test_resizing_in_tk_falls_back_to_pixels(editor):
    _load(editor, InlineRun(image_src="../../assets/images/photo.png", image_width="50%"))
    (widget,) = _image_widgets(editor)

    widget._start_resize(type("E", (), {"x_root": 0, "y_root": 0})(), "se")
    widget._do_resize(type("E", (), {"x_root": 50, "y_root": 0})())

    (block,) = editor.extract_blocks()
    image = block.runs[0]
    assert (image.image_width, image.image_height) == ("400", "200")


def test_legacy_width_alone_keeps_proportions(editor):
    _load(editor, InlineRun(image_src="../../assets/images/photo.png", image_width="300"))

    (widget,) = _image_widgets(editor)
    assert (widget.width, widget.height) == (300, 150)


def test_unusable_width_no_longer_crashes_the_editor(editor):
    _load(editor, InlineRun(image_src="../../assets/images/photo.png", image_width="auto"))

    assert len(_image_widgets(editor)) == 1
