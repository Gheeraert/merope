from __future__ import annotations

from pathlib import Path
import uuid

from bloggen import cli
from bloggen.config.io import save_config
from bloggen.config.defaults import build_default_config

RUNTIME_ROOT = Path("tests/.runtime")
RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)

TEI_SAMPLE = (
    '<TEI xmlns="http://www.tei-c.org/ns/1.0">'
    '<teiHeader><fileDesc><titleStmt><title>Test</title></titleStmt>'
    '<publicationStmt><p>p</p></publicationStmt><sourceDesc><p>s</p></sourceDesc></fileDesc></teiHeader>'
    '<text><body><div><head>Titre</head><p>Contenu.</p></div></body></text>'
    '</TEI>'
)


def _make_project(monkeypatch, name: str) -> Path:
    project = RUNTIME_ROOT / f"cli_{name}_{uuid.uuid4().hex}"
    (project / "content/pages").mkdir(parents=True)
    (project / "content/posts").mkdir(parents=True)

    (project / "content/pages/accueil.md").write_text(
        '---\ntitle: "Accueil"\nslug: "accueil"\ntype: "page"\n---\n\n# Accueil\n',
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
    save_config(config, config_path)

    def fake_convert(input_path, output_path, **_kwargs):
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(TEI_SAMPLE, encoding="utf-8")
        from bloggen.tei.pandoc_converter import MarkdownToTeiResult
        from bloggen.tei.validator import TeiValidationResult

        return MarkdownToTeiResult(
            source_file=Path(input_path),
            tei_file=out,
            command=["pandoc"],
            success=True,
            message="ok",
            validation=TeiValidationResult(valid=True),
        )

    monkeypatch.setattr("bloggen.build.site_builder.convert_markdown_file_to_tei", fake_convert)
    return config_path


def test_cli_build_succeeds_and_prints_report(monkeypatch, capsys):
    config_path = _make_project(monkeypatch, "ok")

    exit_code = cli.main(["build", "--config", str(config_path)])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Succès: oui" in captured.out
    assert (config_path.parent.parent / "site/index.html").exists()


def test_cli_build_reports_invalid_config(capsys):
    project = RUNTIME_ROOT / f"cli_invalid_{uuid.uuid4().hex}"
    project.mkdir(parents=True)
    config_path = project / "site.json"
    config_path.write_text('{"site": {}}', encoding="utf-8")

    exit_code = cli.main(["build", "--config", str(config_path)])

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "Configuration invalide" in captured.err


def test_cli_requires_a_command(capsys):
    try:
        cli.main([])
    except SystemExit as exc:
        assert exc.code != 0
    else:
        raise AssertionError("argparse aurait dû lever SystemExit sans commande.")
