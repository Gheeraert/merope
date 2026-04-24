from __future__ import annotations

from pathlib import Path
import uuid
import re

import pytest

from bloggen.render.xslt_runner import (
    render_tei_file_to_html_fragment,
    render_tei_xml_to_html_fragment,
)

RUNTIME_DIR = Path("tests/.runtime")
RUNTIME_DIR.mkdir(parents=True, exist_ok=True)


def _tei_body(inner: str) -> str:
    return (
        '<TEI xmlns="http://www.tei-c.org/ns/1.0">'
        '<text><body>'
        f"{inner}"
        '</body></text>'
        '</TEI>'
    )


def test_transform_simple_paragraph():
    tei = _tei_body("<p>Bonjour</p>")
    html = render_tei_xml_to_html_fragment(tei)
    assert 'class="tei-fragment article-main"' in html
    assert "<p>Bonjour</p>" in html


def test_transform_adds_article_meta_when_publication_date_is_available():
    tei = (
        '<TEI xmlns="http://www.tei-c.org/ns/1.0">'
        "<teiHeader><fileDesc><publicationStmt><date>2026-04-21</date></publicationStmt></fileDesc></teiHeader>"
        "<text><body><div><head>T</head><p>Body</p></div></body></text>"
        "</TEI>"
    )
    html = render_tei_xml_to_html_fragment(tei)
    assert 'class="article-meta"' in html
    assert '<time datetime="2026-04-21">2026-04-21</time>' in html


def test_transform_titles_and_divisions():
    tei = _tei_body("<div><head>Titre 1</head><div><head>Titre 2</head></div></div>")
    html = render_tei_xml_to_html_fragment(tei)
    assert "<section" in html
    assert "<h1>Titre 1</h1>" in html
    assert "<h2>Titre 2</h2>" in html


def test_transform_inline_styles():
    tei = _tei_body(
        "<p><hi rend='italic'>i</hi> <hi rend='bold'>b</hi> <hi rend='smallcaps'>s</hi></p>"
    )
    html = render_tei_xml_to_html_fragment(tei)
    assert "<em>i</em>" in html
    assert "<strong>b</strong>" in html
    assert '<span class="smallcaps">s</span>' in html


def test_transform_inline_styles_with_pandoc_rendition_attributes():
    tei = _tei_body(
        "<p><hi rendition='simple:italic'>italique</hi> et <hi rendition='simple:bold'>gras</hi></p>"
    )
    html = render_tei_xml_to_html_fragment(tei)
    assert "<em>italique</em>" in html
    assert "<strong>gras</strong>" in html


def test_transform_inline_styles_with_combined_rendition():
    tei = _tei_body("<p><hi rendition='simple:bold simple:italic'>mixte</hi></p>")
    html = render_tei_xml_to_html_fragment(tei)
    assert "<strong><em>mixte</em></strong>" in html


def test_transform_ref_to_link():
    tei = _tei_body("<p><ref target='https://example.org'>Lien</ref></p>")
    html = render_tei_xml_to_html_fragment(tei)
    assert '<a href="https://example.org">Lien</a>' in html


def test_transform_unordered_list():
    tei = _tei_body("<list><item>A</item><item>B</item></list>")
    html = render_tei_xml_to_html_fragment(tei)
    assert "<ul>" in html
    assert "<li>A</li>" in html
    assert "<li>B</li>" in html


def test_transform_ordered_list():
    tei = _tei_body("<list type='ordered'><item>A</item><item>B</item></list>")
    html = render_tei_xml_to_html_fragment(tei)
    assert "<ol>" in html
    assert "<li>A</li>" in html
    assert "<li>B</li>" in html


def test_transform_quote():
    tei = _tei_body("<quote>Texte cité</quote>")
    html = render_tei_xml_to_html_fragment(tei)
    assert "<blockquote>Texte cité</blockquote>" in html


def test_transform_note_call_and_endnotes_block():
    tei = _tei_body("<p>Texte<note>Note test</note></p>")
    html = render_tei_xml_to_html_fragment(tei)
    assert 'class="note-call"' in html
    assert 'href="#note-1"' in html
    assert '<section class="endnotes" id="endnotes">' in html
    assert '<li id="note-1" data-note-number="1">' in html
    assert 'class="note-backref" href="#note-call-1"' in html


def test_transform_image_simple():
    tei = _tei_body(
        "<figure><head>Légende image</head><graphic url='assets/image.jpg'/></figure>"
    )
    html = render_tei_xml_to_html_fragment(tei, parameters={"article_slug": "demo"})
    assert '<figure class="article-figure">' in html
    assert 'class="figure-image-link"' in html
    assert 'data-article-group="article-demo"' in html
    assert '<img src="assets/image.jpg" alt="Légende image">' in html
    assert "<figcaption>Légende image</figcaption>" in html


def test_transform_pandoc_like_figure_without_paragraph_wrapper_or_caption_duplicate():
    tei = Path("fixtures/pandoc_realistic/pandoc_like_output.tei").read_text(encoding="utf-8")
    html = render_tei_xml_to_html_fragment(tei, parameters={"article_slug": "demo"})

    assert "<em>italique</em>" in html
    assert "<strong>gras</strong>" in html
    assert "<figure" in html
    assert "<figcaption>Une image</figcaption>" in html
    assert re.search(r"<p>\s*<figure", html) is None
    assert "<p>Une image</p>" not in html


def test_transform_image_without_clickable_link():
    tei = _tei_body("<figure><graphic url='assets/image.jpg'/></figure>")
    html = render_tei_xml_to_html_fragment(tei, parameters={"clickable_figures": False})
    assert '<img src="assets/image.jpg" alt="Illustration">' in html
    assert "figure-image-link" not in html


def test_transform_table_simple():
    tei = _tei_body(
        "<table><row><cell>A</cell><cell>B</cell></row><row><cell>1</cell><cell>2</cell></row></table>"
    )
    html = render_tei_xml_to_html_fragment(tei)
    assert '<table class="tei-table">' in html
    assert "<tr>" in html
    assert "<td>A</td>" in html
    assert "<td>2</td>" in html


def test_error_on_invalid_xml():
    with pytest.raises(ValueError, match="XML TEI invalide"):
        render_tei_xml_to_html_fragment("<TEI><text></TEI>")


def test_error_on_missing_xslt():
    tei = _tei_body("<p>Bonjour</p>")
    missing = RUNTIME_DIR / f"missing_{uuid.uuid4().hex}.xsl"
    with pytest.raises(FileNotFoundError, match="XSLT introuvable"):
        render_tei_xml_to_html_fragment(tei, xslt_path=missing)


def test_transform_from_file():
    tei_path = RUNTIME_DIR / f"input_{uuid.uuid4().hex}.xml"
    tei_path.write_text(_tei_body("<p>Depuis fichier</p>"), encoding="utf-8")
    html = render_tei_file_to_html_fragment(tei_path)
    assert "<p>Depuis fichier</p>" in html
