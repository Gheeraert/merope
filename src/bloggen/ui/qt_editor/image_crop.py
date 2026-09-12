"""Pure crop geometry, expressed in the pixels of the image as displayed.

Coordinates are integer source pixels of the EXIF-oriented, rotated image
(the one a crop box refers to, see ``image_service.write_cropped_copy``);
rectangles are half-open. The dialog only converts mouse positions into
these coordinates, so no preview rounding ever reaches the saved file.
"""

from __future__ import annotations

from dataclasses import dataclass

MIN_CROP_SIZE = 8
CROP_CORNERS = ("nw", "ne", "sw", "se")
CROP_EDGES = ("n", "e", "s", "w")
CROP_HANDLES = CROP_CORNERS + CROP_EDGES

# (label, width, height); ``None`` sizes mean "free" or "original".
RATIO_PRESETS: tuple[tuple[str, int | None, int | None], ...] = (
    ("Libre", None, None),
    ("Proportions d’origine", 0, 0),
    ("Carré 1:1", 1, 1),
    ("4:3", 4, 3),
    ("3:2", 3, 2),
    ("16:9", 16, 9),
)


@dataclass(frozen=True, slots=True)
class CropRect:
    """Integer source-pixel boundaries using half-open right/bottom."""

    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top

    def box(self) -> tuple[int, int, int, int]:
        return self.left, self.top, self.right, self.bottom


def full_rect(width: int, height: int) -> CropRect:
    _validate_size(width, height)
    return CropRect(0, 0, width, height)


def preset_ratio(index: int, width: int, height: int) -> float | None:
    """Width/height ratio of a preset (``None`` = free)."""

    _label, ratio_w, ratio_h = RATIO_PRESETS[index]
    if ratio_w is None or ratio_h is None:
        return None
    if ratio_w == 0:
        return width / height
    return ratio_w / ratio_h


def clamp_rect(rect: CropRect, width: int, height: int, minimum: int = MIN_CROP_SIZE) -> CropRect:
    """Return a valid rectangle inside the image, keeping ``rect`` if possible."""

    _validate_size(width, height)
    min_w = min(minimum, width)
    min_h = min(minimum, height)
    left = max(0, min(rect.left, width - min_w))
    top = max(0, min(rect.top, height - min_h))
    right = max(left + min_w, min(rect.right, width))
    bottom = max(top + min_h, min(rect.bottom, height))
    return CropRect(left, top, right, bottom)


def move_rect(rect: CropRect, dx: int, dy: int, width: int, height: int) -> CropRect:
    """Translate without resizing, stopping at the image borders."""

    _validate_size(width, height)
    dx = max(-rect.left, min(int(dx), width - rect.right))
    dy = max(-rect.top, min(int(dy), height - rect.bottom))
    return CropRect(rect.left + dx, rect.top + dy, rect.right + dx, rect.bottom + dy)


def resize_rect(
    rect: CropRect,
    handle: str,
    x: float,
    y: float,
    width: int,
    height: int,
    *,
    ratio: float | None = None,
    minimum: int = MIN_CROP_SIZE,
) -> CropRect:
    """Drag one of the eight handles to ``(x, y)``.

    The opposite side (or corner) stays fixed; the dragged side never
    crosses it. With ``ratio`` (width/height) the rectangle keeps those
    proportions: corners follow the dominant pointer axis, edges grow the
    perpendicular dimension symmetrically around the current centre.
    """

    if handle not in CROP_HANDLES:
        raise ValueError(f"Poignée de recadrage inconnue : {handle}")
    _validate_size(width, height)
    min_w = min(minimum, width)
    min_h = min(minimum, height)
    x = max(0.0, min(float(x), float(width)))
    y = max(0.0, min(float(y), float(height)))
    left, top, right, bottom = (float(v) for v in rect.box())

    if ratio is None:
        if "w" in handle:
            left = min(x, right - min_w)
        if "e" in handle:
            right = max(x, left + min_w)
        if "n" in handle:
            top = min(y, bottom - min_h)
        if "s" in handle:
            bottom = max(y, top + min_h)
        return _rounded(left, top, right, bottom, width, height)

    if handle in CROP_CORNERS:
        anchor_x = right if "w" in handle else left
        anchor_y = bottom if "n" in handle else top
        return _ratio_from_anchor(
            anchor_x,
            anchor_y,
            x,
            y,
            -1 if "w" in handle else 1,
            -1 if "n" in handle else 1,
            ratio,
            width,
            height,
            min_w,
            min_h,
        )

    center_x = (left + right) / 2
    center_y = (top + bottom) / 2
    if handle in ("e", "w"):
        anchor = left if handle == "e" else right
        direction = 1 if handle == "e" else -1
        room_x = (width - anchor) if direction > 0 else anchor
        room_h = 2 * min(center_y, height - center_y)
        new_w = max(abs(x - anchor), min_w, min_h * ratio)
        new_w = min(new_w, room_x, room_h * ratio)
        new_h = new_w / ratio
        x0 = anchor if direction > 0 else anchor - new_w
        return _rounded(x0, center_y - new_h / 2, x0 + new_w, center_y + new_h / 2, width, height)

    anchor = top if handle == "s" else bottom
    direction = 1 if handle == "s" else -1
    room_y = (height - anchor) if direction > 0 else anchor
    room_w = 2 * min(center_x, width - center_x)
    new_h = max(abs(y - anchor), min_h, min_w / ratio)
    new_h = min(new_h, room_y, room_w / ratio)
    new_w = new_h * ratio
    y0 = anchor if direction > 0 else anchor - new_h
    return _rounded(center_x - new_w / 2, y0, center_x + new_w / 2, y0 + new_h, width, height)


