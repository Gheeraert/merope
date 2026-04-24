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
    '<text><body><div><head>Titre</head>'
    '<p>Contenu avec note<note>Note E2E</note></p>'
    '<figure><head>Illustration</head><graphic url="../../assets/images/exemple.jpg"/></figure>'
    '</div></body></text>'
    '</TEI>'
)


def test_end_to_end_minimal_project_with_image_note_archive_and_home(monkeypatch):
    source_project = Path("examples/minimal_project")
    target_project = RUNTIME_ROOT / f"e2e_{uuid.uuid4().hex}"
    shutil.copytree(source_project, target_project)

    config_path = target_project / "config/site.json"
    config = load_config(config_path)
    config.content.copy_linked_assets = True
    config.media_handling.copy_media_to_output = True
    config.render.enable_lightbox = True
    config.notes_rendering.enable_margin_notes = True
    config.notes_rendering.enable_footnotes = True

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
    assert (target_project / "site/index.html").exists()
    assert (target_project / "site/billets/index.html").exists()
    assert (target_project / "site/billets/premier-billet/index.html").exists()
    assert (target_project / "site/assets/images/exemple.jpg").exists()

    index_html = (target_project / "site/index.html").read_text(encoding="utf-8")
    post_html = (target_project / "site/billets/premier-billet/index.html").read_text(encoding="utf-8")
    archive_html = (target_project / "site/billets/index.html").read_text(encoding="utf-8")

    assert "top-menu" in index_html
    assert "side-menu" in index_html
    assert "lightbox-link" in post_html
    assert "endnotes" in post_html
    assert "margin-notes" in post_html
    assert 'href="../../index.html"' in post_html
    assert 'href="../index.html"' in post_html
    assert 'href="billets/premier-billet/index.html"' in index_html
    assert 'href="/billets/premier-billet/index.html"' not in index_html
    assert 'href="premier-billet/index.html"' in archive_html
    assert 'href="/billets/premier-billet/index.html"' not in archive_html
