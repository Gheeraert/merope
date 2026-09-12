"""Versioned bidirectional JSON Lines protocol for the Qt editor process."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO


PROTOCOL_VERSION = 1
EVENT_TYPES = frozenset(
    {
        "ready",
        "opened",
        "saved",
        "open_refused",
        "error",
        "closed",
        "config_requested",
    }
)
COMMAND_TYPES = frozenset({"config_snapshot", "config_error"})
_ALLOWED_EVENT_FIELDS = frozenset(
    {"protocol", "type", "path", "message", "request_id"}
)
_ALLOWED_COMMAND_FIELDS = frozenset(
    {"protocol", "type", "request_id", "config", "message"}
)
_PATH_EVENTS = frozenset({"opened", "saved", "open_refused"})
_MESSAGE_EVENTS = frozenset({"open_refused", "error"})


class ProtocolError(ValueError):
    """Raised when one stdout line does not respect the IPC contract."""


@dataclass(frozen=True, slots=True)
class ProtocolEvent:
    protocol: int
    type: str
    path: str | None = None
    message: str | None = None
    request_id: int | None = None


@dataclass(frozen=True, slots=True)
class ProtocolCommand:
    protocol: int
    type: str
    request_id: int
    config: dict[str, object] | None = None
    message: str | None = None


def _positive_request_id(value: object) -> bool:
    return type(value) is int and value > 0


def parse_event_line(line: str) -> ProtocolEvent:
    """Parse and strictly validate one UTF-8 JSON Lines event."""

    try:
        payload = json.loads(line)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ProtocolError(f"Ligne JSON invalide : {exc}") from exc
    if not isinstance(payload, dict):
        raise ProtocolError("Un événement doit être un objet JSON")

    unexpected = set(payload) - _ALLOWED_EVENT_FIELDS
    if unexpected:
        raise ProtocolError(f"Champs de protocole inconnus : {sorted(unexpected)}")
    if type(payload.get("protocol")) is not int or payload["protocol"] != PROTOCOL_VERSION:
        raise ProtocolError(f"Version de protocole attendue : {PROTOCOL_VERSION}")

    event_type = payload.get("type")
    if event_type not in EVENT_TYPES:
        raise ProtocolError(f"Type d’événement inconnu : {event_type!r}")

    expected_fields = {"protocol", "type"}
    if event_type in _PATH_EVENTS:
        expected_fields.add("path")
    if event_type in _MESSAGE_EVENTS:
        expected_fields.add("message")
    if event_type == "config_requested":
        expected_fields.add("request_id")
    unexpected_for_type = set(payload) - expected_fields
    if unexpected_for_type:
        raise ProtocolError(
            f"Champs interdits pour {event_type!r} : {sorted(unexpected_for_type)}"
        )

    path = payload.get("path")
    message = payload.get("message")
    request_id = payload.get("request_id")
    if event_type in _PATH_EVENTS and not isinstance(path, str):
        raise ProtocolError(f"L’événement {event_type!r} exige un chemin")
    if path is not None and not isinstance(path, str):
        raise ProtocolError("Le champ path doit être une chaîne")
    if event_type in _MESSAGE_EVENTS and not isinstance(message, str):
        raise ProtocolError(f"L’événement {event_type!r} exige un message")
    if message is not None and not isinstance(message, str):
        raise ProtocolError("Le champ message doit être une chaîne")
    if event_type == "config_requested" and not _positive_request_id(request_id):
        raise ProtocolError("config_requested exige un request_id entier positif")

    return ProtocolEvent(
        protocol=PROTOCOL_VERSION,
        type=event_type,
        path=path,
        message=message,
        request_id=request_id,
    )


def parse_command_line(line: str) -> ProtocolCommand:
    """Parse one strict parent-to-child JSON Lines command."""

    try:
        payload = json.loads(line)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ProtocolError(f"Ligne JSON invalide : {exc}") from exc
    if not isinstance(payload, dict):
        raise ProtocolError("Une commande doit être un objet JSON")

    unexpected = set(payload) - _ALLOWED_COMMAND_FIELDS
    if unexpected:
        raise ProtocolError(f"Champs de protocole inconnus : {sorted(unexpected)}")
    if type(payload.get("protocol")) is not int or payload["protocol"] != PROTOCOL_VERSION:
        raise ProtocolError(f"Version de protocole attendue : {PROTOCOL_VERSION}")

    command_type = payload.get("type")
    if command_type not in COMMAND_TYPES:
        raise ProtocolError(f"Type de commande inconnu : {command_type!r}")
    request_id = payload.get("request_id")
    if not _positive_request_id(request_id):
        raise ProtocolError("La commande exige un request_id entier positif")

    if command_type == "config_snapshot":
        expected_fields = {"protocol", "type", "request_id", "config"}
        if set(payload) != expected_fields:
            raise ProtocolError(
                "config_snapshot exige uniquement protocol, type, request_id et config"
            )
        config = payload.get("config")
        if not isinstance(config, dict):
            raise ProtocolError("config_snapshot exige un objet config")
        return ProtocolCommand(
            protocol=PROTOCOL_VERSION,
            type=command_type,
            request_id=request_id,
            config=config,
        )

    expected_fields = {"protocol", "type", "request_id", "message"}
    if set(payload) != expected_fields:
        raise ProtocolError(
            "config_error exige uniquement protocol, type, request_id et message"
        )
    message = payload.get("message")
    if not isinstance(message, str):
        raise ProtocolError("config_error exige une chaîne message")
    return ProtocolCommand(
        protocol=PROTOCOL_VERSION,
        type=command_type,
        request_id=request_id,
        message=message,
    )


def encode_command(command: ProtocolCommand) -> str:
    """Encode one command after validating it through the public parser."""

    payload: dict[str, object] = {
        "protocol": command.protocol,
        "type": command.type,
        "request_id": command.request_id,
    }
    if command.config is not None:
        payload["config"] = command.config
    if command.message is not None:
        payload["message"] = command.message
    try:
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise ProtocolError(f"Commande JSON non sérialisable : {exc}") from exc
    parse_command_line(encoded)
    return encoded


def configure_utf8_stdio() -> None:
    """Make the child's IPC pipes speak the protocol's UTF-8.

    On Windows, piped standard streams default to the ANSI code page
    (cp1252), while the Tk parent reads and writes UTF-8: every non-ASCII
    character of the live config (site subtitle, titles...) and of event
    paths would turn into mojibake.  Must run before any stream is used.
    """

    for stream, errors in (
        (sys.stdin, "strict"),
        (sys.stdout, "strict"),
        (sys.stderr, "backslashreplace"),
    ):
        if stream is not None and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors=errors)


def emit_event(
    event_type: str,
    *,
    path: str | Path | None = None,
    message: str | None = None,
    request_id: int | None = None,
    stream: TextIO | None = None,
) -> bool:
    """Emit one immediately flushed event; tolerate a vanished Tk parent."""

    payload: dict[str, object] = {"protocol": PROTOCOL_VERSION, "type": event_type}
    if path is not None:
        payload["path"] = str(path)
    if message is not None:
        payload["message"] = message
    if request_id is not None:
        payload["request_id"] = request_id
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    # Validate the producer through the same strict contract as the consumer.
    parse_event_line(encoded)
    try:
        print(encoded, file=stream or sys.stdout, flush=True)
    except (BrokenPipeError, OSError):
        # Tk may close while Qt still owns unsaved changes. Losing telemetry
        # must never terminate the editor child process.
        return False
    return True
