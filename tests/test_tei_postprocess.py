from __future__ import annotations

from bloggen.tei.postprocess import postprocess_tei_xml
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
