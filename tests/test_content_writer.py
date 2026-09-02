from pathlib import Path

import pytest

from bloggen.content.writer import (
    default_filename,
    list_content_targets,
    read_content_file,
    scan_existing_slugs,
    suggest_slug,
    write_content_file,
)


def test_suggest_slug_is_unique_and_does_not_mutate_existing(tmp_path):
    existing = {"premier-billet"}
    slug = suggest_slug("Premier billet", existing=existing)
    assert slug == "premier-billet-2"
    assert existing == {"premier-billet"}  # not mutated


def test_default_filename_conventions():
    assert default_filename("page", "accueil") == "accueil.md"
    assert default_filename("post", "hello", date="2026-08-08") == "2026-08-08-hello.md"


def test_default_filename_post_requires_date():
    with pytest.raises(ValueError):
        default_filename("post", "hello")


def test_write_and_read_content_file_roundtrip(tmp_path: Path):
    metadata = {"title": "Mon billet", "slug": "mon-billet", "type": "post", "date": "2026-08-08"}
    path = write_content_file(tmp_path, "2026-08-08-mon-billet.md", metadata, "# Titre\n\nCorps.\n")

    assert path.exists()
    read_metadata, body = read_content_file(path)
    assert read_metadata == metadata
    assert body == "\n# Titre\n\nCorps.\n"


def test_scan_existing_slugs_collects_across_pages_and_posts(tmp_path: Path):
    pages = tmp_path / "pages"
    posts = tmp_path / "posts"
    write_content_file(pages, "accueil.md", {"title": "Accueil", "slug": "accueil", "type": "page"}, "Corps\n")
    write_content_file(
        posts,
        "2026-08-08-billet.md",
        {"title": "Billet", "slug": "un-billet", "type": "post", "date": "2026-08-08"},
        "Corps\n",
    )

    assert scan_existing_slugs(pages, posts) == {"accueil", "un-billet"}


def test_scan_existing_slugs_tolerates_broken_files(tmp_path: Path):
    pages = tmp_path / "pages"
    posts = tmp_path / "posts"
    pages.mkdir(parents=True)
    (pages / "broken.md").write_text("---\nno closing delimiter\n", encoding="utf-8")
    write_content_file(pages, "ok.md", {"title": "Ok", "slug": "ok", "type": "page"}, "Corps\n")

    assert scan_existing_slugs(pages, posts) == {"ok"}


def test_scan_existing_slugs_ignores_versions_folder(tmp_path: Path):
    pages = tmp_path / "pages"
    posts = tmp_path / "posts"
    write_content_file(pages, "accueil.md", {"title": "Accueil", "slug": "accueil", "type": "page"}, "Corps\n")
    write_content_file(
        pages / ".versions",
        "accueil.v1.md",
        {"title": "Accueil", "slug": "accueil-ancien", "type": "page"},
        "Ancien corps\n",
    )

    assert scan_existing_slugs(pages, posts) == {"accueil"}


def test_list_content_targets_includes_home_and_archive_by_default(tmp_path: Path):
    pages = tmp_path / "pages"
    posts = tmp_path / "posts"
    targets = list_content_targets(pages, posts)
    assert ("Accueil (page d'accueil du site)", "/index.html") in targets
    assert ("Archive des billets", "/billets/index.html") in targets


def test_list_content_targets_lists_pages_and_posts_with_correct_urls(tmp_path: Path):
    pages = tmp_path / "pages"
    posts = tmp_path / "posts"
    write_content_file(pages, "accueil.md", {"title": "Accueil", "slug": "accueil", "type": "page"}, "Corps\n")
    write_content_file(
        posts,
        "2026-08-08-billet.md",
        {"title": "Mon billet", "slug": "mon-billet", "type": "post", "date": "2026-08-08"},
        "Corps\n",
    )

    targets = list_content_targets(pages, posts, archive_path="billets")
    assert ("Accueil (page)", "/accueil/index.html") in targets
    assert ("Mon billet (billet)", "/billets/mon-billet/index.html") in targets


def test_list_content_targets_respects_custom_archive_path(tmp_path: Path):
    posts = tmp_path / "posts"
    write_content_file(
        posts,
        "2026-08-08-billet.md",
        {"title": "Billet", "slug": "un-billet", "type": "post", "date": "2026-08-08"},
        "Corps\n",
    )

    targets = list_content_targets(tmp_path / "pages", posts, archive_path="/journal/")
    assert ("Billet (billet)", "/journal/un-billet/index.html") in targets
    assert ("Archive des billets", "/journal/index.html") in targets


def test_list_content_targets_tolerates_broken_files(tmp_path: Path):
    pages = tmp_path / "pages"
    posts = tmp_path / "posts"
    pages.mkdir(parents=True)
    (pages / "broken.md").write_text("---\nno closing delimiter\n", encoding="utf-8")

    targets = list_content_targets(pages, posts)
    assert all("broken" not in label for label, _url in targets)
