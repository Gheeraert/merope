"""Adaptateur explicite entre ``Block``/``InlineRun`` et ``QTextDocument``.

Qt n'est jamais utilise ici comme parseur Markdown. Les proprietes applicatives
conservent la semantique Merope qui ne peut pas etre deduite sans ambiguite de
la seule apparence du document.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import replace
from uuid import uuid4

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
    QTextLength,
    QTextListFormat,
)

from bloggen.content.footnotes import FootnoteDefinitions
from bloggen.content.image_size import max_percent_for, parse_width
from bloggen.markdown.rich_text_model import (
    BLOCKQUOTE,
    BULLET_LIST,
    HEADING,
    LIST_ITEM,
    ORDERED_LIST,
    PARAGRAPH,
    TABLE,
    TABLE_CELL,
    TABLE_ROW,
    VERBATIM,
    Block,
    InlineRun,
)
from bloggen.markdown.rich_text_export import blocks_to_markdown
from bloggen.markdown.rich_text_import import parse_table_lines
from bloggen.ui.qt_editor.constants import (
    ALIGNMENT_PROPERTY,
    BLOCK_KIND_PROPERTY,
    BLOCKQUOTE_LEFT_MARGIN,
    BODY_POINT_SIZE,
    BOLD_PROPERTY,
    FOOTNOTE_ID_PROPERTY,
    FOOTNOTE_INSTANCE_PROPERTY,
    FOOTNOTE_MARKER_PROPERTY,
    HEADING_MARGINS,
    HEADING_LEVEL_PROPERTY,
    HEADING_POINT_SIZES,
    IMAGE_ALIGN_PROPERTY,
    IMAGE_ALT_PROPERTY,
    IMAGE_HEIGHT_PROPERTY,
    IMAGE_BLOCK_MARGINS,
    IMAGE_MARKER_PROPERTY,
    IMAGE_SRC_PROPERTY,
    IMAGE_WIDTH_PROPERTY,
    ITALIC_PROPERTY,
    LIST_KIND_PROPERTY,
    RAW_BLOCK_GROUP_PROPERTY,
    RAW_BLOCK_KIND_PROPERTY,
    STRIKETHROUGH_PROPERTY,
    SUPERSCRIPT_PROPERTY,
    UNDERLINE_PROPERTY,
)


SUPPORTED_LEAF_KINDS = {PARAGRAPH, HEADING, BLOCKQUOTE}
SUPPORTED_LIST_KINDS = {BULLET_LIST, ORDERED_LIST}
SUPPORTED_RAW_KINDS = {TABLE, VERBATIM}
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

    if blocks:
        first_block = _write_blocks(cursor, blocks, first=first_block)
    else:
        # ``clear()`` leaves one implicit, untyped empty block that
        # ``extract_blocks`` treats as "no content" (no BLOCK_KIND_PROPERTY).
        # Only its Qt paint alignment is nudged to justify, matching the
        # editor's default paragraph style, without stamping it as an
        # actual paragraph block - typing into it still goes through the
        # normal first-paragraph path once real content exists.
        block_format = cursor.blockFormat()
        block_format.setAlignment(Qt.AlignmentFlag.AlignJustify)
        cursor.setBlockFormat(block_format)

    cursor.movePosition(QTextCursor.MoveOperation.Start)
    document.clearUndoRedoStacks()
    document.setModified(False)


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
    if selection_crosses_raw_boundary(insertion):
        raise UnsupportedBlockError(
            "L’insertion ne peut pas remplacer une frontière de bloc brut"
        )
    if selection_touches_raw_block(insertion):
        raise UnsupportedBlockError(
            "Les objets structurés ne peuvent pas être insérés dans un bloc brut"
        )

    insertion.beginEditBlock()
    try:
        if insertion.hasSelection():
            insertion.removeSelectedText()

        if len(blocks) == 1 and blocks[0].kind == PARAGRAPH:
            heading_level = _heading_level(insertion.block())
            _insert_runs(insertion, blocks[0].runs, heading_level=heading_level)
            refresh_block_visuals(insertion.block())
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


def insert_footnote_reference(cursor: QTextCursor, note_id: str) -> QTextCursor:
    """Insert one canonical atomic reference without inheriting text formats."""

    run = InlineRun(footnote_ref=note_id)
    _validate_footnote_run(run)
    if raw_block_identity(cursor.block()) is not None:
        raise UnsupportedInlineError(
            "Un appel de note ne peut pas être inséré dans un bloc brut"
        )
    if cursor.hasSelection():
        raise UnsupportedInlineError(
            "Désélectionnez le texte avant d’insérer un appel de note"
        )
    insertion = QTextCursor(cursor)
    insertion.beginEditBlock()
    try:
        insertion.insertText(
            footnote_marker_text(note_id),
            make_footnote_format(
                run,
                heading_level=_heading_level(insertion.block()),
                instance_key=insertion.position(),
            ),
        )
    finally:
        insertion.endEditBlock()
    return insertion


def renumber_footnote_references(
    document: QTextDocument,
    mapping: dict[str, str],
) -> bool:
    """Rewrite all mapped references right-to-left in one native edit block."""

    replacements: list[tuple[int, int, str, int | None]] = []
    raw_line_replacements: list[tuple[int, int, str]] = []
    block = document.begin()
    while block.isValid():
        raw_identity = raw_block_identity(block)
        if raw_identity is not None:
            kind, group = raw_identity
            group_blocks: list[QTextBlock] = []
            while block.isValid() and raw_block_identity(block) == (kind, group):
                group_blocks.append(block)
                block = block.next()
            if kind == TABLE:
                parsed = parse_table_lines([item.text() for item in group_blocks])
                if parsed is not None:
                    rewritten = _renumber_block_references(parsed, mapping)
                    if rewritten != parsed:
                        lines = blocks_to_markdown([rewritten]).rstrip("\n").split("\n")
                        if len(lines) != len(group_blocks):
                            raise UnsupportedBlockError(
                                "La renumérotation a modifié la structure source du tableau"
                            )
                        raw_line_replacements.extend(
                            (
                                item.position(),
                                item.position() + item.length() - 1,
                                line,
                            )
                            for item, line in zip(group_blocks, lines, strict=True)
                            if item.text() != line
                        )
            continue
        heading_level = _heading_level(block)
        iterator = block.begin()
        while not iterator.atEnd():
            fragment = iterator.fragment()
            if fragment.isValid() and has_footnote_properties(fragment.charFormat()):
                run = footnote_run_from_format(fragment.charFormat(), fragment.text())
                new_id = mapping.get(run.footnote_ref, run.footnote_ref)
                _validate_footnote_id(new_id)
                if new_id != run.footnote_ref:
                    replacements.append(
                        (
                            fragment.position(),
                            fragment.position() + fragment.length(),
                            new_id,
                            heading_level,
                        )
                    )
            iterator += 1
        block = block.next()
    if not replacements and not raw_line_replacements:
        return False

    edit_cursor = QTextCursor(document)
    edit_cursor.beginEditBlock()
    try:
        operations = [
            (start, end, text, None, False)
            for start, end, text in raw_line_replacements
        ] + [
            (start, end, new_id, heading_level, True)
            for start, end, new_id, heading_level in replacements
        ]
        for start, end, value, heading_level, is_footnote in sorted(
            operations, key=lambda item: item[0], reverse=True
        ):
            target = QTextCursor(document)
            target.setPosition(start)
            target.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
            if is_footnote:
                target.insertText(
                    footnote_marker_text(value),
                    make_footnote_format(
                        InlineRun(footnote_ref=value),
                        heading_level=heading_level,
                        instance_key=start,
                    ),
                )
            else:
                target.insertText(value, make_raw_char_format())
    finally:
        edit_cursor.endEditBlock()
    return True


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
    seen_raw_groups: set[str] = set()
    block = document.begin()
    while block.isValid():
        raw_identity = raw_block_identity(block)
        if raw_identity is not None:
            kind, group = raw_identity
            if group in seen_raw_groups:
                raise UnsupportedBlockError(
                    "Un groupe de bloc brut Qt n’est pas contigu"
                )
            seen_raw_groups.add(group)
            lines: list[str] = []
            while block.isValid() and raw_block_identity(block) == (kind, group):
                _validate_raw_qt_block(block)
                lines.append(block.text())
                block = block.next()
            raw_text = "\n".join(lines)
            if kind == TABLE:
                result.append(
                    parse_table_lines(lines)
                    or Block(kind=VERBATIM, raw_text=raw_text)
                )
            else:
                result.append(Block(kind=VERBATIM, raw_text=raw_text))
            continue

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
    char_format.setProperty(UNDERLINE_PROPERTY, run.underline)
    char_format.setFontWeight(
        QFont.Weight.Bold.value if run.bold else QFont.Weight.Normal.value
    )
    char_format.setFontItalic(run.italic)
    char_format.setFontStrikeOut(run.strikethrough)
    char_format.setFontUnderline(run.underline or run.link_href is not None)
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

    # Mirror the site's CSS: the column (half of it for floats) is always a
    # ceiling, "NN%" is a lower ceiling, and a historical pixel width is
    # applied alone so the height keeps following the image's proportions.
    ceiling = max_percent_for(run.image_align)
    spec = parse_width(run.image_width)
    if spec is not None and spec.kind == "percent":
        ceiling = min(ceiling, spec.value)
    elif spec is not None:
        image_format.setWidth(spec.value)
    image_format.setMaximumWidth(
        QTextLength(QTextLength.Type.PercentageLength, ceiling)
    )
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


def footnote_marker_text(note_id: str) -> str:
    return f"[{note_id}]"


def make_footnote_format(
    run: InlineRun,
    *,
    heading_level: int | None = None,
    instance_key: int | None = None,
) -> QTextCharFormat:
    """Create an atomic native-text marker carrying Merope footnote semantics."""

    _validate_footnote_run(run)
    char_format = make_char_format(InlineRun(), heading_level=heading_level)
    char_format.setProperty(FOOTNOTE_MARKER_PROPERTY, True)
    char_format.setProperty(FOOTNOTE_ID_PROPERTY, run.footnote_ref)
    if instance_key is not None:
        char_format.setProperty(FOOTNOTE_INSTANCE_PROPERTY, instance_key)
    base_size = HEADING_POINT_SIZES.get(heading_level, BODY_POINT_SIZE)
    char_format.setFontPointSize(base_size * 0.8)
    char_format.setVerticalAlignment(
        QTextCharFormat.VerticalAlignment.AlignSuperScript
    )
    char_format.setForeground(QColor("#1a5fb4"))
    return char_format


def footnote_run_from_format(
    char_format: QTextCharFormat,
    visible_text: str,
) -> InlineRun:
    """Reconstruct and validate one semantic footnote-reference fragment."""

    if char_format.isImageFormat():
        raise UnsupportedInlineError("Un appel de note ne peut pas être une image")
    if not bool(char_format.property(FOOTNOTE_MARKER_PROPERTY)):
        raise UnsupportedInlineError("Marqueur de note Qt étranger ou incomplet")
    if not char_format.hasProperty(FOOTNOTE_ID_PROPERTY):
        raise UnsupportedInlineError("Appel de note Qt sans identifiant Mérope")
    note_id = char_format.property(FOOTNOTE_ID_PROPERTY)
    if not isinstance(note_id, str):
        raise UnsupportedInlineError("Identifiant de note Qt invalide")
    run = InlineRun(footnote_ref=note_id)
    _validate_footnote_run(run)
    expected = footnote_marker_text(note_id)
    if visible_text != expected:
        raise UnsupportedInlineError(
            f"Marqueur de note Qt incohérent : {visible_text!r}, attendu {expected!r}"
        )
    if (
        char_format.isAnchor()
        or char_format.fontWeight() >= QFont.Weight.Bold.value
        or char_format.fontItalic()
        or char_format.fontStrikeOut()
        or any(
            inline_format_enabled(char_format, property_id)
            for property_id in (
                BOLD_PROPERTY,
                ITALIC_PROPERTY,
                STRIKETHROUGH_PROPERTY,
                SUPERSCRIPT_PROPERTY,
                UNDERLINE_PROPERTY,
            )
        )
    ):
        raise UnsupportedInlineError(
            "Un appel de note Qt porte un format de texte incompatible"
        )
    return run


def has_footnote_properties(char_format: QTextCharFormat) -> bool:
    """Report any Merope footnote metadata, including incomplete metadata."""

    return any(
        char_format.hasProperty(property_id)
        for property_id in (
            FOOTNOTE_MARKER_PROPERTY,
            FOOTNOTE_ID_PROPERTY,
            FOOTNOTE_INSTANCE_PROPERTY,
        )
    )


def is_semantic_inline_object_format(char_format: QTextCharFormat) -> bool:
    """Return whether text-formatting commands must skip this fragment."""

    return char_format.isImageFormat() or has_footnote_properties(char_format)


def refresh_block_visuals(block: QTextBlock) -> None:
    """Refresh presentation without altering block or inline semantics."""

    if not block.isValid():
        return
    block_format = QTextBlockFormat(block.blockFormat())
    kind = block_format.property(BLOCK_KIND_PROPERTY) or PARAGRAPH
    level = (
        int(block_format.property(HEADING_LEVEL_PROPERTY) or 1)
        if kind == HEADING
        else None
    )
    cursor = QTextCursor(block)
    _set_visual_block_margins(
        block_format,
        kind=kind,
        level=level,
        image_only=kind == PARAGRAPH and block_is_image_only(block),
    )
    cursor.setBlockFormat(block_format)
    cursor.movePosition(
        QTextCursor.MoveOperation.EndOfBlock,
        QTextCursor.MoveMode.KeepAnchor,
    )
    visual_format = QTextCharFormat()
    visual_format.setFontPointSize(HEADING_POINT_SIZES.get(level, BODY_POINT_SIZE))
    cursor.mergeBlockCharFormat(visual_format)
    cursor.mergeCharFormat(visual_format)


def block_is_image_only(block: QTextBlock) -> bool:
    """Return whether a block contains one Merope image and only whitespace."""

    if not block.isValid():
        return False
    image_count = 0
    iterator = block.begin()
    while not iterator.atEnd():
        fragment = iterator.fragment()
        if fragment.isValid():
            char_format = fragment.charFormat()
            if char_format.isImageFormat():
                if not bool(char_format.property(IMAGE_MARKER_PROPERTY)):
                    return False
                image_count += 1
                if image_count > 1:
                    return False
            elif has_footnote_properties(char_format) or fragment.text().strip():
                return False
        iterator += 1
    return image_count == 1


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

        if block.kind == TABLE:
            _validate_table_block(block)
            continue

        if block.kind == VERBATIM:
            if block.runs or block.children:
                raise UnsupportedBlockError(
                    "Un bloc verbatim ne peut contenir ni runs ni enfants"
                )
            if block.raw_text is not None and not isinstance(block.raw_text, str):
                raise UnsupportedBlockError("Le texte verbatim doit être une chaîne")
            continue

        raise UnsupportedBlockError(f"Type de bloc Qt non pris en charge : {block.kind}")


def validate_footnote_definitions(definitions: FootnoteDefinitions) -> None:
    """Validate the rich inline subset retained outside the QTextDocument."""

    for note_id, runs in definitions.items():
        _validate_footnote_id(note_id)
        if not isinstance(runs, list):
            raise UnsupportedInlineError(
                f"La définition de note {note_id} doit contenir une liste de runs"
            )
        for run in runs:
            if run.image_src is not None or any(
                value is not None
                for value in (
                    run.image_alt,
                    run.image_width,
                    run.image_height,
                    run.image_align,
                )
            ):
                raise UnsupportedInlineError(
                    f"Les images dans la définition de note {note_id} ne sont pas prises en charge"
                )
            if run.footnote_ref is not None:
                raise UnsupportedInlineError(
                    f"Les appels imbriqués dans la définition de note {note_id} ne sont pas pris en charge"
                )


def _validate_table_block(block: Block) -> None:
    if block.runs or block.raw_text is not None:
        raise UnsupportedBlockError(
            "Un tableau ne peut contenir ni runs directs ni texte brut"
        )
    if not block.children:
        raise UnsupportedBlockError("Un tableau vide n’est pas représentable")
    for row in block.children:
        if row.kind != TABLE_ROW or row.runs or row.raw_text is not None:
            raise UnsupportedBlockError(
                "Un tableau doit contenir uniquement des lignes TABLE_ROW"
            )
        if not row.children:
            raise UnsupportedBlockError("Une ligne de tableau vide n’est pas représentable")
        for cell in row.children:
            if cell.kind != TABLE_CELL or cell.children or cell.raw_text is not None:
                raise UnsupportedBlockError(
                    "Une ligne de tableau doit contenir uniquement des cellules TABLE_CELL"
                )
            _validate_runs(cell.runs)


def _validate_raw_qt_block(block: QTextBlock) -> None:
    if block.textList() is not None:
        raise UnsupportedBlockError("Un bloc brut Qt ne peut appartenir à une liste")
    iterator = block.begin()
    while not iterator.atEnd():
        fragment = iterator.fragment()
        if fragment.isValid():
            char_format = fragment.charFormat()
            if is_semantic_inline_object_format(char_format):
                raise UnsupportedBlockError(
                    "Un bloc brut Qt contient un objet inline sémantique"
                )
            if any(
                char_format.hasProperty(property_id)
                and bool(char_format.property(property_id))
                for property_id in (
                    BOLD_PROPERTY,
                    ITALIC_PROPERTY,
                    STRIKETHROUGH_PROPERTY,
                    SUPERSCRIPT_PROPERTY,
                    UNDERLINE_PROPERTY,
                )
            ) or char_format.isAnchor():
                raise UnsupportedBlockError(
                    "Un bloc brut Qt contient une mise en forme sémantique"
                )
        iterator += 1


def _renumber_block_references(block: Block, mapping: dict[str, str]) -> Block:
    return replace(
        block,
        runs=[
            replace(run, footnote_ref=mapping.get(run.footnote_ref, run.footnote_ref))
            if run.footnote_ref is not None
            else run
            for run in block.runs
        ],
        children=[
            _renumber_block_references(child, mapping) for child in block.children
        ],
    )


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
            _validate_footnote_run(run)


def _validate_footnote_id(note_id: object) -> None:
    if not isinstance(note_id, str) or not note_id or not note_id.isdigit():
        raise UnsupportedInlineError(
            f"Identifiant numérique de note Mérope invalide : {note_id!r}"
        )


def _validate_footnote_run(run: InlineRun) -> None:
    _validate_footnote_id(run.footnote_ref)
    if run.text:
        raise UnsupportedInlineError(
            "Un appel de note Mérope ne peut pas contenir simultanément du texte"
        )
    if run.image_src is not None or any(
        value is not None
        for value in (
            run.image_alt,
            run.image_width,
            run.image_height,
            run.image_align,
        )
    ):
        raise UnsupportedInlineError(
            "Un appel de note Mérope ne peut pas être simultanément une image"
        )
    if (
        run.bold
        or run.italic
        or run.underline
        or run.strikethrough
        or run.superscript
        or run.link_href is not None
    ):
        raise UnsupportedInlineError(
            "Un appel de note Mérope ne peut pas porter un format de texte ou un lien"
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
        or run.underline
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
    refresh_block_visuals(cursor.block())
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


def _populate_raw_block(cursor: QTextCursor, block: Block, first: bool) -> bool:
    source = (
        blocks_to_markdown([block]).rstrip("\n")
        if block.kind == TABLE
        else block.raw_text or ""
    )
    group = uuid4().hex
    lines = source.split("\n")
    block_format = make_raw_block_format(block.kind, group)
    char_format = make_raw_char_format()
    for index, line in enumerate(lines):
        _begin_block(cursor, block_format, char_format, first and index == 0)
        cursor.insertText(line, char_format)
    return False


def _write_blocks(cursor: QTextCursor, blocks: list[Block], *, first: bool) -> bool:
    for block in blocks:
        if block.kind in SUPPORTED_LEAF_KINDS:
            first = _populate_leaf_block(cursor, block, first)
        elif block.kind in SUPPORTED_LIST_KINDS:
            first = _populate_list(cursor, block, first)
        elif block.kind in SUPPORTED_RAW_KINDS:
            first = _populate_raw_block(cursor, block, first)
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
        elif run.footnote_ref is not None:
            marker = footnote_marker_text(run.footnote_ref)
            cursor.insertText(
                marker,
                make_footnote_format(
                    run,
                    heading_level=heading_level,
                    instance_key=cursor.position(),
                ),
            )
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
    _set_visual_block_margins(
        block_format,
        kind=kind,
        level=level,
        image_only=False,
    )
    return block_format


def _set_visual_block_margins(
    block_format: QTextBlockFormat,
    *,
    kind: object,
    level: int | None,
    image_only: bool,
) -> None:
    if kind == HEADING and level in HEADING_MARGINS:
        top, bottom = HEADING_MARGINS[level]
    elif kind == PARAGRAPH and image_only:
        top, bottom = IMAGE_BLOCK_MARGINS
    else:
        top, bottom = 0.0, 0.0
    block_format.setTopMargin(top)
    block_format.setBottomMargin(bottom)


def make_raw_block_format(kind: str, group: str) -> QTextBlockFormat:
    """Create the visual/documentary format shared by one raw block group."""

    if kind not in SUPPORTED_RAW_KINDS or not isinstance(group, str) or not group:
        raise UnsupportedBlockError("Identité de bloc brut invalide")
    block_format = QTextBlockFormat()
    block_format.setProperty(BLOCK_KIND_PROPERTY, kind)
    block_format.setProperty(RAW_BLOCK_KIND_PROPERTY, kind)
    block_format.setProperty(RAW_BLOCK_GROUP_PROPERTY, group)
    block_format.setBackground(
        QColor("#f3f0e8") if kind == TABLE else QColor("#eef2f5")
    )
    return block_format


def make_raw_char_format() -> QTextCharFormat:
    """Return a presentation-only monospaced format for raw source text."""

    char_format = QTextCharFormat()
    char_format.setFontFamilies(["monospace"])
    char_format.setFontFixedPitch(True)
    char_format.setFontStyleHint(QFont.StyleHint.Monospace)
    char_format.setFontPointSize(BODY_POINT_SIZE)
    return char_format


def raw_block_identity(block: QTextBlock) -> tuple[str, str] | None:
    """Return ``(kind, transient group)`` or reject partial raw metadata."""

    block_format = block.blockFormat()
    stored_kind = block_format.property(BLOCK_KIND_PROPERTY)
    raw_kind = block_format.property(RAW_BLOCK_KIND_PROPERTY)
    has_kind = block_format.hasProperty(RAW_BLOCK_KIND_PROPERTY)
    has_group = block_format.hasProperty(RAW_BLOCK_GROUP_PROPERTY)
    if not has_kind and not has_group and stored_kind not in SUPPORTED_RAW_KINDS:
        return None
    if not has_kind or not has_group:
        raise UnsupportedBlockError("Métadonnées de bloc brut Qt incomplètes")
    group = block_format.property(RAW_BLOCK_GROUP_PROPERTY)
    if raw_kind not in SUPPORTED_RAW_KINDS or stored_kind != raw_kind:
        raise UnsupportedBlockError("Type de bloc brut Qt incohérent")
    if not isinstance(group, str) or not group:
        raise UnsupportedBlockError("Groupe de bloc brut Qt invalide")
    return raw_kind, group


def is_raw_block(block: QTextBlock) -> bool:
    return raw_block_identity(block) is not None


def selection_touches_raw_block(cursor: QTextCursor) -> bool:
    """Report whether a caret/selection addresses at least one raw block."""

    return any(
        identity is not None for identity in selection_block_identities(cursor)
    )


def selection_block_identities(
    cursor: QTextCursor,
) -> set[tuple[str, str] | None]:
    """Return identities touched by text or by a selected block separator.

    A QTextBlock separator belongs to the left block, while the right block's
    position equals the selection end in the boundary-only case.  The right
    identity is therefore added explicitly whenever that separator is selected.
    """

    start = cursor.selectionStart()
    end = cursor.selectionEnd()
    block = cursor.document().findBlock(start)
    identities: set[tuple[str, str] | None] = set()
    if not cursor.hasSelection():
        return {raw_block_identity(block)} if block.isValid() else set()

    while block.isValid() and block.position() < end:
        identities.add(raw_block_identity(block))
        separator_position = block.position() + block.length() - 1
        if start <= separator_position < end:
            right = block.next()
            if right.isValid():
                identities.add(raw_block_identity(right))
        block = block.next()
    return identities


def selection_crosses_raw_boundary(cursor: QTextCursor) -> bool:
    """Return whether a selected paragraph separator crosses a protected edge."""

    if not cursor.hasSelection():
        return False
    start = cursor.selectionStart()
    end = cursor.selectionEnd()
    block = cursor.document().findBlock(start)
    while block.isValid() and block.position() < end:
        separator_position = block.position() + block.length() - 1
        if start <= separator_position < end:
            right = block.next()
            if right.isValid():
                left_identity = raw_block_identity(block)
                right_identity = raw_block_identity(right)
                if left_identity != right_identity and (
                    left_identity is not None or right_identity is not None
                ):
                    return True
        block = block.next()
    return False


def _extract_runs(block: QTextBlock) -> list[InlineRun]:
    runs: list[InlineRun] = []
    iterator = block.begin()
    while not iterator.atEnd():
        fragment = iterator.fragment()
        if fragment.isValid():
            char_format = fragment.charFormat()
            if has_footnote_properties(char_format):
                runs.append(footnote_run_from_format(char_format, fragment.text()))
                iterator += 1
                continue
            if char_format.isImageFormat():
                for _position in range(fragment.length()):
                    runs.append(image_run_from_format(char_format))
                iterator += 1
                continue
            run = InlineRun(
                text=fragment.text(),
                bold=inline_format_enabled(char_format, BOLD_PROPERTY),
                italic=inline_format_enabled(char_format, ITALIC_PROPERTY),
                underline=inline_format_enabled(char_format, UNDERLINE_PROPERTY),
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
            UNDERLINE_PROPERTY,
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
        left.underline,
        left.strikethrough,
        left.superscript,
        left.link_href,
    ) == (
        right.bold,
        right.italic,
        right.underline,
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
    if property_id == UNDERLINE_PROPERTY:
        # Links and foreign Qt formats may be visually underlined. Only the
        # dedicated UserProperty is persistent Merope semantics.
        return False
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
