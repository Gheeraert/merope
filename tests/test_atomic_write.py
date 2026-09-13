from __future__ import annotations

import os
from pathlib import Path

import pytest

import bloggen.content.atomic_write as atomic_write_module
from bloggen.content.atomic_write import atomic_write_text


def _temporary_files_for(path: Path) -> list[Path]:
    return list(path.parent.glob(f".{path.name}.tmp-*"))


def test_atomic_write_replaces_existing_target_without_residue(tmp_path):
    target = tmp_path / "article.md"
    target.write_text("ANCIEN", encoding="utf-8")

    atomic_write_text(target, "NOUVEAU\nCOMPLET")

    assert target.read_text(encoding="utf-8") == "NOUVEAU\nCOMPLET"
    assert _temporary_files_for(target) == []


def test_atomic_write_fsync_failure_preserves_existing_target(tmp_path, monkeypatch):
    target = tmp_path / "article.md"
    target.write_text("ANCIEN", encoding="utf-8")

    def fail_fsync(_descriptor):
        raise OSError("fsync failure")

    monkeypatch.setattr(atomic_write_module.os, "fsync", fail_fsync)

    with pytest.raises(OSError, match="fsync failure"):
        atomic_write_text(target, "NOUVEAU")

    assert target.read_text(encoding="utf-8") == "ANCIEN"
    assert _temporary_files_for(target) == []


def test_atomic_write_replace_failure_preserves_existing_target(tmp_path, monkeypatch):
    target = tmp_path / "article.md"
    target.write_text("ANCIEN", encoding="utf-8")

    def fail_replace(_source, _target):
        raise OSError("replace failure")

    monkeypatch.setattr(atomic_write_module.os, "replace", fail_replace)

    with pytest.raises(OSError, match="replace failure"):
        atomic_write_text(target, "NOUVEAU")

    assert target.read_text(encoding="utf-8") == "ANCIEN"
    assert _temporary_files_for(target) == []


def test_atomic_write_failure_does_not_create_partial_new_target(tmp_path, monkeypatch):
    target = tmp_path / "nouveau.md"

    def fail_replace(_source, _target):
        raise OSError("replace failure")

    monkeypatch.setattr(atomic_write_module.os, "replace", fail_replace)

    with pytest.raises(OSError, match="replace failure"):
        atomic_write_text(target, "NOUVEAU")

    assert not target.exists()
    assert _temporary_files_for(target) == []


def test_atomic_write_flushes_and_fsyncs_before_closed_file_is_replaced(
    tmp_path,
    monkeypatch,
):
    target = tmp_path / "article.md"
    content = "Texte complètement écrit."
    events: list[str] = []
    synced_descriptor: int | None = None
    real_fsync = atomic_write_module.os.fsync
    real_replace = atomic_write_module.os.replace

    def observe_fsync(descriptor):
        nonlocal synced_descriptor
        temporary_files = _temporary_files_for(target)
        assert len(temporary_files) == 1
        assert temporary_files[0].read_text(encoding="utf-8") == content
        synced_descriptor = descriptor
        events.append("fsync")
        real_fsync(descriptor)

    def observe_replace(source, destination):
        assert synced_descriptor is not None
        with pytest.raises(OSError):
            os.fstat(synced_descriptor)
        events.append("replace")
        real_replace(source, destination)

    monkeypatch.setattr(atomic_write_module.os, "fsync", observe_fsync)
    monkeypatch.setattr(atomic_write_module.os, "replace", observe_replace)

    atomic_write_text(target, content)

    assert events == ["fsync", "replace"]
    assert target.read_text(encoding="utf-8") == content
    assert _temporary_files_for(target) == []
