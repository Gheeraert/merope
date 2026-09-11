from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from bloggen.ui import main_window as main_window_module
from bloggen.config.models import ProjectConfig
from bloggen.ui.main_window import MainWindow
from bloggen.ui.qt_editor_launcher import (
    ProcessExited,
    QtEditorLaunchContext,
    StartupTimedOut,
)
from bloggen.ui.qt_editor_protocol import ProtocolEvent


def _context(root: Path) -> QtEditorLaunchContext:
    return QtEditorLaunchContext(
        project_root=root,
        pages_dir=root / "content" / "pages",
        posts_dir=root / "content" / "posts",
        images_dir=root / "assets" / "images",
        slugify_mode="ascii",
    )


def test_importing_main_window_does_not_import_pyside6(tmp_path):
    script = (
        "import sys; import bloggen.ui.main_window; "
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


def test_historical_tk_editor_reuses_shared_resolved_context(tmp_path, monkeypatch):
    context = _context(tmp_path)
    calls = []
    host = SimpleNamespace(
        _resolve_content_editor_context=lambda: context,
        _config_for_preview=lambda: None,
    )
    monkeypatch.setattr(
        main_window_module,
        "ContentEditorWindow",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    MainWindow.open_content_editor(host)

    args, kwargs = calls[0]
    assert args == (host,)
    assert kwargs == {
        "pages_dir": context.pages_dir,
        "posts_dir": context.posts_dir,
        "images_dir": context.images_dir,
        "slugify_mode": context.slugify_mode,
        "project_root": context.project_root,
        "get_config": host._config_for_preview,
    }


def test_experimental_button_starts_one_launcher_and_schedules_tk_poll(
    tmp_path, monkeypatch
):
    context = _context(tmp_path)
    scheduled = []

    class FakeLauncher:
        is_running = True

        def __init__(self, received_context):
            assert received_context == context
            self.started = False

        def start(self):
            self.started = True

    host = SimpleNamespace(
        _qt_editor_launcher=None,
        _qt_editor_diagnostics=["ancien"],
        _qt_editor_last_event=object(),
        _resolve_content_editor_context=lambda: context,
        after=lambda delay, callback: scheduled.append((delay, callback)),
        _poll_qt_editor=lambda: None,
        _offer_tk_editor_fallback=lambda detail: None,
    )
    monkeypatch.setattr(main_window_module, "QtEditorLauncher", FakeLauncher)

    MainWindow.open_qt_content_editor(host)

    assert host._qt_editor_launcher.started is True
    assert host._qt_editor_diagnostics == []
    assert host._qt_editor_last_event is None
    assert len(scheduled) == 1
    assert scheduled[0][0] == 75


def test_double_click_while_qt_process_is_active_does_not_start_another(
    monkeypatch,
):
    messages = []
    active = SimpleNamespace(is_running=True)
    host = SimpleNamespace(_qt_editor_launcher=active)
    monkeypatch.setattr(
        main_window_module.messagebox,
        "showinfo",
        lambda *args, **kwargs: messages.append(args[1]),
    )

    MainWindow.open_qt_content_editor(host)

    assert host._qt_editor_launcher is active
    assert messages == ["L’éditeur Qt expérimental est déjà ouvert."]


def test_poll_handles_ready_saved_closed_and_releases_finished_launcher(tmp_path):
    path = str(tmp_path / "content" / "pages" / "article.md")
    notifications = [
        ProtocolEvent(protocol=1, type="ready"),
        ProtocolEvent(protocol=1, type="saved", path=path),
        ProtocolEvent(protocol=1, type="closed"),
        ProcessExited(returncode=0, before_ready=False),
    ]
    launcher = SimpleNamespace(
        ready=True,
        drain_notifications=lambda: notifications,
    )
    scheduled = []
    host = SimpleNamespace(
        _qt_editor_launcher=launcher,
        _qt_editor_diagnostics=[],
        _qt_editor_last_event=None,
        after=lambda *args: scheduled.append(args),
        _offer_tk_editor_fallback=lambda detail: None,
    )

    MainWindow._poll_qt_editor(host)

    assert host._qt_editor_last_event.type == "closed"
    assert host._qt_editor_launcher is None
    assert scheduled == []


def test_process_exit_before_ready_offers_tk_fallback():
    fallbacks = []
    launcher = SimpleNamespace(
        ready=False,
        drain_notifications=lambda: [
            ProcessExited(returncode=2, before_ready=True)
        ],
    )
    host = SimpleNamespace(
        _qt_editor_launcher=launcher,
        _qt_editor_diagnostics=["PySide6 absent"],
        _qt_editor_last_event=None,
        after=lambda *args: None,
        _offer_tk_editor_fallback=lambda detail: fallbacks.append(detail),
    )

    MainWindow._poll_qt_editor(host)

    assert len(fallbacks) == 1
    assert "n’a pas pu démarrer" in fallbacks[0]
    assert "PySide6 absent" in fallbacks[0]
    assert host._qt_editor_launcher is None


def test_startup_timeout_offers_fallback_and_releases_launcher():
    fallbacks = []
    launcher = SimpleNamespace(
        ready=False,
        drain_notifications=lambda: [],
        check_startup_timeout=lambda: StartupTimedOut(timeout_seconds=10.0),
    )
    host = SimpleNamespace(
        _qt_editor_launcher=launcher,
        _qt_editor_diagnostics=[],
        _qt_editor_last_event=None,
        after=lambda *args: pytest.fail("Le polling ne doit pas être reprogrammé"),
        _offer_tk_editor_fallback=lambda detail: fallbacks.append(detail),
    )

    MainWindow._poll_qt_editor(host)

    assert host._qt_editor_launcher is None
    assert len(fallbacks) == 1
    assert "10 s" in fallbacks[0]


class _ConfigRequestLauncher:
    ready = True

    def __init__(self, context, notifications=()):
        self.context = context
        self.notifications = list(notifications)
        self.snapshots = []
        self.errors = []

    def drain_notifications(self):
        result = self.notifications
        self.notifications = []
        return result

    def check_startup_timeout(self):
        return None

    def send_config_snapshot(self, request_id, payload):
        self.snapshots.append((request_id, payload))

    def send_config_error(self, request_id, message):
        self.errors.append((request_id, message))


def test_poll_collects_a_fresh_unsaved_form_snapshot_for_every_request(
    tmp_path, monkeypatch
):
    context = _context(tmp_path)
    (tmp_path / "site.json").write_text(
        '{"site":{"title":"DISQUE"}}',
        encoding="utf-8",
    )
    launcher = _ConfigRequestLauncher(
        context,
        [ProtocolEvent(1, "config_requested", request_id=1)],
    )
    live_title = ["A"]
    disk_loads = []

    def collect():
        config = ProjectConfig()
        config.site.title = live_title[0]
        return config

    host = SimpleNamespace(
        _qt_editor_launcher=launcher,
        _qt_editor_diagnostics=[],
        _qt_editor_last_event=ProtocolEvent(1, "ready"),
        _collect_from_form=collect,
        _resolve_content_editor_context=lambda: context,
        after=lambda *args: None,
        _offer_tk_editor_fallback=lambda detail: None,
    )
    host._answer_qt_config_request = (
        lambda actual_launcher, event: MainWindow._answer_qt_config_request(
            host, actual_launcher, event
        )
    )
    monkeypatch.setattr(
        main_window_module,
        "load_config",
        lambda *args, **kwargs: disk_loads.append(args),
    )

    MainWindow._poll_qt_editor(host)
    live_title[0] = "B"
    launcher.notifications = [ProtocolEvent(1, "config_requested", request_id=2)]
    MainWindow._poll_qt_editor(host)

    assert [payload["site"]["title"] for _, payload in launcher.snapshots] == [
        "A",
        "B",
    ]
    assert all("ftp" not in payload for _, payload in launcher.snapshots)
    assert launcher.errors == []
    assert disk_loads == []
    assert host._qt_editor_last_event.type == "ready"


def test_invalid_live_form_returns_config_error(tmp_path):
    context = _context(tmp_path)
    launcher = _ConfigRequestLauncher(context)
    config = ProjectConfig()
    config.site.title = ""
    host = SimpleNamespace(
        _qt_editor_launcher=launcher,
        _qt_editor_diagnostics=[],
        _collect_from_form=lambda: config,
        _resolve_content_editor_context=lambda: context,
    )

    MainWindow._answer_qt_config_request(
        host,
        launcher,
        ProtocolEvent(1, "config_requested", request_id=9),
    )

    assert launcher.snapshots == []
    assert launcher.errors and launcher.errors[0][0] == 9
    assert "site.title" in launcher.errors[0][1]


def test_structural_context_change_requires_reopening_editor(tmp_path):
    launch_context = _context(tmp_path)
    current_context = QtEditorLaunchContext(
        project_root=launch_context.project_root,
        pages_dir=launch_context.pages_dir / "nouveau",
        posts_dir=launch_context.posts_dir,
        images_dir=launch_context.images_dir,
        slugify_mode=launch_context.slugify_mode,
    )
    launcher = _ConfigRequestLauncher(launch_context)
    host = SimpleNamespace(
        _qt_editor_launcher=launcher,
        _qt_editor_diagnostics=[],
        _collect_from_form=ProjectConfig,
        _resolve_content_editor_context=lambda: current_context,
    )

    MainWindow._answer_qt_config_request(
        host,
        launcher,
        ProtocolEvent(1, "config_requested", request_id=5),
    )

    assert launcher.snapshots == []
    assert launcher.errors[0][0] == 5
    assert "Fermez et rouvrez" in launcher.errors[0][1]
