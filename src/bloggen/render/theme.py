"""Optional custom HTML template loading for a project theme."""

from __future__ import annotations

from pathlib import Path

from bloggen.config.models import ProjectConfig


def load_custom_template(project_root: Path, config: ProjectConfig, template_name: str) -> str | None:
    """Return the contents of a project-provided template override, if any.

    Looks up ``paths.templates_dir/<template_name>`` relative to the project
    root. Returns ``None`` when the file is absent, so callers fall back to
    the built-in hard-coded document structure.
    """
    name = (template_name or "").strip()
    if not name:
        return None
    candidate = (project_root / config.paths.templates_dir / name).resolve()
    if candidate.is_file():
        return candidate.read_text(encoding="utf-8")
    return None
