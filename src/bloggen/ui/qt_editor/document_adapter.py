"""Adaptateur explicite entre ``Block``/``InlineRun`` et ``QTextDocument``.

Qt n'est jamais utilise ici comme parseur Markdown. Les proprietes applicatives
conservent la semantique Merope qui ne peut pas etre deduite sans ambiguite de
la seule apparence du document.
"""

from __future__ import annotations

from collections.abc import Iterable

from PySide6.QtCore import Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QTextBlock,
    QTextBlockFormat,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
    QTextListFormat,
)

from bloggen.markdown.rich_text_model import (
    BLOCKQUOTE,
    BULLET_LIST,
    HEADING,
    LIST_ITEM,
    ORDERED_LIST,
    PARAGRAPH,
    Block,
    InlineRun,
)
from bloggen.ui.qt_editor.constants import (
    ALIGNMENT_PROPERTY,
    BLOCK_KIND_PROPERTY,
    BLOCKQUOTE_LEFT_MARGIN,
    BODY_POINT_SIZE,
    BOLD_PROPERTY,
    HEADING_LEVEL_PROPERTY,
    HEADING_POINT_SIZES,
    ITALIC_PROPERTY,
    LIST_KIND_PROPERTY,
    STRIKETHROUGH_PROPERTY,
    SUPERSCRIPT_PROPERTY,
)


SUPPORTED_LEAF_KINDS = {PARAGRAPH, HEADING, BLOCKQUOTE}
SUPPORTED_LIST_KINDS = {BULLET_LIST, ORDERED_LIST}
SUPPORTED_ALIGNMENTS = {"left", "center", "right", "justify"}


class UnsupportedDocumentError(ValueError):
    """Base exception for content the prototype cannot preserve safely."""


class UnsupportedBlockError(UnsupportedDocumentError):
    """Raised instead of silently dropping an unsupported block."""


class UnsupportedInlineError(UnsupportedDocumentError):
    """Raised instead of silently dropping an unsupported inline leaf."""


def populate_document(document: QTextDocument, blocks: list[Block]) -> None:
    """Replace ``document`` with the supported portion of ``blocks``.

    Validation happens before clearing the destination so an unsupported block
    never leaves a partially populated document behind.
    """

    _validate_blocks(blocks)
    document.clear()
    cursor = QTextCursor(document)
    first_block = True

    for block in blocks:
        if block.kind in SUPPORTED_LEAF_KINDS:
            first_block = _populate_leaf_block(cursor, block, first_block)
        elif block.kind in SUPPORTED_LIST_KINDS:
            first_block = _populate_list(cursor, block, first_block)
        else:  # Kept as a defensive guard if validation evolves separately.
            raise UnsupportedBlockError(f"Type de bloc Qt non pris en charge : {block.kind}")

    cursor.movePosition(QTextCursor.MoveOperation.Start)
    document.clearUndoRedoStacks()


