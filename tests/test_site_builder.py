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
    '<text><body><div><head>Titre</head><p>Contenu</p></div></body></text>'
    '</TEI>'
)


def test_site_builder_generates_minimal_site(monkeypatch):
    project = RUNTIME_ROOT / f"site_builder_{uuid.uuid4().hex}"
    (project / "content/pages").mkdir(parents=True)
    (project / "content/posts").mkdir(parents=True)
    (project / "assets/images").mkdir(parents=True)
    (project / "assets/images/pic.jpg").write_text("img", encoding="utf-8")

    (project / "content/pages/accueil.md").write_text(
        '---\ntitle: "Accueil"\nslug: "accueil"\n---\n\n# Accueil\n\nTexte.\n',
        encoding="utf-8",
    )
    (project / "content/posts/premier.md").write_text(
        '---\ntitle: "Premier"\nslug: "premier-billet"\ndate: "2026-04-23"\n---\n\n# Premier\n',
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

    def fake_render(_tei_path, xslt_path=None):
        assert xslt_path is None or isinstance(xslt_path, Path)
        return "<article><p>HTML rendu</p></article>"

    monkeypatch.setattr("bloggen.build.site_builder.convert_markdown_file_to_tei", fake_convert)
    monkeypatch.setattr("bloggen.build.site_builder.render_tei_file_to_html_fragment", fake_render)

    report = build_site(config, config_path=config_path)

    assert report.success is True
    assert (project / "site/index.html").exists()
    assert (project / "site/accueil/index.html").exists()
    assert (project / "site/billets/index.html").exists()
    assert (project / "site/billets/premier-billet/index.html").exists()
    assert (project / "build/tei/pages/accueil.xml").exists()
    assert (project / "build/tei/posts/premier-billet.xml").exists()
