"""bloggen.ui.editor_recovery: the autosave/crash-recovery draft file —
pure I/O, no Tk widget involved."""

from __future__ import annotations

from pathlib import Path
import uuid

import pytest

import bloggen.content.atomic_write as atomic_write_module
from bloggen.ui.editor_recovery import (
    RecoveryDraft,
    clear_draft,
    load_draft,
    recovery_file_path,
    save_draft,
)

RUNTIME_ROOT = Path("tests/.runtime")
RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)


def _project() -> Path:
    project = RUNTIME_ROOT / f"editor_recovery_{uuid.uuid4().hex}"
    project.mkdir(parents=True)
    return project


def test_load_draft_returns_none_when_no_file_exists():
    assert load_draft(_project()) is None


def test_save_and_load_round_trip():
    project = _project()
    draft = RecoveryDraft(
        current_path="content/posts/2026-04-23-mon-billet.md",
        current_kind="post",
        metadata={"title": "Mon billet", "slug": "mon-billet", "type": "post", "date": "2026-04-23"},
        body_markdown="# Mon billet\n\nTexte en cours de rédaction.\n",
    )
    save_draft(project, draft)

    loaded = load_draft(project)
    assert loaded == draft
    assert list(recovery_file_path(project).parent.glob(".draft.json.tmp-*")) == []


def test_save_creates_the_recovery_directory():
    project = _project()
    save_draft(project, RecoveryDraft(current_path=None, current_kind="page", metadata={}, body_markdown=""))
    assert recovery_file_path(project).exists()


def test_a_new_or_imported_documents_draft_has_no_current_path():
    project = _project()
    draft = RecoveryDraft(current_path=None, current_kind="page", metadata={"title": "Sans fichier"}, body_markdown="Texte.")
    save_draft(project, draft)
    assert load_draft(project).current_path is None


def test_clear_draft_removes_the_file():
    project = _project()
    save_draft(project, RecoveryDraft(current_path=None, current_kind="page", metadata={}, body_markdown="x"))
    assert recovery_file_path(project).exists()

    clear_draft(project)

    assert not recovery_file_path(project).exists()
    assert load_draft(project) is None


def test_clear_draft_is_a_no_op_when_nothing_exists():
    clear_draft(_project())  # must not raise


def test_load_draft_returns_none_for_malformed_json():
    project = _project()
    path = recovery_file_path(project)
    path.parent.mkdir(parents=True)
    path.write_text("not json at all", encoding="utf-8")
    assert load_draft(project) is None


def test_load_draft_tolerates_a_non_object_json_payload():
    project = _project()
    path = recovery_file_path(project)
    path.parent.mkdir(parents=True)
    path.write_text("[1, 2, 3]", encoding="utf-8")
    assert load_draft(project) is None


def test_load_draft_tolerates_missing_fields():
    project = _project()
    path = recovery_file_path(project)
    path.parent.mkdir(parents=True)
    path.write_text("{}", encoding="utf-8")

    draft = load_draft(project)

    assert draft.current_path is None
    assert draft.current_kind is None
    assert draft.metadata == {}
    assert draft.body_markdown == ""


def test_save_overwrites_a_previous_draft():
    project = _project()
    save_draft(
        project,
        RecoveryDraft(current_path=None, current_kind="page", metadata={"title": "Premier"}, body_markdown="A"),
    )
    save_draft(
        project,
        RecoveryDraft(current_path=None, current_kind="page", metadata={"title": "Second"}, body_markdown="B"),
    )

    loaded = load_draft(project)
    assert loaded.metadata == {"title": "Second"}
    assert loaded.body_markdown == "B"


def test_failed_recovery_replace_preserves_previous_valid_draft(monkeypatch):
    project = _project()
    old = RecoveryDraft(
        current_path="content/pages/ancien.md",
        current_kind="page",
        metadata={"title": "Ancien"},
        body_markdown="Corps ancien.",
    )
    new = RecoveryDraft(
        current_path="content/pages/nouveau.md",
        current_kind="page",
        metadata={"title": "Nouveau"},
        body_markdown="Corps nouveau.",
    )
    save_draft(project, old)

    def fail_replace(_source, _target):
        raise OSError("replace failure")

    monkeypatch.setattr(atomic_write_module.os, "replace", fail_replace)

    with pytest.raises(OSError, match="replace failure"):
        save_draft(project, new)

    assert load_draft(project) == old
    path = recovery_file_path(project)
    assert list(path.parent.glob(".draft.json.tmp-*")) == []


def test_failed_first_recovery_write_leaves_no_partial_draft(monkeypatch):
    project = _project()
    draft = RecoveryDraft(
        current_path=None,
        current_kind="page",
        metadata={"title": "Nouveau"},
        body_markdown="Corps.",
    )

    def fail_replace(_source, _target):
        raise OSError("replace failure")

    monkeypatch.setattr(atomic_write_module.os, "replace", fail_replace)

    with pytest.raises(OSError, match="replace failure"):
        save_draft(project, draft)

    path = recovery_file_path(project)
    assert not path.exists()
    assert list(path.parent.glob(".draft.json.tmp-*")) == []
