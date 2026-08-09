import pytest

from bloggen.render.numbering import to_letters, to_roman


def test_to_roman_basic_values():
    assert to_roman(1) == "I"
    assert to_roman(4) == "IV"
    assert to_roman(9) == "IX"
    assert to_roman(14) == "XIV"
    assert to_roman(40) == "XL"
    assert to_roman(2026) == "MMXXVI"


def test_to_roman_rejects_non_positive():
    with pytest.raises(ValueError):
        to_roman(0)
    with pytest.raises(ValueError):
        to_roman(-1)


def test_to_letters_basic_values():
    assert to_letters(1) == "A"
    assert to_letters(2) == "B"
    assert to_letters(26) == "Z"
    assert to_letters(27) == "AA"
    assert to_letters(28) == "AB"
    assert to_letters(52) == "AZ"
    assert to_letters(53) == "BA"


def test_to_letters_rejects_non_positive():
    with pytest.raises(ValueError):
        to_letters(0)
    with pytest.raises(ValueError):
        to_letters(-1)
