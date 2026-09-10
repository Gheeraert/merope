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
    QTextImageFormat,
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
    IMAGE_ALIGN_PROPERTY,
    IMAGE_ALT_PROPERTY,
    IMAGE_HEIGHT_PROPERTY,
    IMAGE_MARKER_PROPERTY,
    IMAGE_SRC_PROPERTY,
    IMAGE_WIDTH_PROPERTY,
    ITALIC_PROPERTY,
    LIST_KIND_PROPERTY,
    STRIKETHROUGH_PROPERTY,
    SUPERSCRIPT_PROPERTY,
)


SUPPORTED_LEAF_KINDS = {PARAGRAPH, HEADING, BLOCKQUOTE}
SUPPORTED_LIST_KINDS = {BULLET_LIST, ORDERED_LIST}
SUPPORTED_ALIGNMENTS = {"left", "center", "right", "justify"}
SUPPORTED_IMAGE_ALIGNMENTS = {None, "left", "center", "right"}
_OPTIONAL_IMAGE_STRING_PREFIX = "merope-string:"


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

    validate_blocks(blocks)
    document.clear()
    cursor = QTextCursor(document)
    first_block = True

    first_block = _write_blocks(cursor, blocks, first=first_block)

    cursor.movePosition(QTextCursor.MoveOperation.Start)
    document.clearUndoRedoStacks()


def insert_blocks(cursor: QTextCursor, blocks: list[Block]) -> QTextCursor:
    """Insert validated Merope blocks at ``cursor`` in one native edit block.

    One plain paragraph is inserted inline, matching ordinary editor paste.
    Structural content is isolated from any text before and after the cursor,
    so its block kinds do not leak into the surrounding document.
    """

    validate_blocks(blocks)
    insertion = QTextCursor(cursor)
    if not blocks:
        return insertion

    insertion.beginEditBlock()
    try:
        if insertion.hasSelection():
            insertion.removeSelectedText()

        if len(blocks) == 1 and blocks[0].kind == PARAGRAPH:
            heading_level = _heading_level(insertion.block())
            _insert_runs(insertion, blocks[0].runs, heading_level=heading_level)
            return insertion

        original_block_format = QTextBlockFormat(insertion.blockFormat())
        original_char_format = QTextCharFormat(insertion.blockCharFormat())
        original_list = insertion.currentList()
        block = insertion.block()
        has_prefix = insertion.position() > block.position()
        has_suffix = insertion.position() < block.position() + block.length() - 1

        if has_prefix:
            _insert_new_block(insertion, original_block_format, original_char_format)
        elif original_list is not None:
            original_list.remove(insertion.block())

        _write_blocks(insertion, blocks, first=True)

        if has_suffix:
            _insert_new_block(insertion, original_block_format, original_char_format)
            if original_list is not None:
                original_list.add(insertion.block())
    finally:
        insertion.endEditBlock()
    return insertion


def extract_blocks(document: QTextDocument) -> list[Block]:
    """Build Merope blocks by traversing Qt blocks and text fragments.

    Deliberately does not use ``QTextDocument.toPlainText()``: Qt normalizes
    non-breaking spaces in that convenience representation.
    """

    if document.rootFrame().childFrames():
        raise UnsupportedBlockError(
            "Les cadres et tableaux QTextDocument ne sont pas encore pris en charge"
        )

    first_block = document.begin()
    if (
        document.blockCount() == 1
        and first_block.isValid()
        and first_block.textList() is None
        and not _block_has_content(first_block)
        and not first_block.blockFormat().property(BLOCK_KIND_PROPERTY)
        and first_block.blockFormat().headingLevel() == 0
    ):
        return []

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
                    raise UnsupportedBlockError(
                        "Une meme liste Qt melange plusieurs types de listes"
                    )
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


def _block_has_content(block: QTextBlock) -> bool:
    iterator = block.begin()
    while not iterator.atEnd():
        fragment = iterator.fragment()
        if fragment.isValid() and (
            fragment.length() > 0 or fragment.charFormat().isImageFormat()
        ):
            return True
        iterator += 1
    return False


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


def make_image_format(run: InlineRun) -> QTextImageFormat:
    """Create one native Qt image carrying Merope's canonical metadata."""

    _validate_image_run(run)
    image_format = QTextImageFormat()
    image_format.setName(run.image_src)
    image_format.setProperty(IMAGE_MARKER_PROPERTY, True)
    image_format.setProperty(IMAGE_SRC_PROPERTY, run.image_src)
    _set_optional_property(image_format, IMAGE_ALT_PROPERTY, run.image_alt)
    _set_optional_property(image_format, IMAGE_WIDTH_PROPERTY, run.image_width)
    _set_optional_property(image_format, IMAGE_HEIGHT_PROPERTY, run.image_height)
    _set_optional_property(image_format, IMAGE_ALIGN_PROPERTY, run.image_align)

    visual_width = _positive_pixel_dimension(run.image_width)
    visual_height = _positive_pixel_dimension(run.image_height)
    if visual_width is not None:
        image_format.setWidth(visual_width)
    if visual_height is not None:
        image_format.setHeight(visual_height)
    return image_format


