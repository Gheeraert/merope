from __future__ import annotations

import io
import os
import queue
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from bloggen.config.models import ProjectConfig
from bloggen.config.runtime_snapshot import project_config_to_runtime_payload
from bloggen.ui.qt_editor.ipc import QtEditorIpcBridge
from bloggen.ui.qt_editor_protocol import (
    PROTOCOL_VERSION,
    ProtocolCommand,
    encode_command,
    parse_event_line,
)


class _BlockingLines:
    def __init__(self):
        self.lines = queue.Queue()

    def __iter__(self):
        return self

    def __next__(self):
        item = self.lines.get()
        if item is None:
            raise StopIteration
        return item

    def send(self, line: str):
        self.lines.put(line + "\n")

    def close(self):
        self.lines.put(None)


@pytest.fixture(scope="module")
def qapplication():
    yield QApplication.instance() or QApplication([])


def _wait_until(qapplication, predicate, timeout=1.0):
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        qapplication.processEvents()
        time.sleep(0.005)
    assert predicate()


def _command(command_type, request_id, *, config=None, message=None):
    return encode_command(
        ProtocolCommand(
            protocol=PROTOCOL_VERSION,
            type=command_type,
            request_id=request_id,
            config=config,
            message=message,
        )
    )


def test_request_ids_are_increasing_and_emitted_on_stdout(qapplication):
    output = io.StringIO()
    bridge = QtEditorIpcBridge(
        enabled=True,
        input_stream=_BlockingLines(),
        output_stream=output,
        start_reader=False,
    )

    assert bridge.request_config() == 1
    assert bridge.request_config() == 2

    events = [parse_event_line(line) for line in output.getvalue().splitlines()]
    assert [(event.type, event.request_id) for event in events] == [
        ("config_requested", 1),
        ("config_requested", 2),
    ]
    bridge.shutdown()


def test_valid_snapshot_from_reader_thread_emits_correlated_config(qapplication):
    input_stream = _BlockingLines()
    output = io.StringIO()
    bridge = QtEditorIpcBridge(
        enabled=True,
        input_stream=input_stream,
        output_stream=output,
        poll_interval_ms=1,
    )
    ready = []
    bridge.configReady.connect(lambda request_id, config: ready.append((request_id, config)))
    request_id = bridge.request_config()
    config = ProjectConfig()
    config.site.title = "Titre vivant"

    input_stream.send(
        _command(
            "config_snapshot",
            request_id,
            config=project_config_to_runtime_payload(config),
        )
    )
    _wait_until(qapplication, lambda: bool(ready))

    assert ready[0][0] == request_id
    assert ready[0][1].site.title == "Titre vivant"
    input_stream.close()
    bridge.shutdown()


def test_out_of_order_responses_keep_their_request_ids(qapplication):
    input_stream = _BlockingLines()
    bridge = QtEditorIpcBridge(
        enabled=True,
        input_stream=input_stream,
        output_stream=io.StringIO(),
        poll_interval_ms=1,
    )
    ready = []
    bridge.configReady.connect(
        lambda request_id, config: ready.append((request_id, config.site.title))
    )
    first = bridge.request_config()
    second = bridge.request_config()
    config_a = ProjectConfig()
    config_a.site.title = "A"
    config_b = ProjectConfig()
    config_b.site.title = "B"

    input_stream.send(
        _command(
            "config_snapshot",
            second,
            config=project_config_to_runtime_payload(config_b),
        )
    )
    input_stream.send(
        _command(
            "config_snapshot",
            first,
            config=project_config_to_runtime_payload(config_a),
        )
    )
    _wait_until(qapplication, lambda: len(ready) == 2)

    assert ready == [(second, "B"), (first, "A")]
    input_stream.close()
    bridge.shutdown()


def test_config_error_is_correlated(qapplication):
    input_stream = _BlockingLines()
    bridge = QtEditorIpcBridge(
        enabled=True,
        input_stream=input_stream,
        output_stream=io.StringIO(),
        poll_interval_ms=1,
    )
    failures = []
    bridge.configFailed.connect(lambda request_id, message: failures.append((request_id, message)))
    request_id = bridge.request_config()

    input_stream.send(_command("config_error", request_id, message="Formulaire invalide"))
    _wait_until(qapplication, lambda: bool(failures))

    assert failures == [(request_id, "Formulaire invalide")]
    input_stream.close()
    bridge.shutdown()


def test_invalid_snapshot_fails_without_config_ready(qapplication):
    input_stream = _BlockingLines()
    bridge = QtEditorIpcBridge(
        enabled=True,
        input_stream=input_stream,
        output_stream=io.StringIO(),
        poll_interval_ms=1,
    )
    ready = []
    failures = []
    bridge.configReady.connect(lambda *args: ready.append(args))
    bridge.configFailed.connect(lambda *args: failures.append(args))
    request_id = bridge.request_config()

    input_stream.send(_command("config_snapshot", request_id, config={"site": {}}))
    _wait_until(qapplication, lambda: bool(failures))

    assert ready == []
    assert failures[0][0] == request_id
    assert "Configuration" in failures[0][1]
    input_stream.close()
    bridge.shutdown()


def test_invalid_json_reports_protocol_error_without_blocking(qapplication):
    input_stream = _BlockingLines()
    bridge = QtEditorIpcBridge(
        enabled=True,
        input_stream=input_stream,
        output_stream=io.StringIO(),
        poll_interval_ms=1,
    )
    errors = []
    bridge.protocolError.connect(errors.append)

    input_stream.send("not-json")
    _wait_until(qapplication, lambda: bool(errors))

    assert "JSON" in errors[0]
    input_stream.close()
    bridge.shutdown()


def test_stdin_eof_disables_live_config_but_not_qt(qapplication):
    input_stream = _BlockingLines()
    bridge = QtEditorIpcBridge(
        enabled=True,
        input_stream=input_stream,
        output_stream=io.StringIO(),
        poll_interval_ms=1,
    )
    failures = []
    bridge.configFailed.connect(lambda *args: failures.append(args))
    first_request = bridge.request_config()

    input_stream.close()
    _wait_until(qapplication, lambda: not bridge.available)

    assert failures and failures[0][0] == first_request
    second_request = bridge.request_config()
    assert failures[-1][0] == second_request
    assert "indisponible" in failures[-1][1]
    bridge.shutdown()


def test_standalone_request_fails_explicitly_without_disk_fallback(qapplication):
    bridge = QtEditorIpcBridge(enabled=False, output_stream=io.StringIO())
    failures = []
    bridge.configFailed.connect(lambda *args: failures.append(args))

    request_id = bridge.request_config()

    assert failures == [(request_id, "Configuration live indisponible dans ce mode.")]
    bridge.shutdown()
