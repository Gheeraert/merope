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


def test_custom_css_and_js_override_builtin_theme_files(monkeypatch):
    project = RUNTIME_ROOT / f"theme_assets_{uuid.uuid4().hex}"
    (project / "content/pages").mkdir(parents=True)
    (project / "content/posts").mkdir(parents=True)
    (project / "theme/css").mkdir(parents=True)

    (project / "content/pages/accueil.md").write_text(
        '---\ntitle: "Accueil"\nslug: "accueil"\ntype: "page"\n---\n\n# Accueil\n',
        encoding="utf-8",
    )
    (project / "theme/css/site.css").write_text("body { color: red; }\n", encoding="utf-8")

    config = build_default_config()
    config.paths.project_root = "."
    config.paths.pages_dir = "content/pages"
    config.paths.posts_dir = "content/posts"
    config.paths.assets_dir = "assets"
    config.paths.output_dir = "site"
    config.paths.tei_dir = "build/tei"
    config.paths.theme_dir = "theme"
    config.home.source = "content/pages/accueil.md"

    config_path = project / "config/site.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text("{}", encoding="utf-8")

    monkeypatch.setattr("bloggen.build.site_builder.convert_markdown_file_to_tei", _fake_convert)

    report = build_site(config, config_path=config_path)

    assert report.success is True
    css = (project / "site/static/css/site.css").read_text(encoding="utf-8")
    assert css == "body { color: red; }\n"
    assert (project / "site/static/js/app.js").exists()


def test_custom_page_template_overrides_default_document_structure(monkeypatch):
    project = RUNTIME_ROOT / f"theme_template_{uuid.uuid4().hex}"
    (project / "content/pages").mkdir(parents=True)
    (project / "content/posts").mkdir(parents=True)
    (project / "theme/templates").mkdir(parents=True)

    (project / "content/pages/accueil.md").write_text(
        '---\ntitle: "Accueil"\nslug: "accueil"\ntype: "page"\n---\n\n# Accueil\n',
        encoding="utf-8",
    )
    (project / "content/pages/mentions.md").write_text(
        '---\ntitle: "Mentions"\nslug: "mentions"\ntype: "page"\n---\n\n# Mentions\n',
        encoding="utf-8",
    )
    (project / "theme/templates/page.html").write_text(
        "<!doctype html><html lang=\"$lang\"><head><title>$title</title></head>"
        "<body><custom-marker>$content</custom-marker>$scripts</body></html>",
        encoding="utf-8",
    )

    config = build_default_config()
    config.paths.project_root = "."
    config.paths.pages_dir = "content/pages"
    config.paths.posts_dir = "content/posts"
    config.paths.assets_dir = "assets"
    config.paths.output_dir = "site"
    config.paths.tei_dir = "build/tei"
    config.paths.theme_dir = "theme"
    config.paths.templates_dir = "theme/templates"
    config.render.html_template = "page.html"
    config.home.source = "content/pages/accueil.md"

    config_path = project / "config/site.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text("{}", encoding="utf-8")

    monkeypatch.setattr("bloggen.build.site_builder.convert_markdown_file_to_tei", _fake_convert)

    report = build_site(config, config_path=config_path)

    assert report.success is True
    mentions_html = (project / "site/mentions/index.html").read_text(encoding="utf-8")
    assert "<custom-marker>" in mentions_html
    assert "top-menu" not in mentions_html
    assert "side-menu" not in mentions_html

    accueil_html = (project / "site/accueil/index.html").read_text(encoding="utf-8")
    assert "<custom-marker>" in accueil_html
