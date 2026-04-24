"""Run TEI -> HTML transformations through the project XSLT."""

from __future__ import annotations

from pathlib import Path

from lxml import etree

DEFAULT_XSLT_PATH = (
    Path(__file__).resolve().parent.parent / "resources" / "xslt" / "tei_to_html.xsl"
)


def render_tei_xml_to_html_fragment(tei_xml: str, xslt_path: Path | None = None) -> str:
    transform = _load_transform(xslt_path)

    try:
        source_xml = etree.fromstring(tei_xml.encode("utf-8"))
    except etree.XMLSyntaxError as exc:
        raise ValueError(f"XML TEI invalide: {exc}") from exc

    result = transform(source_xml)
    return str(result)


def render_tei_file_to_html_fragment(tei_path: Path, xslt_path: Path | None = None) -> str:
    source_path = Path(tei_path)
    if not source_path.exists():
        raise FileNotFoundError(f"Fichier TEI introuvable: {source_path}")

    tei_xml = source_path.read_text(encoding="utf-8")
    return render_tei_xml_to_html_fragment(tei_xml, xslt_path=xslt_path)


def _load_transform(xslt_path: Path | None) -> etree.XSLT:
    stylesheet_path = Path(xslt_path) if xslt_path is not None else DEFAULT_XSLT_PATH
    if not stylesheet_path.exists():
        raise FileNotFoundError(f"Feuille XSLT introuvable: {stylesheet_path}")

    try:
        xslt_tree = etree.parse(str(stylesheet_path))
    except (OSError, etree.XMLSyntaxError) as exc:
        raise ValueError(f"Feuille XSLT invalide: {exc}") from exc

    try:
        return etree.XSLT(xslt_tree)
    except etree.XSLTParseError as exc:
        raise ValueError(f"Compilation XSLT impossible: {exc}") from exc
