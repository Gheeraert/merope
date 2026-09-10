"""Safe file orchestration for the standalone Qt editor prototype."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QTextDocument

from bloggen.content.versioning import ArchiveResult, archive_previous_version
from bloggen.content.writer import read_content_file, write_content_file
from bloggen.markdown.rich_text_export import blocks_to_markdown
from bloggen.markdown.rich_text_import import markdown_to_blocks
from bloggen.ui.qt_editor.document_adapter import (
    extract_blocks,
    populate_document,
    validate_blocks,
)


@dataclass(frozen=True, slots=True)
class LoadedContent:
    path: Path
    metadata: dict[str, str]


@dataclass(frozen=True, slots=True)
class SaveResult:
    path: Path
    markdown_body: str
    archive: ArchiveResult


def load_content_document(path: Path, document: QTextDocument) -> LoadedContent:
    """Load and fully validate a Merope file before replacing ``document``."""

    path = Path(path)
    metadata, body = read_content_file(path)
    blocks = markdown_to_blocks(body)
    # Change the resource context only after full validation. An unsupported
    # file therefore leaves both the open document and its base URL intact.
    validate_blocks(blocks)
    document.setBaseUrl(_document_base_url(path))
    populate_document(document, blocks)
    document.setModified(False)
    return LoadedContent(path=path, metadata=dict(metadata))


def save_content_document(
    path: Path,
    metadata: dict[str, str],
    document: QTextDocument,
) -> SaveResult:
    """Archive, serialize through Block/Run, and overwrite one Merope file."""

    path = Path(path)
    blocks = extract_blocks(document)
    markdown_body = blocks_to_markdown(blocks)
    archive = archive_previous_version(path)
    written_path = write_content_file(path.parent, path.name, metadata, markdown_body)
    document.setModified(False)
    return SaveResult(path=written_path, markdown_body=markdown_body, archive=archive)


def _document_base_url(path: Path) -> QUrl:
    directory = str(path.resolve().parent) + os.sep
    return QUrl.fromLocalFile(directory)
