"""French typography helpers: smart quotes and non-breaking spaces.

Pure text transforms with no Tkinter dependency, so they can be unit
tested directly and reused both by the live keystroke handling in
:mod:`bloggen.ui.content_editor` and by a manual "fix pasted text" action.
"""

from __future__ import annotations

import re
from dataclasses import replace

from bloggen.markdown.rich_text_model import InlineRun

NBSP = " "
DOUBLE_PUNCTUATION = ";:!?"
CURLY_OPENING_QUOTE = "“"
CURLY_CLOSING_QUOTE = "”"
OPENING_GUILLEMET = "«"  # «
CLOSING_GUILLEMET = "»"  # »


def apply_french_typography(text: str) -> str:
    """Convert straight/curly double quotes to alternating guillemets (with a
    non-breaking space glued to the inside), and ensure a single
    non-breaking space before ``; : ! ?``. Idempotent: running it twice
    does not add extra spaces or re-toggle quote parity incorrectly.
    """
    text = convert_curly_quotes_to_guillemets(text)
    text = _convert_straight_quotes(text)
    return fix_double_punctuation_spacing(text)


def convert_curly_quotes_to_guillemets(text: str) -> str:
    """Directly map already-curly quotes (e.g. from Word/Google Docs
    autocorrect) to guillemets. Unlike straight quotes, curly quotes are
    unambiguous (open vs close is encoded in the character itself), so no
    parity tracking is needed.
    """
    text = text.replace(CURLY_OPENING_QUOTE, OPENING_GUILLEMET + NBSP)
    return text.replace(CURLY_CLOSING_QUOTE, NBSP + CLOSING_GUILLEMET)


def convert_straight_quotes_stateful(text: str, *, opening_next: bool = True) -> tuple[str, bool]:
    """Same conversion as used above, but threads the opening/closing parity
    across multiple calls instead of always restarting at "opening". Needed
    when converting pasted content run by run in document order, where a
    quote pair can span more than one inline run (e.g. a quote containing a
    bolded word).

    Returns ``(converted_text, next_opening_next)``.
    """
    result: list[str] = []
    for char in text:
        if char == '"':
            if opening_next:
                result.append(OPENING_GUILLEMET + NBSP)
            else:
                result.append(NBSP + CLOSING_GUILLEMET)
            opening_next = not opening_next
        else:
            result.append(char)
    return "".join(result), opening_next


def _convert_straight_quotes(text: str) -> str:
    converted, _ = convert_straight_quotes_stateful(text, opening_next=True)
    return converted


def fix_double_punctuation_spacing(text: str) -> str:
    """Ensure a single non-breaking space precedes ``; : ! ?`` (replacing a
    preceding regular space, or inserting one if the punctuation is glued
    to the previous word). Idempotent. Exposed publicly so callers that
    process text run-by-run (e.g. paste import) can apply it without going
    through the quote-conversion half of :func:`apply_french_typography`.
    """
    result: list[str] = []
    for index, char in enumerate(text):
        if char in DOUBLE_PUNCTUATION:
            preceding = text[index - 1] if index > 0 else ""
            if preceding != NBSP:
                if result and result[-1] == " ":
                    result.pop()
                result.append(NBSP)
        result.append(char)
    return "".join(result)


CENTURY_RE = re.compile(r"\b([IVXLCDM]+)(er|e)\s+([Ss]i[eè]cle)\b")


def is_valid_century_ordinal(numeral: str, suffix: str) -> bool:
    """"I" takes "er" (premier siecle), everything else takes "e"
    (deuxieme, vingt-et-unieme...). Rejects mismatches like "Ie" or "IIer"
    so an unrelated match isn't misdetected as a century ordinal.
    """
    if numeral == "I":
        return suffix == "er"
    return suffix == "e"


def split_century_ordinals(runs: list[InlineRun]) -> list[InlineRun]:
    """Split plain-text runs containing a "<numeral><er|e> siecle" pattern
    (e.g. "XXIe siecle") into normal/superscript/normal parts, so the
    ordinal suffix renders as a superscript. Leaves image/footnote/already-
    superscript runs untouched.
    """
    result_runs: list[InlineRun] = []
    for run in runs:
        if run.image_src is not None or run.footnote_ref is not None or run.superscript:
            result_runs.append(run)
            continue
        result_runs.extend(_split_run_by_century(run))
    return result_runs


def _split_run_by_century(run: InlineRun) -> list[InlineRun]:
    text = run.text
    pieces: list[InlineRun] = []
    pos = 0
    for match in CENTURY_RE.finditer(text):
        numeral, suffix = match.group(1), match.group(2)
        if not is_valid_century_ordinal(numeral, suffix):
            continue
        prefix = text[pos : match.start(2)]
        if prefix:
            pieces.append(replace(run, text=prefix, superscript=False))
        pieces.append(replace(run, text=suffix, superscript=True))
        pos = match.end(2)
    remainder = text[pos:]
    if remainder or not pieces:
        pieces.append(replace(run, text=remainder, superscript=False))
    return pieces
