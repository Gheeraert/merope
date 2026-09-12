"""Non-blocking startup monitor for the pywebview preview subprocess."""

from __future__ import annotations

import subprocess
import threading
from typing import TextIO

from PySide6.QtCore import QObject, QTimer, Signal

from bloggen.ui.preview_protocol import PREVIEW_READY_MARKER


PREVIEW_STARTUP_TIMEOUT_MS = 5_000
_MAX_DIAGNOSTIC_CHARS = 16_000


class PreviewStartupMonitor(QObject):
    """Observe READY/process exit without blocking the Qt GUI thread."""

    ready = Signal(object)
    failed = Signal(object, int, str)
    timedOut = Signal(object)
    closed = Signal(object, int)

    _readyDetected = Signal()
    _processExited = Signal(int, bool)

    def __init__(
        self,
        process: subprocess.Popen,
        *,
        timeout_ms: int = PREVIEW_STARTUP_TIMEOUT_MS,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.process = process
        self._state = "pending"
        self._ready_seen = threading.Event()
        self._stderr_parts: list[str] = []
        self._stderr_lock = threading.Lock()
        self._stdout_thread: threading.Thread | None = None
        self._stderr_thread: threading.Thread | None = None
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(timeout_ms)
        self._timer.timeout.connect(self._on_timeout)
        self._readyDetected.connect(self._on_ready_detected)
        self._processExited.connect(self._on_process_exited)

    def start(self) -> None:
        if self._state != "pending" or self._stdout_thread is not None:
            return
        self._stdout_thread = threading.Thread(
            target=self._read_stdout,
            name="merope-preview-stdout",
            daemon=True,
        )
        self._stderr_thread = threading.Thread(
            target=self._read_stderr,
            name="merope-preview-stderr",
            daemon=True,
        )
        self._stdout_thread.start()
        self._stderr_thread.start()
        threading.Thread(
            target=self._wait_for_exit,
            name="merope-preview-wait",
            daemon=True,
        ).start()
        self._timer.start()

    def cancel(self) -> None:
        if self._state in {"pending", "ready"}:
            self._state = "cancelled"
        self._timer.stop()

    def _read_stdout(self) -> None:
        stream = self.process.stdout
        if stream is None:
            return
        try:
            for line in stream:
                if line.rstrip("\r\n") == PREVIEW_READY_MARKER:
                    if not self._ready_seen.is_set():
                        self._ready_seen.set()
                        self._readyDetected.emit()
        except (OSError, ValueError):
            return

    def _read_stderr(self) -> None:
        stream = self.process.stderr
        if stream is None:
            return
        try:
            self._append_stderr(stream)
        except (OSError, ValueError):
            return

    def _append_stderr(self, stream: TextIO) -> None:
        while True:
            chunk = stream.read(4_096)
            if not chunk:
                return
            with self._stderr_lock:
                current = sum(len(part) for part in self._stderr_parts)
                remaining = _MAX_DIAGNOSTIC_CHARS - current
                if remaining > 0:
                    self._stderr_parts.append(chunk[:remaining])

    def _wait_for_exit(self) -> None:
        try:
            returncode = self.process.wait()
        except (OSError, ValueError):
            returncode = -1
        for reader in (self._stdout_thread, self._stderr_thread):
            if reader is not None:
                reader.join(timeout=1.0)
        self._processExited.emit(returncode, self._ready_seen.is_set())

    def _on_ready_detected(self) -> None:
        if self._state != "pending":
            return
        self._state = "ready"
        self._timer.stop()
        self.ready.emit(self.process)

    def _on_process_exited(self, returncode: int, ready_seen: bool) -> None:
        if self._state == "pending" and ready_seen:
            self._on_ready_detected()
        if self._state == "pending":
            self._state = "failed"
            self._timer.stop()
            self.failed.emit(self.process, returncode, self._stderr_text())
        elif self._state == "ready":
            self._state = "closed"
            self.closed.emit(self.process, returncode)

    def _on_timeout(self) -> None:
        if self._state != "pending":
            return
        if self._ready_seen.is_set():
            self._on_ready_detected()
            return
        self._state = "timed_out"
        try:
            if self.process.poll() is None:
                self.process.terminate()
        except OSError:
            pass
        self.timedOut.emit(self.process)

    def _stderr_text(self) -> str:
        with self._stderr_lock:
            return "".join(self._stderr_parts).strip()
