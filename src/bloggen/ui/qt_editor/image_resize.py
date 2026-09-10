"""Viewport-only geometry and ratio calculations for Qt image resizing."""

from __future__ import annotations

import math
from dataclasses import dataclass

from PySide6.QtCore import QPoint, QRect, QSize, QUrl
from PySide6.QtGui import QImage, QImageReader, QPixmap, QTextCursor, QTextDocument
from PySide6.QtWidgets import QTextEdit

from bloggen.ui.qt_editor.document_adapter import UnsupportedDocumentError
from bloggen.ui.qt_editor.image_selection import (
    ImageTarget,
    exactly_selected_merope_image,
)


MIN_IMAGE_SIZE = 40
RESIZE_HANDLE_SIZE = 10
RESIZE_DRAG_THRESHOLD = 3


@dataclass(frozen=True, slots=True)
class ImageResizeGeometry:
    target: ImageTarget
    image_rect: QRect
    handle_rect: QRect


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
    if target is None or not _image_resource_is_renderable(editor.document(), target):
        return None
    image_rect = image_viewport_rect(editor, target)
    if image_rect.width() <= 1 or image_rect.height() <= 1:
        return None
    half = RESIZE_HANDLE_SIZE // 2
    handle = QRect(
        image_rect.right() - half + 1,
        image_rect.bottom() - half + 1,
        RESIZE_HANDLE_SIZE,
        RESIZE_HANDLE_SIZE,
    )
    return ImageResizeGeometry(target, image_rect, handle)


def resize_drag_is_effective(origin: QPoint, current: QPoint) -> bool:
    return math.hypot(current.x() - origin.x(), current.y() - origin.y()) >= (
        RESIZE_DRAG_THRESHOLD
    )


def ratio_preserving_size(
    initial: QSize,
    delta: QPoint,
    *,
    minimum: int = MIN_IMAGE_SIZE,
) -> QSize:
    """Resize from the dominant relative drag axis using one scale factor."""

    width = initial.width()
    height = initial.height()
    if width <= 0 or height <= 0:
        return QSize()
    relative_x = abs(delta.x()) / width
    relative_y = abs(delta.y()) / height
    if relative_x >= relative_y:
        scale = (width + delta.x()) / width
    else:
        scale = (height + delta.y()) / height
    minimum_scale = max(minimum / width, minimum / height)
    scale = max(scale, minimum_scale)
    return QSize(max(1, round(width * scale)), max(1, round(height * scale)))


def _image_resource_is_renderable(
    document: QTextDocument,
    target: ImageTarget,
) -> bool:
    source_url = QUrl(target.run.image_src or "")
    resolved = document.baseUrl().resolved(source_url)
    resource = document.resource(QTextDocument.ResourceType.ImageResource, resolved)
    if isinstance(resource, QImage):
        return not resource.isNull()
    if isinstance(resource, QPixmap):
        return not resource.isNull()
    if resolved.isLocalFile():
        reader = QImageReader(resolved.toLocalFile())
        size = reader.size()
        return reader.canRead() and size.width() > 0 and size.height() > 0
    return False
