"""Helpers for detecting local assets referenced in Markdown."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

_IMAGE_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")
_WINDOWS_ABS_RE = re.compile(r"^[A-Za-z]:[\\/]")
_URI_SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")


@dataclass(slots=True, frozen=True)
class LinkedAssetReference:
    target: str
    resolved_path: Path
    exists: bool


def extract_local_image_targets(markdown_text: str) -> list[str]:
    targets: list[str] = []
    seen: set[str] = set()
    for raw in _IMAGE_RE.findall(markdown_text):
        target = _extract_target_from_image_body(raw)
        if not target or not _is_local_target(target):
            continue
        if target in seen:
            continue
        seen.add(target)
        targets.append(target)
    return targets


def collect_linked_assets(
    source_markdown_path: Path,
    markdown_text: str,
    *,
    project_root: Path | None = None,
) -> list[LinkedAssetReference]:
    references: list[LinkedAssetReference] = []
    for target in extract_local_image_targets(markdown_text):
        resolved = _resolve_target(
            target,
            source_markdown_path=source_markdown_path,
            project_root=project_root,
        )
        references.append(
            LinkedAssetReference(
                target=target,
                resolved_path=resolved,
                exists=resolved.exists(),
            )
        )
    return references


def resolve_markdown_asset_paths(source_markdown_path: Path, markdown_text: str) -> list[Path]:
    return [item.resolved_path for item in collect_linked_assets(source_markdown_path, markdown_text)]


def _extract_target_from_image_body(image_body: str) -> str:
    body = image_body.strip()
    if not body:
        return ""

    if body.startswith("<"):
        closing = body.find(">")
        if closing <= 1:
            return ""
        return body[1:closing].strip()

    return body.split(maxsplit=1)[0].strip()


def _resolve_target(
    target: str,
    *,
    source_markdown_path: Path,
    project_root: Path | None,
) -> Path:
    if _WINDOWS_ABS_RE.match(target):
        return Path(target).resolve()
    if target.startswith("/"):
        base = source_markdown_path.parent if project_root is None else project_root
        return (base / target.lstrip("/\\")).resolve()
    return (source_markdown_path.parent / target).resolve()


def _is_local_target(target: str) -> bool:
    if not target:
        return False
    if target.startswith(("#", "//")):
        return False
    if _WINDOWS_ABS_RE.match(target):
        return True
    if _URI_SCHEME_RE.match(target):
        return False
    return True
