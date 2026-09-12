"""Stand-in for the IPC Qt child: its stdin is a pipe with a blocked reader.

It then starts a preview grandchild through ``launch_preview_process`` (only
the command is swapped for a trivial READY printer, the Popen options are the
real ones) and exits 0 if READY arrives in time, 3 otherwise.
"""

from __future__ import annotations

import subprocess
import sys
import threading
import time
from pathlib import Path

from bloggen.ui.preview_protocol import PREVIEW_READY_MARKER
from bloggen.ui.qt_editor import preview as preview_module


def main() -> int:
    # Same shape as QtEditorIpcBridge._read_stdin: a daemon thread blocked in
    # a synchronous read on the pipe owned by the parent.
    threading.Thread(target=lambda: [None for _ in sys.stdin], daemon=True).start()
    time.sleep(0.3)

    scratch = Path(sys.argv[1])
    preview_module.pywebview_available = lambda: True
    artifact = preview_module.PreviewArtifact(
        scratch, scratch / "index.html", scratch / "_current.txt"
    )
    grandchild = [sys.executable, "-c", f"print({PREVIEW_READY_MARKER!r}, flush=True)"]
    process = preview_module.launch_preview_process(
        artifact,
        popen_factory=lambda _command, **kwargs: subprocess.Popen(grandchild, **kwargs),
    )
    lines: list[str] = []
    threading.Thread(
        target=lambda: lines.append(process.stdout.readline()), daemon=True
    ).start()
    deadline = time.monotonic() + float(sys.argv[2])
    while not lines and time.monotonic() < deadline:
        time.sleep(0.02)
    if process.poll() is None:
        process.kill()
    return 0 if lines and lines[0].strip() == PREVIEW_READY_MARKER else 3


if __name__ == "__main__":
    raise SystemExit(main())
