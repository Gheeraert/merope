from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path

import pytest
from PIL import Image

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QTextCursor, QTextDocument
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog

from bloggen.content.writer import read_content_file, write_content_file
from bloggen.markdown.rich_text_export import blocks_to_markdown
from bloggen.markdown.rich_text_import import markdown_to_blocks
from bloggen.markdown.rich_text_model import PARAGRAPH, Block, InlineRun
from bloggen.ui.qt_editor.document_adapter import extract_blocks, populate_document
from bloggen.ui.qt_editor.file_io import load_content_document
from bloggen.ui.qt_editor.image_crop import (
    CropRect,
    calculate_crop_preview,
    initial_crop_rect,
    move_crop_corner,
    preview_rect_to_source_box,
    validate_source_box,
)
from bloggen.ui.qt_editor.image_crop_dialog import CropImageDialog
from bloggen.ui.qt_editor.image_selection import targeted_merope_image
from bloggen.ui.qt_editor import window as window_module
from bloggen.ui.qt_editor.window import QtEditorWindow


@pytest.fixture(scope="module", autouse=True)
def qapplication():
    app = QApplication.instance() or QApplication([])
    yield app


def _write_image(path, size=(100, 80), color=(40, 100, 180, 255)) -> bytes:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGBA", size, color)
    image.save(path)
    return path.read_bytes()


def _select(editor, start: int, end: int | None = None) -> None:
    cursor = QTextCursor(editor.document())
    cursor.setPosition(start)
    if end is not None:
        cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
    editor.setTextCursor(cursor)
    QApplication.processEvents()


def _window_with_run(tmp_path, run: InlineRun) -> tuple[QtEditorWindow, Path]:
    pages = tmp_path / "content" / "pages"
    body = blocks_to_markdown([Block(kind=PARAGRAPH, runs=[run])])
    path = write_content_file(pages, "article.md", {"title": "Article"}, body)
    window = QtEditorWindow(path)
    _select(window.editor, 0, 1)
    return window, path


def _close_without_prompt(window: QtEditorWindow) -> None:
    window.editor.document().setModified(False)
    window.close()


def test_preview_size_and_scale_use_original_dimensions():
    large = calculate_crop_preview(4000, 3000)
    assert large.scale == pytest.approx(0.175)
    assert (large.preview_width, large.preview_height) == (700, 525)

    small = calculate_crop_preview(400, 300)
    assert small.scale == 1.0
    assert (small.preview_width, small.preview_height) == (400, 300)


def test_initial_rectangle_has_approximately_ten_percent_margin():
    geometry = calculate_crop_preview(4000, 3000)
    rect = initial_crop_rect(geometry)

    assert rect == CropRect(70, 52, 630, 472)
    assert preview_rect_to_source_box(rect, geometry) == (400, 297, 3600, 2697)


def test_preview_borders_convert_to_exact_source_borders():
    geometry = calculate_crop_preview(4000, 3000)

    assert preview_rect_to_source_box(CropRect(0, 0, 700, 525), geometry) == (
        0,
        0,
        4000,
        3000,
    )


def test_preview_rounding_is_bounded_and_never_empty():
    geometry = calculate_crop_preview(1001, 777)
    box = preview_rect_to_source_box(CropRect(699, 542, 700, 543), geometry)

    assert box == (1000, 776, 1001, 777)
    assert validate_source_box(box, 1001, 777) == box


@pytest.mark.parametrize(
    ("corner", "point", "expected"),
    [
        ("nw", QPoint(1000, 1000), CropRect(580, 430, 600, 450)),
        ("ne", QPoint(-10, 1000), CropRect(100, 430, 120, 450)),
        ("sw", QPoint(1000, -10), CropRect(580, 80, 600, 100)),
        ("se", QPoint(-10, -10), CropRect(100, 80, 120, 100)),
    ],
)
def test_each_corner_respects_minimum_size(corner, point, expected):
    geometry = calculate_crop_preview(700, 525)
    rect = CropRect(100, 80, 600, 450)

    assert move_crop_corner(rect, corner, point.x(), point.y(), geometry) == expected


