from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path

import pytest
from PIL import Image

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent, QTextCursor, QTextDocument
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog

from bloggen.content import image_service
from bloggen.content.writer import read_content_file, write_content_file
from bloggen.markdown.rich_text_export import blocks_to_markdown
from bloggen.markdown.rich_text_import import markdown_to_blocks
from bloggen.markdown.rich_text_model import PARAGRAPH, Block, InlineRun
from bloggen.ui.qt_editor.document_adapter import extract_blocks, populate_document
from bloggen.ui.qt_editor.file_io import load_content_document
from bloggen.ui.qt_editor.image_crop import (
    MIN_CROP_SIZE,
    CropRect,
    constrain_to_ratio,
    draw_rect,
    fit_ratio,
    full_rect,
    move_rect,
    preset_ratio,
    resize_rect,
    rotate_rect,
    validate_source_box,
)
from bloggen.ui.qt_editor.image_crop_dialog import CropImageDialog, CropRequest
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


def _shown_dialog(source: Path, size=(1000, 700)) -> CropImageDialog:
    dialog = CropImageDialog(source)
    dialog.resize(*size)
    dialog.show()
    QApplication.processEvents()
    return dialog


def _drag(widget, start: QPointF, end: QPointF, modifier=Qt.KeyboardModifier.NoModifier):
    QTest.mousePress(widget, Qt.MouseButton.LeftButton, modifier, start.toPoint())
    # QTest.mouseMove cannot carry keyboard modifiers: send the move by hand.
    move = QMouseEvent(
        QEvent.Type.MouseMove,
        QPointF(end.toPoint()),
        widget.mapToGlobal(QPointF(end.toPoint())),
        Qt.MouseButton.NoButton,
        Qt.MouseButton.LeftButton,
        modifier,
    )
    QApplication.sendEvent(widget, move)
    QTest.mouseRelease(widget, Qt.MouseButton.LeftButton, modifier, end.toPoint())
    QApplication.processEvents()


# -- pure geometry -----------------------------------------------------------


def test_selection_starts_on_the_whole_image():
    assert full_rect(4000, 3000) == CropRect(0, 0, 4000, 3000)
    with pytest.raises(ValueError):
        full_rect(0, 10)


def test_move_keeps_size_and_stops_at_borders():
    rect = CropRect(10, 10, 60, 40)

    assert move_rect(rect, 5, -3, 100, 80) == CropRect(15, 7, 65, 37)
    assert move_rect(rect, 500, 500, 100, 80) == CropRect(50, 50, 100, 80)
    assert move_rect(rect, -500, -500, 100, 80) == CropRect(0, 0, 50, 30)


@pytest.mark.parametrize(
    ("handle", "point", "expected"),
    [
        ("nw", (1000, 1000), CropRect(600 - MIN_CROP_SIZE, 450 - MIN_CROP_SIZE, 600, 450)),
        ("se", (-10, -10), CropRect(100, 80, 100 + MIN_CROP_SIZE, 80 + MIN_CROP_SIZE)),
        ("n", (300, 20), CropRect(100, 20, 600, 450)),
        ("s", (0, 500), CropRect(100, 80, 600, 500)),
        ("e", (650, 0), CropRect(100, 80, 650, 450)),
        ("w", (-40, 0), CropRect(0, 80, 600, 450)),
    ],
)
def test_free_handles_move_only_their_sides_and_never_cross(handle, point, expected):
    rect = CropRect(100, 80, 600, 450)

    assert resize_rect(rect, handle, *point, 700, 525) == expected


def test_corner_with_ratio_keeps_proportions_and_stays_inside():
    rect = CropRect(100, 100, 300, 250)

    grown = resize_rect(rect, "se", 900, 280, 1000, 600, ratio=16 / 9)
    assert grown.left == 100 and grown.top == 100
    assert grown.width / grown.height == pytest.approx(16 / 9, rel=0.02)
    assert grown.right <= 1000 and grown.bottom <= 600

    shrunk = resize_rect(rect, "nw", 290, 240, 1000, 600, ratio=1.0)
    assert (shrunk.right, shrunk.bottom) == (300, 250)
    assert shrunk.width == shrunk.height >= MIN_CROP_SIZE


