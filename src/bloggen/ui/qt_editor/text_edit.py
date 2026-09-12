"""QTextEdit adaptations for Merope's editing interactions."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from difflib import SequenceMatcher
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QByteArray, QMimeData, QPoint, QSize, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QKeyEvent,
    QKeySequence,
    QMouseEvent,
    QPaintEvent,
    QPainter,
    QPen,
    QResizeEvent,
    QTextCharFormat,
    QTextCursor,
)
from PySide6.QtWidgets import QApplication, QTextEdit

from bloggen.markdown.html_paste_import import (
    UnsupportedHtmlStructureError,
    html_to_blocks,
)
from bloggen.markdown.rich_text_model import Block
from bloggen.markdown.typography import (
    CENTURY_RE,
    CLOSING_GUILLEMET,
    COMMON_CENTURY_ORDINAL_TYPED_RE,
    CURLY_CLOSING_QUOTE,
    CURLY_OPENING_QUOTE,
    DOUBLE_PUNCTUATION,
    NBSP,
    OE_LIGATURE_TYPED_RE,
    OPENING_GUILLEMET,
    PAGE_ABBREVIATION_TYPED_RE,
    SPACE_BEFORE_PERIOD_TYPED_RE,
    convert_curly_quotes_to_guillemets,
    convert_straight_quotes_stateful,
    fix_double_punctuation_spacing,
    fix_guillemet_spacing,
    fix_page_number_spacing,
    fix_period_spacing,
    is_valid_century_ordinal,
    oe_ligature_replacement,
)
from bloggen.ui.qt_editor.clipboard_fragment import (
    MEROPE_FRAGMENT_MIME,
    InvalidMeropeClipboardFragment,
    decode_markdown_fragment,
    encode_selection_as_markdown,
)
from bloggen.ui.qt_editor.clipboard_images import (
    ClipboardImagePasteError,
    ExternalPasteContext,
    PreparedExternalPaste,
    prepare_external_paste,
)
from bloggen.ui.qt_editor.constants import (
    BOLD_PROPERTY,
    FOOTNOTE_ID_PROPERTY,
    FOOTNOTE_INSTANCE_PROPERTY,
    FOOTNOTE_MARKER_PROPERTY,
    ITALIC_PROPERTY,
    STRIKETHROUGH_PROPERTY,
    SUPERSCRIPT_PROPERTY,
)
from bloggen.ui.qt_editor.document_adapter import (
    UnsupportedDocumentError,
    inline_format_enabled,
    insert_blocks,
    is_semantic_inline_object_format,
)
from bloggen.ui.qt_editor.footnote_selection import (
    expand_selection_to_footnotes,
    merope_footnote_at_position,
)
from bloggen.ui.qt_editor.image_resize import (
    ImageResizeGeometry,
    image_viewport_rect,
    resize_drag_is_effective,
    ratio_preserving_size,
    selected_image_resize_geometry,
)
from bloggen.ui.qt_editor.image_selection import (
    ImageTarget,
    merope_image_at_position,
    replace_merope_image,
)


_OE_PAIR_RE = re.compile("oe", re.IGNORECASE)
_REJECTED_RICH_PASTE_TAGS = frozenset(
    {"img", "pre", "table", "v:imagedata", "v:shape"}
)


def blocks_from_rich_mime_data(source: QMimeData) -> list[Block] | None:
    """Decode inspectable rich MIME through Merope's canonical importers.

    ``None`` means that the source contains no rich representation and may be
    handled as plain text by the caller.  Exceptions deliberately propagate so
    each editing surface can refuse the operation before mutating its document.
    """

    if source.hasFormat(MEROPE_FRAGMENT_MIME):
        return decode_markdown_fragment(source.data(MEROPE_FRAGMENT_MIME))
    if source.hasHtml() and source.html().strip():
        return html_to_blocks(
            source.html(),
            reject_tags=_REJECTED_RICH_PASTE_TAGS,
        )
    return None


@dataclass
class _ImageResizeState:
    target: ImageTarget
    original_target: ImageTarget
    origin: QPoint
    initial_size: QSize
    activated: bool = False
    edit_cursor: QTextCursor | None = None


class MeropeTextEdit(QTextEdit):
    """Qt editing surface with Merope's shared French typography rules.

    The widget owns interaction behaviour only.  ``Block`` / ``InlineRun``
    remain canonical and are still converted by ``document_adapter``.

    The historical ``((note))`` shorthand deliberately remains ordinary rich
    text here (including during paste). Only Markdown normalization in the
    build/preview pipeline converts that syntax to a Pandoc inline footnote.
    """

    pasteRefused = Signal(str)
    clipboardRefused = Signal(str)
    footnoteActivated = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAcceptRichText(False)
        self.viewport().setMouseTracking(True)
        self._image_resize_state: _ImageResizeState | None = None
        self._external_paste_context: ExternalPasteContext | None = None
        self.selectionChanged.connect(self.viewport().update)
        self.document().contentsChanged.connect(self.viewport().update)

    def set_external_paste_context(
        self,
        *,
        images_dir: Path | None = None,
        doc_dir: Path | None = None,
    ) -> None:
        """Set only the filesystem context required by external image paste."""

        if images_dir is None or doc_dir is None:
            self._external_paste_context = None
            return
        self._external_paste_context = ExternalPasteContext(images_dir, doc_dir)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.matches(QKeySequence.StandardKey.Copy):
            self.copy()
            event.accept()
            return
        if event.matches(QKeySequence.StandardKey.Cut):
            self.cut()
            event.accept()
            return
        if event.matches(QKeySequence.StandardKey.Paste):
            self.paste()
            event.accept()
            return
        if self._handle_atomic_footnote_key(event):
            return

        char = event.text()
        if char == '"' and self.textCursor().hasSelection():
            self._wrap_selection_in_guillemets()
            return

        if len(char) == 1 and self._typing_requires_autoformat(char):
            cursor = self.textCursor()
            cursor.beginEditBlock()
            try:
                cursor.insertText(char)
                self.setTextCursor(cursor)
            finally:
                cursor.endEditBlock()
            self._apply_typing_autoformat(char)
            return

        super().keyPressEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            geometry = self.image_resize_geometry()
            if geometry is not None and geometry.handle_rect.contains(
                event.position().toPoint()
            ):
                self._start_image_resize(geometry, event.position().toPoint())
                event.accept()
                return

            footnote = self._footnote_at_viewport_point(event.position().toPoint())
            if footnote is not None:
                self.setTextCursor(footnote.cursor(self.document()))
                self.footnoteActivated.emit(footnote.note_id)
                event.accept()
                return

            target = self._image_at_viewport_point(event.position().toPoint())
            if target is not None:
                self.setTextCursor(target.cursor(self.document()))
                self.viewport().update()
                event.accept()
                return
        super().mousePressEvent(event)

    def _footnote_at_viewport_point(self, point: QPoint):
        hit_cursor = self.cursorForPosition(point)
        candidates = {
            target.start: target
            for position in (hit_cursor.position() - 1, hit_cursor.position())
            if (target := merope_footnote_at_position(self.document(), position))
            is not None
        }
        for target in candidates.values():
            start = QTextCursor(self.document())
            start.setPosition(target.start)
            end = QTextCursor(self.document())
            end.setPosition(target.end)
            start_rect = self.cursorRect(start)
            end_rect = self.cursorRect(end)
            left = min(start_rect.center().x(), end_rect.center().x())
            right = max(start_rect.center().x(), end_rect.center().x())
            top = min(start_rect.top(), end_rect.top())
            bottom = max(start_rect.bottom(), end_rect.bottom())
            if left <= point.x() <= right and top <= point.y() <= bottom:
                return target
        return None

    def _handle_atomic_footnote_key(self, event: QKeyEvent) -> bool:
        cursor = self.textCursor()
        key = event.key()
        if key in {Qt.Key.Key_Delete, Qt.Key.Key_Backspace}:
            atomic, contains_note = expand_selection_to_footnotes(cursor)
            if not contains_note and not cursor.hasSelection():
                position = cursor.position() - (
                    1 if key == Qt.Key.Key_Backspace else 0
                )
                target = merope_footnote_at_position(self.document(), position)
                if target is not None:
                    atomic = target.cursor(self.document())
                    contains_note = True
            if contains_note:
                atomic.beginEditBlock()
                try:
                    atomic.removeSelectedText()
                finally:
                    atomic.endEditBlock()
                self.setTextCursor(atomic)
                return True
            return False

        if not event.text() or event.modifiers() & (
            Qt.KeyboardModifier.ControlModifier
            | Qt.KeyboardModifier.AltModifier
            | Qt.KeyboardModifier.MetaModifier
        ):
            return False
        atomic, contains_note = expand_selection_to_footnotes(cursor)
        adjacent_note = False
        if not contains_note and not cursor.hasSelection():
            adjacent_note = self._cursor_touches_footnote(cursor)
        if not contains_note and not adjacent_note:
            return False
        replacement_format = self._plain_footnote_replacement_format(atomic)
        autoformat = len(event.text()) == 1 and self._typing_requires_autoformat(
            event.text()
        )
        atomic.beginEditBlock()
        try:
            atomic.removeSelectedText()
            atomic.insertText(event.text(), replacement_format)
        finally:
            atomic.endEditBlock()
        self.setTextCursor(atomic)
        if autoformat:
            self._apply_typing_autoformat(event.text())
        return True

    def _cursor_touches_footnote(self, cursor: QTextCursor) -> bool:
        if cursor.hasSelection():
            return False
        return any(
            merope_footnote_at_position(self.document(), position) is not None
            for position in (cursor.position() - 1, cursor.position())
        )

    @staticmethod
    def _plain_footnote_replacement_format(cursor: QTextCursor) -> QTextCharFormat:
        replacement_format = QTextCharFormat(cursor.blockCharFormat())
        for property_id in (
            FOOTNOTE_MARKER_PROPERTY,
            FOOTNOTE_ID_PROPERTY,
            FOOTNOTE_INSTANCE_PROPERTY,
        ):
            replacement_format.clearProperty(property_id)
        if is_semantic_inline_object_format(replacement_format):
            replacement_format = QTextCharFormat()
        return replacement_format

    def copy(self) -> None:
        if not self._copy_merope_selection(cut=False):
            super().copy()

    def cut(self) -> None:
        if self.isReadOnly():
            self.copy()
            return
        if self._copy_merope_selection(cut=True):
            return
        super().cut()

    def _copy_merope_selection(self, *, cut: bool) -> bool:
        try:
            cursor, contains_note = expand_selection_to_footnotes(
                self.textCursor()
            )
        except UnsupportedDocumentError as exc:
            self.clipboardRefused.emit(
                f"La sélection Mérope n’a pas pu être copiée sans perte : {exc}"
            )
            return True
        if not cursor.hasSelection():
            return False
        if contains_note:
            self.setTextCursor(cursor)
        try:
            native_mime = super().createMimeDataFromSelection()
            mime_data = QMimeData()
            for mime_type in native_mime.formats():
                mime_data.setData(mime_type, native_mime.data(mime_type))
            payload = encode_selection_as_markdown(cursor)
            mime_data.setData(MEROPE_FRAGMENT_MIME, QByteArray(payload))
        except (ValueError, UnsupportedDocumentError) as exc:
            self.clipboardRefused.emit(
                f"La sélection Mérope n’a pas pu être copiée sans perte : {exc}"
            )
            return True

        QApplication.clipboard().setMimeData(mime_data)
        if cut:
            cursor.beginEditBlock()
            try:
                cursor.removeSelectedText()
            finally:
                cursor.endEditBlock()
            self.setTextCursor(cursor)
        return True

    def _image_at_viewport_point(self, point: QPoint) -> ImageTarget | None:
        hit_cursor = self.cursorForPosition(point)
        candidates = {}
        for position in (hit_cursor.position() - 1, hit_cursor.position()):
            try:
                target = merope_image_at_position(self.document(), position)
            except UnsupportedDocumentError:
                continue
            if target is not None:
                candidates[target.start] = target

        for target in candidates.values():
            rect = image_viewport_rect(self, target)
            if rect is not None and rect.contains(point):
                return target
        return None

    def image_resize_geometry(self) -> ImageResizeGeometry | None:
        """Return viewport geometry for an exactly selected, renderable image."""

        return selected_image_resize_geometry(self)

    def _set_normal_viewport_cursor(self) -> None:
        self.viewport().setCursor(Qt.CursorShape.IBeamCursor)

    def _update_resize_cursor(self, point: QPoint | None = None) -> None:
        if self._image_resize_state is not None:
            self.viewport().setCursor(Qt.CursorShape.SizeFDiagCursor)
            return
        geometry = self.image_resize_geometry()
        if (
            point is not None
            and geometry is not None
            and geometry.handle_rect.contains(point)
        ):
            self.viewport().setCursor(Qt.CursorShape.SizeFDiagCursor)
        else:
            self._set_normal_viewport_cursor()

    def _start_image_resize(self, geometry: ImageResizeGeometry, point: QPoint) -> None:
        self._image_resize_state = _ImageResizeState(
            target=geometry.target,
            original_target=geometry.target,
            origin=QPoint(point),
            initial_size=geometry.image_rect.size(),
        )
        self.viewport().setCursor(Qt.CursorShape.SizeFDiagCursor)

    def _resize_selected_image_to(self, point: QPoint) -> None:
        state = self._image_resize_state
        if state is None:
            return
        if not state.activated:
            if not resize_drag_is_effective(state.origin, point):
                return
            state.activated = True

        if point == state.origin:
            new_run = state.original_target.run
        else:
            size = ratio_preserving_size(state.initial_size, point - state.origin)
            new_run = replace(
                state.target.run,
                image_width=str(size.width()),
                image_height=str(size.height()),
            )
        if new_run == state.target.run:
            return

        if state.edit_cursor is None:
            state.edit_cursor = QTextCursor(self.document())
            state.edit_cursor.beginEditBlock()

        selected = replace_merope_image(self.document(), state.target, new_run)
        state.target = ImageTarget(state.target.start, state.target.end, new_run)
        self.setTextCursor(selected)
        self.viewport().update()

    def _finish_image_resize(self) -> None:
        state = self._image_resize_state
        self._image_resize_state = None
        if state is not None and state.edit_cursor is not None:
            state.edit_cursor.endEditBlock()
        self._set_normal_viewport_cursor()
        self.viewport().update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._image_resize_state is not None:
            self._resize_selected_image_to(event.position().toPoint())
            event.accept()
            return
        self._update_resize_cursor(event.position().toPoint())
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if (
            self._image_resize_state is not None
            and event.button() == Qt.MouseButton.LeftButton
        ):
            self._resize_selected_image_to(event.position().toPoint())
            self._finish_image_resize()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def leaveEvent(self, event) -> None:
        if self._image_resize_state is None:
            self._set_normal_viewport_cursor()
        super().leaveEvent(event)

    def paintEvent(self, event: QPaintEvent) -> None:
        super().paintEvent(event)
        geometry = self.image_resize_geometry()
        if geometry is None:
            return

        painter = QPainter(self.viewport())
        pen = QPen(QColor(42, 109, 181))
        pen.setStyle(Qt.PenStyle.DashLine)
        pen.setWidth(1)
        painter.setPen(pen)
        painter.drawRect(geometry.image_rect.adjusted(0, 0, -1, -1))
        painter.fillRect(geometry.handle_rect, QColor(42, 109, 181))

    def scrollContentsBy(self, dx: int, dy: int) -> None:
        super().scrollContentsBy(dx, dy)
        self.viewport().update()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self.viewport().update()

    def canInsertFromMimeData(self, source: QMimeData) -> bool:
        """Accept only MIME content that Merope can inspect safely itself."""

        if source.hasFormat(MEROPE_FRAGMENT_MIME):
            return True
        if source.hasHtml() and bool(source.html().strip()):
            return True
        if source.hasImage():
            return True
        if source.hasUrls() and source.urls() and all(
            url.isLocalFile() for url in source.urls()
        ):
            return True
        return source.hasText() and bool(source.text())

    def insertFromMimeData(self, source: QMimeData) -> None:
        """Insert clipboard data without letting Qt interpret rich HTML.

        HTML always goes through Merope's canonical ``html_to_blocks``
        importer, then through the validated document adapter.  Unsupported
        semantic structures refuse the entire paste before the selection or
        document is touched.
        """

        has_internal_fragment = source.hasFormat(MEROPE_FRAGMENT_MIME)
        if has_internal_fragment:
            try:
                blocks = blocks_from_rich_mime_data(source)
                if blocks:
                    cursor, contains_note = expand_selection_to_footnotes(
                        self.textCursor()
                    )
                    if contains_note:
                        self.setTextCursor(cursor)
                    cursor = insert_blocks(self.textCursor(), blocks)
                    self.setTextCursor(cursor)
                    return
                return
            except InvalidMeropeClipboardFragment as exc:
                self.pasteRefused.emit(f"Fragment Mérope invalide : {exc}")
                return
            except UnsupportedDocumentError as exc:
                self.pasteRefused.emit(f"Fragment Mérope invalide : {exc}")
                return
            except Exception as exc:
                self.pasteRefused.emit(f"Le fragment Mérope n’a pas pu être analysé : {exc}")
                return

        prepared: PreparedExternalPaste | None = None
        original_cursor = QTextCursor(self.textCursor())
        try:
            prepared = prepare_external_paste(
                source,
                self._external_paste_context,
                html_importer=html_to_blocks,
            )
            if prepared is not None and prepared.blocks:
                blocks = prepared.commit_assets()
                cursor, contains_note = expand_selection_to_footnotes(
                    self.textCursor()
                )
                if contains_note:
                    self.setTextCursor(cursor)
                cursor = insert_blocks(self.textCursor(), blocks)
                self.setTextCursor(cursor)
                prepared.accept()
                return
            if prepared is not None:
                prepared.discard()
        except (
            ClipboardImagePasteError,
            UnsupportedHtmlStructureError,
            UnsupportedDocumentError,
        ) as exc:
            if prepared is not None:
                prepared.rollback()
            self.setTextCursor(original_cursor)
            self.pasteRefused.emit(str(exc))
            return
        except Exception as exc:
            if prepared is not None:
                prepared.rollback()
            self.setTextCursor(original_cursor)
            self.pasteRefused.emit(f"Le collage externe n’a pas pu être analysé : {exc}")
            return

        cursor, contains_note = expand_selection_to_footnotes(self.textCursor())
        if contains_note:
            self.setTextCursor(cursor)

        if source.hasText():
            cursor = self.textCursor()
            atomic_paste = contains_note or self._cursor_touches_footnote(cursor)
            cursor.beginEditBlock()
            try:
                if atomic_paste:
                    cursor.insertText(
                        source.text(),
                        self._plain_footnote_replacement_format(cursor),
                    )
                else:
                    cursor.insertText(source.text())
            finally:
                cursor.endEditBlock()
            self.setTextCursor(cursor)
            return

        self.pasteRefused.emit(
            "Ce format de presse-papiers n’est pas encore pris en charge par l’éditeur Qt"
        )

    def apply_typography_to_selection(self) -> bool:
        """Apply shared pure typography rules while retaining Qt formats.

        Edits are calculated over the whole selected Unicode text, so quote
        parity continues across QTextFragment boundaries.  Only changed
        ranges are rewritten, from right to left, in one native undo block.
        """

        selection = self.textCursor()
        if not selection.hasSelection():
            return False
        start = selection.selectionStart()
        source = selection.selectedText()
        opening_next = self._opening_quote_at_position(start)

        fixed = convert_curly_quotes_to_guillemets(source)
        fixed, _opening_next = convert_straight_quotes_stateful(
            fixed,
            opening_next=opening_next,
        )
        fixed = fix_guillemet_spacing(fixed)
        fixed = fix_double_punctuation_spacing(fixed)
        fixed = fix_page_number_spacing(fixed)
        fixed = fix_period_spacing(fixed)
        if fixed == source:
            return False

        opcodes = SequenceMatcher(None, source, fixed, autojunk=False).get_opcodes()
        source_positions = _utf16_offsets(source)
        edit_block = QTextCursor(self.document())
        edit_block.beginEditBlock()
        try:
            for tag, source_start, source_end, fixed_start, fixed_end in reversed(opcodes):
                if tag == "equal":
                    continue
                absolute_start = start + source_positions[source_start]
                absolute_end = start + source_positions[source_end]
                replacement = fixed[fixed_start:fixed_end]
                char_format = self._format_for_edit(absolute_start, absolute_end)
                self._replace_range(
                    absolute_start,
                    absolute_end,
                    replacement,
                    char_format,
                )
        finally:
            edit_block.endEditBlock()

        updated = QTextCursor(self.document())
        updated.setPosition(start)
        updated.setPosition(start + _utf16_length(fixed), QTextCursor.MoveMode.KeepAnchor)
        self.setTextCursor(updated)
        return True

    def _apply_typing_autoformat(self, char: str) -> None:
        if char == '"':
            self._replace_last_quote()
        elif char == OPENING_GUILLEMET:
            self._space_after_opening_guillemet()
        elif char == CLOSING_GUILLEMET:
            self._space_before_current_character()
        elif char in DOUBLE_PUNCTUATION:
            self._space_before_current_character()

        self._autoformat_century_phrases()
        if char.isdigit():
            self._autoformat_page_number_space()
        elif char == ".":
            self._autoformat_period_spacing()
        elif char.isalpha():
            self._autoformat_oe_ligature()
            if char == "e":
                self._autoformat_common_century_ordinal()

    def _typing_requires_autoformat(self, char: str) -> bool:
        if char in ('"', OPENING_GUILLEMET, CLOSING_GUILLEMET) or char in DOUBLE_PUNCTUATION:
            return True
        _block, prefix = self._current_block_prefix()
        candidate = prefix + char
        if char.isdigit() and PAGE_ABBREVIATION_TYPED_RE.search(candidate):
            return True
        if char == "." and SPACE_BEFORE_PERIOD_TYPED_RE.search(candidate):
            return True
        if char.isalpha() and OE_LIGATURE_TYPED_RE.search(candidate):
            return True
        if char == "e" and COMMON_CENTURY_ORDINAL_TYPED_RE.search(candidate):
            return True
        return any(
            is_valid_century_ordinal(match.group(1), match.group(2))
            for match in CENTURY_RE.finditer(candidate)
        )

    def _replace_last_quote(self) -> None:
        cursor = self.textCursor()
        quote_position = cursor.position() - 1
        if quote_position < 0:
            return
        opening_next = self._opening_quote_at_position(quote_position)
        replacement, _ = convert_straight_quotes_stateful(
            '"',
            opening_next=opening_next,
        )
        char_format = self._format_for_edit(quote_position, quote_position + 1)
        self._joined_with_previous_edit(
            lambda: self._replace_range(
                quote_position,
                quote_position + 1,
                replacement,
                char_format,
            )
        )

    def _space_after_opening_guillemet(self) -> None:
        position = self.textCursor().position()
        char_format = self._format_for_edit(position - 1, position)
        self._joined_with_previous_edit(
            lambda: self._replace_range(position, position, NBSP, char_format)
        )

    def _space_before_current_character(self) -> None:
        cursor = self.textCursor()
        punctuation_position = cursor.position() - 1
        if punctuation_position < 0:
            return
        block = cursor.block()
        block_text = block.text()
        relative_position = _python_index_for_utf16_offset(
            block_text,
            punctuation_position - block.position(),
        )
        preceding = block_text[relative_position - 1] if relative_position > 0 else ""
        if preceding == NBSP:
            return
        if preceding == " ":
            start = punctuation_position - 1
            char_format = self._format_for_edit(start, punctuation_position)
            end = punctuation_position
        else:
            start = punctuation_position
            end = punctuation_position
            char_format = self._format_for_edit(
                punctuation_position,
                punctuation_position + 1,
            )
        self._joined_with_previous_edit(
            lambda: self._replace_range(start, end, NBSP, char_format)
        )

    def _autoformat_page_number_space(self) -> None:
        block, prefix = self._current_block_prefix()
        match = PAGE_ABBREVIATION_TYPED_RE.search(prefix)
        if match is None:
            return
        space_offset = prefix.rfind(" ", match.start(), match.end())
        if space_offset < 0:
            return
        start = _block_position(block, space_offset)
        char_format = self._format_for_edit(start, start + 1)
        self._joined_with_previous_edit(
            lambda: self._replace_range(start, start + 1, NBSP, char_format)
        )

    def _autoformat_period_spacing(self) -> None:
        block, prefix = self._current_block_prefix()
        match = SPACE_BEFORE_PERIOD_TYPED_RE.search(prefix)
        if match is None:
            return
        start = _block_position(block, match.start())
        period_position = self.textCursor().position() - 1
        self._joined_with_previous_edit(
            lambda: self._replace_range(start, period_position, "", QTextCharFormat())
        )

    def _autoformat_oe_ligature(self) -> None:
        block, prefix = self._current_block_prefix()
        match = OE_LIGATURE_TYPED_RE.search(prefix)
        if match is None:
            return
        word = match.group(1)
        replacement = oe_ligature_replacement(word)
        pair = _OE_PAIR_RE.search(word)
        if replacement == word or pair is None:
            return
        start = _block_position(block, match.start(1) + pair.start())
        ligature = replacement[pair.start()]
        char_format = self._format_for_edit(start, start + 2)
        self._joined_with_previous_edit(
            lambda: self._replace_range(start, start + 2, ligature, char_format)
        )

    def _autoformat_century_phrases(self) -> None:
        block, prefix = self._current_block_prefix()
        ranges: list[tuple[int, int]] = []
        for match in CENTURY_RE.finditer(prefix):
            numeral, suffix = match.group(1), match.group(2)
            if not is_valid_century_ordinal(numeral, suffix):
                continue
            start = _block_position(block, match.start(2))
            end = _block_position(block, match.end(2))
            if not inline_format_enabled(
                self._format_for_edit(start, end),
                SUPERSCRIPT_PROPERTY,
            ):
                ranges.append((start, end))
        if ranges:
            self._joined_with_previous_edit(lambda: self._superscript_ranges(ranges))

    def _autoformat_common_century_ordinal(self) -> None:
        _block, prefix = self._current_block_prefix()
        if COMMON_CENTURY_ORDINAL_TYPED_RE.search(prefix) is None:
            return
        end = self.textCursor().position()
        start = end - 1
        source_format = self._format_for_edit(start, end)
        if inline_format_enabled(source_format, SUPERSCRIPT_PROPERTY):
            return

        def apply() -> None:
            self._superscript_ranges([(start, end)])
            continuation_format = QTextCharFormat(source_format)
            continuation_format.setProperty(SUPERSCRIPT_PROPERTY, False)
            continuation_format.setVerticalAlignment(
                QTextCharFormat.VerticalAlignment.AlignNormal
            )
            self.setCurrentCharFormat(continuation_format)

        self._joined_with_previous_edit(apply)

    def _superscript_ranges(self, ranges: list[tuple[int, int]]) -> None:
        semantic_format = QTextCharFormat()
        semantic_format.setProperty(SUPERSCRIPT_PROPERTY, True)
        semantic_format.setVerticalAlignment(
            QTextCharFormat.VerticalAlignment.AlignSuperScript
        )
        for start, end in ranges:
            cursor = QTextCursor(self.document())
            cursor.setPosition(start)
            cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
            cursor.mergeCharFormat(semantic_format)

    def _wrap_selection_in_guillemets(self) -> None:
        selection = self.textCursor()
        start = selection.selectionStart()
        end = selection.selectionEnd()
        opening, _ = convert_straight_quotes_stateful('"', opening_next=True)
        closing, _ = convert_straight_quotes_stateful('"', opening_next=False)
        opening_format = self._plain_wrapper_format(
            self._format_for_edit(start, min(start + 1, end))
        )
        closing_format = self._plain_wrapper_format(
            self._format_for_edit(max(start, end - 1), end)
        )

        edit_block = QTextCursor(self.document())
        edit_block.beginEditBlock()
        try:
            self._replace_range(end, end, closing, closing_format)
            self._replace_range(start, start, opening, opening_format)
        finally:
            edit_block.endEditBlock()
        cursor = QTextCursor(self.document())
        cursor.setPosition(end + _utf16_length(opening) + _utf16_length(closing))
        self.setTextCursor(cursor)

    def _opening_quote_at_position(self, position: int) -> bool:
        opening_next = True
        block = self.document().begin()
        while block.isValid() and block.position() < position:
            length = _python_index_for_utf16_offset(
                block.text(),
                max(0, position - block.position()),
            )
            for char in block.text()[:length]:
                if char in (OPENING_GUILLEMET, CURLY_OPENING_QUOTE):
                    opening_next = False
                elif char in (CLOSING_GUILLEMET, CURLY_CLOSING_QUOTE):
                    opening_next = True
                elif char == '"':
                    opening_next = not opening_next
            block = block.next()
        return opening_next

    def _current_block_prefix(self):
        cursor = self.textCursor()
        block = cursor.block()
        relative_position = _python_index_for_utf16_offset(
            block.text(),
            max(0, cursor.position() - block.position()),
        )
        return block, block.text()[:relative_position]

    def _joined_with_previous_edit(self, operation: Callable[[], None]) -> None:
        edit_block = QTextCursor(self.document())
        edit_block.joinPreviousEditBlock()
        try:
            operation()
        finally:
            edit_block.endEditBlock()

    def _replace_range(
        self,
        start: int,
        end: int,
        replacement: str,
        char_format: QTextCharFormat,
    ) -> None:
        cursor = QTextCursor(self.document())
        cursor.setPosition(start)
        cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
        if replacement:
            cursor.insertText(replacement, char_format)
        else:
            cursor.removeSelectedText()

    def _format_for_edit(self, start: int, end: int) -> QTextCharFormat:
        document_end = max(0, self.document().characterCount() - 1)
        if start < end and start < document_end:
            cursor = QTextCursor(self.document())
            cursor.setPosition(start)
            cursor.setPosition(min(start + 1, document_end), QTextCursor.MoveMode.KeepAnchor)
            return QTextCharFormat(cursor.charFormat())
        if start < document_end:
            cursor = QTextCursor(self.document())
            cursor.setPosition(start)
            cursor.setPosition(start + 1, QTextCursor.MoveMode.KeepAnchor)
            return QTextCharFormat(cursor.charFormat())
        if start > 0:
            cursor = QTextCursor(self.document())
            cursor.setPosition(start - 1)
            cursor.setPosition(start, QTextCursor.MoveMode.KeepAnchor)
            return QTextCharFormat(cursor.charFormat())
        return QTextCharFormat(self.currentCharFormat())

    @staticmethod
    def _plain_wrapper_format(source: QTextCharFormat) -> QTextCharFormat:
        char_format = QTextCharFormat(source)
        char_format.setProperty(BOLD_PROPERTY, False)
        char_format.setProperty(ITALIC_PROPERTY, False)
        char_format.setProperty(STRIKETHROUGH_PROPERTY, False)
        char_format.setProperty(SUPERSCRIPT_PROPERTY, False)
        char_format.setFontWeight(QFont.Weight.Normal.value)
        char_format.setFontItalic(False)
        char_format.setFontStrikeOut(False)
        char_format.setVerticalAlignment(QTextCharFormat.VerticalAlignment.AlignNormal)
        char_format.setAnchor(False)
        char_format.setAnchorHref("")
        char_format.setFontUnderline(False)
        char_format.clearForeground()
        return char_format


def _block_position(block, python_offset: int) -> int:
    return block.position() + _utf16_length(block.text()[:python_offset])


def _utf16_length(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2


def _utf16_offsets(text: str) -> list[int]:
    offsets = [0]
    total = 0
    for char in text:
        total += 2 if ord(char) > 0xFFFF else 1
        offsets.append(total)
    return offsets


def _python_index_for_utf16_offset(text: str, utf16_offset: int) -> int:
    if utf16_offset <= 0:
        return 0
    consumed = 0
    for index, char in enumerate(text):
        consumed += 2 if ord(char) > 0xFFFF else 1
        if consumed >= utf16_offset:
            return index + 1
    return len(text)
