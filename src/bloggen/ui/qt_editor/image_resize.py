"""Viewport geometry for resizing a Qt image by its corner handles.

The stored value is a percentage of the text column (see
``bloggen.content.image_size``); this module only measures what is on
screen: the image's rectangle, the column width Qt resolves percentages
against, the bitmap's natural size and the "ghost" shown while dragging.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from PySide6.QtCore import QPoint, QRect, QSize, QUrl
from PySide6.QtGui import QImage, QImageReader, QPixmap, QTextCursor, QTextDocument
from PySide6.QtWidgets import QTextEdit

from bloggen.content.image_size import ResizeOutcome, max_percent_for
from bloggen.ui.qt_editor.document_adapter import UnsupportedDocumentError
from bloggen.ui.qt_editor.image_selection import (
    ImageTarget,
    exactly_selected_merope_image,
)


RESIZE_HANDLE_SIZE = 10
RESIZE_HANDLE_HIT = 7
RESIZE_DRAG_THRESHOLD = 3
RESIZE_CORNERS = ("nw", "ne", "sw", "se")


@dataclass(frozen=True, slots=True)
class ImageResizeGeometry:
    target: ImageTarget
    image_rect: QRect
    handles: dict[str, QRect]

    @property
    def handle_rect(self) -> QRect:
        """The bottom-right handle (historical single handle)."""

        return self.handles["se"]

    def handle_at(self, point: QPoint) -> str | None:
        for corner in RESIZE_CORNERS:
            if self.handles[corner].adjusted(
                -RESIZE_HANDLE_HIT + RESIZE_HANDLE_SIZE // 2,
                -RESIZE_HANDLE_HIT + RESIZE_HANDLE_SIZE // 2,
                RESIZE_HANDLE_HIT - RESIZE_HANDLE_SIZE // 2,
                RESIZE_HANDLE_HIT - RESIZE_HANDLE_SIZE // 2,
            ).contains(point):
                return corner
        return None


def image_viewport_rect(editor: QTextEdit, target: ImageTarget) -> QRect:
    """Return the current rendered image bounds in viewport coordinates."""

    start = QTextCursor(editor.document())
    start.setPosition(target.start)
    end = QTextCursor(editor.document())
    end.setPosition(target.end)
    start_rect = editor.cursorRect(start)
    end_rect = editor.cursorRect(end)
    left = min(start_rect.center().x(), end_rect.center().x())
    right = max(start_rect.center().x(), end_rect.center().x())
    top = min(start_rect.top(), end_rect.top())
    bottom = max(start_rect.bottom(), end_rect.bottom())
    return QRect(left, top, right - left, bottom - top + 1)


def selected_image_resize_geometry(editor: QTextEdit) -> ImageResizeGeometry | None:
    """Return handle geometry only for one exact, renderable image selection."""

    try:
        target = exactly_selected_merope_image(editor.textCursor())
    except UnsupportedDocumentError:
        return None
    if target is None or natural_image_size(editor.document(), target) is None:
        return None
    image_rect = image_viewport_rect(editor, target)
    if image_rect.width() <= 1 or image_rect.height() <= 1:
        return None
    half = RESIZE_HANDLE_SIZE // 2
    corners = {
        "nw": image_rect.topLeft(),
        "ne": QPoint(image_rect.right() + 1, image_rect.top()),
        "sw": QPoint(image_rect.left(), image_rect.bottom() + 1),
        "se": QPoint(image_rect.right() + 1, image_rect.bottom() + 1),
    }
    handles = {
        name: QRect(point.x() - half, point.y() - half, RESIZE_HANDLE_SIZE, RESIZE_HANDLE_SIZE)
        for name, point in corners.items()
    }
    return ImageResizeGeometry(target, image_rect, handles)


def column_width(document: QTextDocument) -> float:
    """Width Qt resolves an image's percentage maximum width against."""

    width = document.textWidth()
    if width <= 0:
        width = document.idealWidth()
    return max(1.0, width - 2 * document.documentMargin())


def natural_image_size(document: QTextDocument, target: ImageTarget) -> QSize | None:
    """Pixel size of the bitmap as Qt displays it, or ``None`` if unreadable."""

    source_url = QUrl(target.run.image_src or "")
    resolved = document.baseUrl().resolved(source_url)
    resource = document.resource(QTextDocument.ResourceType.ImageResource, resolved)
    if isinstance(resource, (QImage, QPixmap)) and not resource.isNull():
        size = resource.size()
    elif resolved.isLocalFile():
        reader = QImageReader(resolved.toLocalFile())
        if not reader.canRead():
            return None
        size = reader.size()
    else:
        return None
    return size if size.width() > 0 and size.height() > 0 else None


def resize_drag_is_effective(origin: QPoint, current: QPoint) -> bool:
    return math.hypot(current.x() - origin.x(), current.y() - origin.y()) >= (
        RESIZE_DRAG_THRESHOLD
    )


def dragged_width(initial: QSize, delta: QPoint, handle: str) -> float:
    """New width for a corner drag, following the dominant relative axis."""

    width = initial.width()
    height = initial.height()
    if width <= 0 or height <= 0:
        return float(max(width, 1))
    dx = delta.x() if "e" in handle else -delta.x()
    dy = delta.y() if "s" in handle else -delta.y()
    if abs(dx) / width >= abs(dy) / height:
        return max(1.0, width + dx)
    return max(1.0, width * (height + dy) / height)


def displayed_size(
    outcome: ResizeOutcome,
    natural: QSize,
    column: float,
    align: str | None,
) -> QSize:
    """What Qt (and the site) will draw for ``outcome``."""

    ceiling = max_percent_for(align)
    percent = ceiling if outcome.percent is None else min(outcome.percent, ceiling)
    width = min(natural.width(), column * percent / 100.0)
    height = width * natural.height() / natural.width()
    return QSize(max(1, round(width)), max(1, round(height)))


def ghost_rect(image_rect: QRect, handle: str, size: QSize) -> QRect:
    """Place ``size`` so the corner opposite the dragged handle stays put."""

    x = image_rect.left() if "e" in handle else image_rect.right() + 1 - size.width()
    y = image_rect.top() if "s" in handle else image_rect.bottom() + 1 - size.height()
    return QRect(x, y, size.width(), size.height())


def size_label(outcome: ResizeOutcome, size: QSize) -> str:
    pixels = f"{size.width()} × {size.height()} px"
    if outcome.percent is None:
        return f"Taille réelle · {pixels}"
    return f"{outcome.percent} % de la colonne · {pixels}"
