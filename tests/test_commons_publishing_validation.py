"""bloggen.tei.commons_publishing: diagnostic validation of generated TEI
against the TEI Commons Publishing schema bundled from the companion
project Mini-Métopes — both its RelaxNG grammar and its embedded
Schematron assertions. Purely informational: never blocks a build, see
the module's own docstring for what's still known not to validate.
"""

from __future__ import annotations

from bloggen.tei.commons_publishing import (
    validate_commons_publishing_bytes,
    validate_commons_publishing_file,
)

_MINIMAL_VALID_TEI = b"""<TEI xmlns="http://www.tei-c.org/ns/1.0">
<teiHeader><fileDesc><titleStmt><title>Test</title></titleStmt>
<publicationStmt><p>p</p></publicationStmt><sourceDesc><p>s</p></sourceDesc></fileDesc></teiHeader>
<text><body><div><head>Titre</head><p>Contenu.</p></div></body></text>
</TEI>"""


def test_a_minimal_well_formed_tei_document_validates():
    result = validate_commons_publishing_bytes(_MINIMAL_VALID_TEI)
    assert result.valid is True
    assert result.issues == ()


def test_malformed_xml_is_reported_as_invalid_not_raised():
    result = validate_commons_publishing_bytes(b"<TEI><not-closed>")
    assert result.valid is False
    assert len(result.issues) >= 1


def test_a_document_missing_the_tei_root_is_reported_as_invalid():
    result = validate_commons_publishing_bytes(b"<not-tei/>")
    assert result.valid is False
    assert len(result.issues) >= 1


def test_pandocs_own_div_type_convention_is_rejected():
    """Documents Pandoc's real (unmodified) generic TEI output: it types
    each <div> "level1", "level2"... for its heading depth, but Commons
    Publishing's <div> does not declare @type as a permitted attribute
    at all in this schema customization. An undeclared attribute makes
    RelaxNG treat the whole element as not matching its specific
    pattern, which is why the reported errors cascade ("did not expect
    element body/div/p there") instead of naming the attribute
    directly. This exact shape (div/@type="levelN") is what MEROPE's
    real Pandoc-based build produces today (verified directly against a
    real build while researching this integration) — see the module
    docstring and the roadmap towards closing this gap."""
    data = b"""<TEI xmlns="http://www.tei-c.org/ns/1.0">
<teiHeader><fileDesc><titleStmt><title>Test</title></titleStmt>
<publicationStmt><p>p</p></publicationStmt><sourceDesc><p>s</p></sourceDesc></fileDesc></teiHeader>
<text><body><div type="level1" xml:id="un-billet"><head>Titre</head><p>Un paragraphe.</p>
<div type="level2" xml:id="une-section"><head>Sous-section</head><p>Un autre paragraphe.</p></div>
</div></body></text>
</TEI>"""
    result = validate_commons_publishing_bytes(data)
    assert result.valid is False
    assert len(result.issues) >= 1


def test_validate_commons_publishing_file_reads_from_disk(tmp_path):
    path = tmp_path / "sample.xml"
    path.write_bytes(_MINIMAL_VALID_TEI)
    result = validate_commons_publishing_file(path)
    assert result.valid is True


def test_the_schema_is_only_compiled_once():
    """_commons_publishing_schema is lru_cache'd — two calls must return
    the exact same compiled RelaxNG object, not recompile it."""
    from bloggen.tei.commons_publishing import _commons_publishing_schema

    first = _commons_publishing_schema()
    second = _commons_publishing_schema()
    assert first is second


def test_the_schematron_is_only_compiled_once():
    from bloggen.tei.commons_publishing import _commons_publishing_schematron

    first = _commons_publishing_schematron()
    second = _commons_publishing_schematron()
    assert first is second


def test_a_relaxng_valid_document_violating_a_schematron_only_rule_is_still_rejected():
    """<desc type="deprecationInfo"> is legal TEI content wherever <desc>
    itself is (RelaxNG has no opinion on it) — only a Schematron rule in
    the bundled schema restricts it to elements carrying @validUntil.
    Before this validator also ran Schematron, a document like this one
    passed as "valid Commons Publishing TEI" despite violating a real
    constraint of the profile."""
    data = b"""<TEI xmlns="http://www.tei-c.org/ns/1.0">
<teiHeader><fileDesc><titleStmt><title>Test</title></titleStmt>
<publicationStmt><p>p</p></publicationStmt><sourceDesc><p>s</p></sourceDesc>
<encodingDesc><specGrp xml:id="specs"><specGrpRef target="#specs"/>
<desc type="deprecationInfo">Obsolete.</desc></specGrp></encodingDesc>
</fileDesc></teiHeader>
<text><body><div><head>Titre</head><p>Contenu.</p></div></body></text>
</TEI>"""
    result = validate_commons_publishing_bytes(data)
    assert result.valid is False
    assert any("deprecat" in issue.message.lower() for issue in result.issues)


def test_a_document_satisfying_every_schematron_rule_still_validates():
    """Guards against a rewrite of _rewrite_xpath2_comparison_operators
    (or an lxml/libxslt upgrade) silently making every document fail —
    the minimal valid document exercises none of the 9 embedded rules'
    contexts, so this adds one that at least reaches a fired-rule/
    successful-report branch without tripping it."""
    data = b"""<TEI xmlns="http://www.tei-c.org/ns/1.0">
<teiHeader><fileDesc><titleStmt><title>Test</title></titleStmt>
<publicationStmt><p>p</p></publicationStmt><sourceDesc><p>s</p></sourceDesc></fileDesc></teiHeader>
<text><body><div><head>Titre</head><p>Le <date when="2026">2026</date>.</p></div></body></text>
</TEI>"""
    result = validate_commons_publishing_bytes(data)
    assert result.valid is True
    assert result.issues == ()
