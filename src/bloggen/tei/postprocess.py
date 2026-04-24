"""Light TEI post-processing for Pandoc output."""

from __future__ import annotations

from pathlib import Path
import xml.etree.ElementTree as ET

from bloggen.tei.header_builder import TEI_NAMESPACE, ensure_minimal_tei_header, ensure_text_body


def postprocess_tei_xml(tei_xml: str, *, title: str | None = None) -> str:
    try:
        root = ET.fromstring(tei_xml)
    except ET.ParseError as exc:
        raise ValueError(f"XML TEI invalide (parse): {exc}") from exc

    if _local_name(root.tag) != "TEI":
        raise ValueError("La racine XML doit être un élément TEI.")

    _ensure_namespace_on_root(root)
    ensure_minimal_tei_header(root, title=title)
    ensure_text_body(root)

    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    return ET.tostring(root, encoding="unicode") + "\n"


def postprocess_tei_file(
    input_path: str | Path,
    output_path: str | Path | None = None,
    *,
    title: str | None = None,
) -> str:
    source = Path(input_path)
    xml_text = source.read_text(encoding="utf-8")
    processed = postprocess_tei_xml(xml_text, title=title)

    destination = Path(output_path) if output_path is not None else source
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(processed, encoding="utf-8")
    return processed


def _local_name(tag: str) -> str:
    if tag.startswith("{") and "}" in tag:
        return tag.split("}", maxsplit=1)[1]
    return tag


def _ensure_namespace_on_root(root: ET.Element) -> None:
    if root.tag.startswith("{"):
        return
    root.set("xmlns", TEI_NAMESPACE)
