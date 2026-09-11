"""Pure geometry for selecting a crop in a reduced image preview."""

from __future__ import annotations

from dataclasses import dataclass


MAX_CROP_PREVIEW_DIMENSION = 700
MIN_CROP_PREVIEW_SIZE = 20
CROP_INSET_RATIO = 0.10
CROP_CORNERS = ("nw", "ne", "sw", "se")


@dataclass(frozen=True, slots=True)
class CropRect:
    """Integer preview boundaries using half-open right/bottom coordinates."""

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


@dataclass(frozen=True, slots=True)
class CropPreviewGeometry:
    source_width: int
    source_height: int
    preview_width: int
    preview_height: int
    scale: float


def calculate_crop_preview(
    source_width: int,
    source_height: int,
    *,
    max_dimension: int = MAX_CROP_PREVIEW_DIMENSION,
) -> CropPreviewGeometry:
    """Fit a source image into the preview without enlarging it."""

    if source_width <= 0 or source_height <= 0:
        raise ValueError("La taille de l’image source doit être positive")
    if max_dimension <= 0:
        raise ValueError("La taille maximale de prévisualisation doit être positive")
    scale = min(1.0, max_dimension / max(source_width, source_height))
    preview_width = max(1, round(source_width * scale))
    preview_height = max(1, round(source_height * scale))
    return CropPreviewGeometry(
        source_width=source_width,
        source_height=source_height,
        preview_width=preview_width,
        preview_height=preview_height,
        scale=scale,
    )


def initial_crop_rect(
    geometry: CropPreviewGeometry,
    *,
    inset_ratio: float = CROP_INSET_RATIO,
    minimum: int = MIN_CROP_PREVIEW_SIZE,
) -> CropRect:
    """Create an approximately ten-percent inset rectangle."""

    if not 0 <= inset_ratio < 0.5:
        raise ValueError("La marge initiale doit être comprise entre 0 et 0,5")
    width = geometry.preview_width
    height = geometry.preview_height
    left = round(width * inset_ratio)
    top = round(height * inset_ratio)
    right = round(width * (1 - inset_ratio))
    bottom = round(height * (1 - inset_ratio))
    min_width = min(max(1, minimum), width)
    min_height = min(max(1, minimum), height)
    if right - left < min_width:
        left, right = 0, width
    if bottom - top < min_height:
        top, bottom = 0, height
    return CropRect(left, top, right, bottom)


def move_crop_corner(
    rect: CropRect,
    corner: str,
    x: int,
    y: int,
    geometry: CropPreviewGeometry,
    *,
    minimum: int = MIN_CROP_PREVIEW_SIZE,
) -> CropRect:
    """Move one corner freely while retaining bounds and minimum dimensions."""

    if corner not in CROP_CORNERS:
        raise ValueError(f"Coin de recadrage inconnu : {corner}")
    _validate_preview_rect(rect, geometry)
    width = geometry.preview_width
    height = geometry.preview_height
    min_width = min(max(1, minimum), width)
    min_height = min(max(1, minimum), height)
    x = max(0, min(int(x), width))
    y = max(0, min(int(y), height))
    left, top, right, bottom = rect.left, rect.top, rect.right, rect.bottom

    if corner == "nw":
        left = min(x, right - min_width)
        top = min(y, bottom - min_height)
    elif corner == "ne":
        right = max(x, left + min_width)
        top = min(y, bottom - min_height)
    elif corner == "sw":
        left = min(x, right - min_width)
        bottom = max(y, top + min_height)
    else:
        right = max(x, left + min_width)
        bottom = max(y, top + min_height)

    return CropRect(left, top, right, bottom)


def preview_rect_to_source_box(
    rect: CropRect,
    geometry: CropPreviewGeometry,
) -> tuple[int, int, int, int]:
    """Convert preview boundaries into a valid Pillow source-pixel box."""

    _validate_preview_rect(rect, geometry)
    source_width = geometry.source_width
    source_height = geometry.source_height
    left = round(rect.left * source_width / geometry.preview_width)
    top = round(rect.top * source_height / geometry.preview_height)
    right = round(rect.right * source_width / geometry.preview_width)
    bottom = round(rect.bottom * source_height / geometry.preview_height)
    left = max(0, min(left, source_width - 1))
    top = max(0, min(top, source_height - 1))
    right = max(left + 1, min(right, source_width))
    bottom = max(top + 1, min(bottom, source_height))
    return left, top, right, bottom


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


def _validate_preview_rect(
    rect: CropRect,
    geometry: CropPreviewGeometry,
) -> None:
    if not (0 <= rect.left < rect.right <= geometry.preview_width):
        raise ValueError("Rectangle horizontal hors de la prévisualisation")
    if not (0 <= rect.top < rect.bottom <= geometry.preview_height):
        raise ValueError("Rectangle vertical hors de la prévisualisation")