def test_edge_with_ratio_grows_symmetrically_around_centre():
    rect = CropRect(400, 200, 600, 400)

    result = resize_rect(rect, "e", 800, 300, 1000, 1000, ratio=1.0)

    assert result.left == 400
    assert result.width == result.height == 400
    assert (result.top + result.bottom) / 2 == pytest.approx(300, abs=1)


def test_drawing_works_in_every_direction_with_minimum_and_ratio():
    assert draw_rect(50, 40, 20, 10, 100, 80) == CropRect(20, 10, 50, 40)
    assert draw_rect(50, 40, 51, 41, 100, 80) == CropRect(50, 40, 58, 48)
    square = draw_rect(10, 10, 60, 30, 100, 80, ratio=1.0)
    assert square == CropRect(10, 10, 60, 60)


def test_ratio_presets_fit_largest_centred_rectangle():
    assert preset_ratio(0, 400, 300) is None
    assert preset_ratio(1, 400, 300) == pytest.approx(4 / 3)
    assert preset_ratio(2, 400, 300) == 1.0
    image = full_rect(400, 300)

    assert fit_ratio(image, 1.0, 400, 300) == CropRect(50, 0, 350, 300)
    # Centred on the selection, then pushed back inside the image.
    assert fit_ratio(CropRect(0, 0, 40, 40), 16 / 9, 400, 300) == CropRect(0, 0, 400, 225)
    assert constrain_to_ratio(CropRect(0, 0, 200, 100), 1.0, 400, 300) == CropRect(50, 0, 150, 100)


def test_quarter_turns_map_the_selection_and_four_turns_are_identity():
    rect = CropRect(10, 20, 40, 30)

    clockwise = rotate_rect(rect, 100, 80, clockwise=True)
    assert clockwise == CropRect(50, 10, 60, 40)
    assert rotate_rect(clockwise, 80, 100, clockwise=False) == rect
    turned = rect
    size = (100, 80)
    for _ in range(4):
        turned = rotate_rect(turned, *size, clockwise=True)
        size = (size[1], size[0])
    assert turned == rect


def test_source_box_validation_rejects_empty_or_out_of_bounds_boxes():
    for box in ((0, 0, 0, 10), (-1, 0, 10, 10), (0, 0, 101, 10), (0, 0, 10.0, 10)):
        with pytest.raises(ValueError):
            validate_source_box(box, 100, 80)


# -- dialog ------------------------------------------------------------------


def test_dialog_opens_on_whole_image_and_never_writes(tmp_path):
    source = tmp_path / "photo.png"
    _write_image(source, size=(400, 300))
    dialog = _shown_dialog(source)

    assert dialog.crop_request() == CropRequest((0, 0, 400, 300), 0)
    assert (dialog.width_spin.value(), dialog.height_spin.value()) == (400, 300)
    assert "400 × 300 px" in dialog.size_label.text()
    dialog.close()
    assert sorted(path.name for path in tmp_path.iterdir()) == ["photo.png"]


def test_dragging_a_corner_handle_resizes_in_real_pixels(tmp_path):
    source = tmp_path / "photo.png"
    _write_image(source, size=(400, 300))
    dialog = _shown_dialog(source)
    canvas = dialog.canvas

    _drag(canvas, canvas.handle_points()["nw"], canvas.to_view(100, 60))

    rect = canvas.crop_rect
    assert rect.left == pytest.approx(100, abs=2)
    assert rect.top == pytest.approx(60, abs=2)
    assert (rect.right, rect.bottom) == (400, 300)
    assert dialog.x_spin.value() == rect.left
    dialog.close()


