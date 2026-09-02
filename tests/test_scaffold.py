from pathlib import Path

import pytest

from bloggen.build.site_builder import build_site, resolve_project_root
from bloggen.config.io import load_config, save_config
from bloggen.config.defaults import build_default_config
from bloggen.config.scaffold import create_new_project
from bloggen.content.loader import load_content


def test_create_new_project_lays_out_expected_directories(tmp_path: Path):
    config_path = create_new_project(tmp_path)

    assert config_path == tmp_path / "config" / "site.json"
    for relative in (
        "content/pages",
        "content/posts",
        "assets/images",
        "assets/banner",
        "theme/templates",
        "theme/xslt",
    ):
        assert (tmp_path / relative).is_dir()

    pages = list((tmp_path / "content" / "pages").glob("*.md"))
    posts = list((tmp_path / "content" / "posts").glob("*.md"))
    assert len(pages) == 1
    assert len(posts) == 1


def test_scaffolded_config_is_valid_and_loadable(tmp_path: Path):
    config_path = create_new_project(tmp_path)
    config = load_config(config_path)  # raises ConfigValidationError if invalid

    assert config.home.source == "content/pages/bienvenue.md"
    assert config.paths.project_root == "."


def test_scaffolded_content_loads_without_warnings_or_errors(tmp_path: Path):
    config_path = create_new_project(tmp_path)
    config = load_config(config_path)
    project_root = resolve_project_root(config, config_path)

    loaded = load_content(project_root, config)

    assert loaded.warnings == []
    assert [p.metadata.slug for p in loaded.pages] == ["bienvenue"]
    assert [p.metadata.slug for p in loaded.posts] == ["premier-billet"]


def test_page_and_post_slugs_do_not_collide_in_the_shared_namespace(tmp_path: Path):
    # content/loader.py enforces slug uniqueness across pages AND posts
    # together; a real collision would silently rename the post's slug.
    config_path = create_new_project(tmp_path)
    config = load_config(config_path)
    project_root = resolve_project_root(config, config_path)

    loaded = load_content(project_root, config)
    page_slug = loaded.pages[0].metadata.slug
    post_slug = loaded.posts[0].metadata.slug
    assert page_slug != post_slug


def test_scaffolded_project_builds_successfully(tmp_path: Path):
    config_path = create_new_project(tmp_path)
    config = load_config(config_path)

    report = build_site(config, config_path=config_path)

    assert report.success is True
    assert report.errors == []
    assert (tmp_path / "site" / "index.html").exists()
    assert (tmp_path / "site" / "bienvenue" / "index.html").exists()
    assert (tmp_path / "site" / "billets" / "premier-billet" / "index.html").exists()


def test_resolve_project_root_never_falls_back_to_cwd_once_config_path_is_known(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """A loaded/saved config always anchors the project root to its own
    location on disk, even before content/pages exists there yet — it must
    never wander off to wherever the app process happens to be launched
    from, even if that directory coincidentally has a content/pages/ of its
    own (e.g. a stray leftover from an earlier run of the app itself)."""
    real_project = tmp_path / "real_project"
    real_project.mkdir()
    config_path = real_project / "config" / "site.json"
    config_path.parent.mkdir()
    config = build_default_config()
    config.paths.project_root = "."
    save_config(config, config_path)

    decoy_cwd = tmp_path / "decoy_cwd"
    (decoy_cwd / "content" / "pages").mkdir(parents=True)
    monkeypatch.chdir(decoy_cwd)

    project_root = resolve_project_root(config, config_path)

    assert project_root == real_project.resolve()
