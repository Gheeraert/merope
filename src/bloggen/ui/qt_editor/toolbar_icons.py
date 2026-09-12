"""Dependency-free toolbar icons built from Qt themes, styles and glyphs."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
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
    "preview": "document-preview",
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
    "preview": "◉",
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


def toolbar_icon(owner: QWidget, key: str) -> QIcon:
    standard = _STANDARD_ICONS.get(key)
    if standard is not None:
        return owner.style().standardIcon(standard)
    theme_name = _THEME_ICONS.get(key)
    fallback = _text_icon(key, _GLYPHS.get(key, key[:2].upper()))
    if theme_name:
        themed = QIcon.fromTheme(theme_name)
        if not themed.isNull():
            return themed
    return fallback


def _text_icon(key: str, glyph: str) -> QIcon:
    pixmap = QPixmap(24, 24)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    painter.setPen(QColor("#202124"))
    font = QFont()
    font.setPixelSize(13 if len(glyph) > 1 else 16)
    font.setBold(key == "bold")
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
