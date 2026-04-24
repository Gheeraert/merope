from __future__ import annotations

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
    '<text><body><div><head>Titre</head>'
    '<p>Contenu avec note<note>Note test</note></p>'
    '<figure><head>Légende test</head><graphic url="media/inline.jpg"/></figure>'
    '</div></body></text>'
    '</TEI>'
)


def test_site_builder_generates_illustrated_site(monkeypatch):
    project = RUNTIME_ROOT / f"site_builder_{uuid.uuid4().hex}"
    (project / "content/pages").mkdir(parents=True)
    (project / "content/posts/media").mkdir(parents=True)
    (project / "assets/images").mkdir(parents=True)
    (project / "assets/banner").mkdir(parents=True)

    (project / "content/posts/media/inline.jpg").write_bytes(b"img")
    (project / "assets/images/pic.jpg").write_bytes(b"img")
    (project / "assets/banner/site-banner.jpg").write_bytes(b"img")

    (project / "content/pages/accueil.md").write_text(
        '---\ntitle: "Accueil"\nslug: "accueil"\n---\n\n# Accueil\n\nTexte.\n',
        encoding="utf-8",
    )
    (project / "content/posts/premier.md").write_text(
        '---\ntitle: "Premier"\nslug: "premier-billet"\ndate: "2026-04-23"\n---\n\n# Premier\n\nImage ![Inline](media/inline.jpg)\n',
        encoding="utf-8",
    )

    config = build_default_config()
    config.paths.project_root = "."
    config.paths.content_dir = "content"
    config.paths.pages_dir = "content/pages"
    config.paths.posts_dir = "content/posts"
    config.paths.assets_dir = "assets"
    config.paths.output_dir = "site"
    config.paths.tei_dir = "build/tei"
    config.home.source = "content/pages/accueil.md"
    config.content.copy_linked_assets = True
    config.media_handling.copy_media_to_output = True
    config.render.enable_lightbox = True
    config.notes_rendering.enable_margin_notes = True
    config.notes_rendering.enable_footnotes = True
    config.banner.enabled = True
    config.banner.image = "assets/banner/site-banner.jpg"
    config.banner.link = "/index.html"

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
    assert (project / "site/index.html").exists()
    assert (project / "site/accueil/index.html").exists()
    assert (project / "site/billets/index.html").exists()
    assert (project / "site/billets/premier-billet/index.html").exists()
    assert (project / "build/tei/pages/accueil.xml").exists()
    assert (project / "build/tei/posts/premier-billet.xml").exists()
    assert (project / "site/content-media/post/premier-billet/media/inline.jpg").exists()

    post_html = (project / "site/billets/premier-billet/index.html").read_text(encoding="utf-8")
    index_html = (project / "site/index.html").read_text(encoding="utf-8")
    archive_html = (project / "site/billets/index.html").read_text(encoding="utf-8")
    assert "lightbox-link" in post_html
    assert "endnotes" in post_html
    assert "margin-notes" in post_html
    assert 'href="../../index.html"' in post_html
    assert 'href="../index.html"' in post_html
    assert 'href="/index.html"' not in post_html
    assert '<header class="site-banner"' in post_html
    assert 'href="billets/premier-billet/index.html"' in index_html
    assert 'href="/billets/premier-billet/index.html"' not in index_html
    assert 'href="premier-billet/index.html"' in archive_html
    assert 'href="/billets/premier-billet/index.html"' not in archive_html


def test_site_builder_disables_missing_banner_without_failing(monkeypatch):
    project = RUNTIME_ROOT / f"site_builder_banner_{uuid.uuid4().hex}"
    (project / "content/pages").mkdir(parents=True)
    (project / "content/posts").mkdir(parents=True)

    (project / "content/pages/accueil.md").write_text(
        '---\ntitle: "Accueil"\nslug: "accueil"\n---\n\n# Accueil\n',
        encoding="utf-8",
    )

    config = build_default_config()
    config.paths.project_root = "."
    config.paths.content_dir = "content"
    config.paths.pages_dir = "content/pages"
    config.paths.posts_dir = "content/posts"
    config.paths.assets_dir = "assets"
    config.paths.output_dir = "site"
    config.paths.tei_dir = "build/tei"
    config.home.source = "content/pages/accueil.md"
    config.banner.enabled = True
    config.banner.image = "assets/banner/does-not-exist.jpg"

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
    assert any("Bannière désactivée" in warning for warning in report.warnings)
    index_html = (project / "site/index.html").read_text(encoding="utf-8")
    assert '<header class="site-banner"' not in index_html
