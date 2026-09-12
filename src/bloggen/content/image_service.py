"""GUI-independent image operations used by content editors.

The Tkinter editor remains responsible for dialogs, mouse interaction and
rendering.  This module owns the filesystem/path rules and Pillow operations
that a future Qt adapter must share with it.
"""

from __future__ import annotations

import os
import re
import shutil
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageOps, JpegImagePlugin


# Display-size presets are part of the editor's document behaviour rather
# than of a particular GUI toolkit.  Widths are expressed in pixels; ``None``
# means the image's natural width.
SIZE_PRESETS: dict[str, int | None] = {
    "petit": 240,
    "moyen": 420,
    "grand": 700,
    "original": None,
}
DEFAULT_SIZE_PRESET = "petit"


def relative_image_src(path: Path, doc_dir: Path) -> str:
    """Return a POSIX path to ``path`` relative to the Markdown directory."""
    return Path(os.path.relpath(path, doc_dir)).as_posix()


def copy_into_images_dir(source: Path, images_dir: Path, doc_dir: Path) -> str:
    """Copy an image into the project image directory without collisions.

    The returned path is relative to ``doc_dir``, matching the base used by
    the Markdown/Pandoc publication pipeline.  Re-selecting a file that is
    already inside ``images_dir`` is a no-op, as in the historical Tkinter
    implementation.
    """
    source = Path(source)
    images_dir = Path(images_dir)
    doc_dir = Path(doc_dir)
    images_dir.mkdir(parents=True, exist_ok=True)
    destination = images_dir / source.name
    counter = 2
    while destination.exists() and source.resolve() != destination.resolve():
        destination = images_dir / f"{source.stem}-{counter}{source.suffix}"
        counter += 1
    if not destination.exists():
        shutil.copyfile(source, destination)
    return relative_image_src(destination, doc_dir)


def grab_clipboard_image() -> Image.Image | None:
    """Return a bitmap or a single image file from the system clipboard.

    Pillow provides the platform integration.  Failures and non-image
    clipboard contents deliberately return ``None`` so a GUI adapter can
    continue with its ordinary text-paste path.
    """
    try:
        from PIL import ImageGrab

        content = ImageGrab.grabclipboard()
    except Exception:
        return None
    if isinstance(content, Image.Image):
        return content
    if isinstance(content, list) and len(content) == 1:
        try:
            return Image.open(content[0])
        except Exception:
            return None
    return None


def save_clipboard_image(image: Image.Image, images_dir: Path, doc_dir: Path) -> str:
    """Save a clipboard image as a collision-free PNG and return its source."""
    images_dir = Path(images_dir)
    doc_dir = Path(doc_dir)
    images_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    destination = images_dir / f"presse-papiers-{timestamp}.png"
    counter = 2
    while destination.exists():
        destination = images_dir / f"presse-papiers-{timestamp}-{counter}.png"
        counter += 1
    if image.mode not in ("RGB", "RGBA", "L", "LA", "P"):
        image = image.convert("RGBA")
    image.save(destination, "PNG")
    return relative_image_src(destination, doc_dir)


def calculate_display_size(
    natural_size: tuple[int, int],
    *,
    width: int | None = None,
    height: int | None = None,
    size_preset: str | None = None,
) -> tuple[int, int]:
    """Calculate the initial editor display size with historical semantics."""
    natural_width, natural_height = natural_size
    if width and height:
        return width, height
    if width and natural_width:
        # A width alone keeps the image's own proportions.
        return width, max(1, round(natural_height * width / natural_width))
    cap = SIZE_PRESETS.get(
        size_preset or DEFAULT_SIZE_PRESET,
        SIZE_PRESETS[DEFAULT_SIZE_PRESET],
    )
    display_width = min(natural_width, cap) if cap is not None else natural_width
    display_height = (
        round(natural_height * (display_width / natural_width))
        if natural_width
        else natural_height
    )
    return display_width, display_height


