"""Content file loading for pages and posts."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from bloggen.config.models import ProjectConfig
from bloggen.content.assets import LinkedAssetReference, collect_linked_assets
from bloggen.content.metadata import ContentMetadata, ContentMetadataError, build_content_metadata
from bloggen.content.slugify import ensure_unique_slug
from bloggen.markdown.front_matter import FrontMatterParseError, parse_front_matter
from bloggen.markdown.normalizer import normalize_markdown_text


@dataclass(slots=True)
class ContentItem:
    source_path: Path
    kind: str
    metadata: ContentMetadata
    front_matter: dict[str, str]
    raw_markdown: str
    normalized_markdown: str
    linked_assets: list[LinkedAssetReference] = field(default_factory=list)


@dataclass(slots=True)
class LoadedContent:
    pages: list[ContentItem] = field(default_factory=list)
    posts: list[ContentItem] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class ContentLoadError(ValueError):
    """Raised when markdown content is invalid for publication."""


def load_content(project_root: Path, config: ProjectConfig) -> LoadedContent:
    pages_dir = (project_root / config.paths.pages_dir).resolve()
    posts_dir = (project_root / config.paths.posts_dir).resolve()

    result = LoadedContent()
    used_slugs: set[str] = set()

    if pages_dir.exists():
        result.pages, page_warnings = _load_items_from_dir(
            pages_dir,
            project_root=project_root,
            kind="page",
            default_layout=config.content.default_page_layout,
            slug_mode=config.content.slugify_mode,
            markdown_origin=config.content.markdown_origin,
            used_slugs=used_slugs,
        )
        result.warnings.extend(page_warnings)
    else:
        result.warnings.append(f"Dossier pages introuvable: {pages_dir}")

    if posts_dir.exists():
        result.posts, post_warnings = _load_items_from_dir(
            posts_dir,
            project_root=project_root,
            kind="post",
            default_layout=config.content.default_post_layout,
            slug_mode=config.content.slugify_mode,
            markdown_origin=config.content.markdown_origin,
            used_slugs=used_slugs,
        )
        result.warnings.extend(post_warnings)
    else:
        result.warnings.append(f"Dossier billets introuvable: {posts_dir}")

    return result


def _load_items_from_dir(
    directory: Path,
    *,
    project_root: Path,
    kind: str,
    default_layout: str,
    slug_mode: str,
    markdown_origin: str,
    used_slugs: set[str],
) -> tuple[list[ContentItem], list[str]]:
    items: list[ContentItem] = []
    warnings: list[str] = []

    for path in sorted(directory.rglob("*.md")):
        raw_markdown = path.read_text(encoding="utf-8")
        try:
            parsed = parse_front_matter(raw_markdown)
        except FrontMatterParseError as exc:
            raise ContentLoadError(f"Front matter YAML invalide dans {path}: {exc}") from exc
        if not parsed.has_front_matter:
            raise ContentLoadError(f"Front matter YAML manquant dans {path}.")

        normalized = normalize_markdown_text(
            parsed.body,
            google_docs_mode=(markdown_origin == "google_docs_export"),
        )
        try:
            metadata = build_content_metadata(
                front_matter=parsed.metadata,
                kind=kind,
                default_layout=default_layout,
                source_path=str(path),
            )
        except ContentMetadataError as exc:
            raise ContentLoadError(str(exc)) from exc

        if metadata.draft:
            warnings.append(f"Brouillon ignoré: {path}")
            continue

        metadata.slug = ensure_unique_slug(metadata.slug, used_slugs)

        linked_assets = collect_linked_assets(path, normalized, project_root=project_root)
        for linked in linked_assets:
            if linked.exists:
                continue
            warnings.append(
                f"Image ou média introuvable pour {path}: '{linked.target}' -> {linked.resolved_path}"
            )

        items.append(
            ContentItem(
                source_path=path,
                kind=kind,
                metadata=metadata,
                front_matter=parsed.metadata,
                raw_markdown=raw_markdown,
                normalized_markdown=normalized,
                linked_assets=linked_assets,
            )
        )

    return items, warnings
