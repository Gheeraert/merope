"""Paragraph/blockquote alignment marker for the WYSIWYG editor.

Markdown has no native syntax for paragraph-level text alignment, and
Pandoc's TEI writer drops any custom Div/Span attribute suffix (verified:
even the ``{...}`` fenced-div/bracketed-span attribute syntax is silently
discarded by the TEI writer). Instead, the editor's own exporter prefixes
the alignment as a small literal marker at the very start of the block's
text (e.g. ``{{align=center}}Paragraphe...``), which Pandoc passes through
untouched as plain text since it isn't attached to any image/link/heading
where ``{...}`` has special meaning. :mod:`bloggen.tei.postprocess` then
extracts it from the generated TEI text and turns it into a ``@rend``
attribute, the same way image ``width``/``height``/``align`` suffixes are
re-applied after conversion (see :mod:`bloggen.markdown.image_attributes`).

Deliberately scoped to paragraphs and blockquotes (not headings): heading
text also feeds Pandoc's auto-generated ``xml:id`` slug, and a leading
marker would corrupt it.
"""

from __future__ import annotations

import re

ALIGNMENTS = ("left", "center", "right", "justify")
DEFAULT_ALIGNMENT = "left"

_ALIGN_MARKER_RE = re.compile(r"^\{\{align=(left|center|right|justify)\}\}")


def format_alignment_marker(alignment: str) -> str:
    if not alignment or alignment == DEFAULT_ALIGNMENT:
        return ""
    if alignment not in ALIGNMENTS:
        return ""
    return f"{{{{align={alignment}}}}}"


def strip_alignment_marker(text: str) -> tuple[str, str]:
    """Returns ``(clean_text, alignment)``; ``alignment`` is ``"left"`` if absent."""
    match = _ALIGN_MARKER_RE.match(text)
    if not match:
        return text, DEFAULT_ALIGNMENT
    return text[match.end():], match.group(1)