def load_image_or_placeholder(
    path: Path,
    *,
    placeholder_size: tuple[int, int] = (200, 150),
    placeholder_color: str = "#cccccc",
) -> Image.Image:
    """Load an editor image as RGB, or return the historical placeholder."""
    try:
        with Image.open(path) as opened:
            return ImageOps.exif_transpose(opened).convert("RGB")
    except Exception:
        return Image.new("RGB", placeholder_size, color=placeholder_color)


# EXIF orientations 5-8 store the picture sideways: width and height swap
# once the orientation is applied, which is what browsers display.
_SIDEWAYS_ORIENTATIONS = frozenset({5, 6, 7, 8})
_EXIF_ORIENTATION = 0x0112
_CROP_SUFFIX_RE = re.compile(r"-crop\d+$")
_JPEG_QUALITY = 95
_PROBE_CACHE: dict[Path, tuple[tuple[int, int], tuple[int, int] | None]] = {}


def _orientation(image: Image.Image) -> int:
    try:
        return int(image.getexif().get(_EXIF_ORIENTATION, 1))
    except Exception:  # noqa: BLE001 - malformed EXIF must not block editing
        return 1


def _oriented_size(image: Image.Image) -> tuple[int, int]:
    width, height = image.size
    if _orientation(image) in _SIDEWAYS_ORIENTATIONS:
        return height, width
    return width, height


def rotated_size(size: tuple[int, int], quarter_turns: int) -> tuple[int, int]:
    width, height = size
    return (height, width) if quarter_turns % 2 else (width, height)


def _rotate(image: Image.Image, quarter_turns: int) -> Image.Image:
    turns = quarter_turns % 4
    if turns == 1:
        return image.transpose(Image.Transpose.ROTATE_270)  # clockwise
    if turns == 2:
        return image.transpose(Image.Transpose.ROTATE_180)
    if turns == 3:
        return image.transpose(Image.Transpose.ROTATE_90)
    return image


def probe_image(path: Path) -> tuple[int, int] | None:
    """Displayed (EXIF-oriented) size of a readable bitmap, or ``None``.

    Only the file header is read, and the answer is cached per
    (modification time, size): editors call this on every cursor move.
    """
    try:
        resolved = Path(path).resolve()
        stat = resolved.stat()
    except (OSError, RuntimeError):
        return None
    key = (stat.st_mtime_ns, stat.st_size)
    cached = _PROBE_CACHE.get(resolved)
    if cached is not None and cached[0] == key:
        return cached[1]
    try:
        with Image.open(resolved) as opened:
            size = _oriented_size(opened)
    except Exception:  # noqa: BLE001 - any undecodable file is "not an image"
        size = None
    if size is not None and (size[0] <= 0 or size[1] <= 0):
        size = None
    if len(_PROBE_CACHE) > 512:
        _PROBE_CACHE.clear()
    _PROBE_CACHE[resolved] = (key, size)
    return size


def load_oriented_preview(
    path: Path,
    max_dimension: int,
) -> tuple[Image.Image, tuple[int, int]]:
    """Decode a reduced, EXIF-oriented RGBA preview and the full oriented size.

    JPEG files are decoded directly at a reduced scale (``draft``), so a
    24-megapixel photo opens in a fraction of a full decode.
    """
    try:
        with Image.open(path) as opened:
            full_size = _oriented_size(opened)
            if opened.format == "JPEG":
                opened.draft("RGB", (max_dimension, max_dimension))
            image = ImageOps.exif_transpose(opened)
            image.thumbnail((max_dimension, max_dimension))
            preview = image.convert("RGBA")
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"Le fichier image ne peut pas être lu : {path}") from exc
    if full_size[0] <= 0 or full_size[1] <= 0:
        raise ValueError("L’image ne possède pas de dimensions recadrables")
    return preview, full_size


def edited_size(source_path: Path, quarter_turns: int = 0) -> tuple[int, int]:
    """Size of the oriented, rotated image a crop box refers to."""
    size = probe_image(source_path)
    if size is None:
        raise ValueError(f"Le fichier image ne peut pas être lu : {source_path}")
    return rotated_size(size, quarter_turns)


