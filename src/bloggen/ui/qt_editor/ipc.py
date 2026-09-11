"""Non-blocking Qt side of the live-configuration IPC channel."""

from __future__ import annotations

import queue
import sys
import threading
from typing import TextIO

from PySide6.QtCore import QObject, QTimer, Signal

from bloggen.config.runtime_snapshot import (
    RuntimeSnapshotError,
    project_config_from_runtime_payload,
)
from bloggen.ui.qt_editor_protocol import (
    ProtocolCommand,
    ProtocolError,
    emit_event,
    parse_command_line,
)


_UNAVAILABLE_MESSAGE = (
    "Configuration live indisponible dans ce mode. Lancez l’éditeur Qt "
    "depuis Mérope pour utiliser l’aperçu HTML."
)
_PARENT_GONE_MESSAGE = "La configuration live est indisponible : le processus Tk a fermé."


class QtEditorIpcBridge(QObject):
    """Correlate live-config requests without blocking the QApplication thread."""

    configReady = Signal(int, object)
    configFailed = Signal(int, str)
    protocolError = Signal(str)

    def __init__(
        self,
        *,
        enabled: bool,
        input_stream: TextIO | None = None,
        output_stream: TextIO | None = None,
        poll_interval_ms: int = 25,
        start_reader: bool = True,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._input_stream = input_stream or sys.stdin
        self._output_stream = output_stream or sys.stdout
        self._available = enabled
        self._stopped = False
        self._next_request_id = 1
        self._pending_request_ids: set[int] = set()
        self._incoming: queue.SimpleQueue[tuple[str, object]] = queue.SimpleQueue()
        self._drain_timer = QTimer(self)
        self._drain_timer.setInterval(poll_interval_ms)
        self._drain_timer.timeout.connect(self.drain_pending)
        if enabled:
            self._drain_timer.start()
            if start_reader:
                threading.Thread(
                    target=self._read_stdin,
                    daemon=True,
                    name="merope-qt-stdin",
                ).start()

    @property
    def available(self) -> bool:
        return self._available and not self._stopped

    def request_config(self) -> int:
        """Request one fresh snapshot and return its positive correlation ID."""

        request_id = self._next_request_id
        self._next_request_id += 1
        if not self.available:
            self._queue_failure(request_id, _UNAVAILABLE_MESSAGE)
            return request_id

        self._pending_request_ids.add(request_id)
        if not emit_event(
            "config_requested",
            request_id=request_id,
            stream=self._output_stream,
        ):
            self._pending_request_ids.discard(request_id)
            self._available = False
            self._queue_failure(request_id, _PARENT_GONE_MESSAGE)
        return request_id

    def drain_pending(self) -> None:
        """Deliver queued reader-thread results on the Qt main thread."""

        if self._stopped:
            return
        while True:
            try:
                kind, payload = self._incoming.get_nowait()
            except queue.Empty:
                return
            if kind == "command":
                assert isinstance(payload, ProtocolCommand)
                self._handle_command(payload)
            elif kind == "protocol_error":
                self.protocolError.emit(str(payload))
            elif kind == "eof":
                self._mark_parent_unavailable()
            elif kind == "failure":
                request_id, message = payload
                self.configFailed.emit(request_id, message)

    def shutdown(self) -> None:
        """Stop Qt delivery without joining a potentially blocked stdin thread."""

        self._stopped = True
        self._available = False
        self._drain_timer.stop()
        self._pending_request_ids.clear()

    def _read_stdin(self) -> None:
        try:
            for raw_line in self._input_stream:
                line = raw_line.rstrip("\r\n")
                try:
                    command = parse_command_line(line)
                except ProtocolError as exc:
                    self._incoming.put(("protocol_error", str(exc)))
                else:
                    self._incoming.put(("command", command))
        except (OSError, ValueError) as exc:
            self._incoming.put(("protocol_error", f"Lecture stdin impossible : {exc}"))
        finally:
            self._incoming.put(("eof", None))

    def _queue_failure(self, request_id: int, message: str) -> None:
        """Deliver even immediate request failures on a later Qt turn."""

        self._incoming.put(("failure", (request_id, message)))
        QTimer.singleShot(0, self.drain_pending)

    def _handle_command(self, command: ProtocolCommand) -> None:
        request_id = command.request_id
        if request_id not in self._pending_request_ids:
            self.protocolError.emit(
                f"Réponse reçue pour une requête inconnue : {request_id}"
            )
            return
        self._pending_request_ids.remove(request_id)

        if command.type == "config_error":
            self.configFailed.emit(request_id, command.message or "Erreur de configuration")
            return
        try:
            config = project_config_from_runtime_payload(command.config)
        except RuntimeSnapshotError as exc:
            self.configFailed.emit(request_id, str(exc))
            return
        self.configReady.emit(request_id, config)

    def _mark_parent_unavailable(self) -> None:
        if not self._available:
            return
        self._available = False
        for request_id in sorted(self._pending_request_ids):
            self.configFailed.emit(request_id, _PARENT_GONE_MESSAGE)
        self._pending_request_ids.clear()
