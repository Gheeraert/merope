"""Modal Qt crop selector that never writes or mutates document data."""

from __future__ import annotations

from pathlib import Path

from PIL import Image
from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QColor, QImage, QMouseEvent, QPainter, QPaintEvent, QPen, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QVBoxLayout,
    QWidget,
)

from bloggen.ui.qt_editor.image_crop import (
    CROP_CORNERS,
    CropPreviewGeometry,
    CropRect,
    calculate_crop_preview,
    initial_crop_rect,
    move_crop_corner,
    preview_rect_to_source_box,
)


CROP_HANDLE_SIZE = 14


def crop_source_size(path: Path) -> tuple[int, int]:
    """Read and verify the dimensions Pillow will use for the physical crop."""

    try:
        with Image.open(path) as source:
            width, height = source.size
            source.verify()
    except Exception as exc:
        raise ValueError(f"Le fichier image ne peut pas être lu : {path}") from exc
    if width <= 0 or height <= 0:
        raise ValueError("L’image ne possède pas de dimensions recadrables")
    return width, height


def load_crop_preview(path: Path) -> tuple[QImage, tuple[int, int]]:
    """Load pixels with Pillow semantics, matching ``write_cropped_copy``."""

    try:
        with Image.open(path) as source:
            source.load()
            width, height = source.size
            rgba = source.convert("RGBA")
            data = rgba.tobytes("raw", "RGBA")
    except Exception as exc:
        raise ValueError(f"Le fichier image ne peut pas être lu : {path}") from exc
    if width <= 0 or height <= 0:
        raise ValueError("L’image ne possède pas de dimensions recadrables")
    image = QImage(
        data,
        width,
        height,
        width * 4,
        QImage.Format.Format_RGBA8888,
    ).copy()
    if image.isNull():
        raise ValueError("Qt ne peut pas prévisualiser cette image")
    return image, (width, height)


class CropPreviewWidget(QWidget):
    """Paint a reduced image and allow free dragging of its four corners."""

    def __init__(
        self,
        image: QImage,
        geometry: CropPreviewGeometry,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        if image.isNull():
            raise ValueError("La prévisualisation ne peut pas être vide")
        self.geometry_model = geometry
        self.crop_rect = initial_crop_rect(geometry)
        self._dragging_corner: str | None = None
        self._pixmap = QPixmap.fromImage(image).scaled(
            geometry.preview_width,
            geometry.preview_height,
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.setFixedSize(geometry.preview_width, geometry.preview_height)
        self.setMouseTracking(True)

    def source_box(self) -> tuple[int, int, int, int]:
        return preview_rect_to_source_box(self.crop_rect, self.geometry_model)

    def handle_rects(self) -> dict[str, QRect]:
        half = CROP_HANDLE_SIZE // 2
        rect = self.crop_rect
        points = {
            "nw": QPoint(rect.left, rect.top),
            "ne": QPoint(rect.right, rect.top),
            "sw": QPoint(rect.left, rect.bottom),
            "se": QPoint(rect.right, rect.bottom),
        }
        return {
            name: QRect(point.x() - half, point.y() - half, CROP_HANDLE_SIZE, CROP_HANDLE_SIZE)
            for name, point in points.items()
        }

    def set_crop_rect(self, rect: CropRect) -> None:
        preview_rect_to_source_box(rect, self.geometry_model)
        self.crop_rect = rect
        self.update()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            corner = self._corner_at(event.position().toPoint())
            if corner is not None:
                self._dragging_corner = corner
                self._set_corner_cursor(corner)
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        point = event.position().toPoint()
        if self._dragging_corner is not None:
            self.crop_rect = move_crop_corner(
                self.crop_rect,
                self._dragging_corner,
                point.x(),
                point.y(),
                self.geometry_model,
            )
            self.update()
            event.accept()
            return
        corner = self._corner_at(point)
        if corner is None:
            self.unsetCursor()
        else:
            self._set_corner_cursor(corner)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._dragging_corner is not None and event.button() == Qt.MouseButton.LeftButton:
            self._dragging_corner = None
            corner = self._corner_at(event.position().toPoint())
            if corner is None:
                self.unsetCursor()
            else:
                self._set_corner_cursor(corner)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def leaveEvent(self, event) -> None:
        if self._dragging_corner is None:
            self.unsetCursor()
        super().leaveEvent(event)

    def paintEvent(self, event: QPaintEvent) -> None:
        del event
        painter = QPainter(self)
        painter.drawPixmap(0, 0, self._pixmap)
        rect = self.crop_rect
        shade = QColor(0, 0, 0, 95)
        painter.fillRect(QRect(0, 0, self.width(), rect.top), shade)
        painter.fillRect(QRect(0, rect.bottom, self.width(), self.height() - rect.bottom), shade)
        painter.fillRect(QRect(0, rect.top, rect.left, rect.height), shade)
        painter.fillRect(
            QRect(rect.right, rect.top, self.width() - rect.right, rect.height),
            shade,
        )

        pen = QPen(QColor("#1a73e8"), 2)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(QRect(rect.left, rect.top, rect.width, rect.height))
        painter.setPen(QPen(Qt.GlobalColor.white, 1))
        painter.setBrush(QColor("#1a73e8"))
        for handle in self.handle_rects().values():
            painter.drawRect(handle)

    def _corner_at(self, point: QPoint) -> str | None:
        for corner in CROP_CORNERS:
            if self.handle_rects()[corner].contains(point):
                return corner
        return None

    def _set_corner_cursor(self, corner: str) -> None:
        if corner in {"nw", "se"}:
            self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        else:
            self.setCursor(Qt.CursorShape.SizeBDiagCursor)


class CropImageDialog(QDialog):
    """Select a source-pixel crop box; filesystem changes belong to the caller."""

    def __init__(self, source_path: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.source_path = Path(source_path)
        image, (width, height) = load_crop_preview(self.source_path)
        self.preview_geometry = calculate_crop_preview(width, height)
        self.preview = CropPreviewWidget(image, self.preview_geometry, self)
        self.setWindowTitle("Recadrer l’image")

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(self.preview)
        layout.addWidget(buttons)

    def crop_box(self) -> tuple[int, int, int, int]:
        return self.preview.source_box()
