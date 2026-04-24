"""JSON read/write helpers for MEROPE configuration."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from bloggen.config.models import ProjectConfig
from bloggen.config.validator import validate_config_dict


class ConfigValidationError(ValueError):
    """Raised when a configuration does not match the expected schema."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("\n".join(errors))


def load_config(path: str | Path, validate: bool = True) -> ProjectConfig:
    file_path = Path(path)
    raw = json.loads(file_path.read_text(encoding="utf-8"))
    return parse_config(raw, validate=validate)


def parse_config(raw: Any, validate: bool = True) -> ProjectConfig:
    if validate:
        errors = validate_config_dict(raw)
        if errors:
            raise ConfigValidationError(errors)
    if not isinstance(raw, dict):
        raise ConfigValidationError(["La configuration doit être un objet JSON."])
    return ProjectConfig.from_dict(raw)


def save_config(config: ProjectConfig | dict[str, Any], path: str | Path, validate: bool = True) -> None:
    data = _to_dict(config)
    if validate:
        errors = validate_config_dict(data)
        if errors:
            raise ConfigValidationError(errors)

    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(serialize_config(data), encoding="utf-8")


def serialize_config(config: ProjectConfig | dict[str, Any]) -> str:
    data = _to_dict(config)
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def _to_dict(config: ProjectConfig | dict[str, Any]) -> dict[str, Any]:
    if isinstance(config, ProjectConfig):
        return config.to_dict()
    return config
