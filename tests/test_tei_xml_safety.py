from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest
from lxml import etree

from bloggen.tei.xml_safety import (
    UnsafeXmlError,
    parse_xml_safely,
    parse_xml_safely_for_elementtree,
)

_ORDINARY_TEI = (
    '<TEI xmlns="http://www.tei-c.org/ns/1.0">'
    "<teiHeader/><text><body><p>Bonjour</p></body></text>"
    "</TEI>"
)


def test_ordinary_tei_is_accepted():
    root = parse_xml_safely(_ORDINARY_TEI)

    assert isinstance(root, etree._Element)
    assert root.tag == "{http://www.tei-c.org/ns/1.0}TEI"


def test_predefined_entities_still_work():
    root = parse_xml_safely("<TEI><p>A &amp; B</p></TEI>")

    assert root.find("p").text == "A & B"


def test_malformed_xml_is_rejected():
    with pytest.raises(UnsafeXmlError):
        parse_xml_safely("<TEI><p>Bonjour</TEI>")


def test_bare_doctype_without_entities_is_rejected():
    xml = "<!DOCTYPE TEI>\n" + _ORDINARY_TEI

    with pytest.raises(UnsafeXmlError, match="DOCTYPE"):
        parse_xml_safely(xml)


def test_internal_entity_declaration_is_rejected():
    xml = (
        "<!DOCTYPE TEI [\n"
        '  <!ENTITY local "SECRET">\n'
        "]>\n"
        "<TEI><p>&local;</p></TEI>"
    )

    with pytest.raises(UnsafeXmlError, match="DOCTYPE"):
        parse_xml_safely(xml)


def test_external_file_entity_is_rejected_and_never_read(tmp_path):
    secret = tmp_path / "secret.txt"
    secret.write_text("SECRET_FILE_CONTENT", encoding="utf-8")
    secret_uri = secret.resolve().as_uri()
    xml = (
        "<!DOCTYPE TEI [\n"
        f'  <!ENTITY xxe SYSTEM "{secret_uri}">\n'
        "]>\n"
        "<TEI><p>&xxe;</p></TEI>"
    )

    with pytest.raises(UnsafeXmlError, match="DOCTYPE") as excinfo:
        parse_xml_safely(xml)

    assert "SECRET_FILE_CONTENT" not in str(excinfo.value)


def test_external_http_entity_never_triggers_a_network_request():
    """No real server is spun up: rejecting the DOCTYPE before any entity
    is ever expanded is what structurally prevents the network access,
    regardless of the scheme the (never-resolved) entity would have used —
    this only has to prove the document is refused outright."""
    xml = (
        "<!DOCTYPE TEI [\n"
        '  <!ENTITY xxe SYSTEM "http://127.0.0.1:1/should-not-be-contacted">\n'
        "]>\n"
        "<TEI><p>&xxe;</p></TEI>"
    )

    with pytest.raises(UnsafeXmlError, match="DOCTYPE"):
        parse_xml_safely(xml)


def test_for_elementtree_variant_returns_a_stdlib_element_with_the_same_namespace():
    root = parse_xml_safely_for_elementtree(_ORDINARY_TEI)

    assert isinstance(root, ET.Element)
    assert root.tag == "{http://www.tei-c.org/ns/1.0}TEI"


def test_for_elementtree_variant_also_rejects_a_doctype():
    xml = "<!DOCTYPE TEI>\n" + _ORDINARY_TEI

    with pytest.raises(UnsafeXmlError, match="DOCTYPE"):
        parse_xml_safely_for_elementtree(xml)


def test_for_elementtree_variant_preserves_predefined_entities_and_structure():
    xml = '<TEI xmlns="http://www.tei-c.org/ns/1.0"><text><body><p>A &amp; B</p></body></text></TEI>'

    root = parse_xml_safely_for_elementtree(xml)

    body = root.find("{http://www.tei-c.org/ns/1.0}text/{http://www.tei-c.org/ns/1.0}body")
    paragraph = body.find("{http://www.tei-c.org/ns/1.0}p")
    assert paragraph.text == "A & B"


def test_comments_are_dropped_like_the_stdlib_parser_used_to_do():
    """xml.etree.ElementTree.fromstring (what every caller used before)
    silently drops comments; lxml keeps them as nodes with a callable
    .tag unless told otherwise — this must not surface as a broken
    .tag.startswith(...) call somewhere downstream."""
    xml = "<TEI><!-- a comment --><p>Bonjour</p></TEI>"

    root = parse_xml_safely(xml)

    assert [child.tag for child in root] == ["p"]
