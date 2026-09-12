"""Commandes de mise en forme du prototype reposant sur l'undo natif Qt."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPalette, QTextCharFormat, QTextCursor, QTextListFormat
from PySide6.QtWidgets import QTextEdit

from bloggen.markdown.rich_text_model import (
    BLOCKQUOTE,
    BULLET_LIST,
    HEADING,
    LIST_ITEM,
    ORDERED_LIST,
    PARAGRAPH,
)
from bloggen.ui.qt_editor.constants import (
    ALIGNMENT_PROPERTY,
    BLOCK_KIND_PROPERTY,
    BOLD_PROPERTY,
    HEADING_LEVEL_PROPERTY,
    ITALIC_PROPERTY,
    LIST_KIND_PROPERTY,
    STRIKETHROUGH_PROPERTY,
    SUPERSCRIPT_PROPERTY,
    UNDERLINE_PROPERTY,
)
from bloggen.ui.qt_editor.document_adapter import (
    inline_format_enabled,
    is_raw_block,
    is_semantic_inline_object_format,
    refresh_block_visuals,
    selection_touches_raw_block,
)


def toggle_bold(editor: QTextEdit) -> None:
    _toggle_inline(
        editor,
        BOLD_PROPERTY,
        lambda fmt, enabled: fmt.setFontWeight(
            QFont.Weight.Bold.value if enabled else QFont.Weight.Normal.value
        ),
    )


def toggle_italic(editor: QTextEdit) -> None:
    _toggle_inline(editor, ITALIC_PROPERTY, QTextCharFormat.setFontItalic)


def toggle_underline(editor: QTextEdit) -> None:
    _toggle_inline(editor, UNDERLINE_PROPERTY, QTextCharFormat.setFontUnderline)


def toggle_strikethrough(editor: QTextEdit) -> None:
    _toggle_inline(editor, STRIKETHROUGH_PROPERTY, QTextCharFormat.setFontStrikeOut)


def toggle_superscript(editor: QTextEdit) -> None:
    _toggle_inline(
        editor,
        SUPERSCRIPT_PROPERTY,
        lambda fmt, enabled: fmt.setVerticalAlignment(
            QTextCharFormat.VerticalAlignment.AlignSuperScript
            if enabled
            else QTextCharFormat.VerticalAlignment.AlignNormal
        ),
    )


def set_link(editor: QTextEdit, href: str | None) -> None:
    """Apply a native Qt anchor, or remove it when ``href`` is ``None``."""

    selection = editor.textCursor()
    ranges = _selected_text_ranges(selection) if selection.hasSelection() else None
    if ranges == [] or (
        not selection.hasSelection()
        and (
            is_raw_block(selection.block())
            or is_semantic_inline_object_format(selection.charFormat())
        )
    ):
        return

    if not selection.hasSelection():
        char_format = QTextCharFormat()
        char_format.setAnchor(href is not None)
        char_format.setAnchorHref(href or "")
        char_format.setFontUnderline(
            href is not None
            or inline_format_enabled(selection.charFormat(), UNDERLINE_PROPERTY)
        )
        char_format.setForeground(
            QColor("#1a5fb4")
            if href is not None
            else editor.palette().brush(QPalette.ColorRole.Text)
        )
        selection.beginEditBlock()
        selection.mergeCharFormat(char_format)
        selection.endEditBlock()
        editor.setTextCursor(selection)
        return

    targets = ranges
    edit_cursor = QTextCursor(selection.document())
    edit_cursor.beginEditBlock()
    try:
        for start, end, existing_format in targets:
            char_format = QTextCharFormat()
            char_format.setAnchor(href is not None)
            char_format.setAnchorHref(href or "")
            char_format.setFontUnderline(
                href is not None
                or inline_format_enabled(existing_format, UNDERLINE_PROPERTY)
            )
            if href is not None:
                char_format.setForeground(QColor("#1a5fb4"))
            else:
                char_format.setForeground(
                    editor.palette().brush(QPalette.ColorRole.Text)
                )
            target = QTextCursor(selection.document())
            target.setPosition(start)
            if end != start:
                target.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
            target.mergeCharFormat(char_format)
    finally:
        edit_cursor.endEditBlock()
    editor.setTextCursor(selection)


def set_paragraph(editor: QTextEdit) -> None:
    _set_leaf_block_kind(editor, PARAGRAPH)


def clear_formatting(editor: QTextEdit) -> None:
    """Strip inline styling from the selection and reset it to a plain paragraph."""

    cursor = editor.textCursor()
    if not cursor.hasSelection() or selection_touches_raw_block(cursor):
        return
    ranges = _selected_text_ranges(cursor)
    outer = QTextCursor(cursor.document())
    outer.beginEditBlock()
    try:
        blank_format = QTextCharFormat()
        for start, end, _existing_format in ranges:
            target = QTextCursor(cursor.document())
            target.setPosition(start)
            target.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
            target.setCharFormat(blank_format)
        _set_leaf_block_kind(editor, PARAGRAPH)
    finally:
        outer.endEditBlock()
    editor.setTextCursor(cursor)


def set_heading(editor: QTextEdit, level: int) -> None:
    if level not in {1, 2, 3, 4}:
        raise ValueError(f"Niveau de titre non pris en charge : H{level}")
    _set_leaf_block_kind(editor, HEADING, level)


def set_blockquote(editor: QTextEdit) -> None:
    _set_leaf_block_kind(editor, BLOCKQUOTE)


def set_list(editor: QTextEdit, kind: str) -> None:
    if kind not in {BULLET_LIST, ORDERED_LIST}:
        raise ValueError(f"Type de liste non pris en charge : {kind}")
    cursor = editor.textCursor()
    if selection_touches_raw_block(cursor):
        return
    blocks = _selected_blocks(editor.document(), cursor)
    cursor.beginEditBlock()
    for block in blocks:
        text_list = block.textList()
        if text_list is not None:
            text_list.remove(block)
        block_cursor = QTextCursor(block)
        block_format = block.blockFormat()
        _clear_heading_state(block_format)
        block_format.setLeftMargin(0.0)
        block_format.setAlignment(Qt.AlignmentFlag.AlignLeft)
        block_format.setProperty(ALIGNMENT_PROPERTY, "left")
        block_format.setProperty(BLOCK_KIND_PROPERTY, LIST_ITEM)
        block_format.setProperty(LIST_KIND_PROPERTY, kind)
        block_cursor.setBlockFormat(block_format)
        refresh_block_visuals(block)

    list_format = QTextListFormat()
    list_format.setIndent(1)
    list_format.setStyle(
        QTextListFormat.Style.ListDisc
        if kind == BULLET_LIST
        else QTextListFormat.Style.ListDecimal
    )
    list_format.setProperty(LIST_KIND_PROPERTY, kind)
    cursor.createList(list_format)
    for block in blocks:
        block_cursor = QTextCursor(block)
        block_format = block.blockFormat()
        block_format.setProperty(BLOCK_KIND_PROPERTY, LIST_ITEM)
        block_format.setProperty(LIST_KIND_PROPERTY, kind)
        block_cursor.setBlockFormat(block_format)
    cursor.endEditBlock()


def set_alignment(editor: QTextEdit, alignment: str) -> None:
    qt_alignment = {
        "left": Qt.AlignmentFlag.AlignLeft,
        "center": Qt.AlignmentFlag.AlignHCenter,
        "right": Qt.AlignmentFlag.AlignRight,
        "justify": Qt.AlignmentFlag.AlignJustify,
    }.get(alignment)
    if qt_alignment is None:
        raise ValueError(f"Alignement non pris en charge : {alignment}")
    cursor = editor.textCursor()
    if selection_touches_raw_block(cursor):
        return
    blocks = _selected_blocks(editor.document(), cursor)
    if any(block.textList() is not None for block in blocks):
        raise ValueError("L'alignement des elements de liste n'est pas pris en charge")
    cursor.beginEditBlock()
    for block in blocks:
        block_cursor = QTextCursor(block)
        block_format = block.blockFormat()
        block_format.setAlignment(qt_alignment)
        block_format.setProperty(ALIGNMENT_PROPERTY, alignment)
        block_cursor.setBlockFormat(block_format)
    cursor.endEditBlock()


def toggle_justify(editor: QTextEdit) -> None:
    """Toggle only the caret's paragraph between left and justified."""

    selection = editor.textCursor()
    block = selection.block()
    if not block.isValid() or is_raw_block(block) or block.textList() is not None:
        return
    block_format = block.blockFormat()
    stored = block_format.property(ALIGNMENT_PROPERTY)
    justified = stored == "justify" or bool(
        block_format.alignment() & Qt.AlignmentFlag.AlignJustify
    )
    block_format.setAlignment(
        Qt.AlignmentFlag.AlignLeft if justified else Qt.AlignmentFlag.AlignJustify
    )
    block_format.setProperty(
        ALIGNMENT_PROPERTY,
        "left" if justified else "justify",
    )
    edit_cursor = QTextCursor(block)
    edit_cursor.beginEditBlock()
    try:
        edit_cursor.setBlockFormat(block_format)
    finally:
        edit_cursor.endEditBlock()
    editor.setTextCursor(selection)


