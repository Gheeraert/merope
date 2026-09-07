"""Slug helpers for page and post URLs."""

from __future__ import annotations

from pathlib import Path
import re
import unicodedata

_NON_ALNUM = re.compile(r"[^a-z0-9]+")

SLUG_FORMAT_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

# Windows reserves these device names for any path segment, with or
# without an extension (e.g. "con" and "con.md" both fail to create) —
# a slug matching one, case-insensitively, would make every generated
# path under it uncreatable on Windows.
_RESERVED_WINDOWS_NAMES = {
    "con", "prn", "aux", "nul",
    *(f"com{i}" for i in range(1, 10)),
    *(f"lpt{i}" for i in range(1, 10)),
}


def is_valid_slug_format(slug: str) -> bool:
    """Whether ``slug`` is safe to use as a single path segment.

    Requires the same charset ``slugify()`` produces
    (``[a-z0-9]+(-[a-z0-9]+)*``), which rules out path separators,
    ``.``/``..``, control characters, and empty segments — a slug taken
    verbatim from front matter (never itself passed through
    ``slugify()``) could otherwise be used to escape the output
    directory when building HTML/TEI destination paths.
    """
    return bool(SLUG_FORMAT_RE.match(slug)) and slug not in _RESERVED_WINDOWS_NAMES


def slugify(value: str, *, mode: str = "ascii") -> str:
    text = value.strip().lower()
    if mode == "ascii":
        text = unicodedata.normalize("NFKD", text)
        text = text.encode("ascii", "ignore").decode("ascii")
    text = _NON_ALNUM.sub("-", text)
    text = text.strip("-")
    return text or "untitled"


def slug_from_path(path: str | Path, *, mode: str = "ascii") -> str:
    return slugify(Path(path).stem, mode=mode)


def ensure_unique_slug(slug: str, used: set[str]) -> str:
    candidate = slug
    counter = 2
    while candidate in used:
        candidate = f"{slug}-{counter}"
        counter += 1
    used.add(candidate)
    return candidate
