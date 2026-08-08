"""Minimal ``{key=value ...}`` attribute suffix on Markdown images.

``![alt](src){width=300 height=200 align=left}`` is how the WYSIWYG editor
records a non-destructive display size and alignment for an image. Pandoc's
Markdown reader understands (and ignores, for its TEI writer) this suffix
syntax, but does not carry it through to TEI, so :mod:`bloggen.tei.pandoc_converter`
strips it before invoking Pandoc and re-applies it to the generated TEI
afterwards (see :func:`bloggen.tei.postprocess.apply_image_attributes_in_tei_file`).

This is intentionally a tiny, specific parser (space-separated ``key=value``
pairs, no quoting, no classes/ids) — not a general Pandoc attribute parser.
"""

from __future__ import annotations

import re

_IMAGE_WITH_ATTRS_RE = re.compile(r"(!\[[^\]]*\]\([^)]+\))\{([^}]*)\}")
_IMAGE_SRC_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")
_ATTR_KEY_ORDER = ("width", "height", "align")


def parse_image_attributes(attr_text: str) -> dict[str, str]:
    attrs: dict[str, str] = {}
    for token in attr_text.split():
        if "=" not in token:
            continue
        key, _, value = token.partition("=")
        if key and value:
            attrs[key] = value
    return attrs


def format_image_attributes(attrs: dict[str, str]) -> str:
    parts = [f"{key}={attrs[key]}" for key in _ATTR_KEY_ORDER if attrs.get(key)]
    if not parts:
        return ""
    return "{" + " ".join(parts) + "}"


def strip_image_attributes(markdown_text: str) -> tuple[str, dict[str, dict[str, str]]]:
    """Remove ``{...}`` attribute suffixes from image references.

    Returns the cleaned text (plain ``![alt](src)``, safe for Pandoc) and a
    mapping from image ``src`` to its parsed attributes, for later re-injection
    into the generated TEI.
    """
    attrs_by_src: dict[str, dict[str, str]] = {}

    def _replace(match: re.Match[str]) -> str:
        image_markdown, attr_text = match.group(1), match.group(2)
        src_match = _IMAGE_SRC_RE.match(image_markdown)
        if src_match:
            attrs = parse_image_attributes(attr_text)
            if attrs:
                attrs_by_src[src_match.group(1)] = attrs
        return image_markdown

    cleaned = _IMAGE_WITH_ATTRS_RE.sub(_replace, markdown_text)
    return cleaned, attrs_by_src
