"""Light TEI post-processing for Pandoc output.

Also where Pandoc's own div/@type heading-depth convention ("level1",
"level2"...) is replaced with TEI Commons Publishing's own enumerated
equivalent ("section1".."section6") — see apply_heading_levels_in_tei_xml
and Phase 3 of the roadmap in bloggen.tei.commons_publishing's module
docstring. Verified (while building this) to be the single change that
gets a real, representative range of Pandoc-generated content (headings
up to 6 levels deep, paragraphs, ordered/unordered/nested lists,
blockquotes, tables, footnotes, links, figures, bold/italic/
strikethrough/superscript) passing that schema.

extract_heading_levels recognizes both ATX ("# Titre") and Setext
("Titre" underlined by a following line of "="/"-") headings, so either
spelling gets the right depth reapplied — a document mixing the two, or
using Setext exclusively, used to desynchronize the whole positional
correspondence between markdown_text's headings and the TEI's <head>-
carrying <div>s (extract_heading_levels only ever saw the ATX ones,
so every heading from the first Setext one onward silently received
some other heading's level, not just the Setext one itself).

Two rarer Markdown constructs remain NOT representable in Commons
Publishing at all and are left as-is (still correctly flagged by the
Phase 1 diagnostic when present, see build.fail_on_invalid_commons_publishing
to make that flag a build failure instead of a warning): fenced code
blocks (Pandoc's own <ab type="codeblock">, an element this profile
doesn't define) and horizontal rules (Pandoc's <milestone>, likewise
undefined here) — neither already had a dedicated tei_to_html.xsl
template before this, so nothing that currently renders is affected.
"""

from __future__ import annotations

from pathlib import Path
from typing import TypeVar
import re
import xml.etree.ElementTree as ET

_T = TypeVar("_T")

from bloggen.tei.header_builder import (
    TEI_NAMESPACE,
    TeiHeaderMetadata,
    ensure_minimal_tei_header,
    ensure_text_body,
)

_ALIGN_MARKER_RE = re.compile(r"^\{\{align=(left|center|right|justify)\}\}")
_HEADING_LINE_RE = re.compile(r"^(#{1,6})\s+\S")
# A Setext underline: a line made up of only "=" (level 1) or only "-"
# (level 2) characters, with no other content — CommonMark only treats
# it as a heading underline when it directly follows a non-blank line
# (checked positionally in extract_heading_levels, not by this regex
# alone: a bare "---"/"===" preceded by a blank line is a thematic break
# or nothing, not a heading).
_SETEXT_UNDERLINE_RE = re.compile(r"^(=+|-+)\s*$")


def postprocess_tei_xml(
    tei_xml: str, *, title: str | None = None, header_metadata: TeiHeaderMetadata | None = None
) -> str:
    try:
        root = ET.fromstring(tei_xml)
    except ET.ParseError as exc:
        raise ValueError(f"XML TEI invalide (parse): {exc}") from exc

    if _local_name(root.tag) != "TEI":
        raise ValueError("La racine XML doit être un élément TEI.")

    _ensure_namespace_on_root(root)
    ensure_minimal_tei_header(root, title=title, metadata=header_metadata)
    ensure_text_body(root)
    _strip_duplicate_figure_caption_paragraphs(root)

    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    return ET.tostring(root, encoding="unicode") + "\n"


def postprocess_tei_file(
    input_path: str | Path,
    output_path: str | Path | None = None,
    *,
    title: str | None = None,
    header_metadata: TeiHeaderMetadata | None = None,
) -> str:
    source = Path(input_path)
    xml_text = source.read_text(encoding="utf-8")
    processed = postprocess_tei_xml(xml_text, title=title, header_metadata=header_metadata)

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


