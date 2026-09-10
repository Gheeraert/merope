from __future__ import annotations

from bloggen.content.versioning import (
    archive_previous_version,
    convert_content_file,
    list_versions,
    purge_versions,
    versions_to_purge,
)
from bloggen.content.writer import read_content_file, write_content_file


def test_list_versions_sorts_numbers_and_ignores_malformed_names(tmp_path):
    path = tmp_path / "article.md"
    versions_dir = tmp_path / ".versions"
    versions_dir.mkdir()
    for name in ("article.v10.md", "article.v2.md", "article.vx.md", "other.v1.md"):
        (versions_dir / name).write_text(name, encoding="utf-8")

    result = list_versions(path)

    assert [(number, item.name) for number, item in result] == [
        (2, "article.v2.md"),
        (10, "article.v10.md"),
    ]


def test_archive_previous_version_is_noop_for_new_document(tmp_path):
    result = archive_previous_version(tmp_path / "new.md")

    assert result.archived_path is None
    assert result.versions == ()
    assert result.should_offer_purge is False


def test_archive_previous_version_copies_bytes_and_reports_prompt_interval(tmp_path):
    path = tmp_path / "article.md"
    path.write_bytes(b"version one")

    first = archive_previous_version(path, prompt_interval=2)
    path.write_bytes(b"version two")
    second = archive_previous_version(path, prompt_interval=2)

    assert first.archived_path.read_bytes() == b"version one"
    assert first.should_offer_purge is False
    assert second.archived_path.name == "article.v2.md"
    assert second.archived_path.read_bytes() == b"version two"
    assert second.should_offer_purge is True
    assert [number for number, _path in second.versions] == [1, 2]


def test_purge_selection_is_computed_before_explicit_deletion(tmp_path):
    versions = []
    for number in range(1, 6):
        path = tmp_path / f"article.v{number}.md"
        path.write_text(str(number), encoding="utf-8")
        versions.append((number, path))

    selected = versions_to_purge(versions, keep=3)

    assert [number for number, _path in selected] == [1, 2]
    assert all(path.exists() for _number, path in versions)

    purge_versions(selected)

    assert not versions[0][1].exists()
    assert not versions[1][1].exists()
    assert all(path.exists() for _number, path in versions[2:])


def test_convert_page_to_post_preserves_body_and_removes_source(tmp_path):
    pages_dir = tmp_path / "pages"
    posts_dir = tmp_path / "posts"
    source = write_content_file(
        pages_dir,
        "article.md",
        {"title": "Article", "slug": "article", "type": "page"},
        "Texte **riche**.\n",
    )
    _source_metadata, source_body = read_content_file(source)

    result = convert_content_file(
        source,
        new_kind="post",
        target_dir=posts_dir,
        date_value="2026-09-10",
    )

    assert result.path == posts_dir / "2026-09-10-article.md"
    assert not source.exists()
    metadata, body = read_content_file(result.path)
    assert metadata == {
        "title": "Article",
        "slug": "article",
        "type": "post",
        "date": "2026-09-10",
    }
    # write_content_file historically inserts its own separator before the
    # already-parsed body; conversion preserves the body content under that
    # existing front-matter whitespace convention.
    assert result.body == source_body
    assert body.lstrip("\n") == source_body.lstrip("\n")


def test_convert_post_to_page_removes_date(tmp_path):
    posts_dir = tmp_path / "posts"
    pages_dir = tmp_path / "pages"
    source = write_content_file(
        posts_dir,
        "2026-09-10-article.md",
        {
            "title": "Article",
            "slug": "article",
            "type": "post",
            "date": "2026-09-10",
        },
        "Corps.\n",
    )
    _source_metadata, source_body = read_content_file(source)

    result = convert_content_file(source, new_kind="page", target_dir=pages_dir)

    metadata, body = read_content_file(result.path)
    assert result.path == pages_dir / "article.md"
    assert "date" not in metadata
    assert metadata["type"] == "page"
    assert result.body == source_body
    assert body.lstrip("\n") == source_body.lstrip("\n")
