"""Purely visual formatting for Merope graphical tables."""

from __future__ import annotations

import math

from PySide6.QtGui import QColor, QTextLength, QTextTable, QTextTableFormat

from bloggen.ui.qt_editor.constants import (
    MEROPE_TABLE_PROPERTY,
    TABLE_BLOCK_MARGINS,
    TABLE_BORDER_WIDTH,
    TABLE_CELL_PADDING,
    TABLE_CELL_SPACING,
    TABLE_HEADER_BACKGROUND,
)


def make_table_format(columns: int) -> QTextTableFormat:
    """Build the transient Qt format for a canonical Merope table."""

    table_format = QTextTableFormat()
    _configure_table_style(table_format)
    _set_format_column_percentages(table_format, equal_column_percentages(columns))
    return table_format


def refresh_table_visuals(
    table: QTextTable,
    *,
    column_percentages: tuple[float, ...] | None = None,
) -> None:
    """Reapply table visuals while preserving valid user column widths."""

    table_format = table.format()
    if column_percentages is None:
        try:
            column_percentages = table_column_percentages(table)
        except ValueError:
            column_percentages = equal_column_percentages(table.columns())
    _validate_column_percentages(column_percentages, table.columns())
    _configure_table_style(table_format)
    _set_format_column_percentages(table_format, column_percentages)
    table.setFormat(table_format)

    header_rows = table_format.headerRowCount()
    header_color = QColor(TABLE_HEADER_BACKGROUND)
    for row in range(table.rows()):
        for column in range(table.columns()):
            cell = table.cellAt(row, column)
            cell_format = cell.format()
            if row < header_rows:
                cell_format.setBackground(header_color)
            else:
                cell_format.clearBackground()
            cell.setFormat(cell_format)


def table_column_percentages(table: QTextTable) -> tuple[float, ...]:
    """Return validated relative widths from a graphical table."""

    constraints = table.format().columnWidthConstraints()
    if len(constraints) != table.columns() or any(
        item.type() != QTextLength.Type.PercentageLength for item in constraints
    ):
        raise ValueError("Les largeurs de colonnes Qt ne sont pas représentables")
    widths = tuple(float(item.rawValue()) for item in constraints)
    _validate_column_percentages(widths, table.columns())
    return widths


def set_table_column_percentages(
    table: QTextTable,
    widths: tuple[float, ...],
) -> None:
    """Apply validated transient percentages without changing table semantics."""

    _validate_column_percentages(widths, table.columns())
    table_format = table.format()
    _set_format_column_percentages(table_format, widths)
    table.setFormat(table_format)


def equal_column_percentages(columns: int) -> tuple[float, ...]:
    if columns < 1:
        raise ValueError("Un tableau graphique doit avoir au moins une colonne")
    width = 100.0 / columns
    return tuple(width for _column in range(columns))


def percentages_after_column_insert(
    widths: tuple[float, ...],
    source_column: int,
    inserted_column: int,
) -> tuple[float, ...]:
    """Split one neighbouring column equally with a newly inserted column."""

    _validate_column_percentages(widths, len(widths))
    if not 0 <= source_column < len(widths):
        raise ValueError("Colonne source invalide")
    if not 0 <= inserted_column <= len(widths):
        raise ValueError("Position de nouvelle colonne invalide")
    shared = widths[source_column] / 2.0
    result = list(widths)
    result[source_column] = shared
    result.insert(inserted_column, shared)
    return tuple(result)


def percentages_after_column_remove(
    widths: tuple[float, ...],
    removed_column: int,
) -> tuple[float, ...]:
    """Give a removed width to the right neighbour, or the previous one."""

    _validate_column_percentages(widths, len(widths))
    if len(widths) <= 1 or not 0 <= removed_column < len(widths):
        raise ValueError("La dernière colonne ne peut pas être redistribuée")
    removed_width = widths[removed_column]
    result = list(widths)
    del result[removed_column]
    recipient = removed_column if removed_column < len(result) else len(result) - 1
    result[recipient] += removed_width
    return tuple(result)


def _configure_table_style(table_format: QTextTableFormat) -> None:
    table_format.setProperty(MEROPE_TABLE_PROPERTY, True)
    table_format.setHeaderRowCount(1)
    table_format.setBorder(TABLE_BORDER_WIDTH)
    table_format.setCellPadding(TABLE_CELL_PADDING)
    table_format.setCellSpacing(TABLE_CELL_SPACING)
    table_format.setTopMargin(TABLE_BLOCK_MARGINS[0])
    table_format.setBottomMargin(TABLE_BLOCK_MARGINS[1])
    table_format.setWidth(
        QTextLength(QTextLength.Type.PercentageLength, 100.0)
    )


def _set_format_column_percentages(
    table_format: QTextTableFormat,
    widths: tuple[float, ...],
) -> None:
    table_format.setColumnWidthConstraints(
        [
            QTextLength(QTextLength.Type.PercentageLength, width)
            for width in widths
        ]
    )


def _validate_column_percentages(
    widths: tuple[float, ...],
    columns: int,
) -> None:
    if len(widths) != columns or columns < 1:
        raise ValueError("Une largeur est requise pour chaque colonne")
    if any(not math.isfinite(width) or width <= 0 for width in widths):
        raise ValueError("Chaque largeur de colonne doit être strictement positive")
    if not math.isclose(sum(widths), 100.0, abs_tol=0.01):
        raise ValueError("La somme des largeurs de colonnes doit valoir 100 %")
