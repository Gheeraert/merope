from __future__ import annotations

import os
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from lxml import html as lxml_html
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QApplication

from bloggen.build.site_builder import build_site
from bloggen.config.io import load_config
from bloggen.content.writer import write_content_file
from bloggen.markdown.rich_text_export import blocks_to_markdown
from bloggen.markdown.rich_text_model import PARAGRAPH, Block, InlineRun
from bloggen.ui.qt_editor.document_adapter import (
    extract_blocks,
    is_figure_block,
    populate_document,
)
from bloggen.ui.qt_editor.formatting import set_alignment
from bloggen.ui.qt_editor.preview import (
    PreviewSnapshot,
    build_preview_artifact,
    remove_preview_artifact,
)
from bloggen.ui.qt_editor.text_edit import MeropeTextEdit


@pytest.fixture(scope="module", autouse=True)
def qapplication():
    app = QApplication.instance() or QApplication([])
    yield app


def _assert_figure_html(html_text: str) -> None:
    document = lxml_html.fromstring(html_text)
    figures = document.xpath(
        "//figure[contains(concat(' ', normalize-space(@class), ' '), "
        "' article-figure ')]"
    )
    expected = [
        ("align-left", "Gauche"),
        ("align-center", "Centre"),
        ("align-right", "Droite"),
        ("align-center", None),
    ]
    assert len(figures) == len(expected)
    for figure, (alignment, caption) in zip(figures, expected):
        assert alignment in figure.get("class", "").split()
        captions = figure.xpath("./figcaption")
        if caption is None:
            assert captions == []
        else:
            assert len(captions) == 1
            assert captions[0].text_content() == caption


def _graphic_attributes(tei_path: Path) -> list[dict[str, str]]:
    root = ET.parse(tei_path).getroot()
    graphics = root.findall(".//{http://www.tei-c.org/ns/1.0}graphic")
    return [dict(graphic.attrib) for graphic in graphics]


def test_qt_figure_alignment_reaches_preview_and_published_site(tmp_path):
    if shutil.which("pandoc") is None:
        pytest.skip("Pandoc non disponible dans l’environnement de test.")

    project_root = tmp_path / "project"
    shutil.copytree(
        Path("examples/minimal_project"),
        project_root,
        ignore=shutil.ignore_patterns("site", "build", "__pycache__"),
    )
    image_dir = project_root / "assets" / "images"
    image_dir.mkdir(parents=True, exist_ok=True)
    for name in ("left.png", "center.png", "right.png", "plain.png"):
        (image_dir / name).write_bytes(b"image")

    runs = [
        InlineRun(image_src="../../assets/images/left.png", image_alt="Gauche"),
        InlineRun(
            image_src="../../assets/images/center.png",
            image_alt="Centre",
            image_width="40%",
        ),
        InlineRun(
            image_src="../../assets/images/right.png",
            image_alt="Droite",
            image_width="300",
            image_height="200",
        ),
        InlineRun(image_src="../../assets/images/plain.png", image_alt=""),
    ]
    editor = MeropeTextEdit()
    populate_document(
        editor.document(),
        [Block(kind=PARAGRAPH, runs=[run]) for run in runs],
    )
    figure = editor.document().begin()
    for alignment in ("left", "center", "right", "center"):
        assert is_figure_block(figure)
        cursor = QTextCursor(figure)
        cursor.movePosition(
            QTextCursor.MoveOperation.EndOfBlock,
            QTextCursor.MoveMode.KeepAnchor,
        )
        editor.setTextCursor(cursor)
        set_alignment(editor, alignment)
        figure = figure.next().next()

    blocks = extract_blocks(editor.document())
    assert [block.alignment for block in blocks] == ["left"] * 4
    assert [block.runs[0].image_align for block in blocks] == [
        "left",
        "center",
        "right",
        "center",
    ]
    markdown = blocks_to_markdown(blocks)
    assert markdown == (
        "![Gauche](../../assets/images/left.png){align=left}\n\n"
        "![Centre](../../assets/images/center.png){width=40% align=center}\n\n"
        "![Droite](../../assets/images/right.png)"
        "{width=300 height=200 align=right}\n\n"
        "![](../../assets/images/plain.png){align=center}\n"
    )
    assert "{{align=" not in markdown

    metadata = {"title": "Figures", "slug": "figures", "type": "page"}
    source = write_content_file(
        project_root / "content" / "pages",
        "figures.md",
        metadata,
        markdown,
    )
    config_path = project_root / "config" / "site.json"
    config = load_config(config_path)

    artifact = build_preview_artifact(
        PreviewSnapshot(
            body_markdown=markdown,
            metadata=metadata,
            current_path=source,
        ),
        config=config,
        project_root=project_root,
    )
    try:
        preview_html = artifact.html_path.read_text(encoding="utf-8")
        _assert_figure_html(preview_html)
        preview_attrs = _graphic_attributes(
            artifact.scratch_dir / "tei" / "figures.xml"
        )
        assert [attrs.get("rend") for attrs in preview_attrs] == [
            "align-left",
            "align-center",
            "align-right",
            "align-center",
        ]
        assert preview_attrs[1].get("width") == "40%"
        assert preview_attrs[2].get("width") == "300"
        assert preview_attrs[2].get("height") == "200"
    finally:
        remove_preview_artifact(artifact)

    report = build_site(config, config_path=config_path)
    assert report.success, report.errors
    site_html = (project_root / "site" / "figures" / "index.html").read_text(
        encoding="utf-8"
    )
    _assert_figure_html(site_html)
    site_attrs = _graphic_attributes(
        project_root / "build" / "tei" / "pages" / "figures.xml"
    )
    assert [attrs.get("rend") for attrs in site_attrs] == [
        "align-left",
        "align-center",
        "align-right",
        "align-center",
    ]
