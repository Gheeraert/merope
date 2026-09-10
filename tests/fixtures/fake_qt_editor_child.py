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
else:
    raise SystemExit(2)

