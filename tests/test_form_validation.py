from __future__ import annotations

import pytest

from bloggen.ui.form_validation import parse_int_field


def test_parse_int_field_accepts_a_plain_integer():
    assert parse_int_field("220", "Hauteur (px)") == 220


def test_parse_int_field_strips_whitespace():
    assert parse_int_field("  8  ", "Amorce (mots)") == 8


def test_parse_int_field_rejects_empty_string():
    with pytest.raises(ValueError, match="Hauteur"):
        parse_int_field("", "Hauteur (px)")


def test_parse_int_field_rejects_non_numeric_text():
    with pytest.raises(ValueError, match="Hauteur"):
        parse_int_field("abc", "Hauteur (px)")


def test_parse_int_field_enforces_minimum():
    with pytest.raises(ValueError, match="supérieur ou égal à 1"):
        parse_int_field("0", "Hauteur (px)", minimum=1)


def test_parse_int_field_allows_zero_when_minimum_is_zero():
    assert parse_int_field("0", "Amorce (mots)", minimum=0) == 0


def test_parse_int_field_rejects_negative_below_minimum():
    with pytest.raises(ValueError, match="supérieur ou égal à 0"):
        parse_int_field("-5", "Amorce (caractères)", minimum=0)
