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
)
from bloggen.ui.qt_editor.document_adapter import (
    inline_format_enabled,
    refresh_block_visuals,
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

    cursor = editor.textCursor()
    char_format = QTextCharFormat()
    char_format.setAnchor(href is not None)
    char_format.setAnchorHref(href or "")
    char_format.setFontUnderline(href is not None)
    if href is not None:
        char_format.setForeground(QColor("#1a5fb4"))
    else:
        char_format.setForeground(editor.palette().brush(QPalette.ColorRole.Text))
    cursor.beginEditBlock()
    cursor.mergeCharFormat(char_format)
    cursor.endEditBlock()
    editor.setTextCursor(cursor)


def set_paragraph(editor: QTextEdit) -> None:
    _set_leaf_block_kind(editor, PARAGRAPH)


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


def _toggle_inline(
    editor: QTextEdit,
    property_id: int,
    apply_visual: Callable[[QTextCharFormat, bool], None],
) -> None:
    cursor = editor.textCursor()
    enabled = not _selection_all_has_format(cursor, property_id)
    char_format = QTextCharFormat()
    char_format.setProperty(property_id, enabled)
    apply_visual(char_format, enabled)
    cursor.beginEditBlock()
    cursor.mergeCharFormat(char_format)
    cursor.endEditBlock()
    editor.setTextCursor(cursor)


def _set_leaf_block_kind(editor: QTextEdit, kind: str, level: int | None = None) -> None:
    cursor = editor.textCursor()
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
        block_cursor.setBlockFormat(block_format)
        refresh_block_visuals(block)
    cursor.endEditBlock()


def _clear_heading_state(block_format) -> None:
    block_format.clearProperty(HEADING_LEVEL_PROPERTY)
    block_format.setHeadingLevel(0)


def _selection_all_has_format(cursor: QTextCursor, property_id: int) -> bool:
    if not cursor.hasSelection():
        return inline_format_enabled(cursor.charFormat(), property_id)

    selection_start = cursor.selectionStart()
    selection_end = cursor.selectionEnd()
    block = cursor.document().findBlock(selection_start)
    found_text = False
    while block.isValid() and block.position() < selection_end:
        iterator = block.begin()
        while not iterator.atEnd():
            fragment = iterator.fragment()
            fragment_start = fragment.position()
            fragment_end = fragment_start + fragment.length()
            if fragment_end > selection_start and fragment_start < selection_end:
                found_text = True
                if not inline_format_enabled(fragment.charFormat(), property_id):
                    return False
            iterator += 1
        block = block.next()
    return found_text


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
