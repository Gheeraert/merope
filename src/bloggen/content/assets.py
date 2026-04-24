"""Helpers for detecting local assets referenced in Markdown."""

from __future__ import annotations

from pathlib import Path
import re

_IMAGE_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")


def extract_local_image_targets(markdown_text: str) -> list[str]:
    targets: list[str] = []
    for raw in _IMAGE_RE.findall(markdown_text):
        target = raw.strip().split()[0].strip("<>")
        if _is_local_target(target):
            targets.append(target)
    return targets


def resolve_markdown_asset_paths(source_markdown_path: Path, markdown_text: str) -> list[Path]:
    base = source_markdown_path.parent
    resolved: list[Path] = []
    seen: set[Path] = set()
    for target in extract_local_image_targets(markdown_text):
        path = (base / target).resolve()
        if path in seen:
            continue
        seen.add(path)
        resolved.append(path)
    return resolved


def _is_local_target(target: str) -> bool:
    if not target:
        return False
    if target.startswith(("http://", "https://", "mailto:", "#")):
        return False
    return "://" not in target
