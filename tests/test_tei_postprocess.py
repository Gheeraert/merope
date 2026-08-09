from __future__ import annotations

from bloggen.tei.postprocess import (
    apply_image_attributes_in_tei_xml,
    apply_paragraph_alignment_in_tei_xml,
    postprocess_tei_xml,
    rewrite_graphic_urls_in_tei_xml,
)
from bloggen.tei.validator import validate_tei_xml


def test_postprocess_adds_header_to_minimal_tei():
    raw = "<TEI><text><body><p>Bonjour</p></body></text></TEI>"
    processed = postprocess_tei_xml(raw, title="Titre Test")
    assert "teiHeader" in processed
    assert "Titre Test" in processed


def test_validate_minimal_tei_success():
    raw = "<TEI><text><body><p>Bonjour</p></body></text></TEI>"
    processed = postprocess_tei_xml(raw)
    result = validate_tei_xml(processed)
    assert result.valid is True
    assert result.errors == []


def test_validate_xml_failure_on_invalid_xml():
    invalid_xml = "<TEI><text></TEI>"
    result = validate_tei_xml(invalid_xml)
    assert result.valid is False
    assert result.errors


def test_rewrite_graphic_urls_in_tei_xml():
    raw = (
        '<TEI xmlns="http://www.tei-c.org/ns/1.0">'
        "<text><body><figure><graphic url=\"media/a.jpg\"/></figure></body></text>"
        "</TEI>"
    )
    rewritten = rewrite_graphic_urls_in_tei_xml(raw, {"media/a.jpg": "../../content-media/post/a.jpg"})
    assert "../../content-media/post/a.jpg" in rewritten


def test_apply_image_attributes_sets_width_height_and_rend():
    raw = (
        '<TEI xmlns="http://www.tei-c.org/ns/1.0">'
        "<text><body><figure><graphic url=\"media/a.jpg\"/></figure></body></text>"
        "</TEI>"
    )
    rewritten = apply_image_attributes_in_tei_xml(
        raw, {"media/a.jpg": {"width": "300", "height": "200", "align": "left"}}
    )
    assert 'width="300"' in rewritten
    assert 'height="200"' in rewritten
    assert 'rend="align-left"' in rewritten


def test_apply_image_attributes_partial_attrs():
    raw = (
        '<TEI xmlns="http://www.tei-c.org/ns/1.0">'
        "<text><body><figure><graphic url=\"media/a.jpg\"/></figure></body></text>"
        "</TEI>"
    )
    rewritten = apply_image_attributes_in_tei_xml(raw, {"media/a.jpg": {"width": "300"}})
    assert 'width="300"' in rewritten
    assert "height=" not in rewritten
    assert "rend=" not in rewritten


def test_apply_image_attributes_noop_when_empty():
    raw = "<TEI><text><body><p>Bonjour</p></body></text></TEI>"
    assert apply_image_attributes_in_tei_xml(raw, {}) == raw


def test_apply_image_attributes_noop_when_no_matching_graphic():
    raw = (
        '<TEI xmlns="http://www.tei-c.org/ns/1.0">'
        "<text><body><figure><graphic url=\"media/other.jpg\"/></figure></body></text>"
        "</TEI>"
    )
    assert apply_image_attributes_in_tei_xml(raw, {"media/a.jpg": {"width": "300"}}) == raw


def test_apply_paragraph_alignment_strips_marker_and_sets_rend():
    raw = (
        '<TEI xmlns="http://www.tei-c.org/ns/1.0">'
        "<text><body><p>{{align=center}}Paragraphe centre.</p></body></text>"
        "</TEI>"
    )
    rewritten = apply_paragraph_alignment_in_tei_xml(raw)
    assert 'rend="align-center"' in rewritten
    assert "{{align=" not in rewritten
    assert "Paragraphe centre." in rewritten


def test_apply_paragraph_alignment_inside_blockquote():
    raw = (
        '<TEI xmlns="http://www.tei-c.org/ns/1.0">'
        "<text><body><quote><p>{{align=right}}Citation.</p></quote></body></text>"
        "</TEI>"
    )
    rewritten = apply_paragraph_alignment_in_tei_xml(raw)
    assert 'rend="align-right"' in rewritten
    assert "{{align=" not in rewritten


def test_apply_paragraph_alignment_noop_without_marker():
    raw = (
        '<TEI xmlns="http://www.tei-c.org/ns/1.0">'
        "<text><body><p>Paragraphe normal.</p></body></text>"
        "</TEI>"
    )
    assert apply_paragraph_alignment_in_tei_xml(raw) == raw


def test_apply_paragraph_alignment_ignores_unknown_marker_value():
    raw = (
        '<TEI xmlns="http://www.tei-c.org/ns/1.0">'
        "<text><body><p>{{align=bogus}}Paragraphe.</p></body></text>"
        "</TEI>"
    )
    assert apply_paragraph_alignment_in_tei_xml(raw) == raw
