"""Slug helpers for page and post URLs."""

from __future__ import annotations

from pathlib import Path
import re
import unicodedata

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


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
