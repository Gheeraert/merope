"""Embedded video: Pandoc Markdown -> TEI Commons Publishing -> HTML."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from lxml import etree

from bloggen.tei.commons_publishing import validate_commons_publishing_file
from bloggen.tei.pandoc_converter import (
    ENCADRE_LUA_FILTER,
    VIDEO_LUA_FILTER,
    convert_markdown_file_to_tei,
)
from bloggen.markdown.video_syntax import format_video_block

pytestmark = pytest.mark.skipif(shutil.which("pandoc") is None, reason="Pandoc requis")

TEI_NS = {"t": "http://www.tei-c.org/ns/1.0"}
VALID_ID = "dQw4w9WgXcQ"


def _convert(tmp_path: Path, body: str) -> tuple[Path, etree._ElementTree]:
    source = tmp_path / "doc.md"
    source.write_text(f"---\ntitle: Essai\n---\n\n{body}", encoding="utf-8")
    result = convert_markdown_file_to_tei(source, tmp_path / "doc.xml")
    assert result.success, result.message
    return result.tei_file, etree.parse(str(result.tei_file))


def test_lua_filter_is_shipped_with_the_package():
    assert VIDEO_LUA_FILTER.is_file()


def test_video_with_caption_becomes_figure_ref_figdesc_and_validates(tmp_path):
    body = format_video_block(VALID_ID, "Une légende.") + "\n"
    path, tree = _convert(tmp_path, body)

    figures = tree.xpath("//t:figure", namespaces=TEI_NS)
    assert len(figures) == 1
    figure = figures[0]
    assert figure.get("n") == VALID_ID

    refs = figure.xpath("t:p/t:ref", namespaces=TEI_NS)
    assert len(refs) == 1
    ref = refs[0]
    assert ref.get("type") == "video-youtube"
    assert ref.get("target") == f"https://www.youtube.com/watch?v={VALID_ID}"

    fig_desc = figure.xpath("t:figDesc", namespaces=TEI_NS)
    assert len(fig_desc) == 1
    assert "".join(fig_desc[0].itertext()) == "Une légende."

    xml = path.read_text(encoding="utf-8")
    assert "merope-video" not in xml
    assert "<media" not in xml and "<ptr" not in xml

    validation = validate_commons_publishing_file(path)
    assert validation.valid is True, validation.issues


def test_video_without_caption_has_no_figdesc_and_validates(tmp_path):
    body = format_video_block(VALID_ID) + "\n"
    path, tree = _convert(tmp_path, body)

    figures = tree.xpath("//t:figure", namespaces=TEI_NS)
    assert len(figures) == 1
    assert not figures[0].xpath("t:figDesc", namespaces=TEI_NS)

    validation = validate_commons_publishing_file(path)
    assert validation.valid is True, validation.issues


def test_video_coexists_with_encadre_and_image(tmp_path):
    body = (
        "![Une image](photo.jpg)\n\n"
        + format_video_block(VALID_ID, "Légende vidéo.")
        + "\n\n"
        + ":::: {.merope-encadre}\nTexte de l'encadré.\n::::\n"
    )
    path, tree = _convert(tmp_path, body)

    assert len(tree.xpath("//t:figure[t:graphic]", namespaces=TEI_NS)) == 1
    assert len(tree.xpath("//t:figure[@n]", namespaces=TEI_NS)) == 1
    assert len(tree.xpath("//t:floatingText", namespaces=TEI_NS)) == 1
    assert validate_commons_publishing_file(path).valid is True


def test_unsupported_provider_is_refused(tmp_path):
    source = tmp_path / "doc.md"
    source.write_text(
        ':::: {.merope-video data-provider="vimeo" data-video-id="12345678901"}\n::::\n',
        encoding="utf-8",
    )
    result = convert_markdown_file_to_tei(source, tmp_path / "doc.xml")
    assert result.success is False
    assert "Vidéo Mérope" in result.message


@pytest.mark.parametrize(
    "video_id",
    ["short", "has space!!", "way-too-long-id-value", ""],
)
def test_malformed_video_id_is_refused(tmp_path, video_id):
    source = tmp_path / "doc.md"
    source.write_text(
        f':::: {{.merope-video data-provider="youtube" data-video-id="{video_id}"}}\n::::\n',
        encoding="utf-8",
    )
    result = convert_markdown_file_to_tei(source, tmp_path / "doc.xml")
    assert result.success is False
    assert "Vidéo Mérope" in result.message


def test_more_than_one_caption_block_is_refused(tmp_path):
    source = tmp_path / "doc.md"
    source.write_text(
        ':::: {.merope-video data-provider="youtube" data-video-id="'
        + VALID_ID
        + '"}\nUn.\n\nDeux.\n::::\n',
        encoding="utf-8",
    )
    result = convert_markdown_file_to_tei(source, tmp_path / "doc.xml")
    assert result.success is False
    assert "Vidéo Mérope" in result.message


def _render(tmp_path: Path, body: str) -> str:
    from bloggen.render.xslt_runner import render_tei_file_to_html_fragment

    path, _tree = _convert(tmp_path, body)
    return render_tei_file_to_html_fragment(path, parameters={"article_slug": "essai"})


def test_html_video_is_a_responsive_iframe_with_fallback_link_and_caption(tmp_path):
    body = format_video_block(VALID_ID, "Une légende.") + "\n"
    html = _render(tmp_path, body)
    document = etree.HTML(html)

    figures = document.xpath("//figure[@class='video-embed']")
    assert len(figures) == 1
    figure = figures[0]

    iframes = figure.xpath(".//iframe")
    assert len(iframes) == 1
    iframe = iframes[0]
    assert iframe.get("src") == f"https://www.youtube-nocookie.com/embed/{VALID_ID}"
    assert iframe.get("loading") == "lazy"
    assert iframe.get("allowfullscreen") == "allowfullscreen"
    assert iframe.get("referrerpolicy") == "strict-origin-when-cross-origin"
    assert iframe.get("title")
    assert "youtube.com/watch" not in (iframe.get("src") or "")

    fallback_links = figure.xpath(".//a[@href]")
    assert len(fallback_links) == 1
    assert fallback_links[0].get("href") == f"https://www.youtube.com/watch?v={VALID_ID}"

    captions = figure.xpath("figcaption")
    assert len(captions) == 1
    assert "".join(captions[0].itertext()) == "Une légende."


def test_html_video_without_caption_has_no_figcaption(tmp_path):
    body = format_video_block(VALID_ID) + "\n"
    html = _render(tmp_path, body)
    document = etree.HTML(html)

    figures = document.xpath("//figure[@class='video-embed']")
    assert len(figures) == 1
    assert not figures[0].xpath("figcaption")


def test_html_image_figures_are_unaffected(tmp_path):
    body = "![Une image](photo.jpg)\n"
    html = _render(tmp_path, body)
    document = etree.HTML(html)

    figures = document.xpath("//figure")
    assert len(figures) == 1
    assert figures[0].get("class") == "article-figure"
    assert figures[0].xpath(".//img")
    assert not figures[0].xpath(".//iframe")


def test_lua_filters_are_shipped_in_a_deterministic_order():
    from bloggen.tei.pandoc_converter import convert_markdown_to_tei
    import inspect

    source = inspect.getsource(convert_markdown_to_tei)
    assert source.index("ENCADRE_LUA_FILTER") < source.index("VIDEO_LUA_FILTER")
