"""Non-blocking startup monitor for the pywebview preview subprocess."""

from __future__ import annotations

import subprocess
import threading
from typing import TextIO

from PySide6.QtCore import QObject, QTimer, Signal

from bloggen.ui.preview_protocol import PREVIEW_READY_MARKER


PREVIEW_STARTUP_TIMEOUT_MS = 5_000
PREVIEW_TERMINATE_GRACE_MS = 500
_MAX_DIAGNOSTIC_CHARS = 16_000


class PreviewStartupMonitor(QObject):
    """Observe READY/process exit without blocking the Qt GUI thread."""

    ready = Signal(object)
    failed = Signal(object, int, str)
    timedOut = Signal(object)
    closed = Signal(object, int)
    reaped = Signal(object)

    _readyDetected = Signal()
    _processExited = Signal(int, bool)

    def __init__(
        self,
        process: subprocess.Popen,
        *,
        timeout_ms: int = PREVIEW_STARTUP_TIMEOUT_MS,
        terminate_grace_ms: int = PREVIEW_TERMINATE_GRACE_MS,
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
        self._wait_thread: threading.Thread | None = None
        self._escalation_thread: threading.Thread | None = None
        self._thread_lock = threading.Lock()
        self._stop_requested = threading.Event()
        self._reaped = threading.Event()
        self._reap_callbacks: list = []
        self._reap_callback_lock = threading.Lock()
        self._terminate_grace_seconds = max(0, terminate_grace_ms) / 1_000
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(timeout_ms)
        self._timer.timeout.connect(self._on_timeout)
        self._readyDetected.connect(self._on_ready_detected)
        self._processExited.connect(self._on_process_exited)

    def start(self) -> None:
        if self._state != "pending" or self._wait_thread is not None:
            return
        self._ensure_worker_threads()
        self._timer.start()

    def _ensure_worker_threads(self) -> None:
        """Start the readers and the process's sole wait/reap thread."""

        with self._thread_lock:
            if self._stdout_thread is None:
                self._stdout_thread = threading.Thread(
                    target=self._read_stdout,
                    name="merope-preview-stdout",
                    daemon=True,
                )
                self._stdout_thread.start()
            if self._stderr_thread is None:
                self._stderr_thread = threading.Thread(
                    target=self._read_stderr,
                    name="merope-preview-stderr",
                    daemon=True,
                )
                self._stderr_thread.start()
            if self._wait_thread is None:
                self._wait_thread = threading.Thread(
                    target=self._wait_for_exit,
                    name="merope-preview-wait",
                    daemon=False,
                )
                self._wait_thread.start()

    def stop(self) -> None:
        """Asynchronously terminate, escalate if needed, and reap the process."""

        self.cancel()
        self._request_process_stop()

    def when_reaped(self, callback) -> None:
        """Run ``callback(process)`` once after the process has been waited."""

        with self._reap_callback_lock:
            if not self._reaped.is_set():
                self._reap_callbacks.append(callback)
                return
        callback(self.process)

    def wait_until_reaped(self, timeout: float | None = None) -> bool:
        """Wait for tests/workers; never call this from a Qt GUI callback."""

        return self._reaped.wait(timeout)

    def _request_process_stop(self) -> None:
        self._ensure_worker_threads()
        if self._stop_requested.is_set():
            return
        self._stop_requested.set()
        try:
            if self.process.poll() is None:
                self.process.terminate()
        except (OSError, ProcessLookupError, ValueError):
            pass
        with self._thread_lock:
            if self._escalation_thread is None:
                self._escalation_thread = threading.Thread(
                    target=self._kill_after_grace,
                    name="merope-preview-kill",
                    daemon=False,
                )
                self._escalation_thread.start()

    def _kill_after_grace(self) -> None:
        if self._reaped.wait(self._terminate_grace_seconds):
            return
        try:
            if self.process.poll() is None:
                self.process.kill()
        except (OSError, ProcessLookupError, ValueError):
            pass

    def cancel(self) -> None:
        if self._state in {"pending", "ready"}:
            self._state = "cancelled"
        self._timer.stop()

    def _read_stdout(self) -> None:
        stream = getattr(self.process, "stdout", None)
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
        stream = getattr(self.process, "stderr", None)
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
        while True:
            try:
                returncode = self.process.wait()
                break
            except (OSError, ProcessLookupError, ValueError):
                try:
                    returncode = self.process.poll()
                except (OSError, ProcessLookupError, ValueError):
                    returncode = None
                if returncode is not None:
                    break
                self._stop_requested.wait(0.05)
        for reader in (self._stdout_thread, self._stderr_thread):
            if reader is not None:
                reader.join(timeout=1.0)
        while True:
            with self._reap_callback_lock:
                callbacks = self._reap_callbacks
                self._reap_callbacks = []
                if not callbacks:
                    self._reaped.set()
                    break
            for callback in callbacks:
                try:
                    callback(self.process)
                except Exception:
                    pass
        self.reaped.emit(self.process)
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
        self._request_process_stop()
        self.timedOut.emit(self.process)

    def _stderr_text(self) -> str:
        with self._stderr_lock:
            return "".join(self._stderr_parts).strip()


def stop_preview_process(
    process: subprocess.Popen,
    *,
    monitor: PreviewStartupMonitor | None = None,
    parent: QObject | None = None,
    on_reaped=None,
) -> PreviewStartupMonitor:
    """Stop one preview through its single monitor/reaper lifecycle."""

    lifecycle = monitor or PreviewStartupMonitor(process, parent=parent)
    if on_reaped is not None:
        lifecycle.when_reaped(on_reaped)
    lifecycle.stop()
    return lifecycle
