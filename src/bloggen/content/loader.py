"""Content file loading for pages and posts."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from bloggen.config.models import ProjectConfig
from bloggen.content.metadata import ContentMetadata, build_content_metadata
from bloggen.content.slugify import ensure_unique_slug
from bloggen.markdown.front_matter import parse_front_matter
from bloggen.markdown.normalizer import normalize_markdown_text


@dataclass(slots=True)
class ContentItem:
    source_path: Path
    kind: str
    metadata: ContentMetadata
    front_matter: dict[str, str]
    raw_markdown: str
    normalized_markdown: str


@dataclass(slots=True)
class LoadedContent:
    pages: list[ContentItem] = field(default_factory=list)
    posts: list[ContentItem] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def load_content(project_root: Path, config: ProjectConfig) -> LoadedContent:
    pages_dir = (project_root / config.paths.pages_dir).resolve()
    posts_dir = (project_root / config.paths.posts_dir).resolve()

    result = LoadedContent()
    used_slugs: set[str] = set()

    if pages_dir.exists():
        result.pages = _load_items_from_dir(
            pages_dir,
            kind="page",
            default_layout=config.content.default_page_layout,
            slug_mode=config.content.slugify_mode,
            markdown_origin=config.content.markdown_origin,
            used_slugs=used_slugs,
        )
    else:
        result.warnings.append(f"Dossier pages introuvable: {pages_dir}")

    if posts_dir.exists():
        result.posts = _load_items_from_dir(
            posts_dir,
            kind="post",
            default_layout=config.content.default_post_layout,
            slug_mode=config.content.slugify_mode,
            markdown_origin=config.content.markdown_origin,
            used_slugs=used_slugs,
        )
    else:
        result.warnings.append(f"Dossier billets introuvable: {posts_dir}")

    return result


def _load_items_from_dir(
    directory: Path,
    *,
    kind: str,
    default_layout: str,
    slug_mode: str,
    markdown_origin: str,
    used_slugs: set[str],
) -> list[ContentItem]:
    items: list[ContentItem] = []
    for path in sorted(directory.rglob("*.md")):
        raw_markdown = path.read_text(encoding="utf-8")
        parsed = parse_front_matter(raw_markdown)
        normalized = normalize_markdown_text(
            parsed.body,
            google_docs_mode=(markdown_origin == "google_docs_export"),
        )
        metadata = build_content_metadata(
            source_stem=path.stem,
            front_matter=parsed.metadata,
            markdown_body=normalized,
            kind=kind,
            default_layout=default_layout,
            slug_mode=slug_mode,
        )
        metadata.slug = ensure_unique_slug(metadata.slug, used_slugs)
        items.append(
            ContentItem(
                source_path=path,
                kind=kind,
                metadata=metadata,
                front_matter=parsed.metadata,
                raw_markdown=raw_markdown,
                normalized_markdown=normalized,
            )
        )
    return items
