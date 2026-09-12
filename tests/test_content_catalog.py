from __future__ import annotations

from pathlib import Path

import pytest

from bloggen.content.catalog import (
    determine_content_kind,
    scan_content_catalog,
    validate_editor_metadata,
)
from bloggen.content.writer import write_content_file


def test_scan_catalog_includes_nested_and_invalid_but_ignores_versions(tmp_path):
    pages = tmp_path / "content" / "pages"
    posts = tmp_path / "content" / "posts"
    write_content_file(
        pages / "section", "page.md", {"title": "Une page", "slug": "page"}, ""
    )
    invalid = posts / "cassé.md"
    invalid.parent.mkdir(parents=True)
    invalid.write_text("---\ntitle: cassé", encoding="utf-8")
    write_content_file(
        pages / ".versions", "page.v1.md", {"title": "Archive"}, ""
    )

    entries = scan_content_catalog(pages, posts)

    assert [(entry.kind, entry.title, entry.valid) for entry in entries] == [
        ("page", "Une page", True),
        ("post", "(invalide) cassé.md", False),
    ]


def test_determine_kind_uses_location_and_rejects_contradiction(tmp_path):
    pages = tmp_path / "pages"
    posts = tmp_path / "posts"
    path = pages / "nested" / "article.md"

    assert determine_content_kind(path, {}, pages_dir=pages, posts_dir=posts) == "page"
    assert (
        determine_content_kind(
            tmp_path / "external.md",
            {"type": "post"},
            pages_dir=None,
            posts_dir=None,
        )
        == "post"
    )
    with pytest.raises(ValueError, match="contredit"):
        determine_content_kind(
            path,
            {"type": "post"},
            pages_dir=pages,
            posts_dir=posts,
        )


def test_metadata_validation_preserves_unknown_fields_and_normalizes_known():
    result = validate_editor_metadata(
        {
            "title": "  Bossuet  ",
            "slug": "bossuet",
            "type": "page",
            "date": "2026-01-01",
            "orcid": "https://orcid.org/0000-0002-1825-0097",
            "draft": "false",
            "custom-field": " valeur intacte ",
            "bibliography": "refs.json",
        },
        "page",
    )

    assert result["title"] == "Bossuet"
    assert result["orcid"] == "0000-0002-1825-0097"
    assert "date" not in result
    assert "draft" not in result
    assert result["custom-field"] == " valeur intacte "
    assert result["bibliography"] == "refs.json"


@pytest.mark.parametrize(
    ("metadata", "message"),
    [
        ({"slug": "ok"}, "titre"),
        ({"title": "Titre"}, "slug"),
        ({"title": "Titre", "slug": "Pas Bon"}, "slug"),
        ({"title": "Titre", "slug": "ok", "type": "post"}, "contredit"),
        ({"title": "Titre", "slug": "ok", "updated": "hier"}, "mise à jour"),
        ({"title": "Titre", "slug": "ok", "orcid": "123"}, "ORCID"),
    ],
)
def test_metadata_validation_rejects_invalid_values(metadata, message):
    with pytest.raises(ValueError, match=message):
        validate_editor_metadata(metadata, "page")


def test_post_date_and_slug_collision_are_validated():
    metadata = {"title": "Titre", "slug": "pris", "type": "post", "date": "2026-13-40"}
    with pytest.raises(ValueError, match="déjà utilisé"):
        validate_editor_metadata(metadata, "post", existing_slugs={"pris"})
    with pytest.raises(ValueError, match="AAAA-MM-JJ"):
        validate_editor_metadata(metadata, "post", existing_slugs={"pris"}, own_slug="pris")

