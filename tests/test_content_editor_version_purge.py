"""``.versions`` previously grew by one file per save, forever, for the
life of a document — a page/post edited hundreds of times over months
left hundreds of small but never-cleaned-up files behind it. Each save
now prunes the oldest archived versions beyond a fixed cap.
"""

from __future__ import annotations

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


def test_old_versions_beyond_the_cap_are_pruned_on_each_save(editor, tmp_path):
    path = tmp_path / "content" / "pages" / "exemple.md"
    path.write_text("contenu initial", encoding="utf-8")
    versions_dir = path.parent / ".versions"
    cap = content_editor_module._MAX_VERSIONS_PER_DOCUMENT

    # One more save than the cap allows: the very first on-disk version
    # (v1) must be the one pruned away, since it's the oldest.
    for i in range(cap + 1):
        path.write_text(f"contenu {i}", encoding="utf-8")
        editor._archive_previous_version(path)

    archived = sorted(versions_dir.glob("exemple.v*.md"))
    assert len(archived) == cap
    assert versions_dir / "exemple.v1.md" not in set(archived)
    # The most recent versions (v2..v{cap+1}) must all still be present.
    numbers = sorted(int(p.stem.rsplit("v", 1)[1]) for p in archived)
    assert numbers == list(range(2, cap + 2))


def test_version_count_never_exceeds_the_cap_across_many_more_saves(editor, tmp_path):
    path = tmp_path / "content" / "pages" / "exemple.md"
    path.write_text("contenu initial", encoding="utf-8")
    versions_dir = path.parent / ".versions"
    cap = content_editor_module._MAX_VERSIONS_PER_DOCUMENT

    for i in range(cap * 3):
        path.write_text(f"contenu {i}", encoding="utf-8")
        editor._archive_previous_version(path)
        assert len(list(versions_dir.glob("exemple.v*.md"))) <= cap
