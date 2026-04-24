from __future__ import annotations

from pathlib import Path
import uuid

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
    assert "<p>Bonjour</p>" in html


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
    assert '<li id="note-1">Note test</li>' in html


def test_transform_image_simple():
    tei = _tei_body(
        "<figure><head>Légende image</head><graphic url='assets/image.jpg'/></figure>"
    )
    html = render_tei_xml_to_html_fragment(tei)
    assert '<figure class="article-figure">' in html
    assert '<img src="assets/image.jpg" alt="Légende image">' in html
    assert "<figcaption>Légende image</figcaption>" in html


def test_transform_table_simple():
    tei = _tei_body(
        "<table><row><cell>A</cell><cell>B</cell></row><row><cell>1</cell><cell>2</cell></row></table>"
    )
    html = render_tei_xml_to_html_fragment(tei)
    assert "<table>" in html
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
