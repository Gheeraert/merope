"""Auto-convert the Hypothèses/WordPress "double parenthesis" note
shorthand: a span of text wrapped in ``((`` and ``))`` becomes a footnote,
wherever it appears — including right before punctuation (``((note)).``),
which is how footnotes are placed in practice and is exactly what
Hypothèses' own editor accepts (no flanking-space requirement: an earlier
version of this module required one, which meant the extremely common
"note right before the sentence's closing punctuation" case silently never
converted).

Two independent uses:
- Live typing and pasted/imported rich content in
  :mod:`bloggen.ui.content_editor`, via :func:`split_double_paren_notes` /
  :func:`convert_double_paren_notes_in_blocks` (operate on the editor's
  ``InlineRun``/``Block`` model; the two call sites just supply where new
  footnote ids come from — allocating one and recording its definition
  text needs the editor's own ``footnote_definitions`` state, which this
  module knows nothing about).
- Raw Markdown at build time, via
  :func:`convert_double_paren_notes_in_markdown_text` (rewrites straight to
  Pandoc's inline footnote syntax, ``^[note text]``), so content that was
  hand-written or imported straight to Markdown — never touched the
  WYSIWYG editor — still gets the shorthand recognized when the site is
  generated.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import replace

from bloggen.markdown.rich_text_model import Block, InlineRun

# "((", then note text with no nested parentheses, then "))". No
# surrounding-space requirement: the double-paren pair itself is already a
# strong enough signal not to fire on ordinary single-parenthesis asides
# like "(voir (a) et (b))" (that content is not enclosed in "((" "))").
DOUBLE_PAREN_NOTE_RE = re.compile(r"\(\(([^()]+)\)\)")

RegisterNote = Callable[[str], str]


def split_double_paren_notes(runs: list[InlineRun], register_note: RegisterNote) -> list[InlineRun]:
    """Split plain-text runs on the "((note))" shorthand into normal/
    footnote-ref/normal parts, mirroring
    :func:`bloggen.markdown.typography.split_century_ordinals`. Leaves
    image/footnote runs untouched. ``register_note`` is called with each
    note's text, in document order, and must return the footnote id to
    reference.
    """
    result: list[InlineRun] = []
    for run in runs:
        if run.image_src is not None or run.footnote_ref is not None:
            result.append(run)
            continue
        result.extend(_split_run(run, register_note))
    return result


def convert_double_paren_notes_in_blocks(blocks: list[Block], register_note: RegisterNote) -> None:
    """Recursively apply :func:`split_double_paren_notes` to every block's
    runs, mutating ``blocks`` in place. Used for pasted/imported content,
    which arrives as a full block tree rather than a flat run list.
    """
    for block in blocks:
        if block.runs:
            block.runs = split_double_paren_notes(block.runs, register_note)
        if block.children:
            convert_double_paren_notes_in_blocks(block.children, register_note)


def _split_run(run: InlineRun, register_note: RegisterNote) -> list[InlineRun]:
    text = run.text
    if "((" not in text:
        return [run]

    pieces: list[InlineRun] = []
    pos = 0
    for match in DOUBLE_PAREN_NOTE_RE.finditer(text):
        note_text = match.group(1).strip()
        if not note_text:
            continue
        prefix = text[pos : match.start()]
        if prefix:
            pieces.append(replace(run, text=prefix))
        note_id = register_note(note_text)
        pieces.append(InlineRun(footnote_ref=note_id))
        pos = match.end()

    remainder = text[pos:]
    if remainder or not pieces:
        pieces.append(replace(run, text=remainder))
    return pieces


_CODE_FENCE_RE = re.compile(r"^(`{3,}|~{3,})")
_INLINE_CODE_SPLIT_RE = re.compile(r"(`[^`\n]*`)")


def convert_double_paren_notes_in_markdown_text(text: str) -> str:
    """Convert "((note text))" directly in raw Markdown into Pandoc's
    inline footnote syntax ("^[note text]") — applied once at build time,
    right before the Markdown -> TEI conversion (see
    :func:`bloggen.markdown.normalizer.normalize_markdown_text`), so it
    works even for Markdown that never went through the WYSIWYG editor.
    Skips fenced code blocks and inline code spans, so literal double
    parentheses in code samples are left alone.
    """
    if "((" not in text:
        return text

    in_fence = False
    fence_marker = ""
    converted_lines: list[str] = []
    for line in text.split("\n"):
        stripped = line.strip()
        fence_match = _CODE_FENCE_RE.match(stripped)
        if fence_match:
            if not in_fence:
                in_fence = True
                fence_marker = fence_match.group(1)[0] * 3
            elif stripped.startswith(fence_marker):
                in_fence = False
            converted_lines.append(line)
            continue
        if in_fence:
            converted_lines.append(line)
            continue
        converted_lines.append(_convert_markdown_line(line))
    return "\n".join(converted_lines)


def _convert_markdown_line(line: str) -> str:
    parts = _INLINE_CODE_SPLIT_RE.split(line)
    for index, part in enumerate(parts):
        if part.startswith("`"):
            continue
        parts[index] = DOUBLE_PAREN_NOTE_RE.sub(_markdown_replacement, part)
    return "".join(parts)


def _markdown_replacement(match: re.Match[str]) -> str:
    note_text = match.group(1).strip()
    if not note_text:
        return match.group(0)
    return f"^[{note_text}]"
