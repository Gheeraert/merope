"""Autosave / crash-recovery for the content editor's single
in-progress document.

MEROPE has no server and no undo-log of its own beyond the running
process — until now, a crash (or the process being killed) with unsaved
work in the editor meant that work was simply gone, with no recourse.
This periodically persists the not-yet-saved draft to a small JSON file
under the project, and the editor offers to restore it the next time it
opens if one is found.

Kept independent of Tk (pure dataclass + JSON I/O) so it's testable
without a live widget; ``content_editor.autosave`` owns the timer and the
restore/discard prompt.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from bloggen.content.atomic_write import atomic_write_text


@dataclass(slots=True)
class RecoveryDraft:
    # Project-relative, POSIX-style path of the file this draft came
    # from, or None for a brand new / imported document that was never
    # saved under the project at all.
    current_path: str | None
    current_kind: str | None
    metadata: dict[str, str]
    body_markdown: str


def recovery_file_path(project_root: Path) -> Path:
    return project_root / ".merope-recovery" / "draft.json"


def save_draft(project_root: Path, draft: RecoveryDraft) -> None:
    path = recovery_file_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "current_path": draft.current_path,
        "current_kind": draft.current_kind,
        "metadata": draft.metadata,
        "body_markdown": draft.body_markdown,
    }
    atomic_write_text(
        path,
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def load_draft(project_root: Path) -> RecoveryDraft | None:
    path = recovery_file_path(project_root)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None

    metadata = data.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}

    current_path = data.get("current_path")
    current_kind = data.get("current_kind")
    return RecoveryDraft(
        current_path=str(current_path) if isinstance(current_path, str) else None,
        current_kind=str(current_kind) if isinstance(current_kind, str) else None,
        metadata={str(key): str(value) for key, value in metadata.items()},
        body_markdown=str(data.get("body_markdown") or ""),
    )


def clear_draft(project_root: Path) -> None:
    path = recovery_file_path(project_root)
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass
