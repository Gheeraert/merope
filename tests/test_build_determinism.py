"""The footer's "last updated" date previously embedded the wall-clock
time of the current build run (datetime.now()) — every single build then
produced different output even when nothing in the content had actually
changed, defeating any attempt to diff or verify two builds of the same
source as identical. It now reflects the most recent content lastmod
across the whole site instead (see site_builder._compute_site_last_updated).
"""

from __future__ import annotations

import datetime
import os
from pathlib import Path
import uuid

from bloggen.build.site_builder import build_site
from bloggen.config.defaults import build_default_config
from bloggen.tei.pandoc_converter import MarkdownToTeiResult
from bloggen.tei.validator import TeiValidationResult

RUNTIME_ROOT = Path("tests/.runtime")
RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)

TEI_SAMPLE = (
    '<TEI xmlns="http://www.tei-c.org/ns/1.0">'
    '<teiHeader><fileDesc><titleStmt><title>Test</title></titleStmt>'
    '<publicationStmt><p>p</p></publicationStmt><sourceDesc><p>s</p></sourceDesc></fileDesc></teiHeader>'
    '<text><body><div><head>Titre</head><p>Contenu.</p></div></body></text>'
    '</TEI>'
)


def _fake_convert(input_path, output_path, **_kwargs):
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(TEI_SAMPLE, encoding="utf-8")
    return MarkdownToTeiResult(
        source_file=Path(input_path),
        tei_file=out,
        command=["pandoc"],
        success=True,
        message="ok",
        validation=TeiValidationResult(valid=True),
    )


def _make_project(name: str) -> Path:
    project = RUNTIME_ROOT / f"{name}_{uuid.uuid4().hex}"
    (project / "content/pages").mkdir(parents=True)
    (project / "content/posts").mkdir(parents=True)
    (project / "content/pages/accueil.md").write_text(
        '---\ntitle: "Accueil"\nslug: "accueil"\ntype: "page"\nupdated: "2021-01-01"\n---\n\n# Accueil\n',
        encoding="utf-8",
    )
    post_path = project / "content/posts/premier.md"
    post_path.write_text(
        '---\ntitle: "Premier"\nslug: "premier-billet"\ntype: "post"\ndate: "2020-01-01"\n'
        'updated: "2022-06-15"\n---\n\n# Premier\n',
        encoding="utf-8",
    )
    return project


def _base_config(project: Path) -> tuple:
    config = build_default_config()
    config.paths.project_root = "."
    config.paths.pages_dir = "content/pages"
    config.paths.posts_dir = "content/posts"
    config.paths.assets_dir = "assets"
    config.paths.output_dir = "site"
    config.paths.tei_dir = "build/tei"
    config.home.source = "content/pages/accueil.md"
    config.site.base_url = "https://exemple.fr"

    config_path = project / "config/site.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text("{}", encoding="utf-8")
    return config, config_path


def test_footer_last_updated_reflects_content_not_the_build_wall_clock(monkeypatch):
    project = _make_project("footer_lastmod")
    config, config_path = _base_config(project)
    monkeypatch.setattr("bloggen.build.site_builder.convert_markdown_file_to_tei", _fake_convert)

    report = build_site(config, config_path=config_path)
    assert report.success is True

    html = (project / "site/index.html").read_text(encoding="utf-8")
    assert "Mis à jour le 2022-06-15" in html

    today = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
    assert today not in html


def test_two_builds_of_unchanged_content_produce_identical_output(monkeypatch):
    project = _make_project("determinism")
    config, config_path = _base_config(project)
    monkeypatch.setattr("bloggen.build.site_builder.convert_markdown_file_to_tei", _fake_convert)

    report1 = build_site(config, config_path=config_path)
    assert report1.success is True
    first_index = (project / "site/index.html").read_text(encoding="utf-8")
    first_post = (project / "site/billets/premier-billet/index.html").read_text(encoding="utf-8")

    report2 = build_site(config, config_path=config_path)
    assert report2.success is True
    second_index = (project / "site/index.html").read_text(encoding="utf-8")
    second_post = (project / "site/billets/premier-billet/index.html").read_text(encoding="utf-8")

    assert first_index == second_index
    assert first_post == second_post
