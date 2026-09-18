"""Full build coverage for the optional top banner and ordinary asset copy."""

from __future__ import annotations

import shutil
from pathlib import Path

from PIL import Image

from bloggen.build.site_builder import build_site
from bloggen.config.io import load_config
from bloggen.tei.pandoc_converter import MarkdownToTeiResult
from bloggen.tei.validator import TeiValidationResult


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


def test_build_copies_top_banner_and_renders_it_at_every_depth(tmp_path, monkeypatch):
    project = tmp_path / "project"
    shutil.copytree(
        "examples/minimal_project",
        project,
        ignore=shutil.ignore_patterns("site", "build", "__pycache__"),
    )
    config_path = project / "config/site.json"
    config = load_config(config_path)
    config.top_banner.enabled = True
    config.top_banner.image = "assets/top-banner/institution.png"
    config.top_banner.alt = "Institution"
    config.top_banner.link = "/index.html"
    config.banner.enabled = True
    config.banner.image = "assets/banner/editorial.png"

    top_image = project / config.top_banner.image
    top_image.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (200, 40), color="blue").save(top_image)
    original_bytes = top_image.read_bytes()
    banner_image = project / config.banner.image
    banner_image.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (600, 100), color="red").save(banner_image)
    monkeypatch.setattr("bloggen.build.site_builder.convert_markdown_file_to_tei", _fake_convert)

    report = build_site(config, config_path=config_path)

    assert report.success is True
    assert (project / "site/assets/top-banner/institution.png").read_bytes() == original_bytes
    assert top_image.read_bytes() == original_bytes
    assert (project / "site/static/css/site.css").exists()
    assert ".top-banner-image" in (project / "site/static/css/site.css").read_text(encoding="utf-8")

    for page, prefix, href in (
        ("index.html", "", "index.html"),
        ("projet/index.html", "../", "../index.html"),
        ("billets/premier-billet/index.html", "../../", "../../index.html"),
    ):
        html = (project / "site" / page).read_text(encoding="utf-8")
        assert f'<a class="top-banner-link" href="{href}">' in html
        assert f'<img class="top-banner-image" src="{prefix}assets/top-banner/institution.png" alt="Institution">' in html
        assert html.index('class="top-banner"') < html.index('class="site-banner"') < html.index('class="masthead"')

    config.top_banner.enabled = False
    second_report = build_site(config, config_path=config_path)
    assert second_report.success is True
    disabled_html = (project / "site/index.html").read_text(encoding="utf-8")
    assert 'class="top-banner"' not in disabled_html
    assert 'class="site-banner"' in disabled_html
    assert top_image.read_bytes() == original_bytes


def test_build_warns_when_enabled_top_banner_has_no_image(tmp_path, monkeypatch):
    project = tmp_path / "project"
    shutil.copytree(
        "examples/minimal_project",
        project,
        ignore=shutil.ignore_patterns("site", "build", "__pycache__"),
    )
    config_path = project / "config/site.json"
    config = load_config(config_path)
    config.top_banner.enabled = True
    monkeypatch.setattr("bloggen.build.site_builder.convert_markdown_file_to_tei", _fake_convert)

    report = build_site(config, config_path=config_path)

    assert report.success is True
    assert any("Bandeau supérieur désactivé: chemin d'image vide" in warning for warning in report.warnings)
    assert 'class="top-banner"' not in (project / "site/index.html").read_text(encoding="utf-8")
    assert config.top_banner.enabled is True  # only the build's runtime copy is changed
