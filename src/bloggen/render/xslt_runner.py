"""Run TEI -> HTML transformations through the project XSLT."""

from __future__ import annotations

from pathlib import Path

from lxml import etree

DEFAULT_XSLT_PATH = (
    Path(__file__).resolve().parent.parent / "resources" / "xslt" / "tei_to_html.xsl"
)

# Applied to both the TEI input and the XSLT stylesheet itself. lxml's
# defaults already block *network* entity/DTD fetches (no_network=True),
# but still resolve a DOCTYPE-declared entity pointing at a *local* file
# (classic XXE) — resolve_entities=False turns those into inert,
# unresolved nodes instead. A theme's XSLT is exactly the kind of input
# that can come from a third party (see the audit note this fixes).
_SAFE_XML_PARSER = etree.XMLParser(
    resolve_entities=False,
    no_network=True,
    load_dtd=False,
    dtd_validation=False,
)


def render_tei_xml_to_html_fragment(
    tei_xml: str,
    xslt_path: Path | None = None,
    *,
    parameters: dict[str, str | int | bool] | None = None,
) -> str:
    transform = _load_transform(xslt_path)

    try:
        source_xml = etree.fromstring(tei_xml.encode("utf-8"), parser=_SAFE_XML_PARSER)
    except etree.XMLSyntaxError as exc:
        raise ValueError(f"XML TEI invalide: {exc}") from exc

    xslt_params = _build_xslt_params(parameters)
    result = transform(source_xml, **xslt_params)
    return str(result)


def render_tei_file_to_html_fragment(
    tei_path: Path,
    xslt_path: Path | None = None,
    *,
    parameters: dict[str, str | int | bool] | None = None,
) -> str:
    source_path = Path(tei_path)
    if not source_path.exists():
        raise FileNotFoundError(f"Fichier TEI introuvable: {source_path}")

    tei_xml = source_path.read_text(encoding="utf-8")
    return render_tei_xml_to_html_fragment(tei_xml, xslt_path=xslt_path, parameters=parameters)


def _load_transform(xslt_path: Path | None) -> etree.XSLT:
    stylesheet_path = Path(xslt_path) if xslt_path is not None else DEFAULT_XSLT_PATH
    if not stylesheet_path.exists():
        raise FileNotFoundError(f"Feuille XSLT introuvable: {stylesheet_path}")

    try:
        xslt_tree = etree.parse(str(stylesheet_path), parser=_SAFE_XML_PARSER)
    except (OSError, etree.XMLSyntaxError) as exc:
        raise ValueError(f"Feuille XSLT invalide: {exc}") from exc

    try:
        # DENY_ALL: the bundled stylesheet has no legitimate reason to call
        # document()/read a file/hit the network from inside the transform
        # — a third-party theme's XSLT doing so is exactly the case this
        # closes (exfiltrating a local file's content into every page it
        # renders, as document('secret.txt') otherwise would).
        return etree.XSLT(xslt_tree, access_control=etree.XSLTAccessControl.DENY_ALL)
    except etree.XSLTParseError as exc:
        raise ValueError(f"Compilation XSLT impossible: {exc}") from exc


def _build_xslt_params(parameters: dict[str, str | int | bool] | None) -> dict[str, str]:
    if not parameters:
        return {}

    compiled: dict[str, str] = {}
    for key, value in parameters.items():
        if isinstance(value, bool):
            compiled[key] = etree.XSLT.strparam("1" if value else "0")
            continue
        compiled[key] = etree.XSLT.strparam(str(value))
    return compiled
