"""Pure conversion of a live project configuration for runtime IPC.

This path deliberately bypasses the persistence helpers: a runtime snapshot
must neither read nor write FTP credentials.
"""

from __future__ import annotations

from typing import Any

from bloggen.config.models import ProjectConfig
from bloggen.config.validator import validate_config_dict, validate_config_model


class RuntimeSnapshotError(ValueError):
    """A live configuration cannot safely cross the process boundary."""


def _validation_message(errors: list[str]) -> str:
    return "Configuration du projet invalide :\n" + "\n".join(
        f"- {error}" for error in errors
    )


def project_config_to_runtime_payload(
    config: ProjectConfig,
) -> dict[str, object]:
    """Return a validated, credential-free snapshot of ``config``.

    ``ProjectConfig.to_dict`` gives us a detached recursive mapping.  The FTP
    section is then removed in its entirety before the payload can be encoded.
    """

    errors = validate_config_model(config)
    if errors:
        raise RuntimeSnapshotError(_validation_message(errors))
    payload: dict[str, Any] = config.to_dict()
    payload.pop("ftp", None)
    return payload


def project_config_from_runtime_payload(payload: object) -> ProjectConfig:
    """Validate and rebuild a runtime snapshot without credential lookup."""

    if not isinstance(payload, dict):
        raise RuntimeSnapshotError("Le snapshot de configuration doit être un objet")
    if "ftp" in payload:
        raise RuntimeSnapshotError(
            "La section ftp est interdite dans un snapshot de configuration runtime"
        )
    errors = validate_config_dict(payload)
    if errors:
        raise RuntimeSnapshotError(_validation_message(errors))
    return ProjectConfig.from_dict(payload)
