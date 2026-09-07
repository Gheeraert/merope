from __future__ import annotations

import xml.etree.ElementTree as ET

from bloggen.tei.header_builder import TeiHeaderMetadata
from bloggen.tei.postprocess import (
    apply_image_attributes_in_tei_xml,
    apply_paragraph_alignment_in_tei_xml,
    postprocess_tei_xml,
    rewrite_graphic_urls_in_tei_xml,
)
from bloggen.tei.validator import validate_tei_xml

_TEI_NS = "{http://www.tei-c.org/ns/1.0}"


def test_postprocess_adds_header_to_minimal_tei():
    raw = "<TEI><text><body><p>Bonjour</p></body></text></TEI>"
    processed = postprocess_tei_xml(raw, title="Titre Test")
    assert "teiHeader" in processed
    assert "Titre Test" in processed


def test_header_metadata_enriches_author_orcid_dates_license_language_keywords():
    raw = '<TEI xmlns="http://www.tei-c.org/ns/1.0"><text><body><p>Bonjour</p></body></text></TEI>'
    metadata = TeiHeaderMetadata(
        title="Un billet",
        author="Marie Curie",
        orcid="0000-0002-1825-0097",
        language="fr",
        published_date="2026-01-01",
        updated_date="2026-03-15",
        license_name="CC BY 4.0",
        license_url="https://creativecommons.org/licenses/by/4.0/",
        keywords=("radioactivite", "physique"),
        publisher="Carnet de Recherche",
        source_description="Contenu Markdown converti pour Carnet de Recherche.",
    )
    processed = postprocess_tei_xml(raw, header_metadata=metadata)
    root = ET.fromstring(processed)

    author = root.find(f".//{_TEI_NS}author")
    assert author is not None and author.text == "Marie Curie"
    idno = author.find(f"{_TEI_NS}idno")
    assert idno is not None and idno.get("type") == "ORCID" and idno.text == "0000-0002-1825-0097"

    publisher = root.find(f".//{_TEI_NS}publisher")
    assert publisher is not None and publisher.text == "Carnet de Recherche"

    date = root.find(f".//{_TEI_NS}publicationStmt/{_TEI_NS}date")
    assert date is not None and date.get("when") == "2026-01-01"

    licence = root.find(f".//{_TEI_NS}licence")
    assert licence is not None and licence.text == "CC BY 4.0"
    assert licence.get("target") == "https://creativecommons.org/licenses/by/4.0/"

    source_p = root.find(f".//{_TEI_NS}sourceDesc/{_TEI_NS}p")
    assert source_p is not None and source_p.text == "Contenu Markdown converti pour Carnet de Recherche."

    language = root.find(f".//{_TEI_NS}langUsage/{_TEI_NS}language")
    assert language is not None and language.get("ident") == "fr"

    keyword_items = [item.text for item in root.findall(f".//{_TEI_NS}keywords/{_TEI_NS}list/{_TEI_NS}item")]
    assert keyword_items == ["radioactivite", "physique"]

    change = root.find(f".//{_TEI_NS}revisionDesc/{_TEI_NS}change")
    assert change is not None and change.get("when") == "2026-03-15"


def test_header_metadata_omits_revision_desc_when_updated_equals_published():
    raw = '<TEI xmlns="http://www.tei-c.org/ns/1.0"><text><body><p>Bonjour</p></body></text></TEI>'
    metadata = TeiHeaderMetadata(published_date="2026-01-01", updated_date="2026-01-01")
    processed = postprocess_tei_xml(raw, header_metadata=metadata)
    root = ET.fromstring(processed)
    assert root.find(f".//{_TEI_NS}revisionDesc") is None


def test_header_metadata_with_no_fields_set_leaves_the_placeholder_header():
    """No regression for the pre-Phase-2 behaviour: without any metadata
    at all, the header still gets its minimal placeholder content."""
    raw = "<TEI><text><body><p>Bonjour</p></body></text></TEI>"
    processed = postprocess_tei_xml(raw, title="Titre Test", header_metadata=TeiHeaderMetadata())
    assert "Publication statique locale" in processed
    assert "Source Markdown" in processed
    assert "author" not in processed
    assert "licence" not in processed


def test_header_metadata_author_overrides_pandocs_own_author_if_any():
    raw = (
        '<TEI xmlns="http://www.tei-c.org/ns/1.0"><teiHeader><fileDesc><titleStmt>'
        "<title>Un billet</title><author>Auteur Pandoc</author>"
        "</titleStmt></fileDesc></teiHeader><text><body><p>Bonjour</p></body></text></TEI>"
    )
    metadata = TeiHeaderMetadata(author="Marie Curie")
    processed = postprocess_tei_xml(raw, header_metadata=metadata)
    root = ET.fromstring(processed)
    authors = root.findall(f".//{_TEI_NS}author")
    assert len(authors) == 1
    assert authors[0].text == "Marie Curie"


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
        raw, {"media/a.jpg": [{"width": "300", "height": "200", "align": "left"}]}
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
    rewritten = apply_image_attributes_in_tei_xml(raw, {"media/a.jpg": [{"width": "300"}]})
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
    assert apply_image_attributes_in_tei_xml(raw, {"media/a.jpg": [{"width": "300"}]}) == raw


def test_apply_image_attributes_same_src_twice_applies_positionally():
    """Regression: two <graphic> elements sharing the same url used to both
    receive whichever attributes were recorded last for that src. Each
    occurrence must now get its own entry, in document order.
    """
    raw = (
        '<TEI xmlns="http://www.tei-c.org/ns/1.0">'
        "<text><body>"
        '<figure><graphic url="media/a.jpg"/></figure>'
        '<figure><graphic url="media/a.jpg"/></figure>'
        "</body></text>"
        "</TEI>"
    )
    rewritten = apply_image_attributes_in_tei_xml(
        raw,
        {"media/a.jpg": [{"width": "100"}, {"width": "400", "align": "center"}]},
    )
    import xml.etree.ElementTree as ET

    root = ET.fromstring(rewritten)
    graphics = root.findall(".//{http://www.tei-c.org/ns/1.0}graphic")
    assert [g.get("width") for g in graphics] == ["100", "400"]
    assert [g.get("rend") for g in graphics] == [None, "align-center"]


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
