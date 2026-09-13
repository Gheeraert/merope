"""Safe structural operations for marked Merope ``QTextTable`` objects."""

from __future__ import annotations

from PySide6.QtGui import (
    QTextBlock,
    QTextBlockFormat,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
    QTextTable,
    QTextTableCell,
)

from bloggen.markdown.rich_text_model import (
    PARAGRAPH,
    TABLE,
    TABLE_CELL,
    TABLE_ROW,
    Block,
    InlineRun,
)
from bloggen.ui.qt_editor.document_adapter import (
    UnsupportedBlockError,
    cursor_table_context,
    extract_blocks,
    initialize_table_cell,
    insert_blocks,
    is_merope_qtext_table,
    selection_crosses_qt_table_boundary,
    selection_is_within_single_table_cell,
)
from bloggen.ui.qt_editor.constants import BLOCK_KIND_PROPERTY, MEROPE_TABLE_PROPERTY


def insert_empty_table(
    cursor: QTextCursor,
    rows: int,
    columns: int,
) -> QTextCursor:
    """Insert an empty canonical table and return a caret in its first cell."""

    if rows < 1 or columns < 1:
        raise ValueError("Un tableau doit avoir au moins une ligne et une colonne")

    document = cursor.document()
    existing_tables = {
        frame.objectIndex()
        for frame in document.rootFrame().childFrames()
        if isinstance(frame, QTextTable)
    }
    table_block = Block(
        kind=TABLE,
        children=[
            Block(
                kind=TABLE_ROW,
                children=[
                    Block(kind=TABLE_CELL, runs=[InlineRun(text="")])
                    for _column in range(columns)
                ],
            )
            for _row in range(rows)
        ],
    )
    insert_blocks(cursor, [table_block])

    created = [
        frame
        for frame in document.rootFrame().childFrames()
        if isinstance(frame, QTextTable)
        and is_merope_qtext_table(frame)
        and frame.objectIndex() not in existing_tables
    ]
    if len(created) != 1:  # Defensive: insertion itself is already validated.
        raise UnsupportedBlockError(
            "Le tableau inséré ne peut pas être identifié sans ambiguïté"
        )
    return created[0].cellAt(0, 0).firstCursorPosition()


def insert_table_row(cursor: QTextCursor, *, before: bool) -> QTextCursor:
    """Insert one row beside the current row, preserving the header contract."""

    table, cell = _require_single_merope_cell(cursor)
    row = cell.row() if before else cell.row() + 1
    column = cell.column()

    edit = QTextCursor(cursor)
    edit.beginEditBlock()
    try:
        table.insertRows(row, 1)
        for column_index in range(table.columns()):
            initialize_table_cell(table.cellAt(row, column_index))
        _restore_table_contract(table)
    finally:
        edit.endEditBlock()
    return table.cellAt(row, column).firstCursorPosition()


def insert_table_column(cursor: QTextCursor, *, before: bool) -> QTextCursor:
    """Insert one column beside the current column."""

    table, cell = _require_single_merope_cell(cursor)
    row = cell.row()
    column = cell.column() if before else cell.column() + 1

    edit = QTextCursor(cursor)
    edit.beginEditBlock()
    try:
        table.insertColumns(column, 1)
        for row_index in range(table.rows()):
            initialize_table_cell(table.cellAt(row_index, column))
        _restore_table_contract(table)
    finally:
        edit.endEditBlock()
    return table.cellAt(row, column).firstCursorPosition()


def remove_table_row(cursor: QTextCursor) -> QTextCursor:
    """Remove the current row, refusing destruction of the last row."""

    table, cell = _require_single_merope_cell(cursor)
    if table.rows() <= 1:
        raise UnsupportedBlockError(
            "La dernière ligne ne peut être supprimée que avec le tableau"
        )
    row = cell.row()
    column = cell.column()

    edit = QTextCursor(cursor)
    edit.beginEditBlock()
    try:
        table.removeRows(row, 1)
        _restore_table_contract(table)
    finally:
        edit.endEditBlock()
    return table.cellAt(min(row, table.rows() - 1), column).firstCursorPosition()


