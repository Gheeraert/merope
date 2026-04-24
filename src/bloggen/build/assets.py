"""Asset copy helpers for static site build."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
import os
import shutil

from bloggen.content.assets import LinkedAssetReference


@dataclass(slots=True)
class LinkedAssetsCopyResult:
    rewritten_targets: dict[str, str] = field(default_factory=dict)
    copied_files: list[Path] = field(default_factory=list)
    missing: list[LinkedAssetReference] = field(default_factory=list)


def copy_tree_if_exists(source: Path, destination: Path) -> int:
    if not source.exists():
        return 0
    copied = 0
    for path in source.rglob("*"):
        if path.is_dir():
            continue
        target = destination / path.relative_to(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        copied += 1
    return copied


def copy_project_assets(project_root: Path, assets_dir: str, output_root: Path) -> int:
    source = (project_root / assets_dir).resolve()
    destination = output_root / assets_dir
    return copy_tree_if_exists(source, destination)


def copy_linked_content_assets(
    *,
    references: list[LinkedAssetReference],
    project_root: Path,
    output_root: Path,
    html_output_dir: Path,
    source_markdown_path: Path,
    item_kind: str,
    item_slug: str,
    assets_dir: str,
    copy_project_assets_enabled: bool,
) -> LinkedAssetsCopyResult:
    result = LinkedAssetsCopyResult()
    if not references:
        return result

    project_root = project_root.resolve()
    output_root = output_root.resolve()
    html_output_dir = html_output_dir.resolve()
    source_markdown_path = source_markdown_path.resolve()

    project_assets_root = (project_root / assets_dir).resolve()
    seen_destinations: dict[Path, Path] = {}
    copied_sources: dict[Path, Path] = {}

    for ref in references:
        if not ref.exists:
            result.missing.append(ref)
            continue

        source = ref.resolved_path
        if source in copied_sources:
            destination = copied_sources[source]
        else:
            destination, skip_copy = _resolve_destination(
                source=source,
                target=ref.target,
                project_root=project_root,
                project_assets_root=project_assets_root,
                source_markdown_path=source_markdown_path,
                output_root=output_root,
                item_kind=item_kind,
                item_slug=item_slug,
                copy_project_assets_enabled=copy_project_assets_enabled,
            )
            destination = _ensure_unique_destination(destination, source, seen_destinations)
            copied_sources[source] = destination

            if not skip_copy:
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
                result.copied_files.append(destination)

        public_url = _relative_url(from_dir=html_output_dir, to_path=destination)
        result.rewritten_targets[ref.target] = public_url
        result.rewritten_targets[ref.target.replace("\\", "/")] = public_url

    return result


def copy_builtin_resources(output_root: Path) -> int:
    resources_root = Path(__file__).resolve().parent.parent / "resources"
    copied = 0
    copied += copy_tree_if_exists(resources_root / "css", output_root / "static" / "css")
    copied += copy_tree_if_exists(resources_root / "js", output_root / "static" / "js")
    return copied


def _resolve_destination(
    *,
    source: Path,
    target: str,
    project_root: Path,
    project_assets_root: Path,
    source_markdown_path: Path,
    output_root: Path,
    item_kind: str,
    item_slug: str,
    copy_project_assets_enabled: bool,
) -> tuple[Path, bool]:
    if source.is_relative_to(project_assets_root):
        if source.is_relative_to(project_root):
            destination = output_root / source.relative_to(project_root)
        else:
            destination = output_root / "assets" / source.name
        skip_copy = copy_project_assets_enabled
        return destination, skip_copy

    relative_parts = _safe_relative_parts(target=target, source_markdown_path=source_markdown_path)
    destination = output_root / "content-media" / item_kind / item_slug
    for part in relative_parts:
        destination /= part
    return destination, False


def _safe_relative_parts(target: str, source_markdown_path: Path) -> list[str]:
    normalized = target.strip().strip("<>").replace("\\", "/")
    if normalized.startswith("/"):
        normalized = normalized.lstrip("/")

    parts: list[str] = []
    for part in PurePosixPath(normalized).parts:
        if part in ("", "."):
            continue
        if part == "..":
            continue
        parts.append(part)

    if parts:
        return parts

    fallback = source_markdown_path.stem
    return [f"{fallback}-asset"]


def _ensure_unique_destination(destination: Path, source: Path, seen: dict[Path, Path]) -> Path:
    existing_source = seen.get(destination)
    if existing_source is None or existing_source == source:
        seen[destination] = source
        return destination

    suffix = 1
    while True:
        candidate = destination.with_stem(f"{destination.stem}-{suffix}")
        existing_source = seen.get(candidate)
        if existing_source is None or existing_source == source:
            seen[candidate] = source
            return candidate
        suffix += 1


def _relative_url(*, from_dir: Path, to_path: Path) -> str:
    relative = os.path.relpath(to_path, start=from_dir)
    return relative.replace("\\", "/")
