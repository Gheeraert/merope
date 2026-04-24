"""Minimal TEI validation helpers (well-formed XML + required blocks)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import xml.etree.ElementTree as ET


@dataclass(slots=True)
class TeiValidationResult:
    valid: bool
    errors: list[str] = field(default_factory=list)


def validate_tei_xml(tei_xml: str) -> TeiValidationResult:
    errors: list[str] = []

    try:
        root = ET.fromstring(tei_xml)
    except ET.ParseError as exc:
        return TeiValidationResult(valid=False, errors=[f"XML mal formé: {exc}"])

    if _local_name(root.tag) != "TEI":
        errors.append("Racine TEI absente ou invalide.")

    if _find_first(root, "teiHeader") is None:
        errors.append("Élément teiHeader manquant.")

    text_node = _find_first(root, "text")
    if text_node is None:
        errors.append("Élément text manquant.")
    elif _find_first(text_node, "body") is None:
        errors.append("Élément text/body manquant.")

    return TeiValidationResult(valid=not errors, errors=errors)


def validate_tei_file(path: str | Path) -> TeiValidationResult:
    content = Path(path).read_text(encoding="utf-8")
    return validate_tei_xml(content)


def _find_first(parent: ET.Element, local_name: str) -> ET.Element | None:
    for node in parent.iter():
        if _local_name(node.tag) == local_name:
            return node
    return None


def _local_name(tag: str) -> str:
    if tag.startswith("{") and "}" in tag:
        return tag.split("}", maxsplit=1)[1]
    return tag