def remove_table_column(cursor: QTextCursor) -> QTextCursor:
    """Remove the current column, refusing destruction of the last column."""

    table, cell = _require_single_merope_cell(cursor)
    if table.columns() <= 1:
        raise UnsupportedBlockError(
            "La dernière colonne ne peut être supprimée que avec le tableau"
        )
    row = cell.row()
    column = cell.column()

    edit = QTextCursor(cursor)
    edit.beginEditBlock()
    try:
        table.removeColumns(column, 1)
        _restore_table_contract(table)
    finally:
        edit.endEditBlock()
    return table.cellAt(row, min(column, table.columns() - 1)).firstCursorPosition()


def remove_table(cursor: QTextCursor) -> QTextCursor:
    """Remove exactly the current marked table and return a nearby text caret."""

    table, _cell = _require_single_merope_cell(cursor)
    document = cursor.document()
    next_block, previous_block = _surrounding_text_blocks(document, table)
    split_position = (
        previous_block.position() + previous_block.length() - 1
        if previous_block.isValid() and next_block.isValid()
        else None
    )
    next_block_format = (
        QTextBlockFormat(next_block.blockFormat())
        if next_block.isValid()
        else QTextBlockFormat()
    )
    next_char_format = (
        QTextCharFormat(QTextCursor(next_block).blockCharFormat())
        if next_block.isValid()
        else QTextCharFormat()
    )

    edit = QTextCursor(cursor)
    edit.beginEditBlock()
    try:
        table.removeRows(0, table.rows())
        if split_position is not None:
            separator = QTextCursor(document)
            separator.setPosition(
                min(split_position, document.characterCount() - 1)
            )
            separator.insertBlock(next_block_format, next_char_format)
            next_block = separator.block()
    finally:
        edit.endEditBlock()

    if next_block.isValid():
        return QTextCursor(next_block)
    if previous_block.isValid():
        target = QTextCursor(previous_block)
        target.movePosition(QTextCursor.MoveOperation.EndOfBlock)
        return target
    return QTextCursor(document)


def _require_single_merope_cell(
    cursor: QTextCursor,
) -> tuple[QTextTable, QTextTableCell]:
    """Validate table context completely before a structural mutation."""

    if (
        selection_crosses_qt_table_boundary(cursor)
        or not selection_is_within_single_table_cell(cursor)
    ):
        raise UnsupportedBlockError(
            "La commande Tableau exige une sélection dans une seule cellule"
        )
    context = cursor_table_context(cursor)
    if context is None:
        raise UnsupportedBlockError("Aucun tableau Mérope n’est sélectionné")
    # This validates the complete current representation, including the table
    # marker, cell shape, inline objects and foreign frames, before mutation.
    extract_blocks(cursor.document())
    return context


def _restore_table_contract(table: QTextTable) -> None:
    table_format = table.format()
    table_format.setProperty(MEROPE_TABLE_PROPERTY, True)
    table_format.setHeaderRowCount(1)
    table.setFormat(table_format)


def _surrounding_text_blocks(
    document: QTextDocument,
    table: QTextTable,
) -> tuple[QTextBlock, QTextBlock]:
    """Capture real top-level text neighbours, excluding table scaffolding."""

    items: list[QTextBlock | QTextTable] = []
    iterator = document.rootFrame().begin()
    while not iterator.atEnd():
        frame = iterator.currentFrame()
        if frame is not None:
            if isinstance(frame, QTextTable):
                items.append(frame)
        else:
            block = iterator.currentBlock()
            if block.isValid():
                items.append(block)
        iterator += 1

    index = next(i for i, item in enumerate(items) if item == table)
    previous = QTextBlock()
    following = QTextBlock()
    for item in reversed(items[:index]):
        if isinstance(item, QTextTable):
            break
        if not _technical_table_boundary(items, item):
            previous = item
            break
    for item in items[index + 1 :]:
        if isinstance(item, QTextTable):
            break
        if not _technical_table_boundary(items, item):
            following = item
            break
    return following, previous


def _technical_table_boundary(
    items: list[QTextBlock | QTextTable],
    block: QTextBlock,
) -> bool:
    index = items.index(block)
    return (
        not block.text()
        and block.textList() is None
        and not block.blockFormat().property(BLOCK_KIND_PROPERTY)
        and not block.blockFormat().headingLevel()
        and (
            (index > 0 and isinstance(items[index - 1], QTextTable))
            or (
                index + 1 < len(items)
                and isinstance(items[index + 1], QTextTable)
            )
        )
    )
