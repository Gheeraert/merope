"""QTextEdit adaptations for Merope's editing interactions."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from difflib import SequenceMatcher
from pathlib import Path
from typing import Callable

from PySide6.QtCore import (
    QByteArray,
    QEvent,
    QMimeData,
    QPoint,
    QRect,
    QRectF,
    QSize,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QContextMenuEvent,
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
    QTextLayout,
    QWheelEvent,
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
from bloggen.markdown.caption import flatten_caption_text
from bloggen.ui.qt_editor.document_adapter import (
    UnsupportedDocumentError,
    caption_block_for_selection,
    caption_normalization_needed,
    figure_caption_block,
    inline_format_enabled,
    insert_blocks,
    insert_paragraph_after,
    is_caption_block,
    is_semantic_inline_object_format,
    make_caption_char_format,
    normalize_figure_captions,
    selection_crosses_caption_boundary,
    make_raw_block_format,
    make_raw_char_format,
    raw_block_identity,
    selection_block_identities,
    selection_crosses_raw_boundary,
    selection_touches_raw_block,
)
from bloggen.ui.qt_editor.footnote_selection import (
    expand_selection_to_footnotes,
    merope_footnote_at_position,
)
from bloggen.content.image_size import (
    MENU_PERCENTS,
    ResizeOutcome,
    format_percent,
    max_percent_for,
    parse_width,
    resize_to_width,
)
from bloggen.ui.qt_editor.image_resize import (
    ImageResizeGeometry,
    column_width,
    displayed_size,
    dragged_width,
    ghost_rect,
    image_viewport_rect,
    natural_image_size,
    resize_drag_is_effective,
    selected_image_resize_geometry,
    size_label,
)
from bloggen.ui.qt_editor.image_selection import (
    ImageTarget,
    exactly_selected_merope_image,
    merope_image_at_position,
    replace_merope_image,
)


_OE_PAIR_RE = re.compile("oe", re.IGNORECASE)
_REJECTED_RICH_PASTE_TAGS = frozenset(
    {"img", "pre", "table", "v:imagedata", "v:shape"}
)
ZOOM_MIN_PERCENT = 50
ZOOM_MAX_PERCENT = 300
ZOOM_STEP_PERCENT = 10


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
    """One corner drag. The document is only written once, on release."""

    target: ImageTarget
    handle: str
    origin: QPoint
    initial_rect: QRect
    natural: QSize
    column: float
    activated: bool = False
    outcome: ResizeOutcome | None = None
    ghost: QRect | None = None
    label: str = ""


_RESIZE_CURSORS = {
    "nw": Qt.CursorShape.SizeFDiagCursor,
    "se": Qt.CursorShape.SizeFDiagCursor,
    "ne": Qt.CursorShape.SizeBDiagCursor,
    "sw": Qt.CursorShape.SizeBDiagCursor,
}
_RESIZE_ACCENT = QColor(42, 109, 181)
CAPTION_PLACEHOLDER = "Légende de l’image (facultative)"
CAPTION_PLACEHOLDER_COLOR = "#9aa0a6"


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
    imageMetadataRequested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAcceptRichText(False)
        self.viewport().setMouseTracking(True)
        # QAbstractScrollArea dispatches native wheel input to its viewport
        # on Windows. Filtering that real receiver makes Ctrl+wheel reliable;
        # wheelEvent remains as a fallback for synthetic/platform variants.
        self.viewport().installEventFilter(self)
        self._image_resize_state: _ImageResizeState | None = None
        self._external_paste_context: ExternalPasteContext | None = None
        self._zoom_percent = 100
        self._applying_zoom_overlay = False
        self.selectionChanged.connect(self.viewport().update)
        self.document().contentsChanged.connect(self._on_contents_changed)
        # Figure captions are re-paired with their images after any edit
        # (native deletes, drag and drop, undo-free paths...), merged into the
        # edit that broke the pairing so undo stays a single step.
        self._caption_region: tuple[int, int] | None = None
        self._normalizing_captions = False
        self.document().contentsChange.connect(self._note_caption_change)

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

    @property
    def external_paste_context(self) -> ExternalPasteContext | None:
        """Read-only view used by the window workflow and its contracts."""

        return self._external_paste_context

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if self._image_resize_state is not None and event.key() == Qt.Key.Key_Escape:
            self.cancel_image_resize()
            event.accept()
            return
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
        if self._handle_raw_block_key(event):
            event.accept()
            return
        if self._handle_caption_key(event):
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
            handle = (
                geometry.handle_at(event.position().toPoint())
                if geometry is not None
                else None
            )
            if geometry is not None and handle is not None:
                self._start_image_resize(geometry, handle, event.position().toPoint())
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

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        target = self._image_at_viewport_point(event.pos())
        if target is None:
            super().contextMenuEvent(event)
            return
        self.setTextCursor(target.cursor(self.document()))
        self.viewport().update()
        menu = self.createStandardContextMenu(event.pos())
        menu.addSeparator()
        caption_action = menu.addAction("Légende...")
        if figure_caption_block(self.document().findBlock(target.start)) is not None:
            # A figure's caption is typed right below it.
            caption_action.triggered.connect(
                lambda _checked=False, start=target.start: self.edit_figure_caption(start)
            )
        else:
            caption_action.triggered.connect(self.imageMetadataRequested.emit)
        self._add_image_size_menu(menu, target)
        menu.exec(event.globalPos())
        menu.deleteLater()

    def _add_image_size_menu(self, menu, target: ImageTarget) -> None:
        size_menu = menu.addMenu("Taille")
        current = parse_width(target.run.image_width)
        ceiling = max_percent_for(target.run.image_align)
        for percent in MENU_PERCENTS:
            if percent > ceiling:
                continue
            action = size_menu.addAction(f"{percent} % de la colonne")
            action.setCheckable(True)
            action.setChecked(
                current is not None and current.is_percent and current.value == percent
            )
            action.triggered.connect(
                lambda _checked=False, value=format_percent(percent): (
                    self.set_selected_image_width(value)
                )
            )
        size_menu.addSeparator()
        natural = size_menu.addAction("Taille réelle (limitée à la colonne)")
        natural.setCheckable(True)
        natural.setChecked(current is None)
        natural.triggered.connect(lambda _checked=False: self.set_selected_image_width(None))

    def set_selected_image_width(self, width: str | None) -> bool:
        """Give the exactly selected image a new width in one undo step.

        ``width`` is a stored value ("50%") or ``None`` for the natural size.
        A fixed height is always dropped so the proportions stay intact.
        """

        try:
            target = exactly_selected_merope_image(self.textCursor())
        except UnsupportedDocumentError:
            return False
        if target is None:
            return False
        new_run = replace(target.run, image_width=width, image_height=None)
        if new_run == target.run:
            return False
        selected = replace_merope_image(self.document(), target, new_run)
        self.setTextCursor(selected)
        self.viewport().update()
        return True

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

    # -- figure captions ----------------------------------------------------------

    def _handle_caption_key(self, event: QKeyEvent) -> bool:
        """Keep a caption one line, attached to its image, apart from the text.

        Enter never splits a caption (it opens a paragraph after the figure),
        and Backspace/Delete never merge a caption with the image or with the
        text around it. Selections straddling a caption edge are refused.
        """

        key = event.key()
        enter = key in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
        erase = key in (Qt.Key.Key_Backspace, Qt.Key.Key_Delete)
        typing = bool(event.text()) and not event.modifiers() & (
            Qt.KeyboardModifier.ControlModifier
            | Qt.KeyboardModifier.AltModifier
            | Qt.KeyboardModifier.MetaModifier
        )
        if not (enter or erase or typing):
            return False
        cursor = self.textCursor()
        if selection_crosses_caption_boundary(cursor):
            return True

        caption = caption_block_for_selection(cursor)
        if caption is not None:
            if enter:
                self._open_paragraph_after(caption, cursor)
                return True
            if event.text() == "\t":
                return True
            if not cursor.hasSelection():
                at_start = cursor.position() == caption.position()
                at_end = cursor.position() == caption.position() + caption.length() - 1
                if (key == Qt.Key.Key_Backspace and at_start) or (
                    key == Qt.Key.Key_Delete and at_end
                ):
                    return True
            return False

        if cursor.hasSelection():
            return False
        block = cursor.block()
        position = cursor.position()
        if (
            key == Qt.Key.Key_Backspace
            and position == block.position()
            and is_caption_block(block.previous())
        ):
            previous = block.previous()
            self._place_cursor(previous.position() + previous.length() - 1)
            return True
        if key == Qt.Key.Key_Delete and position == block.position() + block.length() - 1:
            following = block.next()
            if is_caption_block(following):
                self._place_cursor(following.position())
                return True
        figure_caption = figure_caption_block(block)
        if enter and figure_caption is not None and position > block.position():
            self._open_paragraph_after(figure_caption, cursor)
            return True
        return False

    def _open_paragraph_after(self, caption, cursor: QTextCursor) -> None:
        edit = QTextCursor(self.document())
        edit.beginEditBlock()
        try:
            if cursor.hasSelection():
                cursor.removeSelectedText()
            paragraph = insert_paragraph_after(caption)
        finally:
            edit.endEditBlock()
        self.setTextCursor(paragraph)

    def _place_cursor(self, position: int) -> None:
        cursor = QTextCursor(self.document())
        cursor.setPosition(position)
        self.setTextCursor(cursor)

    def edit_figure_caption(self, image_position: int) -> bool:
        """Put the caret in a figure's caption, its current text selected."""

        caption = figure_caption_block(self.document().findBlock(image_position))
        if caption is None:
            return False
        cursor = QTextCursor(self.document())
        cursor.setPosition(caption.position())
        cursor.setPosition(
            caption.position() + caption.length() - 1, QTextCursor.MoveMode.KeepAnchor
        )
        self.setTextCursor(cursor)
        self.setFocus(Qt.FocusReason.OtherFocusReason)
        return True

    def _insert_plain_text_in_caption(self, text: str) -> bool:
        flat = flatten_caption_text(text)
        if not flat:
            return False
        cursor = self.textCursor()
        cursor.beginEditBlock()
        try:
            cursor.insertText(flat, make_caption_char_format())
        finally:
            cursor.endEditBlock()
        self.setTextCursor(cursor)
        return True

    def _note_caption_change(self, position: int, _removed: int, added: int) -> None:
        if self._normalizing_captions:
            return
        end = position + max(added, 0)
        region = self._caption_region
        self._caption_region = (
            (position, end)
            if region is None
            else (min(region[0], position), max(region[1], end))
        )
        if region is None:
            QTimer.singleShot(0, self.normalize_captions)

    def normalize_captions(self) -> bool:
        """Re-pair figures and captions, joined to the edit that broke them."""

        region = self._caption_region
        self._caption_region = None
        document = self.document()
        # Right after an undo the restored state was already consistent;
        # joining a fix there would rewrite history.
        if document.isRedoAvailable():
            return False
        start, end = region if region is not None else (None, None)
        if not caption_normalization_needed(document, start, end):
            return False
        self._normalizing_captions = True
        edit = QTextCursor(document)
        edit.joinPreviousEditBlock()
        try:
            changed = normalize_figure_captions(document, start, end)
        finally:
            edit.endEditBlock()
            self._normalizing_captions = False
        self.viewport().update()
        return changed

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

    def _handle_raw_block_key(self, event: QKeyEvent) -> bool:
        cursor = self.textCursor()
        key = event.key()
        identities = selection_block_identities(cursor)
        raw_identities = {identity for identity in identities if identity is not None}
        editing_key = key in {
            Qt.Key.Key_Delete,
            Qt.Key.Key_Backspace,
            Qt.Key.Key_Return,
            Qt.Key.Key_Enter,
        } or bool(event.text())
        if editing_key and selection_crosses_raw_boundary(cursor):
            return True
        if not raw_identities:
            if not cursor.hasSelection() and key in {
                Qt.Key.Key_Delete,
                Qt.Key.Key_Backspace,
            }:
                block = cursor.block()
                at_start = cursor.position() == block.position()
                at_end = cursor.position() == block.position() + block.length() - 1
                adjacent = (
                    block.previous()
                    if key == Qt.Key.Key_Backspace and at_start
                    else block.next()
                    if key == Qt.Key.Key_Delete and at_end
                    else None
                )
                if adjacent is not None and adjacent.isValid() and raw_block_identity(
                    adjacent
                ) is not None:
                    return True
            return False

        if not editing_key:
            return False
        if len(identities) != 1 or len(raw_identities) != 1:
            return True

        identity = next(iter(raw_identities))
        if key in {Qt.Key.Key_Return, Qt.Key.Key_Enter}:
            cursor.beginEditBlock()
            try:
                if cursor.hasSelection():
                    cursor.removeSelectedText()
                cursor.insertBlock(
                    make_raw_block_format(*identity),
                    make_raw_char_format(),
                )
            finally:
                cursor.endEditBlock()
            self.setTextCursor(cursor)
            return True

        if key in {Qt.Key.Key_Delete, Qt.Key.Key_Backspace}:
            if cursor.hasSelection():
                super().keyPressEvent(event)
                return True
            at_start = cursor.position() == cursor.block().position()
            at_end = cursor.position() == cursor.block().position() + cursor.block().length() - 1
            if (key == Qt.Key.Key_Backspace and at_start) or (
                key == Qt.Key.Key_Delete and at_end
            ):
                adjacent = cursor.block().previous() if at_start else cursor.block().next()
                if not adjacent.isValid() or raw_block_identity(adjacent) != identity:
                    return True
            super().keyPressEvent(event)
            return True

        if event.modifiers() & (
            Qt.KeyboardModifier.ControlModifier
            | Qt.KeyboardModifier.AltModifier
            | Qt.KeyboardModifier.MetaModifier
        ):
            return False
        cursor.beginEditBlock()
        try:
            if cursor.hasSelection():
                cursor.removeSelectedText()
            cursor.insertText(event.text(), make_raw_char_format())
        finally:
            cursor.endEditBlock()
        self.setTextCursor(cursor)
        return True

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
        if cut and selection_crosses_raw_boundary(cursor):
            self.clipboardRefused.emit(
                "La coupe ne peut pas traverser la frontière d’un bloc brut"
            )
            return True
        if cut and selection_crosses_caption_boundary(cursor):
            self.clipboardRefused.emit(
                "La coupe ne peut pas séparer une légende de son image"
            )
            return True
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
        state = self._image_resize_state
        if state is not None:
            self.viewport().setCursor(_RESIZE_CURSORS[state.handle])
            return
        geometry = self.image_resize_geometry()
        handle = (
            geometry.handle_at(point)
            if point is not None and geometry is not None
            else None
        )
        if handle is not None:
            self.viewport().setCursor(_RESIZE_CURSORS[handle])
        else:
            self._set_normal_viewport_cursor()

    def _start_image_resize(
        self,
        geometry: ImageResizeGeometry,
        handle: str,
        point: QPoint,
    ) -> None:
        natural = natural_image_size(self.document(), geometry.target)
        if natural is None:
            return
        self._image_resize_state = _ImageResizeState(
            target=geometry.target,
            handle=handle,
            origin=QPoint(point),
            initial_rect=QRect(geometry.image_rect),
            natural=natural,
            column=column_width(self.document()),
        )
        self.viewport().setCursor(_RESIZE_CURSORS[handle])

    def _resize_selected_image_to(self, point: QPoint, modifiers=None) -> None:
        """Update the ghost only; the document is untouched until release."""

        state = self._image_resize_state
        if state is None:
            return
        if not state.activated:
            if not resize_drag_is_effective(state.origin, point):
                return
            state.activated = True
        if modifiers is None:
            modifiers = QApplication.keyboardModifiers()
        outcome = resize_to_width(
            dragged_width(state.initial_rect.size(), point - state.origin, state.handle),
            column_width=state.column,
            natural_width=state.natural.width(),
            align=state.target.run.image_align,
            snap=not modifiers & Qt.KeyboardModifier.AltModifier,
        )
        size = displayed_size(
            outcome, state.natural, state.column, state.target.run.image_align
        )
        state.outcome = outcome
        state.ghost = ghost_rect(state.initial_rect, state.handle, size)
        state.label = size_label(outcome, size)
        self.viewport().update()

    def _finish_image_resize(self, *, commit: bool = True) -> bool:
        state = self._image_resize_state
        self._image_resize_state = None
        changed = False
        if commit and state is not None and state.activated and state.outcome is not None:
            new_run = replace(
                state.target.run,
                image_width=state.outcome.width_value,
                image_height=None,
            )
            if new_run != state.target.run:
                selected = replace_merope_image(self.document(), state.target, new_run)
                self.setTextCursor(selected)
                changed = True
        self._set_normal_viewport_cursor()
        self.viewport().update()
        return changed

    def cancel_image_resize(self) -> None:
        self._finish_image_resize(commit=False)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._image_resize_state is not None:
            self._resize_selected_image_to(event.position().toPoint(), event.modifiers())
            event.accept()
            return
        self._update_resize_cursor(event.position().toPoint())
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if (
            self._image_resize_state is not None
            and event.button() == Qt.MouseButton.LeftButton
        ):
            self._resize_selected_image_to(event.position().toPoint(), event.modifiers())
            self._finish_image_resize()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            geometry = self.image_resize_geometry()
            if geometry is not None and geometry.handle_at(event.position().toPoint()):
                # Double-clicking a handle returns the image to its natural size.
                self.cancel_image_resize()
                self.set_selected_image_width(None)
                event.accept()
                return
        super().mouseDoubleClickEvent(event)

    def leaveEvent(self, event) -> None:
        if self._image_resize_state is None:
            self._set_normal_viewport_cursor()
        super().leaveEvent(event)

    def paintEvent(self, event: QPaintEvent) -> None:
        super().paintEvent(event)
        self._paint_caption_placeholders()
        geometry = self.image_resize_geometry()
        if geometry is None:
            return

        painter = QPainter(self.viewport())
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(_RESIZE_ACCENT, 1.5))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(QRectF(geometry.image_rect).adjusted(0.5, 0.5, -0.5, -0.5))
        painter.setBrush(Qt.GlobalColor.white)
        for handle in geometry.handles.values():
            painter.drawRect(QRectF(handle).adjusted(0.5, 0.5, -0.5, -0.5))

        state = self._image_resize_state
        if state is None or state.ghost is None:
            return
        # The selected image is already tinted by Qt's selection colour: a
        # light veil with a black/white double outline stays readable on it.
        ghost = QRectF(state.ghost).adjusted(0.5, 0.5, -0.5, -0.5)
        painter.setPen(QPen(QColor(0, 0, 0, 150), 3))
        painter.setBrush(QColor(255, 255, 255, 70))
        painter.drawRect(ghost)
        painter.setPen(QPen(Qt.GlobalColor.white, 1.5))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(ghost)
        self._paint_resize_label(painter, state)

    def _paint_caption_placeholders(self) -> None:
        """Hint where an empty caption can be typed (visible blocks only)."""

        layout = self.document().documentLayout()
        dy = self.verticalScrollBar().value()
        bottom = self.viewport().height()
        block = self.cursorForPosition(QPoint(0, 0)).block()
        painter: QPainter | None = None
        while block.isValid():
            if layout.blockBoundingRect(block).top() - dy > bottom:
                break
            if is_caption_block(block) and block.length() <= 1:
                caret = QTextCursor(self.document())
                caret.setPosition(block.position())
                line = self.cursorRect(caret)
                if painter is None:
                    painter = QPainter(self.viewport())
                    painter.setPen(QColor(CAPTION_PLACEHOLDER_COLOR))
                # An empty line keeps its unzoomed height: size the hint to it.
                font = QFont(self.font())
                font.setItalic(True)
                font.setPixelSize(max(8, round(line.height() * 0.7)))
                painter.setFont(font)
                width = self.viewport().width() - line.left() - 4
                painter.drawText(
                    QRect(line.left() + 2, line.top(), max(0, width), line.height()),
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                    CAPTION_PLACEHOLDER,
                )
            block = block.next()
        if painter is not None:
            painter.end()

    def _paint_resize_label(self, painter: QPainter, state: _ImageResizeState) -> None:
        metrics = painter.fontMetrics()
        width = metrics.horizontalAdvance(state.label) + 14
        height = metrics.height() + 8
        viewport = self.viewport().rect()
        x = min(max(state.ghost.left(), 4), viewport.width() - width - 4)
        y = state.ghost.bottom() + 8
        if y + height > viewport.height() - 4:
            y = max(4, state.ghost.top() - height - 8)
        label = QRectF(x, y, width, height)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(30, 30, 30, 215))
        painter.drawRoundedRect(label, 5, 5)
        painter.setPen(Qt.GlobalColor.white)
        painter.drawText(label, Qt.AlignmentFlag.AlignCenter, state.label)

    def scrollContentsBy(self, dx: int, dy: int) -> None:
        super().scrollContentsBy(dx, dy)
        self.viewport().update()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self.viewport().update()

    @property
    def zoom_percent(self) -> int:
        return self._zoom_percent

    def adjust_zoom(self, steps: int) -> bool:
        """Rescale zoom within the 50-300% range, as a pure render overlay.

        ``document_adapter`` stamps an explicit ``fontPointSize`` on every
        run (body text, headings, footnote markers) so heading level stays
        block metadata rather than a font-size guess. That means
        ``QTextEdit.zoomIn``/``zoomOut`` - which only rescale the widget's
        unused default font - have nothing to act on: the explicit sizes
        always win. Editing those sizes directly would work visually, but
        would pollute the undo stack and the modified flag for a change
        that is supposed to be view-only. Instead, each block's
        ``QTextLayout`` gets a scaled overlay format applied purely for
        painting, leaving the document's real character formats untouched.
        """

        target = min(
            ZOOM_MAX_PERCENT,
            max(ZOOM_MIN_PERCENT, self._zoom_percent + steps * ZOOM_STEP_PERCENT),
        )
        if target == self._zoom_percent:
            return False
        self._zoom_percent = target
        self._apply_zoom_overlay()
        self.viewport().update()
        return True

    def _on_contents_changed(self) -> None:
        # Editing a block clears any QTextLayout overlay formats Qt had
        # for it, so re-stamp them whenever zoom is active. Guarded against
        # re-entrancy since re-stamping itself dirties the document.
        if self._zoom_percent != 100 and not self._applying_zoom_overlay:
            self._apply_zoom_overlay()
        self.viewport().update()

    def _apply_zoom_overlay(self) -> None:
        """Paint every run at ``fontPointSize`` * zoom, without touching it."""

        self._applying_zoom_overlay = True
        try:
            self._rebuild_zoom_overlay()
        finally:
            self._applying_zoom_overlay = False

    def _rebuild_zoom_overlay(self) -> None:
        ratio = self._zoom_percent / 100
        document = self.document()
        block = document.begin()
        while block.isValid():
            ranges: list[QTextLayout.FormatRange] = []
            if ratio != 1.0:
                block_position = block.position()
                it = block.begin()
                while not it.atEnd():
                    fragment = it.fragment()
                    if fragment.isValid():
                        base_size = fragment.charFormat().fontPointSize()
                        if base_size > 0:
                            scaled_format = QTextCharFormat()
                            scaled_format.setFontPointSize(base_size * ratio)
                            format_range = QTextLayout.FormatRange()
                            format_range.start = fragment.position() - block_position
                            format_range.length = fragment.length()
                            format_range.format = scaled_format
                            ranges.append(format_range)
                    it += 1
            block.layout().setFormats(ranges)
            block = block.next()
        # Overlay formats alone don't invalidate cached line geometry;
        # force a relayout so wrapping, line height, and the scrollbar
        # range actually reflect the new size.
        document.markContentsDirty(0, document.characterCount())

    def wheelEvent(self, event: QWheelEvent) -> None:
        if self._consume_zoom_wheel(event):
            return
        super().wheelEvent(event)

    def eventFilter(self, watched, event) -> bool:
        if watched is self.viewport() and event.type() == QEvent.Type.Wheel:
            if self._consume_zoom_wheel(event):
                return True
        return super().eventFilter(watched, event)

    def _consume_zoom_wheel(self, event: QWheelEvent) -> bool:
        if not event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            return False
        delta = event.angleDelta().y() or event.pixelDelta().y()
        if not delta:
            return False
        self.adjust_zoom(1 if delta > 0 else -1)
        event.accept()
        return True

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

        paste_cursor = self.textCursor()
        if selection_crosses_raw_boundary(paste_cursor):
            self.pasteRefused.emit(
                "Le collage ne peut pas remplacer une frontière de bloc brut"
            )
            return
        if selection_crosses_caption_boundary(paste_cursor):
            self.pasteRefused.emit(
                "Le collage ne peut pas séparer une légende de son image"
            )
            return
        if caption_block_for_selection(paste_cursor) is not None:
            text = source.text() if source.hasText() else ""
            if not self._insert_plain_text_in_caption(text):
                self.pasteRefused.emit(
                    "Une légende d’image ne peut recevoir que du texte"
                )
            return
        raw_identities = selection_block_identities(paste_cursor)
        if any(identity is not None for identity in raw_identities):
            if len(raw_identities) != 1 or None in raw_identities:
                self.pasteRefused.emit(
                    "Le collage ne peut pas traverser la frontière d’un bloc brut"
                )
                return
            if not source.hasText() or not source.text():
                self.pasteRefused.emit(
                    "Ce presse-papiers ne contient aucun texte utilisable dans ce bloc brut"
                )
                return
            self._insert_plain_text_in_raw_block(source.text(), next(iter(raw_identities)))
            return

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

        if source.hasText():
            self._insert_plain_text(source.text())
            return

        self.pasteRefused.emit(
            "Ce format de presse-papiers n’est pas encore pris en charge par l’éditeur Qt"
        )

    def paste_plain_text(self, text: str | None = None) -> bool:
        """Paste only clipboard text, ignoring every rich MIME representation."""

        plain = QApplication.clipboard().text() if text is None else text
        if not plain:
            return False
        return self._insert_plain_text(plain)

    def _insert_plain_text(self, text: str) -> bool:
        cursor = self.textCursor()
        if selection_crosses_raw_boundary(cursor):
            self.pasteRefused.emit(
                "Le collage ne peut pas remplacer une frontière de bloc brut"
            )
            return False
        if selection_crosses_caption_boundary(cursor):
            self.pasteRefused.emit(
                "Le collage ne peut pas séparer une légende de son image"
            )
            return False
        if caption_block_for_selection(cursor) is not None:
            return self._insert_plain_text_in_caption(text)
        identities = selection_block_identities(cursor)
        raw_identities = {identity for identity in identities if identity is not None}
        if raw_identities:
            if len(identities) != 1 or len(raw_identities) != 1:
                self.pasteRefused.emit(
                    "Le collage ne peut pas traverser la frontière d’un bloc brut"
                )
                return False
            self._insert_plain_text_in_raw_block(text, next(iter(raw_identities)))
            return True

        cursor, contains_note = expand_selection_to_footnotes(cursor)
        if contains_note:
            self.setTextCursor(cursor)
        cursor = self.textCursor()
        atomic_paste = contains_note or self._cursor_touches_footnote(cursor)
        cursor.beginEditBlock()
        try:
            if atomic_paste:
                cursor.insertText(
                    text,
                    self._plain_footnote_replacement_format(cursor),
                )
            else:
                cursor.insertText(text)
        finally:
            cursor.endEditBlock()
        self.setTextCursor(cursor)
        return True

    def insert_nbsp(self) -> bool:
        """Insert one literal U+00A0 while preserving semantic boundaries."""

        cursor = self.textCursor()
        if selection_crosses_raw_boundary(cursor) or self._selection_contains_image(
            cursor
        ):
            return False
        identities = selection_block_identities(cursor)
        raw_identities = {identity for identity in identities if identity is not None}
        if raw_identities:
            if len(identities) != 1 or len(raw_identities) != 1:
                return False
            self._insert_plain_text_in_raw_block(NBSP, next(iter(raw_identities)))
            return True

        cursor, contains_note = expand_selection_to_footnotes(cursor)
        replacement_format = (
            self._plain_footnote_replacement_format(cursor)
            if contains_note or self._cursor_touches_footnote(cursor)
            else None
        )
        cursor.beginEditBlock()
        try:
            if replacement_format is None:
                cursor.insertText(NBSP)
            else:
                cursor.insertText(NBSP, replacement_format)
        finally:
            cursor.endEditBlock()
        self.setTextCursor(cursor)
        return True

    def _selection_contains_image(self, cursor: QTextCursor) -> bool:
        if not cursor.hasSelection():
            return False
        start = cursor.selectionStart()
        end = cursor.selectionEnd()
        block = self.document().findBlock(start)
        while block.isValid() and block.position() < end:
            iterator = block.begin()
            while not iterator.atEnd():
                fragment = iterator.fragment()
                if (
                    fragment.isValid()
                    and fragment.charFormat().isImageFormat()
                    and fragment.position() < end
                    and fragment.position() + fragment.length() > start
                ):
                    return True
                iterator += 1
            block = block.next()
        return False

    def _insert_plain_text_in_raw_block(
        self,
        text: str,
        identity: tuple[str, str],
    ) -> None:
        cursor = self.textCursor()
        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        lines = normalized.split("\n")
        cursor.beginEditBlock()
        try:
            if cursor.hasSelection():
                cursor.removeSelectedText()
            cursor.insertText(lines[0], make_raw_char_format())
            for line in lines[1:]:
                cursor.insertBlock(
                    make_raw_block_format(*identity),
                    make_raw_char_format(),
                )
                cursor.insertText(line, make_raw_char_format())
        finally:
            cursor.endEditBlock()
        self.setTextCursor(cursor)

    def apply_typography_to_selection(self) -> bool:
        """Apply shared pure typography rules while retaining Qt formats.

        Edits are calculated over the whole selected Unicode text, so quote
        parity continues across QTextFragment boundaries.  Only changed
        ranges are rewritten, from right to left, in one native undo block.
        """

        selection = self.textCursor()
        if not selection.hasSelection():
            return False
        if selection_touches_raw_block(selection):
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
