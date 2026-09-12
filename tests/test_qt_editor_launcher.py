from __future__ import annotations

import io
import subprocess
import sys
import time
from pathlib import Path

import pytest

from bloggen.ui.qt_editor_launcher import (
    ProcessExited,
    ProtocolDiagnostic,
    QtEditorAlreadyRunning,
    QtEditorCommandError,
    QtEditorLaunchContext,
    QtEditorLaunchError,
    QtEditorLauncher,
    StartupTimedOut,
    StderrOutput,
    build_qt_editor_command,
)
from bloggen.ui.qt_editor_protocol import (
    PROTOCOL_VERSION,
    ProtocolError,
    ProtocolEvent,
    emit_event,
    parse_event_line,
)


FAKE_CHILD = Path(__file__).parent / "fixtures" / "fake_qt_editor_child.py"


def _context(root: Path) -> QtEditorLaunchContext:
    return QtEditorLaunchContext(
        project_root=root,
        pages_dir=root / "content" / "pages",
        posts_dir=root / "content" / "posts",
        images_dir=root / "assets" / "images",
        slugify_mode="ascii",
    )


def _wait_for_exit(launcher: QtEditorLauncher, timeout: float = 3.0):
    deadline = time.monotonic() + timeout
    notifications = []
    while time.monotonic() < deadline:
        notifications.extend(launcher.drain_notifications())
        if any(isinstance(item, ProcessExited) for item in notifications):
            return notifications
        time.sleep(0.01)
    pytest.fail("Le faux processus Qt ne s’est pas terminé")


def _fake_command(mode: str) -> list[str]:
    return [sys.executable, str(FAKE_CHILD), mode]


def test_command_uses_current_python_and_explicit_project_context(tmp_path):
    context = _context(tmp_path)

    command = build_qt_editor_command(context)

    assert command == [
        sys.executable,
        "-m",
        "bloggen.ui.qt_editor",
        "--ipc",
        "--project-root",
        str(context.project_root),
        "--pages-dir",
        str(context.pages_dir),
        "--posts-dir",
        str(context.posts_dir),
        "--images-dir",
        str(context.images_dir),
        "--slugify-mode",
        "ascii",
    ]


def test_importing_launcher_does_not_import_pyside6(tmp_path):
    script = (
        "import sys; import bloggen.ui.qt_editor_launcher; "
        "print(any(name == 'PySide6' or name.startswith('PySide6.') for name in sys.modules))"
    )

    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=True,
    )

    assert result.stdout.strip() == "False"


def test_valid_json_line_is_parsed():
    event = parse_event_line(
        '{"protocol":1,"type":"saved","path":"C:/project/article.md"}'
    )

    assert event == ProtocolEvent(
        protocol=PROTOCOL_VERSION,
        type="saved",
        path="C:/project/article.md",
    )


@pytest.mark.parametrize(
    "line",
    [
        "not-json",
        "[]",
        '{"protocol":2,"type":"ready"}',
        '{"protocol":1,"type":"unknown"}',
        '{"protocol":1,"type":"saved"}',
        '{"protocol":1,"type":"ready","blocks":[]}',
    ],
)
def test_invalid_protocol_line_is_rejected_with_diagnostic(line: str):
    with pytest.raises(ProtocolError):
        parse_event_line(line)


def test_emit_event_writes_one_flushed_json_line():
    class RecordingStream(io.StringIO):
        flushed = False

        def flush(self):
            self.flushed = True
            super().flush()

    stream = RecordingStream()

    assert emit_event("opened", path="C:/project/article.md", stream=stream) is True
    assert stream.flushed is True
    assert stream.getvalue().count("\n") == 1
    assert parse_event_line(stream.getvalue()).type == "opened"


def test_launcher_handles_ready_saved_and_closed(tmp_path):
    launcher = QtEditorLauncher(_context(tmp_path))

    launcher.start(command=_fake_command("normal"))
    notifications = _wait_for_exit(launcher)

    events = [item for item in notifications if isinstance(item, ProtocolEvent)]
    assert [event.type for event in events] == ["ready", "saved", "closed"]
    assert launcher.ready is True
    assert launcher.returncode == 0


def test_process_dying_before_ready_is_reported_with_stderr(tmp_path):
    launcher = QtEditorLauncher(_context(tmp_path))

    launcher.start(command=_fake_command("die-before-ready"))
    notifications = _wait_for_exit(launcher)

    assert any(
        isinstance(item, StderrOutput) and "PySide6 import failed" in item.line
        for item in notifications
    )
    exit_notice = next(item for item in notifications if isinstance(item, ProcessExited))
    assert exit_notice == ProcessExited(returncode=7, before_ready=True)


def test_living_process_that_never_emits_ready_times_out_without_blocking(tmp_path):
    launcher = QtEditorLauncher(_context(tmp_path), ready_timeout=0.05)
    launcher.start(command=_fake_command("never-ready"))

    deadline = time.monotonic() + 2.0
    timeout_notice = None
    while timeout_notice is None and time.monotonic() < deadline:
        launcher.drain_notifications()
        timeout_notice = launcher.check_startup_timeout()
        time.sleep(0.01)

    assert timeout_notice == StartupTimedOut(timeout_seconds=0.05)
    assert launcher.is_running is False
    _wait_for_exit(launcher)

    launcher.start(command=_fake_command("normal"))
    notifications = _wait_for_exit(launcher)
    assert any(
        isinstance(item, ProtocolEvent) and item.type == "ready"
        for item in notifications
    )


