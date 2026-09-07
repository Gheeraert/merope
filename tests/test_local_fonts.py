"""The generated site previously loaded "IM Fell English" straight from
Google's CDN (fonts.googleapis.com/fonts.gstatic.com) on every visit,
sending each visitor's IP address to Google just to render a heading
font — a real GDPR exposure for a French/EU academic site, not just a
performance nicety. The font is now bundled with MEROPE and served from
the generated site itself.
"""

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


def test_generated_pages_never_reference_googles_font_cdn(monkeypatch):
    project = RUNTIME_ROOT / f"local_fonts_{uuid.uuid4().hex}"
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

    monkeypatch.setattr("bloggen.build.site_builder.convert_markdown_file_to_tei", _fake_convert)

    report = build_site(config, config_path=config_path)
    assert report.success is True

    html = (project / "site/index.html").read_text(encoding="utf-8")
    assert "fonts.googleapis.com" not in html
    assert "fonts.gstatic.com" not in html


def test_the_self_hosted_font_file_is_copied_into_the_generated_site(monkeypatch):
    project = RUNTIME_ROOT / f"local_fonts_asset_{uuid.uuid4().hex}"
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

    monkeypatch.setattr("bloggen.build.site_builder.convert_markdown_file_to_tei", _fake_convert)

    report = build_site(config, config_path=config_path)
    assert report.success is True

    font_files = list((project / "site/static/fonts").glob("*.woff2"))
    assert len(font_files) == 1
    assert font_files[0].stat().st_size > 0

    css = (project / "site/static/css/site.css").read_text(encoding="utf-8")
    assert "@font-face" in css
    assert f"../fonts/{font_files[0].name}" in css
