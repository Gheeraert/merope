from __future__ import annotations

from pathlib import Path
import uuid

import pytest

from bloggen.config.defaults import build_default_config
from bloggen.content.loader import ContentLoadError, load_content

RUNTIME_ROOT = Path("tests/.runtime")
RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)


def _build_runtime_config(project: Path):
    config = build_default_config()
    config.paths.project_root = "."
    config.paths.content_dir = "content"
    config.paths.pages_dir = "content/pages"
    config.paths.posts_dir = "content/posts"
    config.home.source = "content/pages/accueil.md"
    return config


def _prepare_project(name: str) -> Path:
    project = RUNTIME_ROOT / f"{name}_{uuid.uuid4().hex}"
    (project / "content/pages").mkdir(parents=True)
    (project / "content/posts").mkdir(parents=True)
    return project


def test_load_content_accepts_valid_page_yaml():
    project = _prepare_project("loader_page")
    (project / "content/pages/accueil.md").write_text(
        '---\ntitle: "Accueil"\nslug: "accueil"\ntype: "page"\n---\n\n# Accueil\n',
        encoding="utf-8",
    )

    loaded = load_content(project, _build_runtime_config(project))

    assert len(loaded.pages) == 1
    item = loaded.pages[0]
    assert item.metadata.title == "Accueil"
    assert item.metadata.slug == "accueil"
    assert item.metadata.kind == "page"


def test_load_content_accepts_valid_post_yaml_with_date():
    project = _prepare_project("loader_post")
    (project / "content/posts/premier.md").write_text(
        '---\ntitle: "Premier"\nslug: "premier-billet"\ntype: "post"\ndate: "2026-04-23"\n---\n\n# Premier\n',
        encoding="utf-8",
    )

    loaded = load_content(project, _build_runtime_config(project))

    assert len(loaded.posts) == 1
    item = loaded.posts[0]
    assert item.metadata.slug == "premier-billet"
    assert item.metadata.date == "2026-04-23"


@pytest.mark.parametrize(
    ("markdown", "expected_message"),
    [
        ("# Sans YAML\n", "Front matter YAML manquant"),
        ('---\nslug: "x"\ntype: "page"\n---\n', "Champ obligatoire manquant: title"),
        ('---\ntitle: "T"\ntype: "page"\n---\n', "Champ obligatoire manquant: slug"),
        ('---\ntitle: "T"\nslug: "t"\n---\n', "Champ obligatoire manquant: type"),
        ('---\ntitle: "T"\nslug: "t"\ntype: "article"\n---\n', "Valeur invalide pour type"),
    ],
)
def test_load_content_rejects_invalid_page_metadata(markdown: str, expected_message: str):
    project = _prepare_project("loader_invalid_page")
    (project / "content/pages/accueil.md").write_text(markdown, encoding="utf-8")

    with pytest.raises(ContentLoadError, match=expected_message):
        load_content(project, _build_runtime_config(project))


@pytest.mark.parametrize(
    ("markdown", "expected_message"),
    [
        (
            '---\ntitle: "P"\nslug: "p"\ntype: "post"\n---\n',
            "Champ obligatoire manquant: date pour un post",
        ),
        (
            '---\ntitle: "P"\nslug: "p"\ntype: "post"\ndate: "2026/04/23"\n---\n',
            "Date invalide",
        ),
    ],
)
def test_load_content_rejects_invalid_post_metadata(markdown: str, expected_message: str):
    project = _prepare_project("loader_invalid_post")
    (project / "content/posts/premier.md").write_text(markdown, encoding="utf-8")

    with pytest.raises(ContentLoadError, match=expected_message):
        load_content(project, _build_runtime_config(project))


def test_load_content_skips_draft_items():
    project = _prepare_project("loader_draft")
    (project / "content/posts/published.md").write_text(
        '---\ntitle: "Publie"\nslug: "publie"\ntype: "post"\ndate: "2026-04-23"\n---\n\n# Publie\n',
        encoding="utf-8",
    )
    (project / "content/posts/draft.md").write_text(
        '---\ntitle: "Draft"\nslug: "draft"\ntype: "post"\ndate: "2026-04-24"\ndraft: true\n---\n\n# Draft\n',
        encoding="utf-8",
    )

    loaded = load_content(project, _build_runtime_config(project))

    assert [item.metadata.slug for item in loaded.posts] == ["publie"]
    assert any("Brouillon ignoré" in warning for warning in loaded.warnings)