def test_ready_process_is_never_subject_to_startup_timeout(tmp_path):
    now = [0.0]
    launcher = QtEditorLauncher(
        _context(tmp_path),
        ready_timeout=1.0,
        monotonic=lambda: now[0],
    )
    launcher.start(command=_fake_command("wait"))
    deadline = time.monotonic() + 2.0
    while not launcher.ready and time.monotonic() < deadline:
        launcher.drain_notifications()
        time.sleep(0.01)

    now[0] = 100.0
    assert launcher.check_startup_timeout() is None
    assert launcher.is_running is True
    _wait_for_exit(launcher)


def test_invalid_child_stdout_becomes_protocol_diagnostic(tmp_path):
    launcher = QtEditorLauncher(_context(tmp_path))

    launcher.start(command=_fake_command("invalid"))
    notifications = _wait_for_exit(launcher)

    assert any(isinstance(item, ProtocolDiagnostic) for item in notifications)


def test_double_start_is_refused_and_relaunch_after_exit_is_allowed(tmp_path):
    launcher = QtEditorLauncher(_context(tmp_path))
    launcher.start(command=_fake_command("wait"))

    with pytest.raises(QtEditorAlreadyRunning):
        launcher.start(command=_fake_command("normal"))

    _wait_for_exit(launcher)
    launcher.start(command=_fake_command("normal"))
    notifications = _wait_for_exit(launcher)
    assert any(
        isinstance(item, ProtocolEvent) and item.type == "ready"
        for item in notifications
    )


def test_reader_thread_only_queues_ready_until_caller_drains(tmp_path):
    launcher = QtEditorLauncher(_context(tmp_path))
    launcher.start(command=_fake_command("wait"))
    deadline = time.monotonic() + 2.0
    while launcher._notifications.empty() and time.monotonic() < deadline:
        time.sleep(0.01)

    assert launcher.ready is False
    notifications = launcher.drain_notifications()
    assert any(
        isinstance(item, ProtocolEvent) and item.type == "ready"
        for item in notifications
    )
    assert launcher.ready is True
    _wait_for_exit(launcher)


def test_os_start_failure_is_wrapped(tmp_path):
    def fail_to_start(*args, **kwargs):
        raise OSError("interpréteur introuvable")

    launcher = QtEditorLauncher(_context(tmp_path), popen_factory=fail_to_start)

    with pytest.raises(QtEditorLaunchError, match="interpréteur introuvable"):
        launcher.start()


def test_real_child_requests_and_reads_config_snapshot_from_stdin(tmp_path):
    launcher = QtEditorLauncher(_context(tmp_path))
    launcher.start(command=_fake_command("config-request"))

    deadline = time.monotonic() + 3.0
    request = None
    seen = []
    while request is None and time.monotonic() < deadline:
        batch = launcher.drain_notifications()
        seen.extend(batch)
        request = next(
            (
                item
                for item in batch
                if isinstance(item, ProtocolEvent)
                and item.type == "config_requested"
            ),
            None,
        )
        time.sleep(0.01)

    assert request is not None
    assert request.request_id == 7
    launcher.send_config_snapshot(7, {"site": {"title": "Live"}})
    notifications = seen + _wait_for_exit(launcher)
    assert any(
        isinstance(item, ProtocolEvent) and item.type == "closed"
        for item in notifications
    )
    assert launcher.returncode == 0


def test_non_ascii_config_round_trips_through_real_pipes(tmp_path, monkeypatch):
    """Regression: piped stdio defaulted to cp1252 in the child on Windows."""

    # A developer shell may force UTF-8 globally and hide the bug.
    monkeypatch.delenv("PYTHONIOENCODING", raising=False)
    monkeypatch.delenv("PYTHONUTF8", raising=False)
    subtitle = "Carnet académique « statique » — œuvre"
    launcher = QtEditorLauncher(_context(tmp_path))
    launcher.start(command=_fake_command("utf8-echo"))

    deadline = time.monotonic() + 3.0
    seen = []
    while time.monotonic() < deadline and not any(
        isinstance(item, ProtocolEvent) and item.type == "config_requested"
        for item in seen
    ):
        seen.extend(launcher.drain_notifications())
        time.sleep(0.01)
    launcher.send_config_snapshot(3, {"site": {"subtitle": subtitle}})
    notifications = seen + _wait_for_exit(launcher)

    events = [item for item in notifications if isinstance(item, ProtocolEvent)]
    # Tk -> Qt: what the child decoded from its stdin.
    assert [e.message for e in events if e.type == "error"] == [ascii(subtitle)]
    # Qt -> Tk: what the parent decoded from the child's stdout.
    assert [e.path for e in events if e.type == "saved"] == [
        "C:/projet/pages/créé — « œuvre ».md"
    ]
    assert launcher.returncode == 0


def test_send_command_after_process_exit_is_controlled(tmp_path):
    launcher = QtEditorLauncher(_context(tmp_path))
    launcher.start(command=_fake_command("normal"))
    _wait_for_exit(launcher)

    with pytest.raises(QtEditorCommandError, match="plus disponible"):
        launcher.send_config_error(1, "trop tard")


def test_broken_stdin_pipe_is_wrapped(tmp_path):
    class BrokenStream:
        closed = False

        def write(self, value):
            raise BrokenPipeError

        def flush(self):
            pytest.fail("flush ne doit pas suivre un write en échec")

    launcher = QtEditorLauncher(_context(tmp_path))
    SimpleProcess = type(
        "SimpleProcess",
        (),
        {"poll": lambda self: None, "stdin": BrokenStream()},
    )
    launcher._process = SimpleProcess()

    with pytest.raises(QtEditorCommandError, match="Impossible d’envoyer"):
        launcher.send_config_error(1, "pipe fermée")
