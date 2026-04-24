"""Helpers to ensure a minimal TEI header."""

from __future__ import annotations

import xml.etree.ElementTree as ET

TEI_NAMESPACE = "http://www.tei-c.org/ns/1.0"


def ensure_minimal_tei_header(root: ET.Element, *, title: str | None = None) -> None:
    ns = _namespace_from_tag(root.tag)
    q = lambda name: _qname(ns, name)

    tei_header = _find_child(root, "teiHeader")
    if tei_header is None:
        tei_header = ET.SubElement(root, q("teiHeader"))

    file_desc = _find_child(tei_header, "fileDesc")
    if file_desc is None:
        file_desc = ET.SubElement(tei_header, q("fileDesc"))

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

    publication_stmt = _find_child(file_desc, "publicationStmt")
    if publication_stmt is None:
        publication_stmt = ET.SubElement(file_desc, q("publicationStmt"))
    if _find_child(publication_stmt, "p") is None:
        p_node = ET.SubElement(publication_stmt, q("p"))
        p_node.text = "Publication statique locale"

    source_desc = _find_child(file_desc, "sourceDesc")
    if source_desc is None:
        source_desc = ET.SubElement(file_desc, q("sourceDesc"))
    if _find_child(source_desc, "p") is None:
        p_node = ET.SubElement(source_desc, q("p"))
        p_node.text = "Source Markdown"


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
