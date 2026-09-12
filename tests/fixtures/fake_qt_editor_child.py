"""Small subprocess used by launcher tests; deliberately imports no Qt."""

from __future__ import annotations

import json
import sys
import time


def emit(event_type: str, **fields) -> None:
    print(
        json.dumps({"protocol": 1, "type": event_type, **fields}),
        flush=True,
    )


mode = sys.argv[1]
if mode == "normal":
    emit("ready")
    emit("saved", path="C:/project/content/pages/example.md")
    emit("closed")
elif mode == "wait":
    emit("ready")
    time.sleep(0.4)
    emit("closed")
elif mode == "die-before-ready":
    print("PySide6 import failed", file=sys.stderr, flush=True)
    raise SystemExit(7)
elif mode == "invalid":
    print("not-json", flush=True)
    emit("closed")
elif mode == "never-ready":
    time.sleep(5)
elif mode == "config-request":
    emit("ready")
    emit("config_requested", request_id=7)
    command = json.loads(sys.stdin.readline())
    if (
        command.get("protocol") != 1
        or command.get("type") != "config_snapshot"
        or command.get("request_id") != 7
        or not isinstance(command.get("config"), dict)
        or "ftp" in command["config"]
    ):
        print("invalid config response", file=sys.stderr, flush=True)
        raise SystemExit(9)
    emit("closed")
elif mode == "utf8-echo":
    # Real protocol helpers, as used by ``python -m bloggen.ui.qt_editor --ipc``.
    from bloggen.ui.qt_editor_protocol import (
        configure_utf8_stdio,
        emit_event,
        parse_command_line,
    )

    configure_utf8_stdio()
    emit_event("ready")
    emit_event("config_requested", request_id=3)
    command = parse_command_line(sys.stdin.readline().rstrip("\r\n"))
    # ascii() makes the Tk->Qt check independent of the Qt->Tk direction:
    # a cp1252 child would otherwise re-encode its mojibake back to UTF-8.
    emit_event("error", message=ascii(command.config["site"]["subtitle"]))
    emit_event("saved", path="C:/projet/pages/créé — « œuvre ».md")
    emit_event("closed")
else:
    raise SystemExit(2)
