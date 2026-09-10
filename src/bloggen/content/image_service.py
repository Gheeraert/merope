"""GUI-independent image operations used by content editors.

The Tkinter editor remains responsible for dialogs, mouse interaction and
rendering.  This module owns the filesystem/path rules and Pillow operations
that a future Qt adapter must share with it.
"""

from __future__ import annotations

import os
import shutil
from datetime import datetime
from pathlib import Path

from PIL import Image


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
        return Image.open(path).convert("RGB")
    except Exception:
        return Image.new("RGB", placeholder_size, color=placeholder_color)


def write_cropped_copy(
    source_path: Path,
    box: tuple[int, int, int, int],
    doc_dir: Path,
) -> str:
    """Write a numbered cropped copy and return its Markdown-relative path."""
    source_path = Path(source_path)
    image = Image.open(source_path)
    cropped = image.crop(box)
    counter = 1
    candidate = source_path.with_name(
        f"{source_path.stem}-crop{counter}{source_path.suffix}"
    )
    while candidate.exists():
        counter += 1
        candidate = source_path.with_name(
            f"{source_path.stem}-crop{counter}{source_path.suffix}"
        )
    cropped.convert("RGB").save(candidate)
    return relative_image_src(candidate, doc_dir)
