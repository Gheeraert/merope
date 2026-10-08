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


@pytest.mark.parametrize(
    "caption",
    [
        "# Titre",
        "- élément",
        "> citation",
        "1. premier",
        "---",
        "::::",
        "<strong>HTML</strong>",
        "Vidéo : « essai » — n° 1.",
    ],
    ids=[
        "atx-heading",
        "bullet-list",
        "blockquote",
        "ordered-list",
        "thematic-break",
        "fenced-div-close",
        "raw-html",
        "ordinary-punctuation",
    ],
)
def test_caption_with_markdown_block_syntax_is_preserved_as_literal_text(tmp_path, caption):
    """A caption typed into the Qt dialog is plain, single-line text that
    must never turn into a Markdown block construct of its own (heading,
    list, blockquote, thematic break, or -- worse -- a premature close of
    this very fenced div) nor into interpreted raw HTML; see
    bloggen.markdown.video_syntax's systematic punctuation-escaping of the
    caption. The Lua filter's own requirement that the caption be a
    single Para/Plain block is left untouched and still doing real work
    here: an insufficiently escaped caption would make it refuse with
    "la légende doit être un paragraphe simple" instead of reaching this
    point at all.
    """

    block = format_video_block(VALID_ID, caption)  # (1) serializable
    assert block  # non-empty: format_video_block did not raise

    body = block + "\n"
    path, tree = _convert(tmp_path, body)  # (3) Markdown -> TEI succeeds

    # (4) Commons Publishing validation still passes.
    validation = validate_commons_publishing_file(path)
    assert validation.valid is True, validation.issues

    # (2) Only one figure/figDesc was produced -- no extra heading, list,
    # blockquote or div sibling from a misparsed caption, and the Lua
    # filter's "single Para/Plain" requirement was therefore satisfied,
    # not bypassed.
    figures = tree.xpath("//t:figure", namespaces=TEI_NS)
    assert len(figures) == 1
    fig_desc = figures[0].xpath("t:figDesc", namespaces=TEI_NS)
    assert len(fig_desc) == 1

    # (5) The literal caption text survives, with no Markdown or HTML
    # interpretation left in it.
    assert "".join(fig_desc[0].itertext()) == caption

    xml = path.read_text(encoding="utf-8")
    assert "<strong>" not in xml and "</strong>" not in xml


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


def test_lua_id_grammar_matches_python_grammar_exactly(tmp_path):
    """The Lua filter's own id validation must accept/reject exactly what
    :func:`bloggen.markdown.video_syntax.is_valid_youtube_id` does (ASCII
    letters, digits, ``_`` and ``-`` only) — not Lua's locale-dependent
    ``%w``, which is not guaranteed to match only ASCII alphanumerics."""

    from bloggen.markdown.video_syntax import is_valid_youtube_id

    mixed_charset_id = "A1-2_B3-4C"  # exactly the allowed charset, len 10
    assert len(mixed_charset_id) == 10
    full_id = mixed_charset_id + "9"  # 11 chars, still only the allowed charset
    assert is_valid_youtube_id(full_id) is True

    source = tmp_path / "doc.md"
    source.write_text(
        f':::: {{.merope-video data-provider="youtube" data-video-id="{full_id}"}}\n::::\n',
        encoding="utf-8",
    )
    result = convert_markdown_file_to_tei(source, tmp_path / "doc.xml")
    assert result.success is True, result.message


def test_lua_filter_uses_explicit_ascii_ranges_not_locale_dependent_w():
    lua_source = VIDEO_LUA_FILTER.read_text(encoding="utf-8")
    assert "id:match('^[A-Za-z0-9_%-]+$')" in lua_source
    assert "[%w" not in lua_source


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


def test_video_without_width_has_no_rendition_and_validates(tmp_path):
    body = format_video_block(VALID_ID, "Une légende.") + "\n"
    path, tree = _convert(tmp_path, body)

    paragraphs = tree.xpath("//t:p[t:figure]", namespaces=TEI_NS)
    assert len(paragraphs) == 1
    assert paragraphs[0].get("rendition") is None

    validation = validate_commons_publishing_file(path)
    assert validation.valid is True, validation.issues


