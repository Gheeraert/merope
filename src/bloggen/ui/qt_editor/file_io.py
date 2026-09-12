"""Safe file orchestration for the standalone Qt editor prototype."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QTextDocument

from bloggen.content.footnotes import (
    FootnoteDefinitions,
    footnote_definition_blocks,
    separate_footnote_definitions,
)
from bloggen.content.versioning import ArchiveResult, archive_previous_version
from bloggen.content.writer import read_content_file, write_content_file
from bloggen.markdown.rich_text_export import blocks_to_markdown
from bloggen.markdown.rich_text_import import markdown_to_blocks
from bloggen.markdown.rich_text_model import Block
from bloggen.ui.qt_editor.document_adapter import (
    extract_blocks,
    populate_document,
    validate_blocks,
    validate_footnote_definitions,
)


@dataclass(frozen=True, slots=True)
class LoadedContent:
    path: Path
    metadata: dict[str, str]
    footnote_definitions: FootnoteDefinitions


@dataclass(frozen=True, slots=True)
class PreparedContent:
    """Fully parsed canonical content, not yet applied to a Qt document."""

    path: Path
    metadata: dict[str, str]
    markdown_body: str
    body_blocks: list[Block]
    footnote_definitions: FootnoteDefinitions


@dataclass(frozen=True, slots=True)
class SaveResult:
    path: Path
    markdown_body: str
    archive: ArchiveResult


def load_content_document(path: Path, document: QTextDocument) -> LoadedContent:
    """Load and fully validate a Merope file before replacing ``document``."""

    prepared = prepare_content_document(path)
    apply_prepared_content(prepared, document)
    return LoadedContent(
        path=prepared.path,
        metadata=dict(prepared.metadata),
        footnote_definitions=prepared.footnote_definitions,
    )


def prepare_content_document(path: Path) -> PreparedContent:
    """Read and validate one file without mutating any Qt document."""

    path = Path(path)
    metadata, body = read_content_file(path)
    blocks = markdown_to_blocks(body)
    body_blocks, footnote_definitions = separate_footnote_definitions(blocks)
    validate_blocks(body_blocks)
    validate_footnote_definitions(footnote_definitions)
    return PreparedContent(
        path=path,
        metadata=dict(metadata),
        markdown_body=body,
        body_blocks=body_blocks,
        footnote_definitions=footnote_definitions,
    )


def apply_prepared_content(prepared: PreparedContent, document: QTextDocument) -> None:
    """Apply an already validated file model as one clean Qt session body."""

    # Change the resource context only after full validation. An unsupported
    # file therefore leaves both the open document and its base URL intact.
    document.setBaseUrl(document_base_url(prepared.path))
    populate_document(document, prepared.body_blocks)
    document.setModified(False)


def save_content_document(
    path: Path,
    metadata: dict[str, str],
    document: QTextDocument,
    footnote_definitions: FootnoteDefinitions | None = None,
) -> SaveResult:
    """Archive, serialize through Block/Run, and overwrite one Merope file."""

    path = Path(path)
    definitions = footnote_definitions or {}
    validate_footnote_definitions(definitions)
    blocks = extract_blocks(document) + footnote_definition_blocks(definitions)
    markdown_body = blocks_to_markdown(blocks)
    archive = archive_previous_version(path)
    written_path = write_content_file(path.parent, path.name, metadata, markdown_body)
    document.setModified(False)
    return SaveResult(path=written_path, markdown_body=markdown_body, archive=archive)


def document_base_url(path: Path) -> QUrl:
    """Return the local resource base used by a Markdown document."""

    return directory_base_url(Path(path).resolve().parent)


def directory_base_url(path: Path) -> QUrl:
    """Return a local URL whose trailing separator denotes a directory."""

    directory = str(Path(path).resolve()) + os.sep
    return QUrl.fromLocalFile(directory)
