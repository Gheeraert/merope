"""Light TEI post-processing for Pandoc output."""

from __future__ import annotations

from pathlib import Path
from typing import TypeVar
import xml.etree.ElementTree as ET

_T = TypeVar("_T")

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


def rewrite_graphic_urls_in_tei_xml(tei_xml: str, replacements: dict[str, str]) -> str:
    if not replacements:
        return tei_xml

    try:
        root = ET.fromstring(tei_xml)
    except ET.ParseError as exc:
        raise ValueError(f"XML TEI invalide (parse): {exc}") from exc

    changed = False
    for element in root.iter():
        if _local_name(element.tag) != "graphic":
            continue
        current = (element.get("url") or "").strip()
        if not current:
            continue
        replacement = _find_replacement(current, replacements)
        if replacement is None:
            continue
        element.set("url", replacement)
        changed = True

    if not changed:
        return tei_xml

    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    return ET.tostring(root, encoding="unicode") + "\n"


def rewrite_graphic_urls_in_tei_file(tei_path: Path, replacements: dict[str, str]) -> bool:
    if not replacements:
        return False

    source = Path(tei_path)
    original = source.read_text(encoding="utf-8")
    rewritten = rewrite_graphic_urls_in_tei_xml(original, replacements)
    if rewritten == original:
        return False

    source.write_text(rewritten, encoding="utf-8")
    return True


def apply_image_attributes_in_tei_xml(tei_xml: str, attributes_by_src: dict[str, dict[str, str]]) -> str:
    """Set ``@width``/``@height``/``@rend`` on ``<graphic>`` elements matching
    a source in ``attributes_by_src`` (keyed by the same ``src`` as in the
    Markdown, see :func:`bloggen.markdown.image_attributes.strip_image_attributes`).

    Pandoc's TEI writer does not carry Markdown image attribute suffixes
    through, so this re-applies them after conversion, the same way
    :func:`rewrite_graphic_urls_in_tei_xml` re-applies rewritten asset URLs.
    """
    if not attributes_by_src:
        return tei_xml

    try:
        root = ET.fromstring(tei_xml)
    except ET.ParseError as exc:
        raise ValueError(f"XML TEI invalide (parse): {exc}") from exc

    changed = False
    for element in root.iter():
        if _local_name(element.tag) != "graphic":
            continue
        current = (element.get("url") or "").strip()
        if not current:
            continue
        attrs = _find_replacement(current, attributes_by_src)
        if attrs is None:
            continue
        if attrs.get("width"):
            element.set("width", attrs["width"])
            changed = True
        if attrs.get("height"):
            element.set("height", attrs["height"])
            changed = True
        if attrs.get("align"):
            element.set("rend", f"align-{attrs['align']}")
            changed = True

    if not changed:
        return tei_xml

    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    return ET.tostring(root, encoding="unicode") + "\n"


def apply_image_attributes_in_tei_file(tei_path: Path, attributes_by_src: dict[str, dict[str, str]]) -> bool:
    if not attributes_by_src:
        return False

    source = Path(tei_path)
    original = source.read_text(encoding="utf-8")
    rewritten = apply_image_attributes_in_tei_xml(original, attributes_by_src)
    if rewritten == original:
        return False

    source.write_text(rewritten, encoding="utf-8")
    return True


def _find_replacement(current: str, replacements: dict[str, _T]) -> _T | None:
    variants = {
        current,
        current.strip("<>").strip(),
        current.replace("\\", "/"),
        current.strip("<>").strip().replace("\\", "/"),
    }
    for candidate in variants:
        if candidate in replacements:
            return replacements[candidate]
    return None


def _local_name(tag: str) -> str:
    if tag.startswith("{") and "}" in tag:
        return tag.split("}", maxsplit=1)[1]
    return tag


def _ensure_namespace_on_root(root: ET.Element) -> None:
    if root.tag.startswith("{"):
        return
    root.set("xmlns", TEI_NAMESPACE)
