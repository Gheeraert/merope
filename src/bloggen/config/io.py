"""JSON read/write helpers for MEROPE configuration."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from bloggen.config.models import ProjectConfig
from bloggen.config.validator import validate_config_dict
from bloggen.publish import ftp_credentials


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
    config = ProjectConfig.from_dict(raw)
    _resolve_ftp_password(config, raw)
    return config


def _resolve_ftp_password(config: ProjectConfig, raw: dict[str, Any]) -> None:
    """Populates ``config.ftp.password`` in memory for this session.

    A password found in ``raw`` means it's a legacy plaintext site.json —
    migrate it into the OS credential store so the very next save leaves
    it out of the file for good (see ``_strip_ftp_password_for_disk``).
    Otherwise (the normal case going forward) it comes from there.
    """
    ftp = config.ftp
    if ftp.password:
        ftp_credentials.save_password(ftp.host, ftp.username, ftp.password)
    else:
        ftp.password = ftp_credentials.load_password(ftp.host, ftp.username)


def save_config(config: ProjectConfig | dict[str, Any], path: str | Path, validate: bool = True) -> None:
    text = serialize_config(config)
    if validate:
        errors = validate_config_dict(json.loads(text))
        if errors:
            raise ConfigValidationError(errors)

    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(text, encoding="utf-8")


def serialize_config(config: ProjectConfig | dict[str, Any]) -> str:
    _persist_ftp_password(config)
    data = _strip_ftp_password_for_disk(_to_dict(config))
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def _persist_ftp_password(config: ProjectConfig | dict[str, Any]) -> None:
    if isinstance(config, ProjectConfig):
        host, username, password = config.ftp.host, config.ftp.username, config.ftp.password
    else:
        ftp = config.get("ftp") or {}
        host, username, password = ftp.get("host", ""), ftp.get("username", ""), ftp.get("password", "")
    ftp_credentials.save_password(host, username, password)


def _strip_ftp_password_for_disk(data: dict[str, Any]) -> dict[str, Any]:
    """``site.json`` must never carry the FTP password — it lives in the
    OS credential store (see ``_persist_ftp_password``/``ftp_credentials``)."""
    ftp = data.get("ftp")
    if isinstance(ftp, dict) and ftp.get("password"):
        data = dict(data)
        data["ftp"] = {**ftp, "password": ""}
    return data


def _to_dict(config: ProjectConfig | dict[str, Any]) -> dict[str, Any]:
    if isinstance(config, ProjectConfig):
        return config.to_dict()
    return config
