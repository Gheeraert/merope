"""Shared safe-parsing boundary for TEI XML handled by Mérope's own
validation/post-processing helpers (:mod:`bloggen.tei.validator`,
:mod:`bloggen.tei.postprocess`).

The TEI Mérope produces and manipulates always comes from Pandoc and never
needs a DOCTYPE, an external/internal DTD subset, or a custom entity
declaration — so rather than trying to make those safe, this parses with
network access, DTD loading, and entity resolution all disabled, and then
rejects outright any document that declares a DOCTYPE at all, DTD or not.
Confirmed by direct probing against the stdlib parser this replaces
(``xml.etree.ElementTree.fromstring``): it resolves an *internal* general
entity (e.g. ``<!ENTITY test "...">`` then ``&test;``) into that entity's
literal content by default — a real, reproducible gap, not just
theoretical hardening — while an *external* ``SYSTEM`` entity already
fails outright on this Python/libexpat build (external entity loading is
disabled upstream). Rejecting every DOCTYPE closes both cases uniformly,
without relying on that external-entity behaviour remaining true across
Python versions/platforms.

:mod:`bloggen.tei.commons_publishing` and :mod:`bloggen.render.xslt_runner`
already parse with the same no-network/no-DTD hardening for their own
XML inputs (the RelaxNG schema, a TEI document, a theme's XSLT) — this
module exists for the remaining callers that were still using the bare
stdlib parser, not to replace those two, which are left untouched.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from lxml import etree


class UnsafeXmlError(ValueError):
    """Raised when TEI XML fails Mérope's safe-parsing policy: malformed
    XML, or a document declaring a DOCTYPE (DTD or entity declarations),
    which is always rejected regardless of what it declares.
    """


def _safe_xml_parser() -> etree.XMLParser:
    # A fresh parser per call, not a shared module-level instance: an
    # XMLParser carries mutable per-document error state, and nothing here
    # is hot enough to need to amortize its construction cost.
    return etree.XMLParser(
        resolve_entities=False,
        no_network=True,
        load_dtd=False,
        dtd_validation=False,
        recover=False,
        huge_tree=False,
        # xml.etree.ElementTree.fromstring (what every caller of this
        # module used before) silently drops comments/PIs by default.
        # lxml keeps them as _Comment/_ProcessingInstruction nodes whose
        # .tag is a callable, not a string — code written against ET's
        # behaviour (e.g. validator.py's _local_name(node.tag)) would
        # break on either, so they're dropped here too to keep this a
        # safety boundary, not a behavioural change.
        remove_comments=True,
        remove_pis=True,
    )


def parse_xml_safely(xml: str | bytes) -> etree._Element:
    """Parse ``xml`` under Mérope's safe TEI policy and return the lxml root.

    Raises :class:`UnsafeXmlError` (a ``ValueError``) for malformed XML or
    a rejected DOCTYPE — never lets a raw ``lxml.etree.XMLSyntaxError``
    escape this boundary.
    """
    data = xml.encode("utf-8") if isinstance(xml, str) else xml
    try:
        root = etree.fromstring(data, parser=_safe_xml_parser())
    except etree.XMLSyntaxError as exc:
        raise UnsafeXmlError(f"XML TEI invalide (parse): {exc}") from exc
    # load_dtd=False only skips *fetching* an external subset; a DOCTYPE
    # declaration itself (internal subset, entity declarations, or a bare
    # `<!DOCTYPE TEI>`) is still recorded on the parsed document and must
    # be checked for explicitly — docinfo.doctype is the empty string when
    # no DOCTYPE was present at all.
    if root.getroottree().docinfo.doctype:
        raise UnsafeXmlError(
            "Les déclarations DOCTYPE/DTD ne sont pas autorisées dans le TEI Mérope."
        )
    return root


def parse_xml_safely_for_elementtree(xml: str | bytes) -> ET.Element:
    """Same policy as :func:`parse_xml_safely`, for callers built on
    :mod:`xml.etree.ElementTree` (Mérope's TEI post-processing mutates
    plain ``ET.Element`` trees, including via
    :mod:`bloggen.tei.header_builder`'s ``ET.SubElement`` calls, and
    isn't being rewritten onto lxml by this).

    The lxml root — already parsed safely, with no DOCTYPE, no resolved
    external entities, and no unresolved custom-entity nodes reachable —
    is re-serialized and handed to the stdlib parser, which then only
    ever sees XML this module has already vetted.
    """
    safe_root = parse_xml_safely(xml)
    serialized = etree.tostring(safe_root, encoding="unicode")
    return ET.fromstring(serialized)