def test_dragging_inside_moves_and_outside_draws(tmp_path):
    source = tmp_path / "photo.png"
    _write_image(source, size=(400, 300))
    dialog = _shown_dialog(source)
    canvas = dialog.canvas
    canvas.set_crop_rect(CropRect(100, 100, 200, 180))

    _drag(canvas, canvas.to_view(150, 140), canvas.to_view(200, 160))
    moved = canvas.crop_rect
    assert (moved.width, moved.height) == (100, 80)
    assert moved.left == pytest.approx(150, abs=2)

    _drag(canvas, canvas.to_view(10, 10), canvas.to_view(60, 40))
    drawn = canvas.crop_rect
    assert drawn.left == pytest.approx(10, abs=2)
    assert drawn.right == pytest.approx(60, abs=2)
    dialog.close()


def test_shift_drag_keeps_current_proportions(tmp_path):
    source = tmp_path / "photo.png"
    _write_image(source, size=(400, 300))
    dialog = _shown_dialog(source)
    canvas = dialog.canvas
    canvas.set_crop_rect(CropRect(0, 0, 200, 100))

    _drag(
        canvas,
        canvas.handle_points()["se"],
        canvas.to_view(300, 120),
        Qt.KeyboardModifier.ShiftModifier,
    )

    rect = canvas.crop_rect
    assert rect.width / rect.height == pytest.approx(2.0, rel=0.03)
    dialog.close()


def test_ratio_preset_inversion_and_numeric_fields(tmp_path):
    source = tmp_path / "photo.png"
    _write_image(source, size=(400, 300))
    dialog = _shown_dialog(source)

    dialog.ratio_combo.setCurrentIndex(5)  # 16:9
    rect = dialog.canvas.crop_rect
    assert rect.width / rect.height == pytest.approx(16 / 9, rel=0.02)
    assert dialog.invert_ratio_button.isEnabled()
    dialog.invert_ratio_button.click()
    rect = dialog.canvas.crop_rect
    assert rect.height / rect.width == pytest.approx(16 / 9, rel=0.02)

    dialog.ratio_combo.setCurrentIndex(0)
    dialog.x_spin.setValue(20)
    dialog.width_spin.setValue(120)
    assert dialog.canvas.crop_rect.left == 20
    assert dialog.canvas.crop_rect.width == 120
    dialog.close()


def test_arrow_keys_nudge_and_double_click_accepts(tmp_path):
    source = tmp_path / "photo.png"
    _write_image(source, size=(400, 300))
    dialog = _shown_dialog(source)
    canvas = dialog.canvas
    canvas.set_crop_rect(CropRect(100, 100, 200, 200))
    canvas.setFocus()

    QTest.keyClick(canvas, Qt.Key.Key_Right)
    QTest.keyClick(canvas, Qt.Key.Key_Down, Qt.KeyboardModifier.ShiftModifier)
    assert canvas.crop_rect == CropRect(101, 110, 201, 210)

    QTest.mouseDClick(canvas, Qt.MouseButton.LeftButton, pos=canvas.to_view(150, 160).toPoint())
    assert dialog.result() == QDialog.DialogCode.Accepted


def test_rotation_swaps_dimensions_and_reset_restores_everything(tmp_path):
    source = tmp_path / "photo.png"
    _write_image(source, size=(400, 300))
    dialog = _shown_dialog(source)

    dialog.rotate_right_button.click()
    assert dialog.crop_request() == CropRequest((0, 0, 300, 400), 1)
    assert "300 × 400 px" in dialog.size_label.text()
    dialog.rotate_left_button.click()
    dialog.rotate_left_button.click()
    assert dialog.crop_request().quarter_turns == 3

    dialog.canvas.set_crop_rect(CropRect(10, 10, 50, 50))
    dialog.reset_button.click()
    assert dialog.crop_request() == CropRequest((0, 0, 400, 300), 0)
    dialog.close()


def test_dialog_shows_exif_oriented_photo(tmp_path):
    source = tmp_path / "phone.jpg"
    exif = Image.Exif()
    exif[0x0112] = 6
    Image.new("RGB", (400, 300), "white").save(source, exif=exif)

    dialog = _shown_dialog(source)

    assert dialog.canvas.source_size == (300, 400)
    dialog.close()


