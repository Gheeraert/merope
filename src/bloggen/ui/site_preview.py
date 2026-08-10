"""Local HTTP preview server for a generated site.

Launches a lightweight, in-process HTTP server — the same thing
``python -m http.server`` does, but run as a background thread inside this
process rather than a spawned subprocess, so it doesn't depend on
``python``/the right virtualenv being resolvable on PATH and can be
cleanly stopped or restarted. Used by the "Générer le site" report to
offer an "open the site now" action.
"""

from __future__ import annotations

import functools
import http.server
import threading
import webbrowser
from pathlib import Path


class SitePreviewServer:
    """Serves one directory at a time. Reopening the same directory reuses
    the already-running server instead of starting a second one; opening a
    different directory stops the old server first.
    """

    def __init__(self) -> None:
        self._server: http.server.ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._directory: Path | None = None

    @property
    def port(self) -> int | None:
        return self._server.server_address[1] if self._server is not None else None

    def open_in_browser(self, directory: Path) -> str:
        """Start (or reuse) the server for ``directory`` and open it in the
        system's default browser. Returns the URL that was opened.
        """
        directory = Path(directory).resolve()
        if self._server is None or self._directory != directory:
            self.stop()
            handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(directory))
            server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            self._server = server
            self._thread = thread
            self._directory = directory

        url = f"http://127.0.0.1:{self.port}/"
        webbrowser.open(url)
        return url

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
        self._server = None
        self._thread = None
        self._directory = None
