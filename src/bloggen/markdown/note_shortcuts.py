"""Auto-convert the Hypothèses/WordPress "double parenthesis" note
shorthand: a span of text wrapped in ``((`` and ``))`` and flanked by a
space on each side becomes a footnote reference.

Used both for the live-typing autoformat and for content brought in via
paste/import in :mod:`bloggen.ui.content_editor`, so the regex/splitting
logic lives here once; the two call sites just supply where new footnote
ids come from (allocating one and recording its definition text needs the
editor's own ``footnote_definitions`` state, which this module knows
nothing about).
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import replace

from bloggen.markdown.rich_text_model import Block, InlineRun

# A space, then "((", then note text with no nested parentheses, then "))",
# then a space: mirrors how Hypothèses' own editor recognizes the
# shorthand, and the flanking spaces keep it from firing on incidental
# parenthesized asides such as "(voir (a) et (b))".
DOUBLE_PAREN_NOTE_RE = re.compile(r" \(\(([^()]+)\)\) ")

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
        prefix = text[pos : match.start()] + " "  # re-glue the leading space
        pieces.append(replace(run, text=prefix))
        note_id = register_note(note_text)
        pieces.append(InlineRun(footnote_ref=note_id))
        # The match also consumed the trailing space; fold it into whatever
        # text comes next instead of the marker itself, matching how a
        # footnote call is written by hand (no space glued to its brackets).
        pos = match.end() - 1

    remainder = text[pos:]
    if remainder or not pieces:
        pieces.append(replace(run, text=remainder))
    return pieces
