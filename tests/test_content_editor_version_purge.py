""".versions grows by one file per save, for the life of a document. It
used to be pruned automatically and silently. Purging is now optional:
every _VERSION_PURGE_PROMPT_INTERVAL saves, the user is asked whether to
prune the oldest versions down to the cap, and declining keeps every
version archived — never automatic.
"""

from __future__ import annotations

from tkinter import messagebox

import pytest

from bloggen.ui import content_editor as content_editor_module
from bloggen.ui.content_editor import ContentEditorWindow


@pytest.fixture
def editor(tk_root, tmp_path):
    pages_dir = tmp_path / "content" / "pages"
    posts_dir = tmp_path / "content" / "posts"
    images_dir = tmp_path / "assets" / "images"
    pages_dir.mkdir(parents=True)
    posts_dir.mkdir(parents=True)

    window = ContentEditorWindow(
        tk_root, pages_dir=pages_dir, posts_dir=posts_dir, images_dir=images_dir, slugify_mode="ascii"
    )
    yield window
    window.destroy()


def _save_n_versions(editor, path, count):
    for i in range(count):
        path.write_text(f"contenu {i}", encoding="utf-8")
        editor._archive_previous_version(path)


def test_no_prompt_and_no_pruning_before_the_first_interval(editor, tmp_path, monkeypatch):
    path = tmp_path / "content" / "pages" / "exemple.md"
    path.write_text("contenu initial", encoding="utf-8")
    versions_dir = path.parent / ".versions"
    interval = content_editor_module._VERSION_PURGE_PROMPT_INTERVAL

    prompted = []
    monkeypatch.setattr(messagebox, "askyesno", lambda *a, **k: prompted.append(1) or False)

    _save_n_versions(editor, path, interval - 1)

    assert not prompted
    assert len(list(versions_dir.glob("exemple.v*.md"))) == interval - 1


def test_prompt_fires_at_the_interval_and_declining_keeps_every_version(editor, tmp_path, monkeypatch):
    path = tmp_path / "content" / "pages" / "exemple.md"
    path.write_text("contenu initial", encoding="utf-8")
    versions_dir = path.parent / ".versions"
    interval = content_editor_module._VERSION_PURGE_PROMPT_INTERVAL

    prompted = []
    monkeypatch.setattr(messagebox, "askyesno", lambda *a, **k: prompted.append(1) or False)

    _save_n_versions(editor, path, interval)

    assert len(prompted) == 1
    assert len(list(versions_dir.glob("exemple.v*.md"))) == interval


def test_accepting_the_prompt_prunes_down_to_the_cap(editor, tmp_path, monkeypatch):
    path = tmp_path / "content" / "pages" / "exemple.md"
    path.write_text("contenu initial", encoding="utf-8")
    versions_dir = path.parent / ".versions"
    interval = content_editor_module._VERSION_PURGE_PROMPT_INTERVAL
    cap = content_editor_module._MAX_VERSIONS_PER_DOCUMENT

    monkeypatch.setattr(messagebox, "askyesno", lambda *a, **k: True)

    _save_n_versions(editor, path, interval)

    archived = sorted(versions_dir.glob("exemple.v*.md"))
    assert len(archived) == cap
    # The most recent versions are the ones kept, the oldest pruned away.
    numbers = sorted(int(p.stem.rsplit("v", 1)[1]) for p in archived)
    assert numbers == list(range(interval - cap + 1, interval + 1))


def test_declining_repeatedly_lets_versions_grow_past_the_cap_indefinitely(editor, tmp_path, monkeypatch):
    path = tmp_path / "content" / "pages" / "exemple.md"
    path.write_text("contenu initial", encoding="utf-8")
    versions_dir = path.parent / ".versions"
    interval = content_editor_module._VERSION_PURGE_PROMPT_INTERVAL

    monkeypatch.setattr(messagebox, "askyesno", lambda *a, **k: False)

    _save_n_versions(editor, path, interval * 3)

    assert len(list(versions_dir.glob("exemple.v*.md"))) == interval * 3


def test_no_prompt_when_declining_left_the_count_at_or_below_the_cap(editor, tmp_path, monkeypatch):
    """If the interval falls at or below the cap, there is nothing to
    prune, so the user should not be bothered with a prompt."""
    path = tmp_path / "content" / "pages" / "exemple.md"
    path.write_text("contenu initial", encoding="utf-8")
    cap = content_editor_module._MAX_VERSIONS_PER_DOCUMENT

    monkeypatch.setattr(content_editor_module.file_ops, "_VERSION_PURGE_PROMPT_INTERVAL", cap)
    prompted = []
    monkeypatch.setattr(messagebox, "askyesno", lambda *a, **k: prompted.append(1) or False)

    _save_n_versions(editor, path, cap)

    assert not prompted
