"""Toolkit-free rules for an image's display width.

Mérope stores an image's display size in its Markdown attribute suffix:

* ``width=50%`` (current form) means *at most* half of the text column.
  The height always follows the image's proportions and a small image is
  never enlarged: the value is a ceiling, exactly like the site's CSS
  ``max-width`` and the Qt editor's percentage maximum width.
* ``width=400`` (historical form) is a fixed number of CSS pixels, still
  honoured everywhere so existing documents keep rendering as before.
* no width: the natural size, capped at the column width.

Floated (left/right aligned) figures are limited to half the column by the
site's stylesheet; the editor applies the same ceiling so what the author
sets is what readers get.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

MIN_PERCENT = 5
MAX_PERCENT = 100
FLOAT_MAX_PERCENT = 50
SNAP_PERCENTS = (25, 50, 75, 100)
SNAP_TOLERANCE = 2.0
MENU_PERCENTS = (25, 33, 50, 75, 100)
FLOAT_ALIGNMENTS = frozenset({"left", "right"})

_PERCENT_RE = re.compile(r"^\s*(\d+(?:[.,]\d+)?)\s*%\s*$")
_PIXELS_RE = re.compile(r"^\s*(\d+)\s*(?:px)?\s*$", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class WidthSpec:
    kind: Literal["percent", "pixels"]
    value: int

    @property
    def is_percent(self) -> bool:
        return self.kind == "percent"


@dataclass(frozen=True, slots=True)
class ResizeOutcome:
    """Result of an interactive resize.

    ``percent`` is ``None`` when the image returns to its natural size (the
    width attribute is then removed rather than pinned to the editor's
    column, which differs from the site's).
    """

    percent: int | None
    snapped: bool
    at_natural_size: bool

    @property
    def width_value(self) -> str | None:
        return None if self.percent is None else format_percent(self.percent)


def parse_width(value: str | None) -> WidthSpec | None:
    """Interpret a stored width; anything unusable means "natural size"."""

    if not value:
        return None
    match = _PERCENT_RE.match(value)
    if match:
        percent = round(float(match.group(1).replace(",", ".")))
        if percent <= 0:
            return None
        return WidthSpec("percent", min(percent, MAX_PERCENT))
    match = _PIXELS_RE.match(value)
    if match:
        pixels = int(match.group(1))
        return WidthSpec("pixels", pixels) if pixels > 0 else None
    return None


def legacy_pixels(value: str | None) -> int | None:
    """Return a historical pixel dimension, or ``None`` for any other form."""

    spec = parse_width(value)
    return spec.value if spec is not None and spec.kind == "pixels" else None


def format_percent(percent: int) -> str:
    return f"{int(percent)}%"


def max_percent_for(align: str | None) -> int:
    return FLOAT_MAX_PERCENT if align in FLOAT_ALIGNMENTS else MAX_PERCENT


def clamp_percent(percent: float, *, align: str | None = None) -> int:
    return int(max(MIN_PERCENT, min(round(percent), max_percent_for(align))))


def natural_percent(natural_width: int, column_width: float) -> float | None:
    """Natural width as a percentage of the column, if both are known."""

    if natural_width <= 0 or column_width <= 0:
        return None
    return natural_width * 100.0 / column_width


def displayed_percent(
    spec: WidthSpec | None,
    *,
    natural_width: int,
    column_width: float,
    align: str | None = None,
) -> float | None:
    """Percentage of the column the image currently occupies."""

    natural = natural_percent(natural_width, column_width)
    if natural is None:
        return None
    ceiling = float(max_percent_for(align))
    if spec is None:
        return min(natural, ceiling)
    if spec.kind == "percent":
        return min(float(spec.value), natural, ceiling)
    return min(spec.value * 100.0 / column_width, ceiling)


def resize_to_width(
    width_px: float,
    *,
    column_width: float,
    natural_width: int | None,
    align: str | None = None,
    snap: bool = True,
    tolerance: float = SNAP_TOLERANCE,
) -> ResizeOutcome:
    """Turn a dragged width into a stored percentage.

    The result is clamped between :data:`MIN_PERCENT` and the smaller of the
    alignment ceiling and the natural size (no enlargement). With ``snap``,
    values within ``tolerance`` points of 25/50/75/100 % or of the natural
    size stick to them.
    """

    if column_width <= 0:
        raise ValueError("La largeur de colonne doit être positive")
    ceiling = float(max_percent_for(align))
    natural = (
        natural_percent(natural_width, column_width)
        if natural_width is not None
        else None
    )
    limit = min(ceiling, natural) if natural is not None else ceiling
    limit = max(limit, float(MIN_PERCENT))
    percent = max(float(MIN_PERCENT), min(width_px * 100.0 / column_width, limit))

    snapped = False
    if snap:
        candidates = [float(value) for value in SNAP_PERCENTS if value <= limit]
        if natural is not None and natural < ceiling:
            candidates.append(limit)
        nearest = min(candidates, key=lambda value: abs(value - percent), default=None)
        if nearest is not None and abs(nearest - percent) <= tolerance:
            percent = nearest
            snapped = True

    at_natural = natural is not None and natural < ceiling and percent >= limit - 1e-9
    if at_natural:
        return ResizeOutcome(percent=None, snapped=snapped, at_natural_size=True)
    return ResizeOutcome(
        percent=clamp_percent(percent, align=align),
        snapped=snapped,
        at_natural_size=False,
    )
