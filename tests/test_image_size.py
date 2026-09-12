from __future__ import annotations

import pytest

from bloggen.content.image_size import (
    MIN_PERCENT,
    WidthSpec,
    clamp_percent,
    displayed_percent,
    format_percent,
    legacy_pixels,
    max_percent_for,
    parse_width,
    resize_to_width,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("50%", WidthSpec("percent", 50)),
        (" 33 % ", WidthSpec("percent", 33)),
        ("12,6%", WidthSpec("percent", 13)),
        ("150%", WidthSpec("percent", 100)),
        ("400", WidthSpec("pixels", 400)),
        ("400px", WidthSpec("pixels", 400)),
        ("0", None),
        ("0%", None),
        ("", None),
        (None, None),
        ("auto", None),
        ("-5%", None),
    ],
)
def test_parse_width_accepts_percent_and_legacy_pixels(value, expected):
    assert parse_width(value) == expected


def test_legacy_pixels_only_returns_pixel_values():
    assert legacy_pixels("320") == 320
    assert legacy_pixels("320px") == 320
    assert legacy_pixels("50%") is None
    assert legacy_pixels("n'importe quoi") is None


def test_format_and_clamp_follow_alignment_ceiling():
    assert format_percent(42) == "42%"
    assert max_percent_for(None) == 100
    assert max_percent_for("center") == 100
    assert max_percent_for("left") == 50
    assert clamp_percent(120) == 100
    assert clamp_percent(80, align="right") == 50
    assert clamp_percent(1) == MIN_PERCENT


def test_displayed_percent_mirrors_site_rendering():
    # 2000 px photo in an 800 px column.
    assert displayed_percent(None, natural_width=2000, column_width=800) == 100
    assert displayed_percent(
        WidthSpec("percent", 40), natural_width=2000, column_width=800
    ) == 40
    # A 200 px icon is never enlarged.
    assert displayed_percent(
        WidthSpec("percent", 80), natural_width=200, column_width=800
    ) == 25
    assert displayed_percent(
        WidthSpec("pixels", 400), natural_width=2000, column_width=800
    ) == 50
    assert displayed_percent(
        None, natural_width=2000, column_width=800, align="left"
    ) == 50


def test_resize_snaps_near_reference_widths_and_can_be_free():
    snapped = resize_to_width(405, column_width=800, natural_width=4000)
    free = resize_to_width(405, column_width=800, natural_width=4000, snap=False)

    assert (snapped.percent, snapped.snapped) == (50, True)
    assert snapped.width_value == "50%"
    assert (free.percent, free.snapped) == (51, False)


def test_resize_never_enlarges_and_natural_size_removes_width():
    outcome = resize_to_width(700, column_width=800, natural_width=300)

    assert outcome.at_natural_size
    assert outcome.percent is None
    assert outcome.width_value is None


def test_resize_of_big_image_to_full_column_keeps_explicit_percent():
    outcome = resize_to_width(900, column_width=800, natural_width=4000)

    assert outcome == resize_to_width(800, column_width=800, natural_width=4000)
    assert outcome.percent == 100
    assert not outcome.at_natural_size


def test_resize_respects_minimum_and_float_ceiling():
    assert resize_to_width(3, column_width=800, natural_width=4000).percent == MIN_PERCENT
    floated = resize_to_width(700, column_width=800, natural_width=4000, align="left")
    assert floated.percent == 50


def test_resize_requires_a_positive_column():
    with pytest.raises(ValueError):
        resize_to_width(100, column_width=0, natural_width=100)
