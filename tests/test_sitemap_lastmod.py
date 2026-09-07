"""sitemap.xml's <lastmod> previously used only the publication date
(never changing even after a later edit, and never present at all for a
page — only posts require a date field). It now reflects the source
.md file's own filesystem mtime.
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


def test_lastmod_reflects_a_later_edit_not_the_original_publication_date(monkeypatch):
    project = RUNTIME_ROOT / f"sitemap_lastmod_{uuid.uuid4().hex}"
    (project / "content/pages").mkdir(parents=True)
    (project / "content/posts").mkdir(parents=True)
    (project / "content/pages/accueil.md").write_text(
        '---\ntitle: "Accueil"\nslug: "accueil"\ntype: "page"\n---\n\n# Accueil\n',
        encoding="utf-8",
    )
    post_path = project / "content/posts/premier.md"
    post_path.write_text(
        '---\ntitle: "Premier"\nslug: "premier-billet"\ntype: "post"\ndate: "2020-01-01"\n---\n\n# Premier\n',
        encoding="utf-8",
    )

    # Edited long after its stated publication date — the file's mtime
    # is the signal a sitemap lastmod should actually reflect.
    edited_timestamp = datetime.datetime(2026, 6, 15, tzinfo=datetime.timezone.utc).timestamp()
    os.utime(post_path, (edited_timestamp, edited_timestamp))

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

    monkeypatch.setattr("bloggen.build.site_builder.convert_markdown_file_to_tei", _fake_convert)

    report = build_site(config, config_path=config_path)
    assert report.success is True

    sitemap_xml = (project / "site/sitemap.xml").read_text(encoding="utf-8")
    assert "<lastmod>2026-06-15</lastmod>" in sitemap_xml
    assert "<lastmod>2020-01-01</lastmod>" not in sitemap_xml


def test_a_page_with_no_date_field_still_gets_a_lastmod(monkeypatch):
    """Only posts require a `date` front-matter field — a page previously
    had no <lastmod> at all in the sitemap."""
    project = RUNTIME_ROOT / f"sitemap_lastmod_page_{uuid.uuid4().hex}"
    (project / "content/pages").mkdir(parents=True)
    (project / "content/posts").mkdir(parents=True)
    (project / "content/pages/accueil.md").write_text(
        '---\ntitle: "Accueil"\nslug: "accueil"\ntype: "page"\n---\n\n# Accueil\n',
        encoding="utf-8",
    )
    other_page = project / "content/pages/autre.md"
    other_page.write_text(
        '---\ntitle: "Autre"\nslug: "autre"\ntype: "page"\n---\n\n# Autre\n',
        encoding="utf-8",
    )

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

    monkeypatch.setattr("bloggen.build.site_builder.convert_markdown_file_to_tei", _fake_convert)

    report = build_site(config, config_path=config_path)
    assert report.success is True

    sitemap_xml = (project / "site/sitemap.xml").read_text(encoding="utf-8")
    today = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
    assert f'<url><loc>https://exemple.fr/autre/index.html</loc><lastmod>{today}</lastmod></url>' in sitemap_xml


def test_an_explicit_updated_field_overrides_the_filesystem_mtime(monkeypatch):
    """The mtime fallback is reset by anything that touches the file on
    disk without an actual content change (a git checkout, a file
    resync) — an editorial `updated:` front-matter date must win."""
    project = RUNTIME_ROOT / f"sitemap_lastmod_updated_{uuid.uuid4().hex}"
    (project / "content/pages").mkdir(parents=True)
    (project / "content/posts").mkdir(parents=True)
    (project / "content/pages/accueil.md").write_text(
        '---\ntitle: "Accueil"\nslug: "accueil"\ntype: "page"\n---\n\n# Accueil\n',
        encoding="utf-8",
    )
    post_path = project / "content/posts/premier.md"
    post_path.write_text(
        '---\ntitle: "Premier"\nslug: "premier-billet"\ntype: "post"\ndate: "2020-01-01"\n'
        'updated: "2021-03-10"\n---\n\n# Premier\n',
        encoding="utf-8",
    )

    # The file's actual mtime disagrees with the declared `updated:`
    # date — the front-matter value must win regardless.
    checkout_timestamp = datetime.datetime(2026, 6, 15, tzinfo=datetime.timezone.utc).timestamp()
    os.utime(post_path, (checkout_timestamp, checkout_timestamp))

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

    monkeypatch.setattr("bloggen.build.site_builder.convert_markdown_file_to_tei", _fake_convert)

    report = build_site(config, config_path=config_path)
    assert report.success is True

    sitemap_xml = (project / "site/sitemap.xml").read_text(encoding="utf-8")
    assert "<lastmod>2021-03-10</lastmod>" in sitemap_xml
    assert "<lastmod>2026-06-15</lastmod>" not in sitemap_xml


def test_home_lastmod_uses_the_home_page_itself_when_home_mode_is_page(monkeypatch):
    """When the home page is a fixed page (home.mode == "page"), the
    sitemap's /index.html <lastmod> must reflect that page's own
    lastmod, not the most recent post's — a static homepage's real
    last-modified signal has nothing to do with unrelated post activity.
    """
    project = RUNTIME_ROOT / f"sitemap_home_lastmod_{uuid.uuid4().hex}"
    (project / "content/pages").mkdir(parents=True)
    (project / "content/posts").mkdir(parents=True)
    accueil_path = project / "content/pages/accueil.md"
    accueil_path.write_text(
        '---\ntitle: "Accueil"\nslug: "accueil"\ntype: "page"\n---\n\n# Accueil\n',
        encoding="utf-8",
    )
    old_timestamp = datetime.datetime(2020, 1, 1, tzinfo=datetime.timezone.utc).timestamp()
    os.utime(accueil_path, (old_timestamp, old_timestamp))

    post_path = project / "content/posts/premier.md"
    post_path.write_text(
        '---\ntitle: "Premier"\nslug: "premier"\ntype: "post"\ndate: "2026-01-01"\n---\n\n# Premier\n',
        encoding="utf-8",
    )
    recent_timestamp = datetime.datetime(2026, 6, 15, tzinfo=datetime.timezone.utc).timestamp()
    os.utime(post_path, (recent_timestamp, recent_timestamp))

    config = build_default_config()
    config.paths.project_root = "."
    config.paths.pages_dir = "content/pages"
    config.paths.posts_dir = "content/posts"
    config.paths.assets_dir = "assets"
    config.paths.output_dir = "site"
    config.paths.tei_dir = "build/tei"
    config.home.source = "content/pages/accueil.md"
    config.home.mode = "page"
    config.site.base_url = "https://exemple.fr"

    config_path = project / "config/site.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text("{}", encoding="utf-8")

    monkeypatch.setattr("bloggen.build.site_builder.convert_markdown_file_to_tei", _fake_convert)

    report = build_site(config, config_path=config_path)
    assert report.success is True

    sitemap_xml = (project / "site/sitemap.xml").read_text(encoding="utf-8")
    assert '<url><loc>https://exemple.fr/index.html</loc><lastmod>2020-01-01</lastmod></url>' in sitemap_xml
