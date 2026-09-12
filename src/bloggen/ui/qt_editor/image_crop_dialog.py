"""Modal Qt crop/rotate editor that never writes or mutates document data."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QGuiApplication,
    QImage,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPaintEvent,
    QPen,
    QPixmap,
    QResizeEvent,
    QTransform,
)
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from bloggen.content.image_service import load_oriented_preview
from bloggen.ui.qt_editor.image_crop import (
    CROP_CORNERS,
    CROP_EDGES,
    RATIO_PRESETS,
    CropRect,
    clamp_rect,
    draw_rect,
    fit_ratio,
    full_rect,
    move_rect,
    preset_ratio,
    resize_rect,
    rotate_rect,
)


PREVIEW_MAX_DIMENSION = 2048
HANDLE_SIZE = 10
HANDLE_HIT_DISTANCE = 9
VIEW_MARGIN = 18
MAX_VIEW_ZOOM = 4.0
_SHADE = QColor(0, 0, 0, 135)
_ACCENT = QColor("#1a73e8")
_HANDLE_CURSORS = {
    "nw": Qt.CursorShape.SizeFDiagCursor,
    "se": Qt.CursorShape.SizeFDiagCursor,
    "ne": Qt.CursorShape.SizeBDiagCursor,
    "sw": Qt.CursorShape.SizeBDiagCursor,
    "n": Qt.CursorShape.SizeVerCursor,
    "s": Qt.CursorShape.SizeVerCursor,
    "e": Qt.CursorShape.SizeHorCursor,
    "w": Qt.CursorShape.SizeHorCursor,
}


@dataclass(frozen=True, slots=True)
class CropRequest:
    """What the user chose: a box in the rotated image and the rotation."""

    box: tuple[int, int, int, int]
    quarter_turns: int


def load_crop_preview(path: Path) -> tuple[QImage, tuple[int, int]]:
    """Reduced, oriented preview plus the full size a crop box refers to."""

    preview, full_size = load_oriented_preview(path, PREVIEW_MAX_DIMENSION)
    data = preview.tobytes("raw", "RGBA")
    image = QImage(
        data,
        preview.width,
        preview.height,
        preview.width * 4,
        QImage.Format.Format_RGBA8888,
    ).copy()
    if image.isNull():
        raise ValueError("Qt ne peut pas prévisualiser cette image")
    return image, full_size


@dataclass(slots=True)
class _Drag:
    mode: str  # "handle", "move" or "draw"
    handle: str | None
    start: tuple[float, float]
    start_rect: CropRect
    locked_ratio: float | None


class CropCanvas(QWidget):
    """Fit the image in the widget and edit a crop rectangle over it."""

    rectChanged = Signal(object)
    acceptRequested = Signal()

    def __init__(
        self,
        image: QImage,
        source_size: tuple[int, int],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        if image.isNull():
            raise ValueError("La prévisualisation ne peut pas être vide")
        self._base_image = image
        self._base_size = source_size
        self._image = image
        self._quarter_turns = 0
        self._source_w, self._source_h = source_size
        self._rect = full_rect(*source_size)
        self._ratio: float | None = None
        self._drag: _Drag | None = None
        self._pixmap_cache: tuple[QSize, QPixmap] | None = None
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumSize(320, 240)

    # -- public model -------------------------------------------------------

    @property
    def crop_rect(self) -> CropRect:
        return self._rect

    @property
    def source_size(self) -> tuple[int, int]:
        return self._source_w, self._source_h

    @property
    def quarter_turns(self) -> int:
        return self._quarter_turns

    @property
    def ratio(self) -> float | None:
        return self._ratio

    @property
    def dragging(self) -> bool:
        return self._drag is not None

    def source_box(self) -> tuple[int, int, int, int]:
        return self._rect.box()

    def set_crop_rect(self, rect: CropRect) -> None:
        rect = clamp_rect(rect, self._source_w, self._source_h)
        if rect != self._rect:
            self._rect = rect
            self.rectChanged.emit(rect)
        self.update()

    def set_ratio(self, ratio: float | None) -> None:
        self._ratio = ratio
        if ratio is not None:
            self.set_crop_rect(fit_ratio(self._rect, ratio, self._source_w, self._source_h))

    def select_all(self) -> None:
        rect = full_rect(self._source_w, self._source_h)
        if self._ratio is not None:
            rect = fit_ratio(rect, self._ratio, self._source_w, self._source_h)
        self.set_crop_rect(rect)

    def rotate(self, *, clockwise: bool) -> None:
        rect = rotate_rect(self._rect, self._source_w, self._source_h, clockwise=clockwise)
        self._quarter_turns = (self._quarter_turns + (1 if clockwise else -1)) % 4
        self._source_w, self._source_h = self._source_h, self._source_w
        self._image = self._base_image.transformed(
            QTransform().rotate(90 * self._quarter_turns)
        )
        self._pixmap_cache = None
        self._rect = clamp_rect(rect, self._source_w, self._source_h)
        if self._ratio is not None:
            self._rect = fit_ratio(self._rect, self._ratio, self._source_w, self._source_h)
        self.rectChanged.emit(self._rect)
        self.update()

    def reset(self) -> None:
        while self._quarter_turns:
            self.rotate(clockwise=False)
        self.set_crop_rect(full_rect(self._source_w, self._source_h))

    def nudge(self, dx: int, dy: int) -> None:
        self.set_crop_rect(move_rect(self._rect, dx, dy, self._source_w, self._source_h))

    # -- coordinate mapping --------------------------------------------------

    def image_view_rect(self) -> QRectF:
        available_w = max(1.0, self.width() - 2 * VIEW_MARGIN)
        available_h = max(1.0, self.height() - 2 * VIEW_MARGIN)
        scale = min(
            available_w / self._source_w,
            available_h / self._source_h,
            MAX_VIEW_ZOOM,
        )
        view_w = self._source_w * scale
        view_h = self._source_h * scale
        return QRectF(
            (self.width() - view_w) / 2,
            (self.height() - view_h) / 2,
            view_w,
            view_h,
        )

    def _scale(self) -> float:
        return self.image_view_rect().width() / self._source_w

    def view_rect(self, rect: CropRect | None = None) -> QRectF:
        rect = rect or self._rect
        image = self.image_view_rect()
        scale = self._scale()
        return QRectF(
            image.left() + rect.left * scale,
            image.top() + rect.top * scale,
            rect.width * scale,
            rect.height * scale,
        )

    def to_source(self, point: QPointF) -> tuple[float, float]:
        image = self.image_view_rect()
        scale = self._scale()
        return (point.x() - image.left()) / scale, (point.y() - image.top()) / scale

    def to_view(self, x: float, y: float) -> QPointF:
        image = self.image_view_rect()
        scale = self._scale()
        return QPointF(image.left() + x * scale, image.top() + y * scale)

    def handle_points(self) -> dict[str, QPointF]:
        rect = self.view_rect()
        center = rect.center()
        return {
            "nw": rect.topLeft(),
            "ne": rect.topRight(),
            "sw": rect.bottomLeft(),
            "se": rect.bottomRight(),
            "n": QPointF(center.x(), rect.top()),
            "s": QPointF(center.x(), rect.bottom()),
            "w": QPointF(rect.left(), center.y()),
            "e": QPointF(rect.right(), center.y()),
        }

    def handle_at(self, point: QPointF) -> str | None:
        """Corners first, then anywhere along an edge."""

        points = self.handle_points()
        for corner in CROP_CORNERS:
            corner_point = points[corner]
            if (
                abs(point.x() - corner_point.x()) <= HANDLE_HIT_DISTANCE
                and abs(point.y() - corner_point.y()) <= HANDLE_HIT_DISTANCE
            ):
                return corner
        rect = self.view_rect()
        within_x = rect.left() <= point.x() <= rect.right()
        within_y = rect.top() <= point.y() <= rect.bottom()
        for edge in CROP_EDGES:
            edge_point = points[edge]
            if edge in ("n", "s") and within_x and abs(point.y() - edge_point.y()) <= HANDLE_HIT_DISTANCE:
                return edge
            if edge in ("e", "w") and within_y and abs(point.x() - edge_point.x()) <= HANDLE_HIT_DISTANCE:
                return edge
        return None

    # -- interaction ----------------------------------------------------------

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        point = event.position()
        start = self.to_source(point)
        handle = self.handle_at(point)
        if handle is not None:
            mode = "handle"
        elif self.view_rect().contains(point):
            mode = "move"
        elif self.image_view_rect().adjusted(-VIEW_MARGIN, -VIEW_MARGIN, VIEW_MARGIN, VIEW_MARGIN).contains(point):
            mode = "draw"
        else:
            super().mousePressEvent(event)
            return
        self._drag = _Drag(mode, handle, start, self._rect, None)
        self._update_cursor(point)
        self.update()
        event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag is None:
            self._update_cursor(event.position())
            super().mouseMoveEvent(event)
            return
        self._drag_to(event.position(), event.modifiers())
        event.accept()

    def _drag_to(self, point: QPointF, modifiers) -> None:
        drag = self._drag
        if drag is None:
            return
        x, y = self.to_source(point)
        ratio = self._drag_ratio(drag, modifiers)
        if drag.mode == "move":
            rect = move_rect(
                drag.start_rect,
                round(x - drag.start[0]),
                round(y - drag.start[1]),
                self._source_w,
                self._source_h,
            )
        elif drag.mode == "handle":
            rect = resize_rect(
                drag.start_rect,
                drag.handle,
                x,
                y,
                self._source_w,
                self._source_h,
                ratio=ratio,
            )
        else:
            rect = draw_rect(
                drag.start[0],
                drag.start[1],
                x,
                y,
                self._source_w,
                self._source_h,
                ratio=ratio,
            )
        self.set_crop_rect(rect)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._drag is not None and event.button() == Qt.MouseButton.LeftButton:
            self._drag_to(event.position(), event.modifiers())
            self._drag = None
            self._update_cursor(event.position())
            self.update()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if (
            event.button() == Qt.MouseButton.LeftButton
            and self.view_rect().contains(event.position())
        ):
            self._drag = None
            self.acceptRequested.emit()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        step = 10 if event.modifiers() & Qt.KeyboardModifier.ShiftModifier else 1
        moves = {
            Qt.Key.Key_Left: (-step, 0),
            Qt.Key.Key_Right: (step, 0),
            Qt.Key.Key_Up: (0, -step),
            Qt.Key.Key_Down: (0, step),
        }
        if event.key() in moves:
            self.nudge(*moves[event.key()])
            event.accept()
            return
        super().keyPressEvent(event)

    def leaveEvent(self, event) -> None:
        if self._drag is None:
            self.unsetCursor()
        super().leaveEvent(event)

    def resizeEvent(self, event: QResizeEvent) -> None:
        self._pixmap_cache = None
        super().resizeEvent(event)

    def _drag_ratio(self, drag: _Drag, modifiers) -> float | None:
        if self._ratio is not None:
            return self._ratio
        if not modifiers & Qt.KeyboardModifier.ShiftModifier:
            return None
        if drag.mode == "draw":
            return 1.0
        return drag.start_rect.width / drag.start_rect.height

    def _update_cursor(self, point: QPointF) -> None:
        drag = self._drag
        handle = drag.handle if drag is not None and drag.mode == "handle" else None
        if drag is None:
            handle = self.handle_at(point)
        if handle is not None:
            self.setCursor(_HANDLE_CURSORS[handle])
        elif (drag is not None and drag.mode == "move") or (
            drag is None and self.view_rect().contains(point)
        ):
            self.setCursor(Qt.CursorShape.SizeAllCursor)
        else:
            self.setCursor(Qt.CursorShape.CrossCursor)

    # -- painting --------------------------------------------------------------

    def _scaled_pixmap(self, target: QRectF) -> QPixmap:
        ratio = self.devicePixelRatioF()
        size = QSize(max(1, round(target.width() * ratio)), max(1, round(target.height() * ratio)))
        cached = self._pixmap_cache
        if cached is not None and cached[0] == size:
            return cached[1]
        pixmap = QPixmap.fromImage(
            self._image.scaled(
                size,
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        pixmap.setDevicePixelRatio(ratio)
        self._pixmap_cache = (size, pixmap)
        return pixmap

    def paintEvent(self, event: QPaintEvent) -> None:
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        painter.fillRect(self.rect(), QColor(58, 58, 60))
        image_rect = self.image_view_rect()
        self._paint_checkerboard(painter, image_rect)
        painter.drawPixmap(image_rect.topLeft(), self._scaled_pixmap(image_rect))

        selection = self.view_rect()
        shade = QPainterPath()
        shade.addRect(image_rect)
        hole = QPainterPath()
        hole.addRect(selection)
        painter.fillPath(shade.subtracted(hole), _SHADE)

        if self._drag is not None:
            grid_pen = QPen(QColor(255, 255, 255, 110), 1)
            painter.setPen(grid_pen)
            for fraction in (1 / 3, 2 / 3):
                x = selection.left() + selection.width() * fraction
                y = selection.top() + selection.height() * fraction
                painter.drawLine(QPointF(x, selection.top()), QPointF(x, selection.bottom()))
                painter.drawLine(QPointF(selection.left(), y), QPointF(selection.right(), y))

        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(0, 0, 0, 160), 3))
        painter.drawRect(selection)
        painter.setPen(QPen(Qt.GlobalColor.white, 1))
        painter.drawRect(selection)

        half = HANDLE_SIZE / 2
        painter.setPen(QPen(_ACCENT, 1.5))
        painter.setBrush(Qt.GlobalColor.white)
        for handle_point in self.handle_points().values():
            painter.drawRect(
                QRectF(handle_point.x() - half, handle_point.y() - half, HANDLE_SIZE, HANDLE_SIZE)
            )

        if self._drag is not None:
            self._paint_size_label(painter, selection)

    def _paint_checkerboard(self, painter: QPainter, rect: QRectF) -> None:
        painter.save()
        painter.setClipRect(rect)
        painter.fillRect(rect, QColor(236, 236, 236))
        cell = 10
        dark = QColor(204, 204, 204)
        top = int(rect.top())
        left = int(rect.left())
        for row, y in enumerate(range(top, int(rect.bottom()) + 1, cell)):
            for column, x in enumerate(range(left, int(rect.right()) + 1, cell)):
                if (row + column) % 2:
                    painter.fillRect(x, y, cell, cell, dark)
        painter.restore()

    def _paint_size_label(self, painter: QPainter, selection: QRectF) -> None:
        text = f"{self._rect.width} × {self._rect.height} px"
        metrics = painter.fontMetrics()
        width = metrics.horizontalAdvance(text) + 12
        height = metrics.height() + 6
        x = min(max(selection.left() + 6, 4), self.width() - width - 4)
        y = min(selection.bottom() + 6, self.height() - height - 4)
        label = QRectF(x, y, width, height)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 190))
        painter.drawRoundedRect(label, 4, 4)
        painter.setPen(Qt.GlobalColor.white)
        painter.drawText(label, Qt.AlignmentFlag.AlignCenter, text)


class CropImageDialog(QDialog):
    """Choose a crop box and rotation; filesystem changes belong to the caller."""

    def __init__(self, source_path: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.source_path = Path(source_path)
        image, size = load_crop_preview(self.source_path)
        self._syncing = False
        self._ratio_inverted = False
        self.setWindowTitle("Recadrer l’image")
        self.setSizeGripEnabled(True)

        self.canvas = CropCanvas(image, size, self)
        # Kept for callers/tests written against the former preview widget.
        self.preview = self.canvas

        self.ratio_combo = QComboBox(self)
        for label, _w, _h in RATIO_PRESETS:
            self.ratio_combo.addItem(label)
        self.invert_ratio_button = QToolButton(self)
        self.invert_ratio_button.setText("⇄")
        self.invert_ratio_button.setToolTip("Inverser portrait / paysage")
        self.invert_ratio_button.setEnabled(False)
        ratio_row = QHBoxLayout()
        ratio_row.addWidget(self.ratio_combo, 1)
        ratio_row.addWidget(self.invert_ratio_button)

        self.x_spin = self._spin()
        self.y_spin = self._spin()
        self.width_spin = self._spin(minimum=1)
        self.height_spin = self._spin(minimum=1)
        geometry_box = QGroupBox("Sélection (pixels réels)", self)
        geometry_form = QFormLayout(geometry_box)
        geometry_form.addRow("X :", self.x_spin)
        geometry_form.addRow("Y :", self.y_spin)
        geometry_form.addRow("Largeur :", self.width_spin)
        geometry_form.addRow("Hauteur :", self.height_spin)

        self.rotate_left_button = QPushButton("↺ 90°", self)
        self.rotate_left_button.setToolTip("Pivoter d’un quart de tour à gauche")
        self.rotate_right_button = QPushButton("↻ 90°", self)
        self.rotate_right_button.setToolTip("Pivoter d’un quart de tour à droite")
        rotation_row = QHBoxLayout()
        rotation_row.addWidget(self.rotate_left_button)
        rotation_row.addWidget(self.rotate_right_button)

        self.select_all_button = QPushButton("Tout sélectionner", self)
        self.reset_button = QPushButton("Réinitialiser", self)
        self.size_label = QLabel(self)
        help_label = QLabel(
            "Glisser dans le cadre : le déplacer · hors du cadre : en tracer un "
            "nouveau · Maj : garder les proportions · Flèches : ajuster "
            "(Maj : ×10) · Double-clic : valider",
            self,
        )
        help_label.setWordWrap(True)
        help_label.setStyleSheet("color: palette(mid);")

        side = QVBoxLayout()
        side.addWidget(QLabel("Proportions :", self))
        side.addLayout(ratio_row)
        side.addWidget(geometry_box)
        side.addWidget(QLabel("Rotation :", self))
        side.addLayout(rotation_row)
        side.addWidget(self.select_all_button)
        side.addWidget(self.reset_button)
        side.addWidget(self.size_label)
        side.addStretch(1)
        side.addWidget(help_label)
        side_widget = QWidget(self)
        side_widget.setLayout(side)
        side_widget.setFixedWidth(230)

        body = QHBoxLayout()
        body.addWidget(self.canvas, 1)
        body.addWidget(side_widget)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(body, 1)
        layout.addWidget(self.buttons)

        self.canvas.rectChanged.connect(self._sync_fields)
        self.canvas.acceptRequested.connect(self.accept)
        self.ratio_combo.currentIndexChanged.connect(self._apply_ratio)
        self.invert_ratio_button.clicked.connect(self._invert_ratio)
        for spin in (self.x_spin, self.y_spin, self.width_spin, self.height_spin):
            spin.valueChanged.connect(self._fields_changed)
        self.rotate_left_button.clicked.connect(lambda: self._rotate(clockwise=False))
        self.rotate_right_button.clicked.connect(lambda: self._rotate(clockwise=True))
        self.select_all_button.clicked.connect(self.canvas.select_all)
        self.reset_button.clicked.connect(self._reset)

        self._sync_fields()
        self._resize_to_screen()
        self.canvas.setFocus()

    # -- results --------------------------------------------------------------

    def crop_box(self) -> tuple[int, int, int, int]:
        return self.canvas.source_box()

    def crop_request(self) -> CropRequest:
        return CropRequest(self.canvas.source_box(), self.canvas.quarter_turns)

    # -- internals --------------------------------------------------------------

    def _spin(self, *, minimum: int = 0) -> QSpinBox:
        spin = QSpinBox(self)
        spin.setMinimum(minimum)
        spin.setSuffix(" px")
        spin.setKeyboardTracking(False)
        return spin

    def _resize_to_screen(self) -> None:
        screen = self.screen() or QGuiApplication.primaryScreen()
        if screen is None:
            self.resize(900, 640)
            return
        available = screen.availableGeometry()
        self.resize(
            max(640, round(available.width() * 0.75)),
            max(480, round(available.height() * 0.75)),
        )

    def _current_ratio(self) -> float | None:
        width, height = self.canvas.source_size
        ratio = preset_ratio(self.ratio_combo.currentIndex(), width, height)
        if ratio is not None and self._ratio_inverted:
            ratio = 1 / ratio
        return ratio

    def _apply_ratio(self) -> None:
        base = preset_ratio(self.ratio_combo.currentIndex(), *self.canvas.source_size)
        self.invert_ratio_button.setEnabled(base is not None and abs(base - 1) > 1e-9)
        if base is None or abs(base - 1) <= 1e-9:
            self._ratio_inverted = False
        self.canvas.set_ratio(self._current_ratio())

    def _invert_ratio(self) -> None:
        self._ratio_inverted = not self._ratio_inverted
        self.canvas.set_ratio(self._current_ratio())

    def _rotate(self, *, clockwise: bool) -> None:
        self.canvas.rotate(clockwise=clockwise)
        # "Original proportions" follow the rotated image.
        if self.ratio_combo.currentIndex() == 1:
            self.canvas.set_ratio(self._current_ratio())
        self._sync_fields()

    def _reset(self) -> None:
        self._syncing = True
        try:
            self.ratio_combo.setCurrentIndex(0)
            self._ratio_inverted = False
            self.invert_ratio_button.setEnabled(False)
        finally:
            self._syncing = False
        self.canvas.set_ratio(None)
        self.canvas.reset()
        self._sync_fields()

    def _sync_fields(self, *_args) -> None:
        rect = self.canvas.crop_rect
        width, height = self.canvas.source_size
        self._syncing = True
        try:
            self.x_spin.setMaximum(width - 1)
            self.y_spin.setMaximum(height - 1)
            self.width_spin.setMaximum(width)
            self.height_spin.setMaximum(height)
            self.x_spin.setValue(rect.left)
            self.y_spin.setValue(rect.top)
            self.width_spin.setValue(rect.width)
            self.height_spin.setValue(rect.height)
        finally:
            self._syncing = False
        self.size_label.setText(
            f"Image : {width} × {height} px\nRésultat : {rect.width} × {rect.height} px"
        )

    def _fields_changed(self) -> None:
        if self._syncing:
            return
        left = self.x_spin.value()
        top = self.y_spin.value()
        width = self.width_spin.value()
        height = self.height_spin.value()
        ratio = self.canvas.ratio
        if ratio is not None:
            if self.sender() is self.height_spin:
                width = max(1, round(height * ratio))
            else:
                height = max(1, round(width / ratio))
        self.canvas.set_crop_rect(CropRect(left, top, left + width, top + height))
        self._sync_fields()
