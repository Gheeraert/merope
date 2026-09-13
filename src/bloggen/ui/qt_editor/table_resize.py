"""Viewport geometry and transient state for graphical table column drags."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QPoint, QRectF
from PySide6.QtGui import QTextDocument, QTextTable
from PySide6.QtWidgets import QTextEdit

from bloggen.ui.qt_editor.constants import MEROPE_TABLE_PROPERTY
from bloggen.ui.qt_editor.table_visuals import table_column_percentages


TABLE_COLUMN_RESIZE_HIT_TOLERANCE = 5.0
TABLE_COLUMN_RESIZE_DRAG_THRESHOLD = 3.0
TABLE_COLUMN_MIN_WIDTH_PIXELS = 40.0


@dataclass(frozen=True, slots=True)
class TableColumnBoundary:
    """One internal separator hit in viewport coordinates."""

    table_object_index: int
    boundary_index: int
    viewport_x: float


@dataclass(slots=True)
class TableColumnResizeState:
    """A drag preview; the document remains untouched until mouse release."""

    table_object_index: int
    boundary_index: int
    origin_x: float
    original_widths: tuple[float, ...]
    proposed_widths: tuple[float, ...]
    document_was_modified: bool
    activated: bool = False


def table_viewport_rect(editor: QTextEdit, table: QTextTable) -> QRectF:
    """Return a table frame rectangle translated from document to viewport."""

    rect = QRectF(editor.document().documentLayout().frameBoundingRect(table))
    return rect.translated(
        -editor.horizontalScrollBar().value(),
        -editor.verticalScrollBar().value(),
    )


def table_column_boundaries(
    editor: QTextEdit,
    table: QTextTable,
    *,
    widths: tuple[float, ...] | None = None,
) -> list[float]:
    """Return only internal vertical separators in viewport coordinates."""

    percentages = widths or table_column_percentages(table)
    rect = table_viewport_rect(editor, table)
    cumulative = 0.0
    boundaries: list[float] = []
    for width in percentages[:-1]:
        cumulative += width
        boundaries.append(rect.left() + rect.width() * cumulative / 100.0)
    return boundaries


def table_boundary_at(
    editor: QTextEdit,
    point: QPoint,
    *,
    tolerance: float = TABLE_COLUMN_RESIZE_HIT_TOLERANCE,
) -> TableColumnBoundary | None:
    """Hit-test marked top-level tables without relying on text cursors."""

    for frame in editor.document().rootFrame().childFrames():
        if not isinstance(frame, QTextTable) or not _is_merope_table(frame):
            continue
        rect = table_viewport_rect(editor, frame)
        if not rect.adjusted(-tolerance, 0.0, tolerance, 0.0).contains(point):
            continue
        try:
            boundaries = table_column_boundaries(editor, frame)
        except ValueError:
            continue
        for boundary_index, boundary_x in enumerate(boundaries):
            if abs(point.x() - boundary_x) <= tolerance:
                return TableColumnBoundary(
                    frame.objectIndex(),
                    boundary_index,
                    boundary_x,
                )
    return None


def resized_column_percentages(
    editor: QTextEdit,
    table: QTextTable,
    widths: tuple[float, ...],
    boundary_index: int,
    viewport_x: float,
) -> tuple[float, ...]:
    """Resize only two adjacent columns, clamped to a visible minimum."""

    if len(widths) != table.columns() or not 0 <= boundary_index < len(widths) - 1:
        raise ValueError("Frontière de colonne invalide")
    rect = table_viewport_rect(editor, table)
    if rect.width() <= 0:
        raise ValueError("Le tableau n’a pas de largeur visible")

    prefix = sum(widths[:boundary_index])
    pair_width = widths[boundary_index] + widths[boundary_index + 1]
    pair_pixels = rect.width() * pair_width / 100.0
    effective_minimum = min(
        TABLE_COLUMN_MIN_WIDTH_PIXELS,
        max(0.25, (pair_pixels - 1.0) / 2.0),
    )
    minimum_percent = effective_minimum / rect.width() * 100.0
    pointer_percent = (viewport_x - rect.left()) / rect.width() * 100.0
    left_width = min(
        max(pointer_percent - prefix, minimum_percent),
        pair_width - minimum_percent,
    )

    result = list(widths)
    result[boundary_index] = left_width
    result[boundary_index + 1] = pair_width - left_width
    return tuple(result)


def table_for_object_index(
    document: QTextDocument,
    object_index: int,
) -> QTextTable | None:
    """Resolve a still-live marked top-level table during a drag."""

    for frame in document.rootFrame().childFrames():
        if (
            isinstance(frame, QTextTable)
            and frame.objectIndex() == object_index
            and _is_merope_table(frame)
        ):
            return frame
    return None


def _is_merope_table(table: QTextTable) -> bool:
    table_format = table.format()
    return table_format.hasProperty(MEROPE_TABLE_PROPERTY) and bool(
        table_format.property(MEROPE_TABLE_PROPERTY)
    )