def test_corner_drag_is_free_ratio_and_bounded_inside_preview():
    geometry = calculate_crop_preview(700, 525)
    rect = CropRect(100, 80, 600, 450)

    changed = move_crop_corner(rect, "se", 690, 300, geometry)
    assert changed == CropRect(100, 80, 690, 300)
    assert changed.width / changed.height != pytest.approx(rect.width / rect.height)

    bounded = move_crop_corner(changed, "nw", -200, -100, geometry)
    assert bounded == CropRect(0, 0, 690, 300)


def test_source_box_validation_rejects_empty_or_out_of_bounds_boxes():
    for box in ((0, 0, 0, 10), (-1, 0, 10, 10), (0, 0, 101, 10)):
        with pytest.raises(ValueError):
            validate_source_box(box, 100, 80)


def test_dialog_corner_drag_updates_crop_without_creating_file(tmp_path):
    source = tmp_path / "photo.png"
    _write_image(source)
    dialog = CropImageDialog(source)
    dialog.show()
    QApplication.processEvents()
    initial = dialog.preview.crop_rect
    handle = dialog.preview.handle_rects()["nw"].center()
    destination = QPoint(initial.left + 15, initial.top + 12)

    QTest.mousePress(dialog.preview, Qt.MouseButton.LeftButton, pos=handle)
    QTest.mouseMove(dialog.preview, destination, delay=1)
    QTest.mouseRelease(dialog.preview, Qt.MouseButton.LeftButton, pos=destination)

    assert dialog.preview.crop_rect == CropRect(
        destination.x(),
        destination.y(),
        initial.right,
        initial.bottom,
    )
    assert dialog.crop_box() == (
        destination.x(),
        destination.y(),
        initial.right,
        initial.bottom,
    )
    assert list(tmp_path.glob("*-crop*.png")) == []
    dialog.close()


def test_real_crop_changes_only_src_and_preserves_original_and_metadata(tmp_path):
    source = tmp_path / "assets" / "images" / "bossuet.png"
    original_bytes = _write_image(source)
    run = InlineRun(
        image_src="../../assets/images/bossuet.png",
        image_alt="**Bossuet** à *Meaux*",
        image_width="300",
        image_height="200",
        image_align="center",
    )
    window, _path = _window_with_run(tmp_path, run)
    window._update_image_action()

    assert window.crop_image_action.isEnabled()

    assert window.crop_targeted_image((10, 5, 80, 55))

    crop_path = source.with_name("bossuet-crop1.png")
    changed = targeted_merope_image(window.editor.textCursor()).run
    assert changed == replace(
        run,
        image_src="../../assets/images/bossuet-crop1.png",
    )
    assert source.read_bytes() == original_bytes
    assert crop_path.is_file()
    with Image.open(crop_path) as cropped:
        assert cropped.size == (70, 50)
    assert window.editor.document().isModified()
    assert window.windowTitle().endswith("*")

    window.editor.undo()
    assert extract_blocks(window.editor.document()) == [
        Block(kind=PARAGRAPH, runs=[run])
    ]
    assert crop_path.is_file()
    assert not window.editor.document().isUndoAvailable()
    window.editor.redo()
    assert targeted_merope_image(window.editor.textCursor()).run == changed
    _close_without_prompt(window)


def test_crop_survives_save_and_reopen(tmp_path):
    source = tmp_path / "assets" / "images" / "photo.png"
    _write_image(source)
    run = InlineRun(
        image_src="../../assets/images/photo.png",
        image_alt="Légende",
        image_width="50%",
        image_height=None,
        image_align="right",
    )
    window, path = _window_with_run(tmp_path, run)

    assert window.crop_targeted_image((0, 0, 60, 40))
    changed = targeted_merope_image(window.editor.textCursor()).run
    assert window.save_document()

    metadata, body = read_content_file(path)
    assert metadata == {"title": "Article"}
    assert markdown_to_blocks(body) == [Block(kind=PARAGRAPH, runs=[changed])]
    reopened = QTextDocument()
    load_content_document(path, reopened)
    assert extract_blocks(reopened) == [Block(kind=PARAGRAPH, runs=[changed])]
    window.close()


