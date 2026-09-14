from __future__ import annotations

import os

import pytest
from PIL import Image

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QDialog

from bloggen.ui.qt_editor.image_adjust_dialog import (
    AdjustImageDialog,
    ImageAdjustmentRequest,
)


@pytest.fixture(scope="module", autouse=True)
def qapplication():
    app = QApplication.instance() or QApplication([])
    yield app


def _source(path):
    image = Image.new("RGBA", (4, 2))
    image.putdata(
        [
            (30, 40, 50, 0),
            (80, 90, 100, 64),
            (130, 140, 150, 128),
            (180, 190, 200, 255),
        ]
        * 2
    )
    image.save(path)
    return path


def _pixels(dialog: AdjustImageDialog):
    image = dialog.preview.image
    return [
        image.pixelColor(x, y).getRgb()
        for y in range(image.height())
        for x in range(image.width())
    ]


def test_dialog_starts_at_identity_and_never_writes(tmp_path):
    source = _source(tmp_path / "photo.png")

    dialog = AdjustImageDialog(source)

    assert dialog.request() == ImageAdjustmentRequest(brightness=0, contrast=0)
    assert dialog.brightness_slider.minimum() == -100
    assert dialog.brightness_slider.maximum() == 100
    assert dialog.contrast_slider.minimum() == -100
    assert dialog.contrast_slider.maximum() == 100
    assert dialog.brightness_value.text() == "+0"
    assert dialog.contrast_value.text() == "+0"
    dialog.close()
    assert sorted(path.name for path in tmp_path.iterdir()) == ["photo.png"]


def test_sliders_recompute_preview_from_source_and_reset_exactly(tmp_path):
    source = _source(tmp_path / "photo.png")
    dialog = AdjustImageDialog(source)
    original = _pixels(dialog)

    dialog.brightness_slider.setValue(50)
    bright = _pixels(dialog)
    assert dialog.brightness_value.text() == "+50"
    assert bright != original
    assert [pixel[3] for pixel in bright] == [pixel[3] for pixel in original]

    dialog.contrast_slider.setValue(-40)
    combined = _pixels(dialog)
    assert dialog.contrast_value.text() == "-40"
    assert combined != bright

    dialog.brightness_slider.setValue(-25)
    dialog.brightness_slider.setValue(50)
    assert _pixels(dialog) == combined

    dialog.reset_button.click()
    assert dialog.request() == ImageAdjustmentRequest(0, 0)
    assert _pixels(dialog) == original
    dialog.close()


def test_slider_changes_do_not_reopen_source_file(tmp_path, monkeypatch):
    source = _source(tmp_path / "photo.png")
    dialog = AdjustImageDialog(source)

    def fail_open(*_args, **_kwargs):
        raise AssertionError("le déplacement d’un curseur ne doit pas relire le disque")

    monkeypatch.setattr(Image, "open", fail_open)
    dialog.brightness_slider.setValue(30)
    dialog.contrast_slider.setValue(-20)

    assert dialog.request() == ImageAdjustmentRequest(30, -20)
    dialog.close()


def test_preview_keeps_aspect_ratio_when_resized(tmp_path):
    source = _source(tmp_path / "photo.png")
    dialog = AdjustImageDialog(source)
    dialog.preview.resize(500, 300)

    rect = dialog.preview.image_rect()

    assert rect.width() / rect.height() == pytest.approx(2.0)
    assert rect.center().x() == pytest.approx(dialog.preview.width() / 2)
    assert rect.center().y() == pytest.approx(dialog.preview.height() / 2)
    dialog.close()


def test_cancel_and_apply_set_dialog_result(tmp_path):
    source = _source(tmp_path / "photo.png")
    cancelled = AdjustImageDialog(source)
    cancelled.button_box.button(
        cancelled.button_box.StandardButton.Cancel
    ).click()
    assert cancelled.result() == QDialog.DialogCode.Rejected

    accepted = AdjustImageDialog(source)
    accepted.brightness_slider.setValue(15)
    accepted.contrast_slider.setValue(-25)
    accepted.apply_button.click()
    assert accepted.result() == QDialog.DialogCode.Accepted
    assert accepted.request() == ImageAdjustmentRequest(15, -25)