def test_video_with_width_75_carries_rendition_and_validates(tmp_path):
    body = format_video_block(VALID_ID, "Une légende.", width=75) + "\n"
    path, tree = _convert(tmp_path, body)

    paragraphs = tree.xpath("//t:p[t:figure]", namespaces=TEI_NS)
    assert len(paragraphs) == 1
    assert paragraphs[0].get("rendition") == "urn:merope:video-width:75"

    figures = tree.xpath("//t:figure", namespaces=TEI_NS)
    assert len(figures) == 1
    assert figures[0].get("n") == VALID_ID

    validation = validate_commons_publishing_file(path)
    assert validation.valid is True, validation.issues


@pytest.mark.parametrize("width", ["0", "24", "101", "-1", "50%", "abc", "75.5"])
def test_invalid_hand_written_width_is_refused(tmp_path, width):
    source = tmp_path / "doc.md"
    source.write_text(
        ':::: {.merope-video data-provider="youtube" data-video-id="'
        + VALID_ID
        + '" data-width="'
        + width
        + '"}\n::::\n',
        encoding="utf-8",
    )
    result = convert_markdown_file_to_tei(source, tmp_path / "doc.xml")
    assert result.success is False
    assert "Vidéo Mérope" in result.message


def test_html_video_width_75_sets_custom_property_and_keeps_ratio(tmp_path):
    body = format_video_block(VALID_ID, width=75) + "\n"
    html = _render(tmp_path, body)
    document = etree.HTML(html)

    figures = document.xpath("//figure[@class='video-embed']")
    assert len(figures) == 1
    style = figures[0].get("style") or ""
    assert "--video-width:75%" in style

    iframes = figures[0].xpath(".//iframe")
    assert len(iframes) == 1
    assert iframes[0].get("src") == f"https://www.youtube-nocookie.com/embed/{VALID_ID}"


def test_html_video_width_50(tmp_path):
    body = format_video_block(VALID_ID, width=50) + "\n"
    html = _render(tmp_path, body)
    document = etree.HTML(html)

    figures = document.xpath("//figure[@class='video-embed']")
    assert "--video-width:50%" in (figures[0].get("style") or "")


def test_html_video_width_100_has_no_inline_style(tmp_path):
    body = format_video_block(VALID_ID, width=100) + "\n"
    html = _render(tmp_path, body)
    document = etree.HTML(html)

    figures = document.xpath("//figure[@class='video-embed']")
    assert len(figures) == 1
    assert not (figures[0].get("style") or "").strip()


def test_html_video_without_width_attribute_defaults_to_100(tmp_path):
    body = format_video_block(VALID_ID) + "\n"
    html = _render(tmp_path, body)
    document = etree.HTML(html)

    figures = document.xpath("//figure[@class='video-embed']")
    assert len(figures) == 1
    assert not (figures[0].get("style") or "").strip()


def test_video_survives_lightbox_and_notes_post_processing_with_trailing_text(tmp_path):
    """Reproduces the real-post bug: the XSLT fragment is correct on its own,
    but apply_lightbox_markup() and apply_notes_rendering() used to
    re-serialize it with lxml's default XML method, which self-closes the
    empty-content <iframe> as ``<iframe .../>``. Browsers do not treat
    iframe as a void element, so everything after it in the DOM was pulled
    in as the iframe's fallback content and vanished from the page.
    """

    from bloggen.render.lightbox import apply_lightbox_markup
    from bloggen.render.margin_notes import apply_notes_rendering

    body = (
        format_video_block(VALID_ID, "Une légende.")
        + "\n\nTexte après la vidéo.\n"
    )
    html_fragment = _render(tmp_path, body)

    lightbox_result = apply_lightbox_markup(
        html_fragment,
        enabled=True,
        group_name="essai",
        use_caption=True,
    )
    notes_result = apply_notes_rendering(
        lightbox_result.html_fragment,
        enable_margin_notes=False,
        enable_footnotes=True,
        excerpt_words=4,
        excerpt_chars=30,
        prefer_words=True,
    )
    final_html = notes_result.html_fragment

    assert "</iframe>" in final_html
    assert "/>" not in final_html
    assert "Texte après la vidéo." in final_html

    document = etree.HTML(final_html)
    paragraphs = document.xpath("//p[contains(text(), 'Texte après la vidéo.')]")
    assert len(paragraphs) == 1
    assert paragraphs[0].xpath("ancestor::iframe") == []


def test_lua_filters_are_shipped_in_a_deterministic_order():
    from bloggen.tei.pandoc_converter import convert_markdown_to_tei
    import inspect

    source = inspect.getsource(convert_markdown_to_tei)
    assert source.index("ENCADRE_LUA_FILTER") < source.index("VIDEO_LUA_FILTER")
