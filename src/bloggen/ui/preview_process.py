"""Standalone pywebview process for the content editor's HTML preview.

pywebview 6.x hard-requires ``webview.start()`` to run on the process's
actual main thread (``webview.errors.WebViewException: pywebview must be
run on a main thread.``) — discovered while testing
``bloggen.ui.content_editor.preview``, whose Tkinter-based editor already
owns its own process's main thread. Rather than fight that constraint
in-process, the preview window runs as its own small subprocess, spawned
by ``PreviewMixin._open_preview_window``.

Usage: ``python -m bloggen.ui.preview_process <pointer_file_path>``

``pointer_file_path`` is a small text file containing the absolute path
of the HTML file to display; the editor rewrites it (to name a freshly
generated file, see ``PreviewMixin._render_temp_content_file``) every
time the previewed content changes, and this process polls it and
reloads. The indirection matters: reloading the very same file:// URL
after its content changed on disk silently keeps showing the stale
version (WebView2 caches it), and appending a cache-busting query string
to a file:// URL makes WebView2 fail the navigation outright
(``ERR_FILE_NOT_FOUND`` — it treats the query string as literally part
of the file path) — both discovered by testing this against a real
window. Pointing at a genuinely different path each time sidesteps both.
"""

from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

from bloggen.ui.preview_protocol import PREVIEW_READY_MARKER

_POLL_INTERVAL_SECONDS = 0.4


def _read_target(pointer_path: Path) -> str | None:
    try:
        return pointer_path.read_text(encoding="utf-8").strip()
    except OSError:
        return None


def _watch_and_reload(window, pointer_path: Path, initial_target: str) -> None:
    last_target = initial_target
    while True:
        time.sleep(_POLL_INTERVAL_SECONDS)
        target = _read_target(pointer_path)
        if not target or target == last_target:
            continue
        last_target = target
        try:
            window.load_url(Path(target).as_uri())
        except Exception:
            return  # the window was closed from under us


def main() -> None:
    import webview

    if len(sys.argv) != 2:
        raise SystemExit("usage: python -m bloggen.ui.preview_process <pointer_file_path>")
    pointer_path = Path(sys.argv[1]).resolve()
    initial_target = _read_target(pointer_path)
    if not initial_target:
        raise SystemExit(f"pointer file introuvable ou vide : {pointer_path}")

    window = webview.create_window(
        "Aperçu — MEROPE", Path(initial_target).as_uri(), width=960, height=800
    )

    def start_watcher() -> None:
        print(PREVIEW_READY_MARKER, flush=True)
        threading.Thread(
            target=_watch_and_reload, args=(window, pointer_path, initial_target), daemon=True
        ).start()

    # The watcher must not call window.load_url() until the underlying GUI
    # window actually exists — create_window() only registers it, the real
    # browser control is built once webview.start() runs. webview.start(
    # func=...) is pywebview's documented hook for running code exactly
    # once that's ready.
    webview.start(func=start_watcher)


if __name__ == "__main__":
    main()
