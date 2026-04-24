from __future__ import annotations

from pathlib import Path
import shutil
import uuid

from bloggen.build.site_builder import build_site
from bloggen.config.io import load_config
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


def test_end_to_end_minimal_project_simulated(monkeypatch):
    source_project = Path("examples/minimal_project")
    target_project = RUNTIME_ROOT / f"e2e_{uuid.uuid4().hex}"
    shutil.copytree(source_project, target_project)

    config_path = target_project / "config/site.json"
    config = load_config(config_path)

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
    monkeypatch.setattr(
        "bloggen.build.site_builder.render_tei_file_to_html_fragment",
        lambda _tei_path, xslt_path=None: "<article><p>Rendu E2E</p></article>",
    )

    report = build_site(config, config_path=config_path)

    assert report.success is True
    assert (target_project / "site/index.html").exists()
    assert (target_project / "site/billets/index.html").exists()
    assert (target_project / "site/billets/premier-billet/index.html").exists()
    assert (target_project / "site/assets/banner/.gitkeep").exists()

    index_html = (target_project / "site/index.html").read_text(encoding="utf-8")
    assert "top-menu" in index_html
    assert "side-menu" in index_html
