from __future__ import annotations

from bloggen.tei.validator import validate_tei_xml

_ORDINARY_TEI = (
    '<TEI xmlns="http://www.tei-c.org/ns/1.0">'
    "<teiHeader><fileDesc><titleStmt><title>Test</title></titleStmt>"
    "<publicationStmt><p>p</p></publicationStmt><sourceDesc><p>s</p></sourceDesc></fileDesc></teiHeader>"
    "<text><body><p>Bonjour</p></body></text>"
    "</TEI>"
)


def test_ordinary_tei_is_still_valid():
    result = validate_tei_xml(_ORDINARY_TEI)

    assert result.valid is True
    assert result.errors == []


def test_malformed_xml_is_invalid_with_a_clear_message():
    result = validate_tei_xml("<TEI><text><body><p>Bonjour</body></text></TEI>")

    assert result.valid is False
    assert result.errors


def test_a_bare_doctype_is_rejected_with_a_dtd_policy_message():
    xml = "<!DOCTYPE TEI>\n" + _ORDINARY_TEI

    result = validate_tei_xml(xml)

    assert result.valid is False
    assert any("DOCTYPE" in error or "DTD" in error for error in result.errors)


def test_an_internal_entity_declaration_is_rejected_without_being_resolved():
    xml = (
        "<!DOCTYPE TEI [\n"
        '  <!ENTITY local "SECRET_CONTENT">\n'
        "]>\n"
        '<TEI xmlns="http://www.tei-c.org/ns/1.0">'
        "<teiHeader><fileDesc><titleStmt><title>Test</title></titleStmt>"
        "<publicationStmt><p>p</p></publicationStmt><sourceDesc><p>s</p></sourceDesc></fileDesc></teiHeader>"
        "<text><body><p>&local;</p></body></text>"
        "</TEI>"
    )

    result = validate_tei_xml(xml)

    assert result.valid is False
    assert any("DOCTYPE" in error or "DTD" in error for error in result.errors)
    assert not any("SECRET_CONTENT" in error for error in result.errors)


def test_an_external_file_entity_is_rejected_and_never_read(tmp_path):
    secret = tmp_path / "secret.txt"
    secret.write_text("SECRET_FILE_CONTENT", encoding="utf-8")
    secret_uri = secret.resolve().as_uri()
    xml = (
        "<!DOCTYPE TEI [\n"
        f'  <!ENTITY xxe SYSTEM "{secret_uri}">\n'
        "]>\n"
        '<TEI xmlns="http://www.tei-c.org/ns/1.0">'
        "<teiHeader><fileDesc><titleStmt><title>Test</title></titleStmt>"
        "<publicationStmt><p>p</p></publicationStmt><sourceDesc><p>s</p></sourceDesc></fileDesc></teiHeader>"
        "<text><body><p>&xxe;</p></body></text>"
        "</TEI>"
    )

    result = validate_tei_xml(xml)

    assert result.valid is False
    assert not any("SECRET_FILE_CONTENT" in error for error in result.errors)
