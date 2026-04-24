from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import re
import xml.etree.ElementTree as ET

import pytest

from bloggen.render.xslt_runner import render_tei_file_to_html_fragment
from bloggen.tei.pandoc_converter import (
    PandocUnavailableError,
    convert_markdown_file_to_tei,
    convert_markdown_to_tei,
)

RUNTIME_DIR = Path("tests/.runtime")
RUNTIME_DIR.mkdir(parents=True, exist_ok=True)


def test_convert_markdown_to_tei_with_simulated_pandoc(monkeypatch: pytest.MonkeyPatch):
    def fake_run(command, **_kwargs):
        output_path = Path(command[command.index("-o") + 1])
        output_path.write_text("<TEI><text><body><p>ok</p></body></text></TEI>", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr("bloggen.utils.subprocesses.subprocess.run", fake_run)

    output_path = RUNTIME_DIR / "pandoc_simulated.xml"
    result = convert_markdown_to_tei("fixtures/markdown/simple_post.md", output_path)

    assert result.success is True
    assert result.command[0] == "pandoc"
    assert result.tei_file == output_path


def test_convert_markdown_to_tei_reports_missing_pandoc(monkeypatch: pytest.MonkeyPatch):
    def fake_run(*_args, **_kwargs):
        raise FileNotFoundError("pandoc")

    monkeypatch.setattr("bloggen.utils.subprocesses.subprocess.run", fake_run)

    with pytest.raises(PandocUnavailableError):
        convert_markdown_to_tei("fixtures/markdown/simple_post.md", RUNTIME_DIR / "missing.xml")


def test_end_to_end_markdown_to_tei_simulated(monkeypatch: pytest.MonkeyPatch):
    markdown_source = RUNTIME_DIR / "pipeline_source.md"
    markdown_source.write_text(
        "---\n"
        "title: \"Titre Pipeline\"\n"
        "---\n"
        "# Section\n\nTexte avec note[^1].\n\n[^1]: note.\n",
        encoding="utf-8",
    )

    def fake_run(command, **_kwargs):
        output_path = Path(command[command.index("-o") + 1])
        output_path.write_text("<TEI><text><body><p>Simule</p></body></text></TEI>", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr("bloggen.utils.subprocesses.subprocess.run", fake_run)

    output_path = RUNTIME_DIR / "pipeline_output.xml"
    result = convert_markdown_file_to_tei(markdown_source, output_path)

    assert result.success is True
    assert result.validation.valid is True
    tei_content = output_path.read_text(encoding="utf-8")
    assert "teiHeader" in tei_content
    assert "Titre Pipeline" in tei_content


def test_end_to_end_markdown_to_tei_with_real_pandoc_if_available():
    if shutil.which("pandoc") is None:
        pytest.skip("Pandoc non disponible dans l'environnement de test.")

    markdown_source = RUNTIME_DIR / "pipeline_real_pandoc_source.md"
    markdown_source.write_text(
        "# Titre test\n\n"
        "Texte *italique* et **gras** avec note[^1].\n\n"
        "![Une image](../../assets/images/exemple.jpg)\n\n"
        "[^1]: Note simple.\n",
        encoding="utf-8",
    )

    output_path = RUNTIME_DIR / "pipeline_real_pandoc_output.xml"
    result = convert_markdown_file_to_tei(markdown_source, output_path, pandoc_command="pandoc")

    assert result.success is True
    tei_content = output_path.read_text(encoding="utf-8")
    assert 'rendition="simple:italic"' in tei_content
    assert 'rendition="simple:bold"' in tei_content
    root = ET.fromstring(tei_content)
    local_names = [node.tag.split("}", maxsplit=1)[-1] for node in root.iter()]
    assert "figure" in local_names
    paragraphs = [node for node in root.iter() if node.tag.split("}", maxsplit=1)[-1] == "p"]
    assert any("Une image" == " ".join((node.text or "").split()) for node in paragraphs)

    html = render_tei_file_to_html_fragment(output_path, parameters={"article_slug": "real"})
    assert "<em>italique</em>" in html
    assert "<strong>gras</strong>" in html
    assert "<figure" in html
    assert "<img" in html
    assert "<figcaption>Une image</figcaption>" in html
    assert re.search(r"<p>\s*<figure", html) is None
    assert "<p>Une image</p>" not in html