def draw_rect(
    start_x: float,
    start_y: float,
    x: float,
    y: float,
    width: int,
    height: int,
    *,
    ratio: float | None = None,
    minimum: int = MIN_CROP_SIZE,
) -> CropRect:
    """Create a new selection by dragging from ``start`` to ``(x, y)``."""

    _validate_size(width, height)
    min_w = min(minimum, width)
    min_h = min(minimum, height)
    start_x = max(0.0, min(float(start_x), float(width)))
    start_y = max(0.0, min(float(start_y), float(height)))
    direction_x = -1 if x < start_x else 1
    direction_y = -1 if y < start_y else 1
    x = max(0.0, min(float(x), float(width)))
    y = max(0.0, min(float(y), float(height)))
    if ratio is not None:
        return _ratio_from_anchor(
            start_x, start_y, x, y, direction_x, direction_y, ratio, width, height, min_w, min_h
        )
    x0, x1 = sorted((start_x, x))
    y0, y1 = sorted((start_y, y))
    if x1 - x0 < min_w:
        x0, x1 = _grow_span(start_x, direction_x, min_w, width)
    if y1 - y0 < min_h:
        y0, y1 = _grow_span(start_y, direction_y, min_h, height)
    return _rounded(x0, y0, x1, y1, width, height)


def fit_ratio(rect: CropRect, ratio: float, width: int, height: int) -> CropRect:
    """Largest rectangle of ``ratio`` inside the image, centred on ``rect``."""

    _validate_size(width, height)
    new_w = float(width)
    new_h = new_w / ratio
    if new_h > height:
        new_h = float(height)
        new_w = new_h * ratio
    center_x = (rect.left + rect.right) / 2
    center_y = (rect.top + rect.bottom) / 2
    x0 = max(0.0, min(center_x - new_w / 2, width - new_w))
    y0 = max(0.0, min(center_y - new_h / 2, height - new_h))
    return _rounded(x0, y0, x0 + new_w, y0 + new_h, width, height)


def constrain_to_ratio(rect: CropRect, ratio: float, width: int, height: int) -> CropRect:
    """Largest rectangle of ``ratio`` that fits inside ``rect`` (centred)."""

    _validate_size(width, height)
    new_w = float(rect.width)
    new_h = new_w / ratio
    if new_h > rect.height:
        new_h = float(rect.height)
        new_w = new_h * ratio
    center_x = (rect.left + rect.right) / 2
    center_y = (rect.top + rect.bottom) / 2
    return _rounded(
        center_x - new_w / 2,
        center_y - new_h / 2,
        center_x + new_w / 2,
        center_y + new_h / 2,
        width,
        height,
    )


def rotate_rect(rect: CropRect, width: int, height: int, *, clockwise: bool) -> CropRect:
    """Map a selection onto the image rotated by a quarter turn.

    ``width``/``height`` are the dimensions *before* the rotation.
    """

    _validate_size(width, height)
    if clockwise:
        return CropRect(height - rect.bottom, rect.left, height - rect.top, rect.right)
    return CropRect(rect.top, width - rect.right, rect.bottom, width - rect.left)


def validate_source_box(
    box: tuple[int, int, int, int],
    source_width: int,
    source_height: int,
) -> tuple[int, int, int, int]:
    """Return a source box only when every half-open boundary is valid."""

    if len(box) != 4 or any(isinstance(value, bool) for value in box):
        raise ValueError("La boîte de recadrage doit contenir quatre entiers")
    if any(not isinstance(value, int) for value in box):
        raise ValueError("La boîte de recadrage doit contenir quatre entiers")
    left, top, right, bottom = box
    if not (0 <= left < right <= source_width):
        raise ValueError("Les limites horizontales du recadrage sont invalides")
    if not (0 <= top < bottom <= source_height):
        raise ValueError("Les limites verticales du recadrage sont invalides")
    return box


def _ratio_from_anchor(
    anchor_x: float,
    anchor_y: float,
    x: float,
    y: float,
    direction_x: int,
    direction_y: int,
    ratio: float,
    width: int,
    height: int,
    min_w: int,
    min_h: int,
) -> CropRect:
    room_x = (width - anchor_x) if direction_x > 0 else anchor_x
    room_y = (height - anchor_y) if direction_y > 0 else anchor_y
    new_w = max(0.0, (x - anchor_x) * direction_x)
    new_h = max(0.0, (y - anchor_y) * direction_y)
    # Follow whichever axis the pointer went furthest along.
    if new_h * ratio > new_w:
        new_w = new_h * ratio
    new_w = max(new_w, float(min_w), min_h * ratio)
    new_w = min(new_w, room_x, room_y * ratio)
    new_h = new_w / ratio
    x0 = anchor_x if direction_x > 0 else anchor_x - new_w
    y0 = anchor_y if direction_y > 0 else anchor_y - new_h
    return _rounded(x0, y0, x0 + new_w, y0 + new_h, width, height)


def _grow_span(start: float, direction: int, size: int, limit: int) -> tuple[float, float]:
    if direction > 0:
        end = min(start + size, float(limit))
        return end - size, end
    begin = max(start - size, 0.0)
    return begin, begin + size


def _rounded(
    left: float,
    top: float,
    right: float,
    bottom: float,
    width: int,
    height: int,
) -> CropRect:
    l = max(0, min(round(left), width - 1))
    t = max(0, min(round(top), height - 1))
    r = max(l + 1, min(round(right), width))
    b = max(t + 1, min(round(bottom), height))
    return CropRect(l, t, r, b)


def _validate_size(width: int, height: int) -> None:
    if width <= 0 or height <= 0:
        raise ValueError("La taille de l’image doit être positive")