def image_run_from_format(char_format: QTextCharFormat) -> InlineRun:
    """Reconstruct one canonical image run from a marked Qt image format."""

    if not char_format.isImageFormat() or not bool(
        char_format.property(IMAGE_MARKER_PROPERTY)
    ):
        raise UnsupportedInlineError("Image Qt etrangere sans metadonnees Merope")
    _validate_image_char_format(char_format)
    run = InlineRun(
        image_src=_required_image_property(char_format, IMAGE_SRC_PROPERTY, "src"),
        image_alt=_optional_image_property(char_format, IMAGE_ALT_PROPERTY),
        image_width=_optional_image_property(char_format, IMAGE_WIDTH_PROPERTY),
        image_height=_optional_image_property(char_format, IMAGE_HEIGHT_PROPERTY),
        image_align=_optional_image_property(char_format, IMAGE_ALIGN_PROPERTY),
    )
    _validate_image_run(run)
    return run


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
    cursor.mergeBlockCharFormat(visual_format)
    cursor.mergeCharFormat(visual_format)


def validate_blocks(blocks: Iterable[Block]) -> None:
    """Reject any model content that the Qt adapter cannot preserve."""

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
        has_image_data = run.image_src is not None or any(
            value is not None
            for value in (run.image_alt, run.image_width, run.image_height, run.image_align)
        )
        if has_image_data:
            _validate_image_run(run)
            continue
        if run.footnote_ref is not None:
            raise UnsupportedInlineError(
                "Les appels de note ne sont pas encore pris en charge par Qt"
            )


def _validate_image_run(run: InlineRun) -> None:
    if not isinstance(run.image_src, str) or not run.image_src.strip():
        raise UnsupportedInlineError("Une image Merope doit avoir un src non vide")
    for label, value in (
        ("alt", run.image_alt),
        ("width", run.image_width),
        ("height", run.image_height),
    ):
        if value is not None and not isinstance(value, str):
            raise UnsupportedInlineError(
                f"L'attribut image {label} doit etre une chaine ou None"
            )
    if run.image_align not in SUPPORTED_IMAGE_ALIGNMENTS:
        raise UnsupportedInlineError(
            f"Alignement d'image Merope non pris en charge : {run.image_align!r}"
        )
    if run.text:
        raise UnsupportedInlineError(
            "Une image Merope ne peut pas contenir simultanement du texte"
        )
    if run.footnote_ref is not None:
        raise UnsupportedInlineError(
            "Une image Merope ne peut pas etre simultanement un appel de note"
        )
    if (
        run.bold
        or run.italic
        or run.strikethrough
        or run.superscript
        or run.link_href is not None
    ):
        raise UnsupportedInlineError(
            "Une image Merope ne peut pas porter un format de texte ou un lien"
        )


def _validate_alignment(alignment: str) -> None:
    if alignment not in SUPPORTED_ALIGNMENTS:
        raise UnsupportedBlockError(f"Alignement Qt non pris en charge : {alignment!r}")


