"""Write new/edited page and post Markdown files to disk.

Counterpart to :mod:`bloggen.content.loader` (which only reads content):
this module is what the content-authoring UI calls to persist a page or
post, keeping slug/filename conventions consistent with the rest of the
pipeline.
"""

from __future__ import annotations

from pathlib import Path

from bloggen.content.slugify import ensure_unique_slug, slugify
from bloggen.markdown.front_matter import format_front_matter, parse_front_matter


def scan_existing_slugs(pages_dir: Path, posts_dir: Path) -> set[str]:
    """Collect slugs already in use across pages and posts.

    Tolerant of unreadable/invalid files: a broken legacy file elsewhere in
    the project should not prevent authoring a new one. Compare with
    :func:`bloggen.content.loader.load_content`, which is strict on purpose
    for the actual build.
    """
    slugs: set[str] = set()
    for directory in (pages_dir, posts_dir):
        if not directory.exists():
            continue
        for path in directory.rglob("*.md"):
            try:
                text = path.read_text(encoding="utf-8")
                result = parse_front_matter(text)
            except (OSError, ValueError):
                continue
            slug = result.metadata.get("slug", "").strip()
            if slug:
                slugs.add(slug)
    return slugs


def suggest_slug(title: str, *, mode: str = "ascii", existing: set[str] | None = None) -> str:
    """Suggest a unique slug for ``title``, without reserving it.

    Safe to call repeatedly (e.g. on every keystroke while typing a title):
    ``existing`` is never mutated.
    """
    candidate = slugify(title, mode=mode)
    return ensure_unique_slug(candidate, set(existing or ()))


def default_filename(kind: str, slug: str, *, date: str | None = None) -> str:
    if kind == "post":
        if not date:
            raise ValueError("Une date est requise pour nommer le fichier d'un billet.")
        return f"{date}-{slug}.md"
    return f"{slug}.md"


def write_content_file(
    directory: Path,
    filename: str,
    metadata: dict[str, str],
    markdown_body: str,
) -> Path:
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / filename
    text = format_front_matter(metadata) + "\n" + markdown_body
    path.write_text(text, encoding="utf-8")
    return path


def read_content_file(path: Path) -> tuple[dict[str, str], str]:
    text = Path(path).read_text(encoding="utf-8")
    result = parse_front_matter(text)
    return result.metadata, result.body
