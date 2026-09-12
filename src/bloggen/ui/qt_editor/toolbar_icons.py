"""Dependency-free toolbar icons built from Qt themes, styles and glyphs."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import QStyle, QWidget


_STANDARD_ICONS = {
    "open": QStyle.StandardPixmap.SP_DialogOpenButton,
    "save": QStyle.StandardPixmap.SP_DialogSaveButton,
    "undo": QStyle.StandardPixmap.SP_ArrowBack,
    "redo": QStyle.StandardPixmap.SP_ArrowForward,
}

_THEME_ICONS = {
    "cut": "edit-cut",
    "copy": "edit-copy",
    "paste": "edit-paste",
    "find": "edit-find",
    "replace": "edit-find-replace",
    "metadata": "document-properties",
    "link": "insert-link",
    "image": "insert-image",
    "table": "insert-table",
    "left": "format-justify-left",
    "center": "format-justify-center",
    "right": "format-justify-right",
    "justify": "format-justify-fill",
}

_GLYPHS = {
    "metadata": "⚙",
    "replace": "↔",
    "plain_paste": "T",
    "nbsp": "␠",
    "bold": "G",
    "italic": "I",
    "underline": "U",
    "strike": "S",
    "superscript": "x²",
    "link": "↗",
    "note": "†",
    "renumber": "1†",
    "image_edit": "▧",
    "image_replace": "⇄",
    "crop": "⌗",
    "paragraph": "¶",
    "h1": "H1",
    "h2": "H2",
    "h3": "H3",
    "h4": "H4",
    "quote": "❞",
    "bullets": "•≡",
    "numbered": "1≡",
    "table": "▦",
    "left": "≡",
    "center": "≡",
    "right": "≡",
    "justify": "☰",
    "typography": "œ",
    "markdown": "M↓",
}


_ICON_SIZE = 30


def toolbar_icon(owner: QWidget, key: str) -> QIcon:
    standard = _STANDARD_ICONS.get(key)
    if standard is not None:
        return owner.style().standardIcon(standard)
    if key == "preview":
        return _eye_icon()
    if key == "clear_format":
        return _clear_format_icon()
    theme_name = _THEME_ICONS.get(key)
    fallback = _text_icon(key, _GLYPHS.get(key, key[:2].upper()))
    if theme_name:
        themed = QIcon.fromTheme(theme_name)
        if not themed.isNull():
            return themed
    return fallback


def _text_icon(key: str, glyph: str) -> QIcon:
    pixmap = QPixmap(_ICON_SIZE, _ICON_SIZE)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    painter.setPen(QColor("#202124"))
    font = QFont()
    font.setPixelSize(18 if len(glyph) > 1 else 23)
    font.setBold(True)
    font.setItalic(key == "italic")
    font.setUnderline(key == "underline")
    font.setStrikeOut(key == "strike")
    painter.setFont(font)
    alignment = Qt.AlignmentFlag.AlignCenter
    if key == "left":
        alignment = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
    elif key == "right":
        alignment = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
    painter.drawText(pixmap.rect().adjusted(2, 1, -2, -1), alignment, glyph)
    painter.end()
    return QIcon(pixmap)


def _clear_format_icon() -> QIcon:
    """A big "T" with a small subscript "x", mirroring the common
    "clear formatting" pictogram (as seen in Google Docs / Word)."""

    size = _ICON_SIZE
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    color = QColor("#202124")
    painter.setPen(color)

    big_font = QFont()
    big_font.setPixelSize(int(size * 0.62))
    big_font.setBold(True)
    painter.setFont(big_font)
    painter.drawText(
        QRectF(0, 0, size * 0.66, size),
        Qt.AlignmentFlag.AlignCenter,
        "T",
    )

    small_font = QFont()
    small_font.setPixelSize(int(size * 0.4))
    small_font.setBold(True)
    painter.setFont(small_font)
    painter.drawText(
        QRectF(size * 0.48, size * 0.42, size * 0.5, size * 0.56),
        Qt.AlignmentFlag.AlignCenter,
        "x",
    )
    painter.end()
    return QIcon(pixmap)


def _eye_icon() -> QIcon:
    size = _ICON_SIZE
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    color = QColor("#202124")

    margin = size * 0.08
    center_y = size * 0.5
    half_height = size * 0.24
    left = QPointF(margin, center_y)
    right = QPointF(size - margin, center_y)
    outline = QPainterPath()
    outline.moveTo(left)
    outline.quadTo(QPointF(size * 0.5, center_y - half_height), right)
    outline.quadTo(QPointF(size * 0.5, center_y + half_height), left)
    outline.closeSubpath()

    pen = painter.pen()
    pen.setColor(color)
    pen.setWidthF(size * 0.075)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawPath(outline)

    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(color)
    pupil_radius = size * 0.09
    painter.drawEllipse(QPointF(size * 0.5, center_y), pupil_radius, pupil_radius)
    painter.end()
    return QIcon(pixmap)