def crop_is_identity(
    source_path: Path,
    box: tuple[int, int, int, int],
    quarter_turns: int = 0,
) -> bool:
    """True when cropping would reproduce exactly what is already displayed."""
    width, height = edited_size(source_path, quarter_turns)
    return quarter_turns % 4 == 0 and tuple(box) == (0, 0, width, height)


def _validate_box(box: tuple[int, int, int, int], size: tuple[int, int]) -> None:
    if len(box) != 4 or any(
        isinstance(value, bool) or not isinstance(value, int) for value in box
    ):
        raise ValueError("La boîte de recadrage doit contenir quatre entiers")
    left, top, right, bottom = box
    width, height = size
    if not (0 <= left < right <= width):
        raise ValueError("Les limites horizontales du recadrage sont invalides")
    if not (0 <= top < bottom <= height):
        raise ValueError("Les limites verticales du recadrage sont invalides")


def _next_crop_path(source_path: Path) -> Path:
    # Cropping "photo-crop2.jpg" yields "photo-crop3.jpg", not a growing
    # "photo-crop2-crop1.jpg" chain.
    base = _CROP_SUFFIX_RE.sub("", source_path.stem) or source_path.stem
    counter = 1
    while True:
        candidate = source_path.with_name(f"{base}-crop{counter}{source_path.suffix}")
        if not candidate.exists():
            return candidate
        counter += 1


def _save_like_source(
    image: Image.Image,
    destination: Path,
    *,
    source_format: str | None,
    icc_profile: bytes | None,
    jpeg_sampling: int,
) -> None:
    """Save without avoidable quality loss.

    Transparency and the colour profile survive; JPEG is re-encoded at high
    quality with the source's chroma subsampling. Other EXIF data (camera,
    GPS position...) is deliberately not copied into a published image.
    """
    options: dict[str, object] = {}
    if icc_profile:
        options["icc_profile"] = icc_profile
    target_format = Image.registered_extensions().get(destination.suffix.lower())
    target_format = target_format or source_format
    if target_format == "JPEG":
        if image.mode not in ("RGB", "L", "CMYK"):
            image = image.convert("RGB")
        options.update(quality=_JPEG_QUALITY, optimize=True)
        if jpeg_sampling >= 0:
            options["subsampling"] = jpeg_sampling
    elif target_format == "WEBP":
        options.update(quality=_JPEG_QUALITY)
    elif target_format not in ("PNG", "GIF", "TIFF", "BMP"):
        if image.mode not in ("RGB", "RGBA", "L", "LA"):
            image = image.convert("RGBA")
    image.save(destination, format=target_format, **options)


def write_cropped_copy(
    source_path: Path,
    box: tuple[int, int, int, int],
    doc_dir: Path,
    *,
    quarter_turns: int = 0,
) -> str:
    """Write a numbered edited copy and return its Markdown-relative path.

    ``box`` is expressed in the pixels of the image as displayed: EXIF
    orientation applied, then ``quarter_turns`` clockwise quarter turns.
    The original file is never modified.
    """
    source_path = Path(source_path)
    with Image.open(source_path) as opened:
        source_format = opened.format
        icc_profile = opened.info.get("icc_profile")
        jpeg_sampling = (
            JpegImagePlugin.get_sampling(opened) if source_format == "JPEG" else -1
        )
        image = _rotate(ImageOps.exif_transpose(opened), quarter_turns)
        _validate_box(tuple(box), image.size)
        cropped = image.crop(tuple(box))
    candidate = _next_crop_path(source_path)
    try:
        _save_like_source(
            cropped,
            candidate,
            source_format=source_format,
            icc_profile=icc_profile,
            jpeg_sampling=jpeg_sampling,
        )
    except Exception:
        candidate.unlink(missing_ok=True)
        raise
    return relative_image_src(candidate, doc_dir)
