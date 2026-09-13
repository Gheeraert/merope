"""Purely visual formatting for Merope graphical tables."""

from __future__ import annotations

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
    _configure_table_format(table_format, columns)
    return table_format


def refresh_table_visuals(table: QTextTable) -> None:
    """Reapply equal widths and row-role visuals after a structural edit."""

    table_format = table.format()
    _configure_table_format(table_format, table.columns())
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


def _configure_table_format(
    table_format: QTextTableFormat,
    columns: int,
) -> None:
    if columns < 1:
        raise ValueError("Un tableau graphique doit avoir au moins une colonne")
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
    width = 100.0 / columns
    table_format.setColumnWidthConstraints(
        [
            QTextLength(QTextLength.Type.PercentageLength, width)
            for _column in range(columns)
        ]
    )
