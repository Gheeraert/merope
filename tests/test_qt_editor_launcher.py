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
    QtEditorLaunchContext,
    QtEditorLaunchError,
    QtEditorLauncher,
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