def extract_blocks(document: QTextDocument) -> list[Block]:
    """Build Merope blocks by traversing Qt blocks and text fragments.

    Deliberately does not use ``QTextDocument.toPlainText()``: Qt normalizes
    non-breaking spaces in that convenience representation.
    """

    if document.rootFrame().childFrames():
        raise UnsupportedBlockError(
            "Les cadres et tableaux QTextDocument ne sont pas encore pris en charge"
        )

    result: list[Block] = []
    block = document.begin()
    while block.isValid():
        text_list = block.textList()
        if text_list is not None:
            list_kind = _list_kind(block)
            list_object_index = text_list.objectIndex()
            items: list[Block] = []
            while block.isValid():
                current_list = block.textList()
                if current_list is None or current_list.objectIndex() != list_object_index:
                    break
                if _list_kind(block) != list_kind:
                    raise UnsupportedBlockError("Une meme liste Qt melange plusieurs types de listes")
                stored_kind = block.blockFormat().property(BLOCK_KIND_PROPERTY)
                if stored_kind not in (None, "", LIST_ITEM):
                    raise UnsupportedBlockError(
                        f"Bloc {stored_kind!r} imbrique dans une liste Qt non pris en charge"
                    )
                items.append(Block(kind=LIST_ITEM, runs=_extract_runs(block)))
                block = block.next()
            result.append(Block(kind=list_kind, children=items))
            continue

        block_format = block.blockFormat()
        kind = block_format.property(BLOCK_KIND_PROPERTY)
        if not kind:
            native_heading_level = block_format.headingLevel()
            kind = HEADING if native_heading_level else PARAGRAPH
        if kind not in SUPPORTED_LEAF_KINDS:
            raise UnsupportedBlockError(f"Type de bloc Qt non pris en charge : {kind}")

        level = None
        if kind == HEADING:
            raw_level = (
                block_format.property(HEADING_LEVEL_PROPERTY)
                or block_format.headingLevel()
            )
            level = int(raw_level or 1)
            if level not in HEADING_POINT_SIZES:
                raise UnsupportedBlockError(f"Niveau de titre Qt non pris en charge : H{level}")

        result.append(
            Block(
                kind=kind,
                level=level,
                runs=_extract_runs(block),
                alignment=_alignment_from_format(block_format),
            )
        )
        block = block.next()
    return result


def make_char_format(run: InlineRun, *, heading_level: int | None = None) -> QTextCharFormat:
    """Create the Qt format carrying one run's visual and semantic state."""

    char_format = QTextCharFormat()
    char_format.setProperty(BOLD_PROPERTY, run.bold)
    char_format.setProperty(ITALIC_PROPERTY, run.italic)
    char_format.setProperty(STRIKETHROUGH_PROPERTY, run.strikethrough)
    char_format.setProperty(SUPERSCRIPT_PROPERTY, run.superscript)
    char_format.setFontWeight(
        QFont.Weight.Bold.value if run.bold else QFont.Weight.Normal.value
    )
    char_format.setFontItalic(run.italic)
    char_format.setFontStrikeOut(run.strikethrough)
    char_format.setVerticalAlignment(
        QTextCharFormat.VerticalAlignment.AlignSuperScript
        if run.superscript
        else QTextCharFormat.VerticalAlignment.AlignNormal
    )
    char_format.setFontPointSize(
        HEADING_POINT_SIZES.get(heading_level, BODY_POINT_SIZE)
    )
    if run.link_href is not None:
        char_format.setAnchor(True)
        char_format.setAnchorHref(run.link_href)
        char_format.setFontUnderline(True)
        char_format.setForeground(QColor("#1a5fb4"))
    return char_format


def refresh_block_visuals(block: QTextBlock) -> None:
    """Refresh heading/body size without altering inline semantic properties."""

    if not block.isValid():
        return
    block_format = block.blockFormat()
    level = (
        int(block_format.property(HEADING_LEVEL_PROPERTY) or 1)
        if block_format.property(BLOCK_KIND_PROPERTY) == HEADING
        else None
    )
    cursor = QTextCursor(block)
    cursor.movePosition(
        QTextCursor.MoveOperation.EndOfBlock,
        QTextCursor.MoveMode.KeepAnchor,
    )
    visual_format = QTextCharFormat()
    visual_format.setFontPointSize(HEADING_POINT_SIZES.get(level, BODY_POINT_SIZE))
    cursor.mergeCharFormat(visual_format)


def _validate_blocks(blocks: Iterable[Block]) -> None:
    for block in blocks:
        if block.kind in SUPPORTED_LEAF_KINDS:
            if block.children:
                raise UnsupportedBlockError(
                    f"Bloc {block.kind!r} avec enfants non pris en charge par le prototype Qt"
                )
            if block.kind == HEADING and block.level not in HEADING_POINT_SIZES:
                raise UnsupportedBlockError(
                    f"Niveau de titre Qt non pris en charge : H{block.level}"
                )
            _validate_alignment(block.alignment)
            _validate_runs(block.runs)
            continue

        if block.kind in SUPPORTED_LIST_KINDS:
            if block.runs:
                raise UnsupportedBlockError(
                    f"Contenu direct inattendu dans le bloc de liste {block.kind!r}"
                )
            if not block.children:
                raise UnsupportedBlockError("Les listes vides ne sont pas representables dans Qt")
            for item in block.children:
                if item.kind != LIST_ITEM or item.children:
                    raise UnsupportedBlockError(
                        "Seuls les elements de liste simples sont pris en charge par Qt"
                    )
                if item.alignment != "left":
                    raise UnsupportedBlockError(
                        "L'alignement des elements de liste n'est pas encore pris en charge"
                    )
                _validate_runs(item.runs)
            continue

        raise UnsupportedBlockError(f"Type de bloc Qt non pris en charge : {block.kind}")


