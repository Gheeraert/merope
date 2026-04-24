"""Content metadata extraction helpers."""

from __future__ import annotations

from dataclasses import dataclass
import re

from bloggen.content.slugify import slugify

_HEADING_RE = re.compile(r"^#{1,6}\s+(.+?)\s*$")


@dataclass(slots=True)
class ContentMetadata:
    title: str
    slug: str
    kind: str
    date: str | None
    layout: str
    author: str | None = None


def extract_first_heading(markdown_body: str) -> str | None:
    for line in markdown_body.splitlines():
        match = _HEADING_RE.match(line.strip())
        if match:
            return match.group(1).strip()
    return None


def build_content_metadata(
    *,
    source_stem: str,
    front_matter: dict[str, str],
    markdown_body: str,
    kind: str,
    default_layout: str,
    slug_mode: str = "ascii",
) -> ContentMetadata:
    title = (
        front_matter.get("title")
        or extract_first_heading(markdown_body)
        or source_stem.replace("-", " ").replace("_", " ").strip().title()
    )
    slug = front_matter.get("slug") or slugify(title or source_stem, mode=slug_mode)
    date = front_matter.get("date")
    layout = front_matter.get("layout") or default_layout
    author = front_matter.get("author")

    return ContentMetadata(
        title=title,
        slug=slug,
        kind=kind,
        date=date,
        layout=layout,
        author=author,
    )
