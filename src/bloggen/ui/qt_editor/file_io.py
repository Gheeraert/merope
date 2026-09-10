"""Safe file orchestration for the standalone Qt editor prototype."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtGui import QTextDocument

from bloggen.content.versioning import ArchiveResult, archive_previous_version
from bloggen.content.writer import read_content_file, write_content_file
from bloggen.markdown.rich_text_export import blocks_to_markdown
from bloggen.markdown.rich_text_import import markdown_to_blocks
from bloggen.ui.qt_editor.document_adapter import extract_blocks, populate_document


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
    # populate_document validates every block before clearing the current Qt
    # document, so an unsupported file leaves the open document untouched.
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