def _validate_runs(runs: Iterable[InlineRun]) -> None:
    for run in runs:
        if run.image_src is not None or any(
            value is not None
            for value in (run.image_alt, run.image_width, run.image_height, run.image_align)
        ):
            raise UnsupportedInlineError("Les images ne sont pas encore prises en charge par Qt")
        if run.footnote_ref is not None:
            raise UnsupportedInlineError("Les appels de note ne sont pas encore pris en charge par Qt")


def _validate_alignment(alignment: str) -> None:
    if alignment not in SUPPORTED_ALIGNMENTS:
        raise UnsupportedBlockError(f"Alignement Qt non pris en charge : {alignment!r}")


def _populate_leaf_block(cursor: QTextCursor, block: Block, first: bool) -> bool:
    block_format = _make_block_format(block.kind, block.alignment, block.level)
    default_char_format = make_char_format(
        InlineRun(), heading_level=block.level if block.kind == HEADING else None
    )
    _begin_block(cursor, block_format, default_char_format, first)
    for run in block.runs:
        cursor.insertText(
            run.text,
            make_char_format(
                run,
                heading_level=block.level if block.kind == HEADING else None,
            ),
        )
    return False


def _populate_list(cursor: QTextCursor, block: Block, first: bool) -> bool:
    list_format = QTextListFormat()
    list_format.setIndent(1)
    list_format.setStyle(
        QTextListFormat.Style.ListDisc
        if block.kind == BULLET_LIST
        else QTextListFormat.Style.ListDecimal
    )
    list_format.setProperty(LIST_KIND_PROPERTY, block.kind)

    qt_list = None
    for index, item in enumerate(block.children):
        item_format = _make_block_format(LIST_ITEM, "left", None)
        item_format.setProperty(LIST_KIND_PROPERTY, block.kind)
        default_char_format = make_char_format(InlineRun())
        _begin_block(cursor, item_format, default_char_format, first and index == 0)
        if qt_list is None:
            qt_list = cursor.createList(list_format)
        else:
            qt_list.add(cursor.block())
        for run in item.runs:
            cursor.insertText(run.text, make_char_format(run))
    return False


def _begin_block(
    cursor: QTextCursor,
    block_format: QTextBlockFormat,
    char_format: QTextCharFormat,
    first: bool,
) -> None:
    if first:
        cursor.setBlockFormat(block_format)
        cursor.setBlockCharFormat(char_format)
        return

    cursor.movePosition(QTextCursor.MoveOperation.End)
    cursor.insertBlock(block_format, char_format)
    current_list = cursor.currentList()
    if current_list is not None:
        current_list.remove(cursor.block())
        cursor.setBlockFormat(block_format)


def _make_block_format(kind: str, alignment: str, level: int | None) -> QTextBlockFormat:
    block_format = QTextBlockFormat()
    block_format.setProperty(BLOCK_KIND_PROPERTY, kind)
    block_format.setProperty(ALIGNMENT_PROPERTY, alignment)
    block_format.setAlignment(_QT_ALIGNMENTS[alignment])
    if kind == HEADING:
        block_format.setProperty(HEADING_LEVEL_PROPERTY, level)
        block_format.setHeadingLevel(level)
    elif kind == BLOCKQUOTE:
        block_format.setLeftMargin(BLOCKQUOTE_LEFT_MARGIN)
    return block_format