def apply_image_attributes_in_tei_xml(tei_xml: str, attributes_by_src: dict[str, list[dict[str, str]]]) -> str:
    """Set ``@width``/``@height``/``@rend`` on ``<graphic>`` elements matching
    a source in ``attributes_by_src`` (keyed by the same ``src`` as in the
    Markdown, see :func:`bloggen.markdown.image_attributes.strip_image_attributes`).

    ``attributes_by_src`` maps each ``src`` to a *list* of attribute sets,
    one per occurrence in the original Markdown, in document order — the
    same ``src`` can appear more than once (the same file inserted twice
    with different sizes), and ``<graphic>`` elements are walked in that
    same document order here, consuming one entry per match so each
    occurrence gets its own attributes instead of every occurrence
    collapsing onto whichever one was recorded last.

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
        queue = _find_replacement(current, attributes_by_src)
        if not queue:
            continue
        attrs = queue.pop(0)
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


def apply_image_attributes_in_tei_file(tei_path: Path, attributes_by_src: dict[str, list[dict[str, str]]]) -> bool:
    if not attributes_by_src:
        return False

    source = Path(tei_path)
    original = source.read_text(encoding="utf-8")
    rewritten = apply_image_attributes_in_tei_xml(original, attributes_by_src)
    if rewritten == original:
        return False

    source.write_text(rewritten, encoding="utf-8")
    return True


def apply_paragraph_alignment_in_tei_xml(tei_xml: str) -> str:
    """Turn a leading ``{{align=...}}`` marker (see
    :mod:`bloggen.markdown.paragraph_alignment`) on a ``<p>`` element's own
    text into a ``@rend="align-..."`` attribute, stripping the marker text.

    The marker travels through Pandoc as ordinary leading text of the
    paragraph (or, for a blockquote, of its wrapped ``<p>`` inside
    ``<quote>``), so it is found directly on the element that carries it —
    no positional matching against the source Markdown is needed.
    """
    try:
        root = ET.fromstring(tei_xml)
    except ET.ParseError as exc:
        raise ValueError(f"XML TEI invalide (parse): {exc}") from exc

    changed = False
    for element in root.iter():
        if _local_name(element.tag) != "p":
            continue
        text = element.text or ""
        match = _ALIGN_MARKER_RE.match(text)
        if not match:
            continue
        element.text = text[match.end():]
        element.set("rend", f"align-{match.group(1)}")
        changed = True

    if not changed:
        return tei_xml

    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    return ET.tostring(root, encoding="unicode") + "\n"


def apply_paragraph_alignment_in_tei_file(tei_path: Path) -> bool:
    source = Path(tei_path)
    original = source.read_text(encoding="utf-8")
    rewritten = apply_paragraph_alignment_in_tei_xml(original)
    if rewritten == original:
        return False

    source.write_text(rewritten, encoding="utf-8")
    return True


def extract_heading_levels(markdown_text: str) -> list[int]:
    """Return the literal ATX heading levels (1-6), in document order.

    Pandoc's TEI writer shifts every heading level so that the shallowest
    heading in the whole document becomes ``div/@type="level1"`` (and so
    on), which silently changes the level typed in the content editor
    whenever that heading isn't the document's shallowest. The literal
    levels are captured here straight from the source Markdown so they
    can be reapplied to the generated TEI afterwards (see
    :func:`apply_heading_levels_in_tei_file`), guaranteeing the level typed
    in the editor is always the level rendered, without exception.
    """
    levels: list[int] = []
    in_code_fence = False
    # Tracks the last non-blank line seen, cleared by a blank line, a
    # fence, or a heading itself — a Setext underline only counts when it
    # directly follows real paragraph content (see _SETEXT_UNDERLINE_RE).
    previous_line: str | None = None
    for line in markdown_text.split("\n"):
        stripped = line.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_code_fence = not in_code_fence
            previous_line = None
            continue
        if in_code_fence:
            previous_line = None
            continue

        match = _HEADING_LINE_RE.match(line)
        if match:
            levels.append(len(match.group(1)))
            previous_line = None
            continue

        if previous_line and _SETEXT_UNDERLINE_RE.match(line):
            levels.append(1 if line.lstrip()[0] == "=" else 2)
            previous_line = None
            continue

        previous_line = stripped or None
    return levels


def apply_heading_levels_in_tei_xml(tei_xml: str, levels: list[int]) -> str:
    if not levels:
        return tei_xml

    try:
        root = ET.fromstring(tei_xml)
    except ET.ParseError as exc:
        raise ValueError(f"XML TEI invalide (parse): {exc}") from exc

    remaining = list(levels)
    changed = False
    for element in root.iter():
        if _local_name(element.tag) != "div":
            continue
        if not any(_local_name(child.tag) == "head" for child in element):
            continue
        if not remaining:
            break
        level = remaining.pop(0)
        # "sectionN", not Pandoc's own "levelN": div/@type is a TEI Commons
        # Publishing enumerated attribute (see the module docstring below
        # and bloggen.tei.commons_publishing) that only accepts a fixed
        # set of values — section1..section6 among them — never an
        # arbitrary token like "level1". tei_to_html.xsl's tei:div/tei:head
        # template reads this same convention back for its own heading
        # depth, so the two must always agree.
        element.set("type", f"section{level}")
        changed = True

    if not changed:
        return tei_xml

    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    return ET.tostring(root, encoding="unicode") + "\n"


def apply_heading_levels_in_tei_file(tei_path: Path, levels: list[int]) -> bool:
    if not levels:
        return False

    source = Path(tei_path)
    original = source.read_text(encoding="utf-8")
    rewritten = apply_heading_levels_in_tei_xml(original, levels)
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


def _strip_duplicate_figure_caption_paragraphs(root: ET.Element) -> bool:
    """Drop the redundant ``<p>`` Pandoc's TEI writer emits right after a
    standalone-image ``<figure>``, duplicating its ``<head>``/``<figDesc>``
    caption as plain body text (a quirk of its "implicit figure" handling,
    reproducible with ``pandoc --to=tei`` on an image alone in a paragraph).
    Left alone, the caption set from the editor's image alt/caption text
    would render twice on the generated page: once in the figure itself,
    once as a stray paragraph right below it.
    """
    changed = False
    for parent in root.iter():
        children = list(parent)
        to_remove = []
        for index, child in enumerate(children):
            if _local_name(child.tag) != "p" or len(child) != 1:
                continue
            figure = child[0]
            if _local_name(figure.tag) != "figure":
                continue
            captions = {
                "".join(sub.itertext()).strip()
                for sub in figure
                if _local_name(sub.tag) in ("head", "figDesc")
            }
            captions.discard("")
            if not captions:
                continue
            next_index = index + 1
            if next_index >= len(children):
                continue
            sibling = children[next_index]
            if _local_name(sibling.tag) != "p":
                continue
            if "".join(sibling.itertext()).strip() in captions:
                to_remove.append(sibling)
        for element in to_remove:
            parent.remove(element)
            changed = True
    return changed


def _local_name(tag: str) -> str:
    if tag.startswith("{") and "}" in tag:
        return tag.split("}", maxsplit=1)[1]
    return tag


def _ensure_namespace_on_root(root: ET.Element) -> None:
    if root.tag.startswith("{"):
        return
    root.set("xmlns", TEI_NAMESPACE)
