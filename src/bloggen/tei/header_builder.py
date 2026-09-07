"""Helpers to build a real TEI header — author(s), dates, source,
licence, language, and edit history — instead of the placeholder
strings this used to fall back to unconditionally.

Phase 2 of the roadmap towards TEI Commons Publishing (see
bloggen.tei.commons_publishing's module docstring, and the report
produced while examining the companion project Mini-Métopes,
C:/mini-metopes / https://github.com/Gheeraert/mini-metopes, whose own
metadata model and teiHeader serializer this is inspired by, adapted
to MEROPE's much simpler blog/page front matter instead of a separate
JSON metadata file). This alone does not make the generated TEI
Commons-Publishing-valid — that still needs Phase 3's native
serializer — but it closes the specific "auteurs, dates, source,
licence, langue, historique" gap the second external audit named.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import xml.etree.ElementTree as ET

TEI_NAMESPACE = "http://www.tei-c.org/ns/1.0"
XML_NAMESPACE = "http://www.w3.org/XML/1998/namespace"


@dataclass(slots=True, frozen=True)
class TeiHeaderMetadata:
    """Everything ensure_minimal_tei_header can enrich the header with,
    beyond the bare title it always accepted. Every field is optional —
    absent ones are simply not serialized, never replaced by a
    placeholder (a missing licence must not look like a real one)."""

    title: str | None = None
    author: str | None = None
    orcid: str | None = None
    language: str | None = None
    published_date: str | None = None
    updated_date: str | None = None
    license_name: str | None = None
    license_url: str | None = None
    keywords: tuple[str, ...] = field(default_factory=tuple)
    publisher: str | None = None
    source_description: str | None = None


def ensure_minimal_tei_header(
    root: ET.Element, *, title: str | None = None, metadata: TeiHeaderMetadata | None = None
) -> None:
    ns = _namespace_from_tag(root.tag)
    q = lambda name: _qname(ns, name)
    effective_title = title or (metadata.title if metadata else None)

    tei_header = _find_child(root, "teiHeader")
    if tei_header is None:
        tei_header = ET.SubElement(root, q("teiHeader"))

    file_desc = _find_child(tei_header, "fileDesc")
    if file_desc is None:
        file_desc = ET.SubElement(tei_header, q("fileDesc"))

    _ensure_title_stmt(file_desc, q, title=effective_title, metadata=metadata)
    _ensure_publication_stmt(file_desc, q, metadata=metadata)
    _ensure_source_desc(file_desc, q, metadata=metadata)

    if metadata is not None and (metadata.language or metadata.keywords):
        _ensure_profile_desc(tei_header, q, metadata=metadata)

    if metadata is not None and metadata.updated_date and metadata.updated_date != metadata.published_date:
        _ensure_revision_desc(tei_header, q, metadata=metadata)


def _ensure_title_stmt(
    file_desc: ET.Element, q, *, title: str | None, metadata: TeiHeaderMetadata | None
) -> None:
    title_stmt = _find_child(file_desc, "titleStmt")
    if title_stmt is None:
        title_stmt = ET.SubElement(file_desc, q("titleStmt"))

    title_node = _find_child(title_stmt, "title")
    if title_node is None:
        title_node = ET.SubElement(title_stmt, q("title"))
    if title:
        title_node.text = title
    elif not (title_node.text or "").strip():
        title_node.text = "Untitled"

    # MEROPE's own front-matter author (when given) always supersedes
    # whatever <author> Pandoc's own TEI writer may already have put
    # here — the same "our own authoritative metadata wins" reasoning
    # as the title above.
    if metadata is not None and metadata.author:
        for existing in [child for child in title_stmt if _local_name(child.tag) == "author"]:
            title_stmt.remove(existing)
        author_node = ET.SubElement(title_stmt, q("author"))
        author_node.text = metadata.author
        if metadata.orcid:
            idno_node = ET.SubElement(author_node, q("idno"))
            idno_node.set("type", "ORCID")
            idno_node.text = metadata.orcid


def _ensure_publication_stmt(
    file_desc: ET.Element, q, *, metadata: TeiHeaderMetadata | None
) -> None:
    publication_stmt = _find_child(file_desc, "publicationStmt")
    if publication_stmt is None:
        publication_stmt = ET.SubElement(file_desc, q("publicationStmt"))

    has_enrichable_details = metadata is not None and (
        metadata.publisher or metadata.published_date or metadata.license_name
    )
    if not has_enrichable_details:
        if _find_child(publication_stmt, "p") is None and _find_child(publication_stmt, "publisher") is None:
            p_node = ET.SubElement(publication_stmt, q("p"))
            p_node.text = "Publication statique locale"
        return

    # Once there is real publication metadata to serialize, it replaces
    # whatever placeholder <p> Pandoc's own writer (or the fallback
    # above, on a previous run) may have put here — TEI's publicationStmt
    # allows either a bare <p> or the structured elements below, not
    # both, so keeping the placeholder alongside real data would be
    # actively misleading, not just redundant.
    for existing in list(publication_stmt):
        publication_stmt.remove(existing)

    if metadata.publisher:
        ET.SubElement(publication_stmt, q("publisher")).text = metadata.publisher
    if metadata.published_date:
        date_node = ET.SubElement(publication_stmt, q("date"))
        date_node.set("when", metadata.published_date)
        date_node.text = metadata.published_date
    if metadata.license_name:
        availability = ET.SubElement(publication_stmt, q("availability"))
        licence_node = ET.SubElement(availability, q("licence"))
        if metadata.license_url:
            licence_node.set("target", metadata.license_url)
        licence_node.text = metadata.license_name


def _ensure_source_desc(file_desc: ET.Element, q, *, metadata: TeiHeaderMetadata | None) -> None:
    source_desc = _find_child(file_desc, "sourceDesc")
    if source_desc is None:
        source_desc = ET.SubElement(file_desc, q("sourceDesc"))

    description = (metadata.source_description if metadata else None) or "Source Markdown"
    existing_p = _find_child(source_desc, "p")
    if existing_p is None:
        existing_p = ET.SubElement(source_desc, q("p"))
    # Always MEROPE's own description once one is available, in place of
    # Pandoc's own generic "Produced by pandoc." — same reasoning as the
    # title/author/publicationStmt enrichment above.
    if metadata is not None and metadata.source_description:
        existing_p.text = description
    elif not (existing_p.text or "").strip():
        existing_p.text = description


def _ensure_profile_desc(tei_header: ET.Element, q, *, metadata: TeiHeaderMetadata) -> None:
    profile_desc = _find_child(tei_header, "profileDesc")
    if profile_desc is None:
        profile_desc = ET.SubElement(tei_header, q("profileDesc"))

    if metadata.language:
        lang_usage = _find_child(profile_desc, "langUsage")
        if lang_usage is None:
            lang_usage = ET.SubElement(profile_desc, q("langUsage"))
        for existing in [child for child in lang_usage if _local_name(child.tag) == "language"]:
            lang_usage.remove(existing)
        language_node = ET.SubElement(lang_usage, q("language"))
        language_node.set("ident", metadata.language)
        language_node.text = metadata.language

    if metadata.keywords:
        text_class = _find_child(profile_desc, "textClass")
        if text_class is None:
            text_class = ET.SubElement(profile_desc, q("textClass"))
        for existing in [child for child in text_class if _local_name(child.tag) == "keywords"]:
            text_class.remove(existing)
        keywords_node = ET.SubElement(text_class, q("keywords"))
        list_node = ET.SubElement(keywords_node, q("list"))
        for keyword in metadata.keywords:
            ET.SubElement(list_node, q("item")).text = keyword


def _ensure_revision_desc(tei_header: ET.Element, q, *, metadata: TeiHeaderMetadata) -> None:
    revision_desc = _find_child(tei_header, "revisionDesc")
    if revision_desc is None:
        revision_desc = ET.SubElement(tei_header, q("revisionDesc"))
    change_node = ET.SubElement(revision_desc, q("change"))
    change_node.set("when", metadata.updated_date)


def ensure_text_body(root: ET.Element) -> None:
    ns = _namespace_from_tag(root.tag)
    q = lambda name: _qname(ns, name)

    text_node = _find_child(root, "text")
    if text_node is None:
        text_node = ET.SubElement(root, q("text"))

    body_node = _find_child(text_node, "body")
    if body_node is None:
        ET.SubElement(text_node, q("body"))


def _find_child(parent: ET.Element, local_name: str) -> ET.Element | None:
    for child in list(parent):
        if _local_name(child.tag) == local_name:
            return child
    return None


def _local_name(tag: str) -> str:
    if tag.startswith("{") and "}" in tag:
        return tag.split("}", maxsplit=1)[1]
    return tag


def _namespace_from_tag(tag: str) -> str | None:
    if tag.startswith("{") and "}" in tag:
        return tag[1:].split("}", maxsplit=1)[0]
    return None


def _qname(namespace: str | None, name: str) -> str:
    if namespace:
        return f"{{{namespace}}}{name}"
    return name
