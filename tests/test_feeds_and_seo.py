from __future__ import annotations

from pathlib import Path
import uuid

from bloggen.build.site_builder import build_site
from bloggen.config.defaults import build_default_config
from bloggen.render.feeds import FeedItem, render_rss_feed, render_sitemap
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


def test_render_rss_feed_contains_items_and_channel_metadata():
    xml = render_rss_feed(
        site_title="Carnet",
        site_description="Un carnet",
        base_url="https://example.org",
        language="fr",
        items=[FeedItem(title="Billet", url="/billets/un/index.html", date="2026-04-23", description="Résumé")],
    )
    assert "<title>Carnet</title>" in xml
    assert "<link>https://example.org/billets/un/index.html</link>" in xml
    assert "<pubDate>" in xml
    assert "Résumé" in xml


def test_render_sitemap_lists_absolute_urls():
    xml = render_sitemap(base_url="https://example.org/", urls=["/index.html", "/billets/un/index.html"])
    assert "<loc>https://example.org/index.html</loc>" in xml
    assert "<loc>https://example.org/billets/un/index.html</loc>" in xml


def test_build_site_generates_feed_sitemap_and_seo_meta(monkeypatch):
    project = RUNTIME_ROOT / f"seo_{uuid.uuid4().hex}"
    (project / "content/pages").mkdir(parents=True)
    (project / "content/posts").mkdir(parents=True)

    (project / "content/pages/accueil.md").write_text(
        '---\ntitle: "Accueil"\nslug: "accueil"\ntype: "page"\n---\n\n# Accueil\n',
        encoding="utf-8",
    )
    (project / "content/posts/premier.md").write_text(
        '---\ntitle: "Premier"\nslug: "premier-billet"\ntype: "post"\ndate: "2026-04-23"\n'
        'description: "Un résumé de billet"\n---\n\n# Premier\n',
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

    def fake_convert(input_path, output_path, **_kwargs):
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

    monkeypatch.setattr("bloggen.build.site_builder.convert_markdown_file_to_tei", fake_convert)

    report = build_site(config, config_path=config_path)

    assert report.success is True
    feed_path = project / "site/feed.xml"
    sitemap_path = project / "site/sitemap.xml"
    assert feed_path.exists()
    assert sitemap_path.exists()

    feed_xml = feed_path.read_text(encoding="utf-8")
    assert "https://exemple.fr/billets/premier-billet/index.html" in feed_xml
    assert "Un résumé de billet" in feed_xml

    sitemap_xml = sitemap_path.read_text(encoding="utf-8")
    assert "https://exemple.fr/index.html" in sitemap_xml
    assert "https://exemple.fr/billets/premier-billet/index.html" in sitemap_xml
    assert "https://exemple.fr/accueil/index.html" in sitemap_xml

    post_html = (project / "site/billets/premier-billet/index.html").read_text(encoding="utf-8")
    assert '<meta name="description" content="Un résumé de billet">' in post_html
    assert '<link rel="canonical" href="https://exemple.fr/billets/premier-billet/index.html">' in post_html
    assert '<meta property="og:title" content="Premier">' in post_html


def test_build_site_warns_when_base_url_missing_for_feed(monkeypatch):
    project = RUNTIME_ROOT / f"seo_nourl_{uuid.uuid4().hex}"
    (project / "content/pages").mkdir(parents=True)
    (project / "content/posts").mkdir(parents=True)
    (project / "content/pages/accueil.md").write_text(
        '---\ntitle: "Accueil"\nslug: "accueil"\ntype: "page"\n---\n\n# Accueil\n',
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

    config_path = project / "config/site.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text("{}", encoding="utf-8")

    def fake_convert(input_path, output_path, **_kwargs):
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

    monkeypatch.setattr("bloggen.build.site_builder.convert_markdown_file_to_tei", fake_convert)

    report = build_site(config, config_path=config_path)

    assert report.success is True
    assert not (project / "site/feed.xml").exists()
    assert not (project / "site/sitemap.xml").exists()
    assert any("Flux RSS non généré" in warning for warning in report.warnings)
    assert any("Sitemap non généré" in warning for warning in report.warnings)
