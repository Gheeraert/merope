"""Roman numeral / letter numbering for the side menu's optional outline
mode (``SideMenuSection.numbered``): "I.", "II.", "III." for sections and
"A.", "B.", "C." for their subsections.
"""

from __future__ import annotations

_ROMAN_VALUES = (
    (1000, "M"), (900, "CM"), (500, "D"), (400, "CD"),
    (100, "C"), (90, "XC"), (50, "L"), (40, "XL"),
    (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"),
)


def to_roman(n: int) -> str:
    """1-based upper-case roman numeral (1 -> "I", 4 -> "IV", 12 -> "XII")."""
    if n <= 0:
        raise ValueError(f"to_roman attend un entier positif, reçu {n}.")
    parts: list[str] = []
    remainder = n
    for value, symbol in _ROMAN_VALUES:
        count, remainder = divmod(remainder, value)
        parts.append(symbol * count)
    return "".join(parts)


def to_letters(n: int) -> str:
    """1-based spreadsheet-column-style letters (1 -> "A", 26 -> "Z", 27 -> "AA")."""
    if n <= 0:
        raise ValueError(f"to_letters attend un entier positif, reçu {n}.")
    letters: list[str] = []
    remainder = n
    while remainder > 0:
        remainder, rest = divmod(remainder - 1, 26)
        letters.append(chr(ord("A") + rest))
    return "".join(reversed(letters))