def _toggle_inline(
    editor: QTextEdit,
    property_id: int,
    apply_visual: Callable[[QTextCharFormat, bool], None],
) -> None:
    cursor = editor.textCursor()
    text_ranges = _selected_text_ranges(cursor) if cursor.hasSelection() else None
    if text_ranges == [] or (
        not cursor.hasSelection()
        and is_semantic_inline_object_format(cursor.charFormat())
    ):
        return
    enabled = not _selection_all_has_format(cursor, property_id, text_ranges)
    char_format = QTextCharFormat()
    char_format.setProperty(property_id, enabled)
    apply_visual(char_format, enabled)
    _merge_text_char_format(editor, char_format, text_ranges=text_ranges)


def _set_leaf_block_kind(editor: QTextEdit, kind: str, level: int | None = None) -> None:
    cursor = editor.textCursor()
    if selection_touches_raw_block(cursor):
        return
    blocks = _selected_blocks(editor.document(), cursor)
    cursor.beginEditBlock()
    for block in blocks:
        text_list = block.textList()
        if text_list is not None:
            text_list.remove(block)
        block_cursor = QTextCursor(block)
        block_format = block.blockFormat()
        block_format.setProperty(BLOCK_KIND_PROPERTY, kind)
        block_format.clearProperty(LIST_KIND_PROPERTY)
        if kind == HEADING:
            block_format.setProperty(HEADING_LEVEL_PROPERTY, level)
            block_format.setHeadingLevel(level)
        else:
            _clear_heading_state(block_format)
        block_format.setLeftMargin(24.0 if kind == BLOCKQUOTE else 0.0)
        # Switching block kind resets to that kind's own default alignment
        # (normal paragraphs justified, headings/quotes left) rather than
        # carrying over whatever the previous kind happened to have.
        default_alignment = "justify" if kind == PARAGRAPH else "left"
        block_format.setAlignment(
            Qt.AlignmentFlag.AlignJustify
            if default_alignment == "justify"
            else Qt.AlignmentFlag.AlignLeft
        )
        block_format.setProperty(ALIGNMENT_PROPERTY, default_alignment)
        block_cursor.setBlockFormat(block_format)
        refresh_block_visuals(block)
    cursor.endEditBlock()


