"""Canonical clipboard fragments shared between Merope Qt editor widgets."""

from __future__ import annotations

from PySide6.QtCore import QByteArray
from PySide6.QtGui import QTextCursor, QTextDocument, QTextDocumentFragment

from bloggen.markdown.rich_text_export import blocks_to_markdown
from bloggen.markdown.rich_text_import import markdown_to_blocks
from bloggen.markdown.rich_text_model import Block
from bloggen.ui.qt_editor.document_adapter import extract_blocks, validate_blocks


MEROPE_FRAGMENT_MIME = "application/x-merope-markdown-fragment"


class InvalidMeropeClipboardFragment(ValueError):
    """Raised when an internal clipboard payload cannot be preserved safely."""


def encode_selection_as_markdown(cursor: QTextCursor) -> bytes:
    """Serialize one Qt selection through the canonical Block/Run model."""

    if not cursor.hasSelection():
        raise InvalidMeropeClipboardFragment("Aucune sélection à copier")
    fragment_document = QTextDocument()
    fragment_cursor = QTextCursor(fragment_document)
    fragment_cursor.insertFragment(QTextDocumentFragment(cursor))
    blocks = extract_blocks(fragment_document)
    validate_blocks(blocks)
    return blocks_to_markdown(blocks).encode("utf-8")


def decode_markdown_fragment(data: QByteArray | bytes) -> list[Block]:
    """Decode and fully validate one internal Markdown clipboard payload."""

    payload = bytes(data)
    if not payload:
        raise InvalidMeropeClipboardFragment("Fragment Mérope vide")
    try:
        markdown = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise InvalidMeropeClipboardFragment(
            "Le fragment Mérope n’est pas un texte UTF-8 valide"
        ) from exc
    try:
        blocks = markdown_to_blocks(markdown)
    except Exception as exc:
        raise InvalidMeropeClipboardFragment(
            "Le fragment Mérope ne peut pas être interprété"
        ) from exc
    if not blocks:
        raise InvalidMeropeClipboardFragment("Fragment Mérope sans contenu")
    validate_blocks(blocks)
    return blocks
