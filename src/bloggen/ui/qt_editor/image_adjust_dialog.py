"""Modal brightness/contrast preview with no document or filesystem writes."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPaintEvent
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from bloggen.content.image_service import adjust_image, load_oriented_preview


PREVIEW_MAX_DIMENSION = 1200
_CHECKER_LIGHT = QColor(236, 236, 236)
_CHECKER_DARK = QColor(204, 204, 204)


@dataclass(frozen=True, slots=True)
class ImageAdjustmentRequest:
    brightness: int
    contrast: int


def pillow_to_qimage(image: Image.Image) -> QImage:
    """Return an owning RGBA QImage detached from Pillow's byte buffer."""

    rgba = image.convert("RGBA")
    data = rgba.tobytes("raw", "RGBA")
    converted = QImage(
        data,
        rgba.width,
        rgba.height,
        rgba.width * 4,
        QImage.Format.Format_RGBA8888,
    ).copy()
    if converted.isNull():
        raise ValueError("Qt ne peut pas prévisualiser cette image")
    return converted


class AdjustmentPreview(QWidget):
    """Aspect-preserving preview over a checkerboard for transparent pixels."""

    def __init__(self, image: QImage, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        if image.isNull():
            raise ValueError("La prévisualisation ne peut pas être vide")
        self._image = QImage(image)
        self.setMinimumSize(320, 240)

    @property
    def image(self) -> QImage:
        return QImage(self._image)

    def set_image(self, image: QImage) -> None:
        if image.isNull():
            raise ValueError("La prévisualisation ne peut pas être vide")
        self._image = QImage(image)
        self.update()

    def image_rect(self) -> QRectF:
        available = self.rect().adjusted(12, 12, -12, -12)
        scale = min(
            available.width() / self._image.width(),
            available.height() / self._image.height(),
        )
        width = max(1.0, self._image.width() * scale)
        height = max(1.0, self._image.height() * scale)
        return QRectF(
            (self.width() - width) / 2,
            (self.height() - height) / 2,
            width,
            height,
        )

    def paintEvent(self, event: QPaintEvent) -> None:
        del event
        painter = QPainter(self)
        painter.fillRect(self.rect(), self.palette().window())
        target = self.image_rect()
        painter.save()
        painter.setClipRect(target)
        cell = 10
        left = int(target.left())
        top = int(target.top())
        right = int(target.right()) + 1
        bottom = int(target.bottom()) + 1
        painter.fillRect(target, _CHECKER_LIGHT)
        for row, y in enumerate(range(top, bottom, cell)):
            for column, x in enumerate(range(left, right, cell)):
                if (row + column) % 2:
                    painter.fillRect(x, y, cell, cell, _CHECKER_DARK)
        painter.restore()
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.drawImage(target, self._image)


class AdjustImageDialog(QDialog):
    """Preview tonal settings; the caller owns Apply's filesystem mutation."""

    def __init__(self, source_path: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.source_path = Path(source_path)
        self._source_preview, _full_size = load_oriented_preview(
            self.source_path,
            PREVIEW_MAX_DIMENSION,
        )
        self.setWindowTitle("Ajuster l’image")
        self.setSizeGripEnabled(True)

        source_image = pillow_to_qimage(self._source_preview)
        self.preview = AdjustmentPreview(source_image, self)
        self.brightness_slider, self.brightness_value = self._slider_row()
        self.contrast_slider, self.contrast_value = self._slider_row()

        controls = QVBoxLayout()
        controls.addLayout(
            self._labelled_slider(
                "Luminosité",
                self.brightness_slider,
                self.brightness_value,
            )
        )
        controls.addLayout(
            self._labelled_slider(
                "Contraste",
                self.contrast_slider,
                self.contrast_value,
            )
        )

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        self.reset_button = self.button_box.addButton(
            "Réinitialiser",
            QDialogButtonBox.ButtonRole.ResetRole,
        )
        self.apply_button = self.button_box.addButton(
            "Appliquer",
            QDialogButtonBox.ButtonRole.AcceptRole,
        )

        layout = QVBoxLayout(self)
        layout.addWidget(self.preview, 1)
        layout.addLayout(controls)
        layout.addWidget(self.button_box)

        self.brightness_slider.valueChanged.connect(self._update_preview)
        self.contrast_slider.valueChanged.connect(self._update_preview)
        self.reset_button.clicked.connect(self.reset)
        self.apply_button.clicked.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        self.resize(700, 600)
        self._update_preview()

    def _slider_row(self) -> tuple[QSlider, QLabel]:
        slider = QSlider(Qt.Orientation.Horizontal, self)
        slider.setRange(-100, 100)
        slider.setValue(0)
        value = QLabel("0", self)
        value.setMinimumWidth(36)
        value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return slider, value

    def _labelled_slider(
        self,
        text: str,
        slider: QSlider,
        value: QLabel,
    ) -> QHBoxLayout:
        label = QLabel(text, self)
        label.setBuddy(slider)
        row = QHBoxLayout()
        row.addWidget(label)
        row.addWidget(slider, 1)
        row.addWidget(value)
        return row

    def request(self) -> ImageAdjustmentRequest:
        return ImageAdjustmentRequest(
            brightness=self.brightness_slider.value(),
            contrast=self.contrast_slider.value(),
        )

    def reset(self) -> None:
        self.brightness_slider.blockSignals(True)
        self.contrast_slider.blockSignals(True)
        try:
            self.brightness_slider.setValue(0)
            self.contrast_slider.setValue(0)
        finally:
            self.brightness_slider.blockSignals(False)
            self.contrast_slider.blockSignals(False)
        self._update_preview()

    def _update_preview(self) -> None:
        request = self.request()
        self.brightness_value.setText(f"{request.brightness:+d}")
        self.contrast_value.setText(f"{request.contrast:+d}")
        adjusted = adjust_image(
            self._source_preview,
            brightness=request.brightness,
            contrast=request.contrast,
        )
        self.preview.set_image(pillow_to_qimage(adjusted))