def _clear_heading_state(block_format) -> None:
    block_format.clearProperty(HEADING_LEVEL_PROPERTY)
    block_format.setHeadingLevel(0)


def _selection_all_has_format(
    cursor: QTextCursor,
    property_id: int,
    text_ranges: list[tuple[int, int, QTextCharFormat]] | None = None,
) -> bool:
    if not cursor.hasSelection():
        return inline_format_enabled(cursor.charFormat(), property_id)

    ranges = text_ranges if text_ranges is not None else _selected_text_ranges(cursor)
    return bool(ranges) and all(
        inline_format_enabled(char_format, property_id)
        for _start, _end, char_format in ranges
    )


def _selected_text_ranges(
    cursor: QTextCursor,
) -> list[tuple[int, int, QTextCharFormat]]:
    if not cursor.hasSelection():
        return []
    selection_start = cursor.selectionStart()
    selection_end = cursor.selectionEnd()
    ranges: list[tuple[int, int, QTextCharFormat]] = []
    block = cursor.document().findBlock(selection_start)
    while block.isValid() and block.position() < selection_end:
        if is_raw_block(block):
            block = block.next()
            continue
        iterator = block.begin()
        while not iterator.atEnd():
            fragment = iterator.fragment()
            fragment_start = fragment.position()
            fragment_end = fragment_start + fragment.length()
            if (
                fragment.isValid()
                and not is_semantic_inline_object_format(fragment.charFormat())
                and fragment_end > selection_start
                and fragment_start < selection_end
            ):
                ranges.append(
                    (
                        max(fragment_start, selection_start),
                        min(fragment_end, selection_end),
                        fragment.charFormat(),
                    )
                )
            iterator += 1
        block = block.next()
    return ranges


def _merge_text_char_format(
    editor: QTextEdit,
    char_format: QTextCharFormat,
    *,
    text_ranges: list[tuple[int, int, QTextCharFormat]] | None = None,
) -> bool:
    selection = editor.textCursor()
    if not selection.hasSelection():
        if is_raw_block(selection.block()) or is_semantic_inline_object_format(
            selection.charFormat()
        ):
            return False
        selection.beginEditBlock()
        selection.mergeCharFormat(char_format)
        selection.endEditBlock()
        editor.setTextCursor(selection)
        return True

    ranges = text_ranges if text_ranges is not None else _selected_text_ranges(selection)
    if not ranges:
        return False
    edit_block = QTextCursor(selection.document())
    edit_block.beginEditBlock()
    try:
        for start, end, _existing_format in ranges:
            text_cursor = QTextCursor(selection.document())
            text_cursor.setPosition(start)
            text_cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
            text_cursor.mergeCharFormat(char_format)
    finally:
        edit_block.endEditBlock()
    editor.setTextCursor(selection)
    return True


def _selected_blocks(document, cursor: QTextCursor):
    start = cursor.selectionStart()
    end = cursor.selectionEnd()
    block = document.findBlock(start)
    blocks = []
    while block.isValid() and (start == end or block.position() < end):
        blocks.append(block)
        if block.position() + block.length() > end:
            break
        block = block.next()
    return blocks