# -- window integration --------------------------------------------------------


def test_real_crop_changes_src_drops_stale_height_and_is_one_undo(tmp_path):
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
        image_height=None,
    )
    assert source.read_bytes() == original_bytes
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


def test_whole_unrotated_selection_is_a_clean_noop(tmp_path):
    source = tmp_path / "assets" / "images" / "photo.png"
    _write_image(source)
    run = InlineRun(image_src="../../assets/images/photo.png")
    window, _path = _window_with_run(tmp_path, run)

    assert window.crop_targeted_image((0, 0, 100, 80)) is False
    assert list(source.parent.glob("photo-crop*.png")) == []
    assert not window.editor.document().isModified()
    window.close()


def test_rotation_only_writes_a_rotated_copy(tmp_path):
    source = tmp_path / "assets" / "images" / "photo.png"
    _write_image(source, size=(100, 80))
    window, _path = _window_with_run(
        tmp_path, InlineRun(image_src="../../assets/images/photo.png", image_width="40%")
    )
    run = targeted_merope_image(window.editor.textCursor()).run

    assert window.crop_targeted_image((0, 0, 80, 100), quarter_turns=1)

    changed = targeted_merope_image(window.editor.textCursor()).run
    assert changed == replace(run, image_src="../../assets/images/photo-crop1.png")
    with Image.open(source.with_name("photo-crop1.png")) as rotated:
        assert rotated.size == (80, 100)
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
    assert "{width=50% align=right}" in body
    assert markdown_to_blocks(body) == [Block(kind=PARAGRAPH, runs=[changed])]
    reopened = QTextDocument()
    load_content_document(path, reopened)
    assert extract_blocks(reopened) == [Block(kind=PARAGRAPH, runs=[changed])]
    window.close()


def test_successive_crops_number_copies_without_chaining(tmp_path):
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
    assert second.image_src == "../../assets/images/photo-crop3.png"
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


def test_cursor_moves_do_not_reread_the_image_file(tmp_path, monkeypatch):
    source = tmp_path / "assets" / "images" / "photo.png"
    _write_image(source)
    run = InlineRun(image_src="../../assets/images/photo.png")
    window, _path = _window_with_run(tmp_path, run)
    window._update_image_action()
    opened = []
    real_open = image_service.Image.open
    monkeypatch.setattr(
        image_service.Image,
        "open",
        lambda *args, **kwargs: opened.append(args) or real_open(*args, **kwargs),
    )

    for position in (0, 1, 0, 1):
        _select(window.editor, position)
        window._update_image_action()

    assert opened == []
    assert window.crop_image_action.isEnabled()
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

        def crop_request(self):
            raise AssertionError("Une annulation ne doit pas demander la boîte")

    monkeypatch.setattr(window_module, "CropImageDialog", CancelledDialog)

    assert window._crop_image_from_dialog() is False
    assert list(source.parent.glob("photo-crop*.png")) == []
    assert not window.editor.document().isModified()
    assert not window.editor.document().isUndoAvailable()
    window.close()


def test_accepted_dialog_request_is_applied_with_rotation(tmp_path, monkeypatch):
    source = tmp_path / "assets" / "images" / "photo.png"
    _write_image(source, size=(100, 80))
    run = InlineRun(image_src="../../assets/images/photo.png")
    window, _path = _window_with_run(tmp_path, run)

    class AcceptedDialog:
        def __init__(self, source_path, parent):
            pass

        def exec(self):
            return QDialog.DialogCode.Accepted

        def crop_request(self):
            return CropRequest((0, 0, 40, 50), 3)

    monkeypatch.setattr(window_module, "CropImageDialog", AcceptedDialog)

    assert window._crop_image_from_dialog() is True
    with Image.open(source.with_name("photo-crop1.png")) as result:
        assert result.size == (40, 50)
    _close_without_prompt(window)


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
