"""French typography helpers: smart quotes and non-breaking spaces.

Pure text transforms with no Tkinter dependency, so they can be unit
tested directly and reused both by the live keystroke handling in
:mod:`bloggen.ui.content_editor` and by a manual "fix pasted text" action.
"""

from __future__ import annotations

NBSP = " "
DOUBLE_PUNCTUATION = ";:!?"
OPENING_GUILLEMET = "«"  # «
CLOSING_GUILLEMET = "»"  # »


def apply_french_typography(text: str) -> str:
    """Convert straight double quotes to alternating « » (with a non-breaking
    space glued to the inside), and ensure a single non-breaking space
    before ``; : ! ?``. Idempotent: running it twice does not add extra
    spaces or re-toggle quote parity incorrectly.
    """
    return _fix_double_punctuation_spacing(_convert_straight_quotes(text))


def _convert_straight_quotes(text: str) -> str:
    result: list[str] = []
    opening_next = True
    for char in text:
        if char == '"':
            if opening_next:
                result.append(OPENING_GUILLEMET + NBSP)
            else:
                result.append(NBSP + CLOSING_GUILLEMET)
            opening_next = not opening_next
        else:
            result.append(char)
    return "".join(result)


def _fix_double_punctuation_spacing(text: str) -> str:
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
