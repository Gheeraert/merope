"""Asset copy helpers for static site build."""

from __future__ import annotations

from pathlib import Path
import shutil


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


def copy_builtin_resources(output_root: Path) -> int:
    resources_root = Path(__file__).resolve().parent.parent / "resources"
    copied = 0
    copied += copy_tree_if_exists(resources_root / "css", output_root / "static" / "css")
    copied += copy_tree_if_exists(resources_root / "js", output_root / "static" / "js")
    return copied
