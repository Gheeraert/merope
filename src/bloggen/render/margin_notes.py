"""Notes rendering post-processing for HTML fragments."""

from __future__ import annotations

from dataclasses import dataclass

from lxml import etree, html


@dataclass(slots=True)
class NotesRenderingResult:
    html_fragment: str
    footnotes_count: int
    margin_notes_count: int


def apply_notes_rendering(
    html_fragment: str,
    *,
    enable_margin_notes: bool,
    enable_footnotes: bool,
    excerpt_words: int,
    excerpt_chars: int,
    prefer_words: bool,
) -> NotesRenderingResult:
    root = html.fragment_fromstring(html_fragment, create_parent="div")

    endnotes_nodes = root.xpath(
        ".//section[contains(concat(' ', normalize-space(@class), ' '), ' endnotes ')]"
    )
    if not endnotes_nodes:
        return NotesRenderingResult(
            html_fragment=_serialize_fragment(root),
            footnotes_count=0,
            margin_notes_count=0,
        )

    endnotes = endnotes_nodes[0]
    note_items = endnotes.xpath(".//ol/li")
    margin_count = 0

    if enable_margin_notes and note_items:
        margin_aside = _build_margin_notes_block(
            root,
            note_items,
            excerpt_words=excerpt_words,
            excerpt_chars=excerpt_chars,
            prefer_words=prefer_words,
        )
        article_nodes = root.xpath(
            ".//*[contains(concat(' ', normalize-space(@class), ' '), ' tei-fragment ')]"
        )
        anchor = article_nodes[0] if article_nodes else root
        anchor.append(margin_aside)
        margin_count = len(note_items)

    if not enable_footnotes:
        parent = endnotes.getparent()
        if parent is not None:
            parent.remove(endnotes)

    return NotesRenderingResult(
        html_fragment=_serialize_fragment(root),
        footnotes_count=len(note_items) if enable_footnotes else 0,
        margin_notes_count=margin_count,
    )


def _build_margin_notes_block(
    root: etree._Element,
    note_items: list[etree._Element],
    *,
    excerpt_words: int,
    excerpt_chars: int,
    prefer_words: bool,
) -> etree._Element:
    aside = etree.Element("aside", attrib={"class": "margin-notes", "aria-label": "Notes marginales"})
    title = etree.SubElement(aside, "h2")
    title.text = "Notes en marge"
    notes_list = etree.SubElement(aside, "ol")

    for note_item in note_items:
        note_id = (note_item.get("id") or "").strip()
        note_number = note_id.replace("note-", "") if note_id.startswith("note-") else ""
        if not note_number:
            continue

        margin_note_id = f"margin-note-{note_number}"
        excerpt = _build_excerpt(
            _extract_note_text(note_item),
            excerpt_words=excerpt_words,
            excerpt_chars=excerpt_chars,
            prefer_words=prefer_words,
        )

        list_item = etree.SubElement(
            notes_list,
            "li",
            attrib={"id": margin_note_id, "data-note-number": note_number},
        )

        ref_link = etree.SubElement(
            list_item,
            "a",
            attrib={"class": "margin-note-ref", "href": f"#note-call-{note_number}"},
        )
        ref_link.text = note_number

        body_link = etree.SubElement(
            list_item,
            "a",
            attrib={"class": "margin-note-link", "href": f"#note-{note_number}"},
        )
        body_link.text = excerpt

        call_links = root.xpath(f".//sup[@id='note-call-{note_number}']/a")
        for call_link in call_links:
            call_link.set("data-margin-note-target", margin_note_id)

    return aside


def _extract_note_text(note_item: etree._Element) -> str:
    clone = html.fromstring(etree.tostring(note_item, encoding="unicode"))
    for node in clone.xpath(
        ".//a[contains(concat(' ', normalize-space(@class), ' '), ' note-backref ')]"
    ):
        parent = node.getparent()
        if parent is not None:
            parent.remove(node)
    text = " ".join(clone.text_content().split())
    return text


def _build_excerpt(
    text: str,
    *,
    excerpt_words: int,
    excerpt_chars: int,
    prefer_words: bool,
) -> str:
    cleaned = " ".join(text.split())
    if not cleaned:
        return ""

    if prefer_words and excerpt_words > 0:
        words = cleaned.split()
        if len(words) <= excerpt_words:
            return cleaned
        return " ".join(words[:excerpt_words]) + "…"

    limit = max(excerpt_chars, 0)
    if limit == 0 or len(cleaned) <= limit:
        return cleaned
    return cleaned[:limit].rstrip() + "…"


def _serialize_fragment(root: etree._Element) -> str:
    return "".join(etree.tostring(child, encoding="unicode") for child in root)
