"""Small toolbar icons for the content editor's formatting toolbar.

Drawn at runtime as 16x16 ``tk.PhotoImage`` bitmaps — bar-and-block
pictograms in the same spirit as the icons TinyMCE/Word use for the same
actions (blockquote = indent bar + text lines, lists = marker + lines,
alignment = ragged/flush text-line bars, link/image/table/save =
simplified pictograms) — rather than external image files, so there is
nothing to bundle, license, or keep in sync with a particular icon pack.

Background/foreground default to a plain light-gray-on-dark-gray pair, but
:func:`configure_colors` lets a caller resolve the active Tk theme's real
button colors first (``PhotoImage.put()`` only accepts ``#rrggbb`` colors,
not the symbolic names like ``SystemButtonFace`` widget options otherwise
take — resolve those via ``widget.winfo_rgb(...)`` and pass the hex result
in), so icons match the active Windows theme (including dark mode) instead
of a hard-coded color that could clash.

Every ``icon_*()`` call returns a fresh ``PhotoImage``; callers must keep a
reference to it for as long as the button using it exists (Tk does not —
an image with no surviving Python reference can be garbage-collected out
from under the widget displaying it).
"""

from __future__ import annotations

import tkinter as tk

_SIZE = 16
_BG = "#f0f0f0"
_FG = "#1e1e1e"


def configure_colors(bg: str, fg: str) -> None:
    """Set the ``#rrggbb`` background/foreground used by every icon drawn
    after this call. Meant to be called once, early, with colors resolved
    from the real active theme (see module docstring); icons drawn before
    any call keep the plain default pair.
    """
    global _BG, _FG
    _BG = bg
    _FG = fg


def _blank() -> tk.PhotoImage:
    image = tk.PhotoImage(width=_SIZE, height=_SIZE)
    image.put(_BG, to=(0, 0, _SIZE, _SIZE))
    return image


def _fill_rect(image: tk.PhotoImage, x0: int, y0: int, x1: int, y1: int, color: str = _FG) -> None:
    """Fill the inclusive pixel rectangle [x0, x1] x [y0, y1]."""
    image.put(color, to=(x0, y0, x1 + 1, y1 + 1))


def _rect_outline(image: tk.PhotoImage, x0: int, y0: int, x1: int, y1: int, color: str = _FG) -> None:
    _fill_rect(image, x0, y0, x1, y0, color)
    _fill_rect(image, x0, y1, x1, y1, color)
    _fill_rect(image, x0, y0, x0, y1, color)
    _fill_rect(image, x1, y0, x1, y1, color)


def icon_blockquote() -> tk.PhotoImage:
    image = _blank()
    _fill_rect(image, 2, 2, 3, 13)
    for y0 in (3, 7, 11):
        _fill_rect(image, 6, y0, 13, y0 + 1)
    return image


def icon_bullet_list() -> tk.PhotoImage:
    image = _blank()
    for y0 in (2, 7, 12):
        _fill_rect(image, 2, y0, 3, y0 + 1)
        _fill_rect(image, 6, y0, 13, y0 + 1)
    return image


def icon_ordered_list() -> tk.PhotoImage:
    image = _blank()
    for y0 in (2, 7, 12):
        _fill_rect(image, 2, y0 - 1, 2, y0 + 2)  # tall numeral-like tick
        _fill_rect(image, 6, y0, 13, y0 + 1)
    return image


def _align_icon(lengths: list[int], side: str) -> tk.PhotoImage:
    image = _blank()
    left, right = 2, 13
    y = 2
    for length in lengths:
        if side == "left":
            x0, x1 = left, left + length
        elif side == "right":
            x0, x1 = right - length, right
        else:  # "center"
            pad = ((right - left) - length) // 2
            x0, x1 = left + pad, left + pad + length
        _fill_rect(image, x0, y, x1, y + 1)
        y += 4
    return image


def icon_align_left() -> tk.PhotoImage:
    return _align_icon([11, 7, 11, 5], "left")


def icon_align_center() -> tk.PhotoImage:
    return _align_icon([11, 7, 11, 5], "center")


def icon_align_right() -> tk.PhotoImage:
    return _align_icon([11, 7, 11, 5], "right")


def icon_align_justify() -> tk.PhotoImage:
    return _align_icon([11, 11, 11, 11], "left")


def icon_link() -> tk.PhotoImage:
    image = _blank()
    # Two overlapping rings, offset diagonally, to read as a linked chain
    # rather than two separate boxes.
    _rect_outline(image, 2, 4, 8, 9)
    _rect_outline(image, 7, 7, 13, 12)
    return image


def icon_image() -> tk.PhotoImage:
    image = _blank()
    _rect_outline(image, 1, 3, 14, 12)
    _fill_rect(image, 10, 5, 11, 6)  # "sun"
    _fill_rect(image, 3, 9, 5, 10)  # "mountains"
    _fill_rect(image, 4, 8, 7, 9)
    _fill_rect(image, 8, 10, 12, 11)
    return image


def icon_table() -> tk.PhotoImage:
    image = _blank()
    _rect_outline(image, 1, 2, 14, 13)
    _fill_rect(image, 1, 6, 14, 6)
    _fill_rect(image, 1, 9, 14, 9)
    _fill_rect(image, 6, 2, 6, 13)
    _fill_rect(image, 10, 2, 10, 13)
    return image


def icon_save() -> tk.PhotoImage:
    image = _blank()
    _rect_outline(image, 2, 2, 13, 13)
    _fill_rect(image, 4, 2, 11, 5)  # write-protect tab
    _fill_rect(image, 4, 8, 11, 12)  # label area
    return image