def _populate_leaf_block(cursor: QTextCursor, block: Block, first: bool) -> bool:
    block_format = _make_block_format(block.kind, block.alignment, block.level)
    default_char_format = make_char_format(
        InlineRun(), heading_level=block.level if block.kind == HEADING else None
    )
    _begin_block(cursor, block_format, default_char_format, first)
    _insert_runs(
        cursor,
        block.runs,
        heading_level=block.level if block.kind == HEADING else None,
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
        _insert_runs(cursor, item.runs)
    return False


def _write_blocks(cursor: QTextCursor, blocks: list[Block], *, first: bool) -> bool:
    for block in blocks:
        if block.kind in SUPPORTED_LEAF_KINDS:
            first = _populate_leaf_block(cursor, block, first)
        elif block.kind in SUPPORTED_LIST_KINDS:
            first = _populate_list(cursor, block, first)
        else:  # Kept as a defensive guard if validation evolves separately.
            raise UnsupportedBlockError(f"Type de bloc Qt non pris en charge : {block.kind}")
    return first


def _insert_runs(
    cursor: QTextCursor,
    runs: Iterable[InlineRun],
    *,
    heading_level: int | None = None,
) -> None:
    for run in runs:
        if run.image_src is not None:
            cursor.insertImage(make_image_format(run))
        else:
            cursor.insertText(run.text, make_char_format(run, heading_level=heading_level))


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

    _insert_new_block(cursor, block_format, char_format)


def _insert_new_block(
    cursor: QTextCursor,
    block_format: QTextBlockFormat,
    char_format: QTextCharFormat,
) -> None:
    cursor.insertBlock(block_format, char_format)
    current_list = cursor.currentList()
    if current_list is not None:
        current_list.remove(cursor.block())
        cursor.setBlockFormat(block_format)


def _heading_level(block: QTextBlock) -> int | None:
    block_format = block.blockFormat()
    if block_format.property(BLOCK_KIND_PROPERTY) != HEADING:
        return None
    return int(
        block_format.property(HEADING_LEVEL_PROPERTY)
        or block_format.headingLevel()
        or 1
    )


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
                for _position in range(fragment.length()):
                    runs.append(image_run_from_format(char_format))
                iterator += 1
                continue
            run = InlineRun(
                text=fragment.text(),
                bold=inline_format_enabled(char_format, BOLD_PROPERTY),
                italic=inline_format_enabled(char_format, ITALIC_PROPERTY),
                strikethrough=inline_format_enabled(
                    char_format, STRIKETHROUGH_PROPERTY
                ),
                superscript=inline_format_enabled(char_format, SUPERSCRIPT_PROPERTY),
                link_href=char_format.anchorHref() if char_format.isAnchor() else None,
            )
            _append_semantic_run(runs, run)
        iterator += 1
    return runs or [InlineRun(text="")]


def _validate_image_char_format(char_format: QTextCharFormat) -> None:
    if char_format.isAnchor() or any(
        inline_format_enabled(char_format, property_id)
        for property_id in (
            BOLD_PROPERTY,
            ITALIC_PROPERTY,
            STRIKETHROUGH_PROPERTY,
            SUPERSCRIPT_PROPERTY,
        )
    ):
        raise UnsupportedInlineError(
            "Une image Qt Merope porte un format de texte incompatible"
        )


def _set_optional_property(
    image_format: QTextImageFormat,
    property_id: int,
    value: str | None,
) -> None:
    if value is not None:
        # An empty Python string can round-trip through QVariant as an empty
        # QStringList in PySide. A private prefix preserves "" versus None.
        image_format.setProperty(
            property_id,
            _OPTIONAL_IMAGE_STRING_PREFIX + value,
        )


def _required_image_property(
    char_format: QTextCharFormat,
    property_id: int,
    label: str,
) -> str:
    if not char_format.hasProperty(property_id):
        raise UnsupportedInlineError(
            f"Image Qt Merope sans propriete obligatoire {label}"
        )
    value = char_format.property(property_id)
    if not isinstance(value, str):
        raise UnsupportedInlineError(
            f"Propriete image Merope {label} invalide"
        )
    return value


def _optional_image_property(
    char_format: QTextCharFormat,
    property_id: int,
) -> str | None:
    if not char_format.hasProperty(property_id):
        return None
    value = char_format.property(property_id)
    if not isinstance(value, str) or not value.startswith(
        _OPTIONAL_IMAGE_STRING_PREFIX
    ):
        raise UnsupportedInlineError("Propriete image Merope optionnelle invalide")
    return value[len(_OPTIONAL_IMAGE_STRING_PREFIX) :]


def _positive_pixel_dimension(value: str | None) -> int | None:
    if value is None or not value.isascii() or not value.isdecimal():
        return None
    pixels = int(value)
    return pixels if pixels > 0 else None


def _append_semantic_run(runs: list[InlineRun], run: InlineRun) -> None:
    if (
        runs
        and runs[-1].image_src is None
        and runs[-1].footnote_ref is None
        and run.image_src is None
        and run.footnote_ref is None
        and _same_inline_format(runs[-1], run)
    ):
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


def inline_format_enabled(char_format: QTextCharFormat, property_id: int) -> bool:
    """Return a semantic inline state, falling back to native Qt formatting."""

    if char_format.hasProperty(property_id):
        return bool(char_format.property(property_id))
    if property_id == BOLD_PROPERTY:
        return char_format.fontWeight() >= QFont.Weight.Bold.value
    if property_id == ITALIC_PROPERTY:
        return char_format.fontItalic()
    if property_id == STRIKETHROUGH_PROPERTY:
        return char_format.fontStrikeOut()
    if property_id == SUPERSCRIPT_PROPERTY:
        return (
            char_format.verticalAlignment()
            == QTextCharFormat.VerticalAlignment.AlignSuperScript
        )
    raise ValueError(f"Propriete inline Merope inconnue : {property_id}")


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