def test_successive_crops_and_existing_collision_follow_service_names(tmp_path):
    source = tmp_path / "assets" / "images" / "photo.png"
    _write_image(source)
    _write_image(source.with_name("photo-crop1.png"), color=(200, 20, 20, 255))
    run = InlineRun(image_src="../../assets/images/photo.png", image_alt="Image")
    window, _path = _window_with_run(tmp_path, run)

    assert window.crop_targeted_image((0, 0, 80, 60))
    first = targeted_merope_image(window.editor.textCursor()).run
    assert first.image_src == "../../assets/images/photo-crop2.png"
    assert window.crop_targeted_image((0, 0, 40, 30))
    second = targeted_merope_image(window.editor.textCursor()).run
    assert second.image_src == "../../assets/images/photo-crop2-crop1.png"
    assert source.with_name("photo-crop2-crop1.png").is_file()
    _close_without_prompt(window)


def test_two_occurrences_of_same_src_are_cropped_by_target_range(tmp_path):
    source = tmp_path / "assets" / "images" / "photo.png"
    _write_image(source)
    image_a = InlineRun(image_src="../../assets/images/photo.png", image_alt="A")
    image_b = InlineRun(image_src="../../assets/images/photo.png", image_alt="B")
    window, _path = _window_with_run(tmp_path, image_a)
    original = [
        Block(
            kind=PARAGRAPH,
            runs=[image_a, InlineRun(text=" milieu "), image_b],
        )
    ]
    populate_document(window.editor.document(), original)
    window.editor.document().setModified(False)
    _select(window.editor, 0, 1)

    assert window.crop_targeted_image((10, 10, 90, 70))

    changed_a = replace(
        image_a,
        image_src="../../assets/images/photo-crop1.png",
    )
    assert extract_blocks(window.editor.document()) == [
        Block(
            kind=PARAGRAPH,
            runs=[changed_a, InlineRun(text=" milieu "), image_b],
        )
    ]
    window.editor.undo()
    assert extract_blocks(window.editor.document()) == original
    window.close()


@pytest.mark.parametrize(
    ("image_src", "create_invalid_file"),
    [
        ("../../assets/images/missing.png", False),
        ("../../assets/images/not-image.png", True),
        ("https://example.test/photo.png", False),
    ],
)
def test_missing_unreadable_and_remote_sources_are_not_croppable(
    tmp_path,
    image_src,
    create_invalid_file,
):
    if create_invalid_file:
        invalid = tmp_path / "assets" / "images" / "not-image.png"
        invalid.parent.mkdir(parents=True)
        invalid.write_text("not an image", encoding="utf-8")
    run = InlineRun(image_src=image_src, image_alt="Image")
    window, _path = _window_with_run(tmp_path, run)
    window._update_image_action()

    assert window.image_action.isEnabled()
    assert window.replace_image_action.isEnabled()
    assert window.crop_image_action.isEnabled() is False
    with pytest.raises(ValueError, match="source local lisible"):
        window.crop_targeted_image((0, 0, 10, 10))
    assert not window.editor.document().isModified()
    window.close()


def test_crop_dialog_cancellation_creates_nothing_and_is_clean(tmp_path, monkeypatch):
    source = tmp_path / "assets" / "images" / "photo.png"
    _write_image(source)
    run = InlineRun(image_src="../../assets/images/photo.png")
    window, _path = _window_with_run(tmp_path, run)

    class CancelledDialog:
        def __init__(self, source_path, parent):
            assert source_path == source.resolve()
            assert parent is window

        def exec(self):
            return QDialog.DialogCode.Rejected

        def crop_box(self):
            raise AssertionError("Une annulation ne doit pas demander la boîte")

    monkeypatch.setattr(window_module, "CropImageDialog", CancelledDialog)

    assert window._crop_image_from_dialog() is False
    assert list(source.parent.glob("photo-crop*.png")) == []
    assert not window.editor.document().isModified()
    assert not window.editor.document().isUndoAvailable()
    window.close()


def test_write_failure_keeps_document_unchanged(tmp_path, monkeypatch):
    source = tmp_path / "assets" / "images" / "photo.png"
    _write_image(source)
    run = InlineRun(image_src="../../assets/images/photo.png", image_alt="Image")
    window, _path = _window_with_run(tmp_path, run)

    def fail_write(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(window_module, "write_cropped_copy", fail_write)

    with pytest.raises(OSError, match="disk full"):
        window.crop_targeted_image((0, 0, 50, 40))
    assert extract_blocks(window.editor.document()) == [
        Block(kind=PARAGRAPH, runs=[run])
    ]
    assert not window.editor.document().isModified()
    window.close()
