"""format_front_matter/parse_front_matter must round-trip any value byte
for byte. The external audit flagged a real data-corruption bug: a value
containing both an apostrophe and a double quote had its double quotes
silently stripped instead of escaped — a title or citation like
``"le mot « juste »" et l'usage`` would come back mangled.
"""

from __future__ import annotations

import pytest

from bloggen.markdown.front_matter import format_front_matter, parse_front_matter


def _round_trip(value: str) -> str:
    block = format_front_matter({"title": value})
    result = parse_front_matter(block + "\nCorps.\n")
    return result.metadata["title"]


@pytest.mark.parametrize(
    "value",
    [
        "Titre simple",
        "L'apostrophe seule",
        'Les "guillemets" seuls',
        """Un titre avec l'apostrophe et des "guillemets" ensemble""",
        "Chemin C:\\Users\\alice\\document.docx",  # a literal backslash
        "Cas extrême: \\ puis \" puis '",
        "",
    ],
)
def test_value_round_trips_exactly(value):
    assert _round_trip(value) == value


def test_value_with_both_apostrophe_and_double_quote_keeps_its_double_quotes():
    """The exact bug reported by the audit: previously, format_front_matter
    silently dropped every double quote from a value once it also
    contained an apostrophe."""
    value = 'le mot "juste" et l\'usage'
    assert _round_trip(value) == value


def test_format_front_matter_escapes_backslashes_and_quotes():
    block = format_front_matter({"title": 'a "quote" and \\ backslash'})
    assert block == '---\ntitle: "a \\"quote\\" and \\\\ backslash"\n---\n'


def test_parse_front_matter_reads_legacy_single_quoted_values():
    """Backward compatibility: a hand-written or older file may still use
    single quotes (no escaping needed there since ' was only chosen when
    the value itself had no apostrophe)."""
    text = "---\ntitle: 'Sans guillemets doubles'\ntype: 'page'\n---\n\nCorps.\n"
    result = parse_front_matter(text)
    assert result.metadata["title"] == "Sans guillemets doubles"


def test_parse_front_matter_reads_unquoted_legacy_values():
    text = "---\ntitle: Bossuet\ntype: page\n---\n\nCorps.\n"
    result = parse_front_matter(text)
    assert result.metadata["title"] == "Bossuet"


def test_multiple_values_with_mixed_quoting_round_trip():
    metadata = {
        "title": 'Le mot "juste" et l\'usage',
        "slug": "le-mot-juste",
        "author": "Marie O'Brien",
        "description": 'Une "citation" complète.',
    }
    block = format_front_matter(metadata)
    result = parse_front_matter(block + "\nCorps.\n")
    assert result.metadata == metadata