def _extract_runs(block: QTextBlock) -> list[InlineRun]:
    runs: list[InlineRun] = []
    iterator = block.begin()
    while not iterator.atEnd():
        fragment = iterator.fragment()
        if fragment.isValid():
            char_format = fragment.charFormat()
            if char_format.isImageFormat():
                raise UnsupportedInlineError(
                    "Les images QTextDocument ne sont pas encore prises en charge"
                )
            run = InlineRun(
                text=fragment.text(),
                bold=_semantic_or_native(
                    char_format,
                    BOLD_PROPERTY,
                    char_format.fontWeight() >= QFont.Weight.Bold.value,
                ),
                italic=_semantic_or_native(
                    char_format, ITALIC_PROPERTY, char_format.fontItalic()
                ),
                strikethrough=_semantic_or_native(
                    char_format,
                    STRIKETHROUGH_PROPERTY,
                    char_format.fontStrikeOut(),
                ),
                superscript=_semantic_or_native(
                    char_format,
                    SUPERSCRIPT_PROPERTY,
                    char_format.verticalAlignment()
                    == QTextCharFormat.VerticalAlignment.AlignSuperScript,
                ),
                link_href=char_format.anchorHref() if char_format.isAnchor() else None,
            )
            _append_semantic_run(runs, run)
        iterator += 1
    return runs or [InlineRun(text="")]


def _append_semantic_run(runs: list[InlineRun], run: InlineRun) -> None:
    if runs and _same_inline_format(runs[-1], run):
        runs[-1].text += run.text
    else:
        runs.append(run)


def _same_inline_format(left: InlineRun, right: InlineRun) -> bool:
    return (
        left.bold,
        left.italic,
        left.strikethrough,
        left.superscript,
        left.link_href,
    ) == (
        right.bold,
        right.italic,
        right.strikethrough,
        right.superscript,
        right.link_href,
    )


def _semantic_or_native(
    char_format: QTextCharFormat,
    property_id: int,
    native_value: bool,
) -> bool:
    if char_format.hasProperty(property_id):
        return bool(char_format.property(property_id))
    return native_value


def _list_kind(block: QTextBlock) -> str:
    stored = block.blockFormat().property(LIST_KIND_PROPERTY)
    if stored in SUPPORTED_LIST_KINDS:
        return stored
    text_list = block.textList()
    if text_list is None:
        raise UnsupportedBlockError("Element de liste Qt orphelin")
    if text_list.format().indent() != 1:
        raise UnsupportedBlockError("Les listes Qt imbriquees ne sont pas encore prises en charge")
    style = text_list.format().style()
    if style in {
        QTextListFormat.Style.ListDecimal,
        QTextListFormat.Style.ListLowerAlpha,
        QTextListFormat.Style.ListUpperAlpha,
        QTextListFormat.Style.ListLowerRoman,
        QTextListFormat.Style.ListUpperRoman,
    }:
        return ORDERED_LIST
    if style in {
        QTextListFormat.Style.ListDisc,
        QTextListFormat.Style.ListCircle,
        QTextListFormat.Style.ListSquare,
    }:
        return BULLET_LIST
    raise UnsupportedBlockError(f"Style de liste Qt non pris en charge : {style}")


def _alignment_from_format(block_format: QTextBlockFormat) -> str:
    stored = block_format.property(ALIGNMENT_PROPERTY)
    if stored in SUPPORTED_ALIGNMENTS:
        return stored
    alignment = block_format.alignment()
    if alignment & Qt.AlignmentFlag.AlignHCenter:
        return "center"
    if alignment & Qt.AlignmentFlag.AlignRight:
        return "right"
    if alignment & Qt.AlignmentFlag.AlignJustify:
        return "justify"
    return "left"


_QT_ALIGNMENTS = {
    "left": Qt.AlignmentFlag.AlignLeft,
    "center": Qt.AlignmentFlag.AlignHCenter,
    "right": Qt.AlignmentFlag.AlignRight,
    "justify": Qt.AlignmentFlag.AlignJustify,
}
