"""Auto-convert the Hypothèses/WordPress "double parenthesis" note
shorthand: a span of text wrapped in ``((`` and ``))`` becomes a footnote,
wherever it appears — including right before punctuation (``((note)).``),
which is how footnotes are placed in practice and is exactly what
Hypothèses' own editor accepts (no flanking-space requirement: an earlier
version of this module required one, which meant the extremely common
"note right before the sentence's closing punctuation" case silently never
converted).

The shorthand is deliberately left untouched while typing or pasting in the
Tk and Qt content editors — converting it live used to flatten it
to a resolved footnote reference immediately, which meant the note text
could no longer be edited like normal body text (selecting it to toggle
bold/italic, for instance, meant reopening the footnote panel). Instead
the editors store ``((note))`` as ordinary rich text, and it is only ever
resolved at Markdown-normalization time, via
:func:`convert_double_paren_notes_in_markdown_text` (rewrites straight to
Pandoc's inline footnote syntax, ``^[note text]``) — see
:func:`bloggen.markdown.normalizer.normalize_markdown_text`, called by
both the real build (:mod:`bloggen.content.loader`) and the editor's own
HTML preview (:mod:`bloggen.ui.content_editor.preview`), so the two stay
in sync automatically.

:func:`split_double_paren_notes` / :func:`convert_double_paren_notes_in_blocks`
below operate on the editor's ``InlineRun``/``Block`` model instead of
raw Markdown text (formatting inside a note — e.g. an italicized title —
carries over into the footnote definition). They are not currently wired
into any editor call site (see above), but stay covered by
``tests/test_note_shortcuts.py`` as reusable, general-purpose building
blocks should a future feature need block-level conversion again.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import replace

from bloggen.markdown.rich_text_model import Block, InlineRun

# "((", then the shortest possible span up to the next "))". No
# surrounding-space requirement: the double-paren pair itself is already a
# strong enough signal not to fire on ordinary single-parenthesis asides
# like "(voir (a) et (b))" (that content is not enclosed in "((" "))").
# Unlike an earlier version, single parentheses ARE allowed inside the note
# — a note ending in "((voir [ce lien](https://exemple.org) ici))" has a
# literal "(" ")" around the URL as soon as it's a Markdown link, and that
# must not stop the match from reaching the real, later "))".
DOUBLE_PAREN_NOTE_RE = re.compile(r"\(\((.+?)\)\)")

RegisterNote = Callable[[list[InlineRun]], str]


def split_double_paren_notes(runs: list[InlineRun], register_note: RegisterNote) -> list[InlineRun]:
    """Split runs on the "((note))" shorthand into normal/footnote-ref/
    normal parts. ``register_note`` is called with each note's own inline
    runs (formatting intact — bold/italic/link runs all carry over into
    the footnote definition), in document order, and must return the
    footnote id to reference.

    A note's ``((``/``))`` delimiters do not need to land in the same run:
    pasted rich text routinely splits "((intro " / "a link" / " outro))"
    across three runs (a plain run, a link run, another plain run) the
    moment the note contains any inline formatting (e.g. a link). Runs are
    therefore grouped into maximal stretches of "text-bearing" runs (any
    run that isn't an image or an already-resolved footnote — bold/italic/
    link runs all qualify) and matched against the concatenation of that
    whole stretch, not run by run; everything up to the first image/
    footnote boundary is fair game.
    """
    result: list[InlineRun] = []
    group: list[InlineRun] = []

    def flush_group() -> None:
        if group:
            result.extend(_split_run_group(group, register_note))
            group.clear()

    for run in runs:
        if run.image_src is not None or run.footnote_ref is not None:
            flush_group()
            result.append(run)
        else:
            group.append(run)
    flush_group()
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


def _split_run_group(group: list[InlineRun], register_note: RegisterNote) -> list[InlineRun]:
    flat_text = "".join(run.text for run in group)
    if "((" not in flat_text:
        return group

    offsets: list[int] = []
    pos = 0
    for run in group:
        offsets.append(pos)
        pos += len(run.text)
    total_length = pos

    def slice_group(start: int, end: int) -> list[InlineRun]:
        pieces: list[InlineRun] = []
        for index, run in enumerate(group):
            run_start = offsets[index]
            run_end = run_start + len(run.text)
            seg_start, seg_end = max(start, run_start), min(end, run_end)
            if seg_start < seg_end:
                pieces.append(replace(run, text=run.text[seg_start - run_start : seg_end - run_start]))
        return pieces

    pieces: list[InlineRun] = []
    cursor = 0
    for match in DOUBLE_PAREN_NOTE_RE.finditer(flat_text):
        note_runs = strip_runs(slice_group(match.start(1), match.end(1)))
        if not any(run.text for run in note_runs):
            continue
        pieces.extend(slice_group(cursor, match.start()))
        note_id = register_note(note_runs)
        pieces.append(InlineRun(footnote_ref=note_id))
        cursor = match.end()

    remainder = slice_group(cursor, total_length)
    if remainder or not pieces:
        pieces.extend(remainder)
    return pieces


def strip_runs(runs: list[InlineRun]) -> list[InlineRun]:
    """Trim leading/trailing whitespace off a run sequence (the ``.strip()``
    a plain-string note's text used to get), without disturbing the
    formatting of whatever non-whitespace text remains. Only ever called
    with plain-text-bearing runs (no images/footnotes — see
    :func:`split_double_paren_notes`'s grouping), so every run here is
    guaranteed to have a ``.text``.
    """
    runs = list(runs)
    while runs and not runs[0].text.strip():
        runs.pop(0)
    if runs:
        runs[0] = replace(runs[0], text=runs[0].text.lstrip())
    while runs and not runs[-1].text.strip():
        runs.pop()
    if runs:
        runs[-1] = replace(runs[-1], text=runs[-1].text.rstrip())
    return runs


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
        parts[index] = _convert_markdown_segment(part)
    return "".join(parts)


def _convert_markdown_segment(text: str) -> str:
    """Convert shortcuts while respecting balanced parentheses in content.

    A Markdown link ending immediately before the shortcut delimiter contains
    three consecutive closing parentheses: one closes the URL, then two close
    the note. A non-greedy regular expression mistakes the first two for the
    note delimiter. This small scanner distinguishes balanced inner
    parentheses from the outer ``))`` without parsing Markdown generally.
    """

    converted: list[str] = []
    cursor = 0
    while True:
        start = text.find("((", cursor)
        if start < 0:
            converted.append(text[cursor:])
            break
        end = _find_double_paren_note_end(text, start + 2)
        if end is None:
            converted.append(text[cursor:])
            break
        note_text = text[start + 2 : end].strip()
        converted.append(text[cursor:start])
        if note_text:
            converted.append(f"^[{note_text}]")
        else:
            converted.append(text[start : end + 2])
        cursor = end + 2
    return "".join(converted)


def _find_double_paren_note_end(text: str, start: int) -> int | None:
    depth = 0
    position = start
    while position < len(text) - 1:
        character = text[position]
        if character == "(":
            depth += 1
        elif character == ")":
            if depth:
                depth -= 1
            elif text[position + 1] == ")":
                return position
        position += 1
    return None
