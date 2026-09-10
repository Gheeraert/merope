"""Selection and atomic replacement of semantic Merope Qt images."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtGui import QTextCursor, QTextDocument

from bloggen.markdown.rich_text_model import InlineRun
from bloggen.ui.qt_editor.document_adapter import (
    UnsupportedInlineError,
    image_run_from_format,
    make_image_format,
)


@dataclass(frozen=True, slots=True)
class ImageTarget:
    """One image object and its exact half-open QTextDocument range."""

    start: int
    end: int
    run: InlineRun

    def cursor(self, document: QTextDocument) -> QTextCursor:
        cursor = QTextCursor(document)
        cursor.setPosition(self.start)
        cursor.setPosition(self.end, QTextCursor.MoveMode.KeepAnchor)
        return cursor


def merope_image_at_position(
    document: QTextDocument,
    position: int,
) -> ImageTarget | None:
    """Return the Merope image occupying ``position``, if any."""

    if position < 0 or position >= document.characterCount() - 1:
        return None
    block = document.findBlock(position)
    if not block.isValid():
        return None
    iterator = block.begin()
    while not iterator.atEnd():
        fragment = iterator.fragment()
        if fragment.isValid():
            start = fragment.position()
            end = start + fragment.length()
            if start <= position < end:
                if not fragment.charFormat().isImageFormat():
                    return None
                return ImageTarget(
                    start=position,
                    end=position + 1,
                    run=image_run_from_format(fragment.charFormat()),
                )
        iterator += 1
    return None


def merope_images_in_selection(cursor: QTextCursor) -> list[ImageTarget]:
    """Return every semantic image intersecting a non-empty selection."""

    if not cursor.hasSelection():
        return []
    start = cursor.selectionStart()
    end = cursor.selectionEnd()
    targets: list[ImageTarget] = []
    block = cursor.document().findBlock(start)
    while block.isValid() and block.position() < end:
        iterator = block.begin()
        while not iterator.atEnd():
            fragment = iterator.fragment()
            fragment_start = fragment.position()
            fragment_end = fragment_start + fragment.length()
            if (
                fragment.isValid()
                and fragment.charFormat().isImageFormat()
                and fragment_end > start
                and fragment_start < end
            ):
                run = image_run_from_format(fragment.charFormat())
                selected_start = max(fragment_start, start)
                selected_end = min(fragment_end, end)
                targets.extend(
                    ImageTarget(position, position + 1, run)
                    for position in range(selected_start, selected_end)
                )
            iterator += 1
        block = block.next()
    return targets


def targeted_merope_image(cursor: QTextCursor) -> ImageTarget | None:
    """Resolve one unambiguous selected or adjacent Merope image.

    A non-empty selection may include text but must intersect exactly one
    image. A collapsed cursor targets its unique adjacent image; a boundary
    between two images is deliberately ambiguous.
    """

    if cursor.hasSelection():
        targets = merope_images_in_selection(cursor)
        return targets[0] if len(targets) == 1 else None

    candidates = {
        target.start: target
        for position in (cursor.position() - 1, cursor.position())
        if (target := merope_image_at_position(cursor.document(), position))
        is not None
    }
    return next(iter(candidates.values())) if len(candidates) == 1 else None


def exactly_selected_merope_image(cursor: QTextCursor) -> ImageTarget | None:
    """Return the target only when its one-character range is selected exactly."""

    if not cursor.hasSelection():
        return None
    target = targeted_merope_image(cursor)
    if target is None:
        return None
    if (
        cursor.selectionStart() != target.start
        or cursor.selectionEnd() != target.end
    ):
        return None
    return target


def replace_merope_image(
    document: QTextDocument,
    target: ImageTarget,
    run: InlineRun,
    *,
    allow_source_change: bool = False,
) -> QTextCursor:
    """Replace exactly one image with a fresh canonical format in one undo.

    Metadata editing remains protected against accidental source changes.
    The dedicated file-replacement workflow must opt in explicitly.
    """

    if not allow_source_change and run.image_src != target.run.image_src:
        raise UnsupportedInlineError("Le src d'une image ne peut pas etre modifie ici")
    current = merope_image_at_position(document, target.start)
    if current != target:
        raise UnsupportedInlineError("La cible image n'est plus valide")
    if run == target.run:
        return target.cursor(document)

    cursor = target.cursor(document)
    cursor.beginEditBlock()
    try:
        cursor.removeSelectedText()
        cursor.insertImage(make_image_format(run))
    finally:
        cursor.endEditBlock()
    cursor.setPosition(target.start)
    cursor.setPosition(target.start + 1, QTextCursor.MoveMode.KeepAnchor)
    return cursor
