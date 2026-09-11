"""Canonical crash-recovery conversion for the standalone Qt editor."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtGui import QTextDocument

from bloggen.content.footnotes import (
    FootnoteDefinitions,
    footnote_definition_blocks,
    separate_footnote_definitions,
)
from bloggen.markdown.rich_text_export import blocks_to_markdown
from bloggen.markdown.rich_text_import import markdown_to_blocks
from bloggen.markdown.rich_text_model import Block
from bloggen.ui.editor_recovery import RecoveryDraft
from bloggen.ui.qt_editor.document_adapter import (
    extract_blocks,
    validate_blocks,
    validate_footnote_definitions,
)


AUTOSAVE_INTERVAL_MS = 30_000


@dataclass(frozen=True, slots=True)
class PreparedRecoveryDraft:
    """A fully parsed draft that is safe to apply to the Qt session."""

    body_blocks: list[Block]
    footnote_definitions: FootnoteDefinitions
    metadata: dict[str, str]
    current_path: Path | None
    current_kind: str | None
    resource_directory: Path


def build_recovery_draft(
    document: QTextDocument,
    footnote_definitions: FootnoteDefinitions,
    metadata: dict[str, str],
    *,
    project_root: Path,
    current_path: Path | None,
    current_kind: str | None,
) -> RecoveryDraft:
    """Serialize the complete session only through the canonical model."""

    validate_footnote_definitions(footnote_definitions)
    all_blocks = extract_blocks(document) + footnote_definition_blocks(
        footnote_definitions
    )
    return RecoveryDraft(
        current_path=project_relative_path(project_root, current_path),
        current_kind=current_kind,
        metadata=dict(metadata),
        body_markdown=blocks_to_markdown(all_blocks),
    )


def prepare_recovery_draft(
    project_root: Path,
    draft: RecoveryDraft,
) -> PreparedRecoveryDraft:
    """Parse and validate a draft completely before any widget is mutated."""

    blocks = markdown_to_blocks(draft.body_markdown)
    body_blocks, definitions = separate_footnote_definitions(blocks)
    validate_blocks(body_blocks)
    validate_footnote_definitions(definitions)
    current_path, resource_directory = resolve_recovery_path(
        project_root,
        draft.current_path,
    )
    return PreparedRecoveryDraft(
        body_blocks=body_blocks,
        footnote_definitions=definitions,
        metadata=dict(draft.metadata),
        current_path=current_path,
        current_kind=draft.current_kind,
        resource_directory=resource_directory,
    )


def project_relative_path(
    project_root: Path,
    current_path: Path | None,
) -> str | None:
    """Return a safe project-relative POSIX path, never an absolute path."""

    if current_path is None:
        return None
    try:
        root = Path(project_root).resolve()
        return Path(current_path).resolve().relative_to(root).as_posix()
    except (OSError, RuntimeError, ValueError):
        return None


def resolve_recovery_path(
    project_root: Path,
    stored_path: str | None,
) -> tuple[Path | None, Path]:
    """Resolve a draft path without ever escaping ``project_root``.

    The resource directory remains useful for relative image rendering when
    the original Markdown file disappeared, while ``current_path`` becomes
    ``None`` so recovery never recreates that file implicitly.
    """

    root = Path(project_root).resolve()
    if not stored_path:
        return None, root
    source = Path(stored_path)
    if source.is_absolute():
        return None, root
    try:
        candidate = (root / source).resolve()
        candidate.relative_to(root)
    except (OSError, RuntimeError, ValueError):
        return None, root
    return (candidate if candidate.is_file() else None), candidate.parent
