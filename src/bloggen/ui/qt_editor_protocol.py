"""Versioned, one-way JSON Lines protocol for the Qt editor child process."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO


PROTOCOL_VERSION = 1
EVENT_TYPES = frozenset(
    {"ready", "opened", "saved", "open_refused", "error", "closed"}
)
_ALLOWED_FIELDS = frozenset({"protocol", "type", "path", "message"})
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


def parse_event_line(line: str) -> ProtocolEvent:
    """Parse and strictly validate one UTF-8 JSON Lines event."""

    try:
        payload = json.loads(line)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ProtocolError(f"Ligne JSON invalide : {exc}") from exc
    if not isinstance(payload, dict):
        raise ProtocolError("Un événement doit être un objet JSON")

    unexpected = set(payload) - _ALLOWED_FIELDS
    if unexpected:
        raise ProtocolError(f"Champs de protocole inconnus : {sorted(unexpected)}")
    if type(payload.get("protocol")) is not int or payload["protocol"] != PROTOCOL_VERSION:
        raise ProtocolError(f"Version de protocole attendue : {PROTOCOL_VERSION}")

    event_type = payload.get("type")
    if event_type not in EVENT_TYPES:
        raise ProtocolError(f"Type d’événement inconnu : {event_type!r}")

    path = payload.get("path")
    message = payload.get("message")
    if event_type in _PATH_EVENTS and not isinstance(path, str):
        raise ProtocolError(f"L’événement {event_type!r} exige un chemin")
    if path is not None and not isinstance(path, str):
        raise ProtocolError("Le champ path doit être une chaîne")
    if event_type in _MESSAGE_EVENTS and not isinstance(message, str):
        raise ProtocolError(f"L’événement {event_type!r} exige un message")
    if message is not None and not isinstance(message, str):
        raise ProtocolError("Le champ message doit être une chaîne")

    return ProtocolEvent(
        protocol=PROTOCOL_VERSION,
        type=event_type,
        path=path,
        message=message,
    )


def emit_event(
    event_type: str,
    *,
    path: str | Path | None = None,
    message: str | None = None,
    stream: TextIO | None = None,
) -> bool:
    """Emit one immediately flushed event; tolerate a vanished Tk parent."""

    payload: dict[str, object] = {"protocol": PROTOCOL_VERSION, "type": event_type}
    if path is not None:
        payload["path"] = str(path)
    if message is not None:
        payload["message"] = message
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

