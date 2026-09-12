from __future__ import annotations

import io
import os
import shutil
import subprocess
import sys
import threading
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtGui import QTextCursor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from bloggen.config.io import load_config
from bloggen.config.models import ProjectConfig
from bloggen.content.writer import write_content_file
from bloggen.markdown.rich_text_model import InlineRun
from bloggen.tei.pandoc_converter import MarkdownToTeiResult, PandocUnavailableError
from bloggen.tei.validator import TeiValidationResult
from bloggen.ui.preview_protocol import PREVIEW_READY_MARKER
from bloggen.ui.qt_editor import preview as preview_module
from bloggen.ui.qt_editor import window as window_module
from bloggen.ui.qt_editor.document_adapter import extract_blocks
from bloggen.ui.qt_editor.preview import (
    PreviewArtifact,
    PreviewBuildError,
    PreviewSnapshot,
    build_preview_artifact,
    determine_content_kind,
    launch_preview_process,
    remove_preview_artifact,
)
from bloggen.ui.qt_editor.preview_startup import PreviewStartupMonitor
from bloggen.ui.qt_editor.window import QtEditorWindow
from bloggen.ui.editor_recovery import recovery_file_path


_TEI_SAMPLE = (
    '<TEI xmlns="http://www.tei-c.org/ns/1.0">'
    '<teiHeader><fileDesc><titleStmt><title>Test</title></titleStmt>'
    '<publicationStmt><p>p</p></publicationStmt>'
    '<sourceDesc><p>s</p></sourceDesc></fileDesc></teiHeader>'
    '<text><body><div><head>Titre</head>'
    '<p>Contenu du snapshot<note>Note structurée</note>'
    '<note>Note différée</note></p>'
    '<figure><head>Image</head>'
    '<graphic url="../../assets/images/exemple.jpg"/></figure>'
    '</div></body></text></TEI>'
)


@pytest.fixture(scope="module", autouse=True)
def qapplication():
    yield QApplication.instance() or QApplication([])


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "project"
    shutil.copytree(
        Path("examples/minimal_project"),
        root,
        ignore=shutil.ignore_patterns("site", "build", "__pycache__"),
    )
    return root, load_config(root / "config" / "site.json")


def _source(root: Path, *, kind: str = "page", slug: str = "apercu-qt") -> Path:
    directory = root / "content" / ("pages" if kind == "page" else "posts")
    metadata = {"title": "Source disque", "slug": slug, "type": kind}
    if kind == "post":
        metadata["date"] = "2026-09-11"
    return write_content_file(directory, f"{slug}.md", metadata, "Corps disque.\n")


def _snapshot(path: Path, *, kind: str = "page", slug: str = "apercu-qt"):
    metadata = {"title": "Aperçu Qt", "slug": slug, "type": kind}
    if kind == "post":
        metadata["date"] = "2026-09-11"
    return PreviewSnapshot(
        body_markdown=(
            "Texte Qt non enregistré[^7] et ((note différée)).\n\n"
            "![Image](../../assets/images/exemple.jpg)\n\n"
            "[^7]: Une **note riche**."
        ),
        metadata=metadata,
        current_path=path,
    )


def _install_fake_pandoc(monkeypatch, seen_paths=None):
    def fake_convert(input_path, output_path, **_kwargs):
        if seen_paths is not None:
            seen_paths.append(Path(input_path))
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(_TEI_SAMPLE, encoding="utf-8")
        return MarkdownToTeiResult(
            source_file=Path(input_path),
            tei_file=output,
            command=["pandoc"],
            success=True,
            message="ok",
            validation=TeiValidationResult(valid=True),
        )

    monkeypatch.setattr(
        "bloggen.build.site_builder.convert_markdown_file_to_tei",
        fake_convert,
    )


def test_page_preview_uses_real_pipeline_and_leaves_project_untouched(
    project, monkeypatch
):
    root, config = project
    source = _source(root)
    before = source.read_bytes()
    seen_paths = []
    seen_items = []
    _install_fake_pandoc(monkeypatch, seen_paths)
    real_build = preview_module._build_single_item

    def capture_item(item, **kwargs):
        seen_items.append(item)
        return real_build(item, **kwargs)

    monkeypatch.setattr(preview_module, "_build_single_item", capture_item)

    artifact = build_preview_artifact(
        _snapshot(source),
        config=config,
        project_root=root,
    )

    assert artifact.html_path == artifact.scratch_dir / "apercu-qt" / "index.html"
    assert artifact.html_path.exists()
    html = artifact.html_path.read_text(encoding="utf-8")
    assert "Aperçu Qt" in html
    assert "endnotes" in html
    assert "exemple.jpg" in html
    assert seen_paths[0].parent == source.parent
    assert seen_paths[0].name.startswith(".__merope_qt_preview__-")
    assert "[^7]: Une **note riche**." in seen_items[0].raw_markdown
    assert "((note différée))" in seen_items[0].raw_markdown
    assert "^[note différée]" in seen_items[0].normalized_markdown
    assert (artifact.scratch_dir / "assets" / "images" / "exemple.jpg").exists()
    assert (artifact.scratch_dir / "static" / "css" / "site.css").exists()
    assert source.read_bytes() == before
    assert list(source.parent.glob(".__merope_qt_preview__-*.md")) == []
    assert not (source.parent / ".versions").exists()
    assert not source.with_suffix(".xml").exists()
    assert not (root / config.paths.output_dir).exists()
    assert not (root / config.paths.tei_dir).exists()
    remove_preview_artifact(artifact)


def test_post_preview_uses_archive_path(project, monkeypatch):
    root, config = project
    config.blog.archive_path = "chroniques"
    source = _source(root, kind="post", slug="billet-qt")
    _install_fake_pandoc(monkeypatch)

    artifact = build_preview_artifact(
        _snapshot(source, kind="post", slug="billet-qt"),
        config=config,
        project_root=root,
    )

    assert artifact.html_path == (
        artifact.scratch_dir / "chroniques" / "billet-qt" / "index.html"
    )
    assert artifact.html_path.exists()
    remove_preview_artifact(artifact)


def test_kind_detection_rejects_metadata_path_contradiction(project):
    root, config = project
    source = _source(root, kind="page")
    snapshot = PreviewSnapshot(
        body_markdown="Texte.",
        metadata={"title": "X", "slug": "x", "type": "post", "date": "2026-09-11"},
        current_path=source,
    )

    with pytest.raises(PreviewBuildError, match="contradictoire"):
        determine_content_kind(snapshot, config=config, project_root=root)


def test_kind_detection_refuses_unanchored_document(project, tmp_path):
    root, config = project
    snapshot = PreviewSnapshot(
        body_markdown="Texte.",
        metadata={"title": "X", "slug": "x"},
        current_path=tmp_path / "hors-projet.md",
    )

    with pytest.raises(PreviewBuildError, match="Impossible de déterminer"):
        determine_content_kind(snapshot, config=config, project_root=root)


@pytest.mark.parametrize(
    ("kind", "metadata", "message"),
    [
        ("page", {"title": "", "slug": "valide", "type": "page"}, "title"),
        (
            "page",
            {"title": "Titre", "slug": "Slug invalide", "type": "page"},
            "Slug invalide",
        ),
        (
            "post",
            {"title": "Titre", "slug": "billet", "type": "post", "date": "11/09/2026"},
            "Date invalide",
        ),
    ],
)
def test_metadata_error_removes_neighboring_markdown(
    project, kind, metadata, message
):
    root, config = project
    source = _source(root, kind=kind)
    snapshot = PreviewSnapshot(
        body_markdown="Texte.",
        metadata=metadata,
        current_path=source,
    )

    with pytest.raises(PreviewBuildError, match=message):
        build_preview_artifact(snapshot, config=config, project_root=root)

    assert list(source.parent.glob(".__merope_qt_preview__-*.md")) == []


def test_pandoc_failure_removes_new_scratch_and_temp_markdown(project, monkeypatch):
    root, config = project
    source = _source(root)
    created_scratch = []
    real_mkdtemp = preview_module.tempfile.mkdtemp

    def record_mkdtemp(*args, **kwargs):
        path = Path(real_mkdtemp(*args, **kwargs))
        created_scratch.append(path)
        return str(path)

    def fail_convert(*args, **kwargs):
        raise PandocUnavailableError("pandoc absent")

    monkeypatch.setattr(preview_module.tempfile, "mkdtemp", record_mkdtemp)
    monkeypatch.setattr(
        "bloggen.build.site_builder.convert_markdown_file_to_tei",
        fail_convert,
    )

    with pytest.raises(PreviewBuildError, match="pandoc absent"):
        build_preview_artifact(_snapshot(source), config=config, project_root=root)

    assert created_scratch and not created_scratch[0].exists()
    assert list(source.parent.glob(".__merope_qt_preview__-*.md")) == []


def test_each_preview_uses_fresh_scratch_and_current_theme(project, monkeypatch):
    root, config = project
    source = _source(root)
    _install_fake_pandoc(monkeypatch)
    for name, marker in (("theme-a", "/* A */"), ("theme-b", "/* B */")):
        css = root / name / "css" / "site.css"
        css.parent.mkdir(parents=True)
        css.write_text(marker, encoding="utf-8")

    config.paths.theme_dir = "theme-a"
    first = build_preview_artifact(_snapshot(source), config=config, project_root=root)
    config.paths.theme_dir = "theme-b"
    second = build_preview_artifact(_snapshot(source), config=config, project_root=root)

    assert first.scratch_dir != second.scratch_dir
    assert (first.scratch_dir / "static/css/site.css").read_text(encoding="utf-8") == "/* A */"
    assert (second.scratch_dir / "static/css/site.css").read_text(encoding="utf-8") == "/* B */"
    remove_preview_artifact(first)
    remove_preview_artifact(second)


def test_preview_process_uses_existing_module_and_pointer(tmp_path, monkeypatch):
    scratch = tmp_path / "scratch"
    html = scratch / "page" / "index.html"
    html.parent.mkdir(parents=True)
    html.write_text("<html></html>", encoding="utf-8")
    pointer = html.parent / "_current.txt"
    pointer.write_text(str(html.resolve()), encoding="utf-8")
    artifact = PreviewArtifact(scratch, html, pointer)
    calls = []
    process = object()
    monkeypatch.setattr(preview_module, "pywebview_available", lambda: True)

    result = launch_preview_process(
        artifact,
        popen_factory=lambda command, **kwargs: calls.append((command, kwargs)) or process,
    )

    assert result is process
    assert calls == [
        (
            [sys.executable, "-m", "bloggen.ui.preview_process", str(pointer.resolve())],
            {
                "stdin": preview_module.subprocess.DEVNULL,
                "stdout": preview_module.subprocess.PIPE,
                "stderr": preview_module.subprocess.PIPE,
                "text": True,
                "encoding": "utf-8",
                "errors": "replace",
            },
        )
    ]


def test_preview_process_starts_while_ipc_stdin_reader_is_blocked(tmp_path):
    """Regression: the grandchild must not inherit the busy IPC stdin pipe.

    On Windows an inherited stdin with a pending read in the Qt child hung the
    preview interpreter before READY, which surfaced as the 5 s timeout.
    """

    child_script = Path(__file__).parent / "fixtures" / "busy_stdin_preview_child.py"
    stderr_path = tmp_path / "child-stderr.txt"
    with stderr_path.open("w", encoding="utf-8") as stderr_file:
        child = subprocess.Popen(
            [sys.executable, str(child_script), str(tmp_path), "10"],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=stderr_file,
        )
        try:
            # Never write to nor close the child's stdin: its reader thread must
            # stay blocked for the whole test, exactly like the IPC bridge.
            child.wait(timeout=30)
        finally:
            if child.poll() is None:
                child.kill()
            child.stdin.close()
    assert child.returncode == 0, stderr_path.read_text(encoding="utf-8")


def test_preview_process_refuses_missing_pywebview(tmp_path, monkeypatch):
    artifact = PreviewArtifact(tmp_path, tmp_path / "index.html", tmp_path / "pointer")
    monkeypatch.setattr(preview_module, "pywebview_available", lambda: False)

    with pytest.raises(PreviewBuildError, match="pywebview"):
        launch_preview_process(
            artifact,
            popen_factory=lambda command, **kwargs: pytest.fail(
                "Popen ne doit pas être appelé"
            ),
        )


def _wait_for(predicate, *, timeout_ms: int = 1_000) -> None:
    elapsed = 0
    while not predicate() and elapsed < timeout_ms:
        QTest.qWait(10)
        elapsed += 10
    assert predicate()


def test_process_exit_before_ready_reports_captured_stderr(tmp_path, monkeypatch):
    artifact = PreviewArtifact(tmp_path, tmp_path / "index.html", tmp_path / "pointer")

    class ImmediateFailureProcess:
        stdout = io.StringIO("")
        stderr = io.StringIO("backend pywebview indisponible\n")

        @staticmethod
        def wait():
            return 1

        @staticmethod
        def poll():
            return 1

    process = ImmediateFailureProcess()
    monkeypatch.setattr(preview_module, "pywebview_available", lambda: True)
    launched = launch_preview_process(
        artifact,
        popen_factory=lambda _command, **_kwargs: process,
    )
    failures = []
    monitor = PreviewStartupMonitor(launched, timeout_ms=500)
    monitor.failed.connect(
        lambda failed_process, returncode, diagnostic: failures.append(
            (failed_process, returncode, diagnostic)
        )
    )

    monitor.start()
    _wait_for(lambda: bool(failures))

    assert failures == [(process, 1, "backend pywebview indisponible")]


def test_startup_monitor_accepts_ready_while_process_keeps_running():
    released = threading.Event()

    class ReadyProcess:
        stdout = io.StringIO(f"{PREVIEW_READY_MARKER}\n")
        stderr = io.StringIO("")

        def __init__(self):
            self.terminated = False

        def wait(self):
            released.wait(timeout=1.0)
            return 0

        def poll(self):
            return 0 if self.terminated else None

        def terminate(self):
            self.terminated = True
            released.set()

    process = ReadyProcess()
    ready = []
    failures = []
    monitor = PreviewStartupMonitor(process, timeout_ms=500)
    monitor.ready.connect(ready.append)
    monitor.failed.connect(lambda *args: failures.append(args))

    monitor.start()
    _wait_for(lambda: bool(ready))

    assert ready == [process]
    assert failures == []
    monitor.cancel()
    process.terminate()


def test_startup_monitor_times_out_and_terminates_process():
    released = threading.Event()

    class HangingProcess:
        stdout = io.StringIO("")
        stderr = io.StringIO("")

        def __init__(self):
            self.terminated = False

        def wait(self):
            released.wait(timeout=1.0)
            return -15

        def poll(self):
            return -15 if self.terminated else None

        def terminate(self):
            self.terminated = True
            released.set()

    process = HangingProcess()
    timeouts = []
    monitor = PreviewStartupMonitor(process, timeout_ms=20)
    monitor.timedOut.connect(timeouts.append)

    monitor.start()
    _wait_for(lambda: bool(timeouts))

    assert timeouts == [process]
    assert process.terminated


def _dispose(window: QtEditorWindow) -> None:
    window.autosave_timer.stop()
    window._close_html_preview()
    window.ipc_bridge.shutdown()
    window.deleteLater()
    QApplication.processEvents()


def test_window_preview_snapshot_is_transactional_and_uses_matching_live_config(
    project, monkeypatch, tmp_path
):
    root, _ = project
    source = write_content_file(
        root / "content/pages",
        "transaction.md",
        {"title": "Transaction", "slug": "transaction", "type": "page"},
        "Texte[^7] et ((note différée)).\n\n[^7]: Note initiale.",
    )
    window = QtEditorWindow(markdown_path=source, project_root=root)
    window.footnote_store.update("7", [InlineRun(text="Note modifiée", bold=True)])
    cursor = QTextCursor(window.editor.document())
    cursor.movePosition(QTextCursor.MoveOperation.End)
    cursor.insertText(" D1")
    window.editor.setTextCursor(cursor)
    request_ids = iter((1, 2))
    monkeypatch.setattr(window, "request_live_config", lambda: next(request_ids))
    builds = []

    def fake_build(snapshot, *, config, project_root):
        builds.append((snapshot, config.site.title, project_root))
        scratch = tmp_path / f"artifact-{len(builds)}"
        html = scratch / "transaction/index.html"
        html.parent.mkdir(parents=True)
        html.write_text("ok", encoding="utf-8")
        pointer = html.parent / "_current.txt"
        pointer.write_text(str(html), encoding="utf-8")
        return PreviewArtifact(scratch, html, pointer)

    monkeypatch.setattr(window_module, "build_preview_artifact", fake_build)
    monkeypatch.setattr(window, "_activate_preview_artifact", lambda artifact: None)
    store_before = window.footnote_store.snapshot()
    modified_before = window.document_has_unsaved_changes

    window._request_html_preview()
    first_snapshot = window._pending_preview_snapshots[1]
    cursor = QTextCursor(window.editor.document())
    cursor.movePosition(QTextCursor.MoveOperation.End)
    cursor.insertText(" D2")
    window.editor.setTextCursor(cursor)
    body_after_user_edit = extract_blocks(window.editor.document())
    undo_before_build = window.editor.document().isUndoAvailable()
    redo_before_build = window.editor.document().isRedoAvailable()
    selection_before_build = (
        window.editor.textCursor().position(),
        window.editor.textCursor().anchor(),
    )
    config_a = ProjectConfig()
    config_a.site.title = "Configuration A"
    window._on_preview_config_ready(1, config_a)

    assert "D1" in first_snapshot.body_markdown
    assert "D2" not in first_snapshot.body_markdown
    assert "[^7]: **Note modifiée**" in first_snapshot.body_markdown
    assert "((note différée))" in first_snapshot.body_markdown
    assert builds[0][1:] == ("Configuration A", root)

    window._request_html_preview()
    config_b = ProjectConfig()
    config_b.site.title = "Configuration B"
    window._on_preview_config_ready(2, config_b)
    assert "D2" in builds[1][0].body_markdown
    assert builds[1][1] == "Configuration B"
    assert window.footnote_store.snapshot() == store_before
    assert extract_blocks(window.editor.document()) == body_after_user_edit
    assert window.document_has_unsaved_changes == modified_before
    assert window.editor.document().isUndoAvailable() == undo_before_build
    assert window.editor.document().isRedoAvailable() == redo_before_build
    assert selection_before_build == (
        window.editor.textCursor().position(),
        window.editor.textCursor().anchor(),
    )
    assert window.preview_action.isEnabled()
    _dispose(window)


def test_clean_preview_preserves_dirty_undo_selection_recovery_and_source(
    project, monkeypatch, tmp_path
):
    root, _ = project
    source = _source(root, slug="lecture-seule")
    source_before = source.read_bytes()
    window = QtEditorWindow(markdown_path=source, project_root=root)
    recovery = recovery_file_path(root)
    recovery.parent.mkdir(parents=True, exist_ok=True)
    recovery.write_bytes(b'{"sentinel":"unchanged"}')
    recovery_before = recovery.read_bytes()
    monkeypatch.setattr(window, "request_live_config", lambda: 21)
    scratch = tmp_path / "clean-artifact"
    html = scratch / "lecture-seule/index.html"
    html.parent.mkdir(parents=True)
    html.write_text("ok", encoding="utf-8")
    pointer = html.parent / "_current.txt"
    pointer.write_text(str(html), encoding="utf-8")
    monkeypatch.setattr(
        window_module,
        "build_preview_artifact",
        lambda *args, **kwargs: PreviewArtifact(scratch, html, pointer),
    )
    monkeypatch.setattr(window, "_activate_preview_artifact", lambda artifact: None)
    cursor = window.editor.textCursor()
    cursor.setPosition(1)
    window.editor.setTextCursor(cursor)
    before = (
        window.document_has_unsaved_changes,
        window.editor.document().isUndoAvailable(),
        window.editor.document().isRedoAvailable(),
        cursor.position(),
        cursor.anchor(),
        window.footnote_store.snapshot(),
    )

    window._request_html_preview()
    window._on_preview_config_ready(21, ProjectConfig())

    after_cursor = window.editor.textCursor()
    after = (
        window.document_has_unsaved_changes,
        window.editor.document().isUndoAvailable(),
        window.editor.document().isRedoAvailable(),
        after_cursor.position(),
        after_cursor.anchor(),
        window.footnote_store.snapshot(),
    )
    assert after == before
    assert source.read_bytes() == source_before
    assert recovery.read_bytes() == recovery_before
    _dispose(window)


def test_obsolete_config_response_is_ignored(project, monkeypatch, tmp_path):
    root, _ = project
    source = _source(root, slug="obsolete")
    window = QtEditorWindow(markdown_path=source, project_root=root)
    request_ids = iter((10, 11))
    monkeypatch.setattr(window, "request_live_config", lambda: next(request_ids))
    builds = []
    monkeypatch.setattr(
        window_module,
        "build_preview_artifact",
        lambda snapshot, **kwargs: builds.append((snapshot, kwargs["config"]))
        or PreviewArtifact(tmp_path, tmp_path / "x", tmp_path / "p"),
    )
    monkeypatch.setattr(window, "_activate_preview_artifact", lambda artifact: None)

    window._request_html_preview()
    window._request_html_preview()
    window._on_preview_config_ready(10, ProjectConfig())
    assert builds == []
    window._on_preview_config_ready(11, ProjectConfig())
    assert len(builds) == 1
    _dispose(window)


def test_window_refuses_preview_without_current_path(monkeypatch):
    window = QtEditorWindow()
    errors = []
    monkeypatch.setattr(window, "_show_preview_error", errors.append)
    monkeypatch.setattr(
        window,
        "request_live_config",
        lambda: pytest.fail("aucune configuration ne doit être demandée"),
    )

    window._request_html_preview()

    assert errors and "document Mérope déjà ouvert" in errors[0]
    _dispose(window)


def test_preview_action_triggers_snapshot_and_live_config_request(project, monkeypatch):
    root, _ = project
    source = _source(root, slug="action-trigger")
    window = QtEditorWindow(markdown_path=source, project_root=root)
    requests = []

    def request_config():
        requests.append(True)
        return 44

    monkeypatch.setattr(window, "request_live_config", request_config)

    window.preview_action.trigger()

    assert requests == [True]
    assert window._pending_preview_request_id == 44
    assert 44 in window._pending_preview_snapshots
    assert not window.preview_action.isEnabled()
    _dispose(window)


def test_standalone_preview_failure_is_async_and_reenables_action(
    project, monkeypatch, qapplication
):
    root, _ = project
    source = _source(root, slug="standalone")
    window = QtEditorWindow(markdown_path=source, project_root=root, ipc=False)
    errors = []
    monkeypatch.setattr(window, "_show_preview_error", errors.append)

    window._request_html_preview()

    assert errors == []
    assert not window.preview_action.isEnabled()
    qapplication.processEvents()
    assert errors == [
        "Configuration live indisponible dans ce mode. Lancez l’éditeur Qt "
        "depuis Mérope pour utiliser l’aperçu HTML."
    ]
    assert window.preview_action.isEnabled()
    _dispose(window)


class _ManualSignal:
    def __init__(self):
        self._callbacks = []

    def connect(self, callback):
        self._callbacks.append(callback)

    def emit(self, *args):
        for callback in list(self._callbacks):
            callback(*args)


class _ManualPreviewStartupMonitor:
    def __init__(self, process, *, parent=None):
        self.process = process
        self.parent = parent
        self.ready = _ManualSignal()
        self.failed = _ManualSignal()
        self.timedOut = _ManualSignal()
        self.closed = _ManualSignal()
        self.started = False
        self.cancelled = False

    def start(self):
        self.started = True

    def cancel(self):
        self.cancelled = True

    def emit_timeout(self):
        if self.process.poll() is None:
            self.process.terminate()
        self.timedOut.emit(self.process)


def test_preview_process_and_scratch_are_replaced_then_closed(
    monkeypatch, tmp_path
):
    window = QtEditorWindow()

    class FakeProcess:
        def __init__(self):
            self.terminated = False

        def poll(self):
            return None

        def terminate(self):
            self.terminated = True

    old_process = FakeProcess()
    new_process = FakeProcess()
    old_scratch = tmp_path / "old"
    new_scratch = tmp_path / "new"
    old_scratch.mkdir()
    new_scratch.mkdir()
    old_artifact = PreviewArtifact(old_scratch, old_scratch / "index.html", old_scratch / "p")
    new_artifact = PreviewArtifact(new_scratch, new_scratch / "index.html", new_scratch / "p")
    window._preview_process = old_process
    window._preview_artifact = old_artifact
    monkeypatch.setattr(window_module, "pywebview_available", lambda: True)
    monkeypatch.setattr(window_module, "launch_preview_process", lambda artifact: new_process)
    monkeypatch.setattr(
        window_module,
        "PreviewStartupMonitor",
        _ManualPreviewStartupMonitor,
    )
    window.preview_action.setEnabled(False)

    window._activate_preview_artifact(new_artifact)

    monitor = window._preview_candidate_monitor
    assert monitor is not None and monitor.started
    assert window._preview_process is old_process
    assert not old_process.terminated
    assert old_scratch.exists()
    assert not window.preview_action.isEnabled()

    monitor.ready.emit(new_process)

    assert old_process.terminated
    assert not old_scratch.exists()
    assert window._preview_process is new_process
    assert window.preview_action.isEnabled()
    window._close_html_preview()
    assert new_process.terminated
    assert not new_scratch.exists()
    _dispose(window)


def test_crash_before_ready_is_visible_and_cleans_candidate(monkeypatch, tmp_path):
    window = QtEditorWindow()

    class FailedProcess:
        def poll(self):
            return 1

    process = FailedProcess()
    scratch = tmp_path / "failed-preview"
    scratch.mkdir()
    artifact = PreviewArtifact(scratch, scratch / "index.html", scratch / "pointer")
    errors = []
    monkeypatch.setattr(window_module, "pywebview_available", lambda: True)
    monkeypatch.setattr(window_module, "launch_preview_process", lambda _artifact: process)
    monkeypatch.setattr(
        window_module,
        "PreviewStartupMonitor",
        _ManualPreviewStartupMonitor,
    )
    monkeypatch.setattr(window, "_show_preview_error", errors.append)
    window.preview_action.setEnabled(False)

    window._activate_preview_artifact(artifact)
    monitor = window._preview_candidate_monitor
    assert monitor is not None
    monitor.failed.emit(process, 1, "backend failure")

    assert errors == [
        "Impossible d’ouvrir la fenêtre d’aperçu.\n\n"
        "Diagnostic :\nbackend failure"
    ]
    assert window._preview_candidate_process is None
    assert window._preview_candidate_artifact is None
    assert not scratch.exists()
    assert window.preview_action.isEnabled()
    _dispose(window)


def test_crash_before_ready_keeps_existing_preview(monkeypatch, tmp_path):
    window = QtEditorWindow()

    class Process:
        def __init__(self, returncode=None):
            self.returncode = returncode
            self.terminated = False

        def poll(self):
            return self.returncode

        def terminate(self):
            self.terminated = True
            self.returncode = -15

    old_process = Process()
    candidate_process = Process(1)
    old_scratch = tmp_path / "old-active-preview"
    candidate_scratch = tmp_path / "failed-candidate-preview"
    old_scratch.mkdir()
    candidate_scratch.mkdir()
    old_artifact = PreviewArtifact(
        old_scratch, old_scratch / "index.html", old_scratch / "pointer"
    )
    candidate_artifact = PreviewArtifact(
        candidate_scratch,
        candidate_scratch / "index.html",
        candidate_scratch / "pointer",
    )
    window._preview_process = old_process
    window._preview_artifact = old_artifact
    monkeypatch.setattr(window_module, "pywebview_available", lambda: True)
    monkeypatch.setattr(
        window_module,
        "launch_preview_process",
        lambda _artifact: candidate_process,
    )
    monkeypatch.setattr(
        window_module,
        "PreviewStartupMonitor",
        _ManualPreviewStartupMonitor,
    )
    monkeypatch.setattr(window, "_show_preview_error", lambda _message: None)

    window._activate_preview_artifact(candidate_artifact)
    monitor = window._preview_candidate_monitor
    assert monitor is not None
    monitor.failed.emit(candidate_process, 1, "backend failure")

    assert window._preview_process is old_process
    assert window._preview_artifact is old_artifact
    assert not old_process.terminated
    assert old_scratch.exists()
    assert not candidate_scratch.exists()
    _dispose(window)


def test_preview_startup_timeout_cleans_candidate_and_reenables_action(
    monkeypatch, tmp_path
):
    window = QtEditorWindow()

    class HangingProcess:
        def __init__(self):
            self.terminated = False

        def poll(self):
            return None if not self.terminated else -15

        def terminate(self):
            self.terminated = True

    process = HangingProcess()
    scratch = tmp_path / "timed-out-preview"
    scratch.mkdir()
    artifact = PreviewArtifact(scratch, scratch / "index.html", scratch / "pointer")
    errors = []
    monkeypatch.setattr(window_module, "pywebview_available", lambda: True)
    monkeypatch.setattr(window_module, "launch_preview_process", lambda _artifact: process)
    monkeypatch.setattr(
        window_module,
        "PreviewStartupMonitor",
        _ManualPreviewStartupMonitor,
    )
    monkeypatch.setattr(window, "_show_preview_error", errors.append)
    window.preview_action.setEnabled(False)

    window._activate_preview_artifact(artifact)
    monitor = window._preview_candidate_monitor
    assert monitor is not None
    monitor.emit_timeout()

    assert process.terminated
    assert not scratch.exists()
    assert window.preview_action.isEnabled()
    assert errors and "délai attendu de 5 secondes" in errors[0]
    _dispose(window)


def test_exit_after_ready_is_normal_and_cleans_active_preview(monkeypatch, tmp_path):
    window = QtEditorWindow()

    class Process:
        def __init__(self):
            self.terminated = False

        def poll(self):
            return 0

        def terminate(self):
            self.terminated = True

    process = Process()
    scratch = tmp_path / "ready-then-closed"
    scratch.mkdir()
    artifact = PreviewArtifact(scratch, scratch / "index.html", scratch / "pointer")
    errors = []
    monkeypatch.setattr(window_module, "pywebview_available", lambda: True)
    monkeypatch.setattr(window_module, "launch_preview_process", lambda _artifact: process)
    monkeypatch.setattr(
        window_module,
        "PreviewStartupMonitor",
        _ManualPreviewStartupMonitor,
    )
    monkeypatch.setattr(window, "_show_preview_error", errors.append)

    window._activate_preview_artifact(artifact)
    monitor = window._preview_candidate_monitor
    assert monitor is not None
    monitor.ready.emit(process)
    monitor.closed.emit(process, 0)

    assert errors == []
    assert window._preview_process is None
    assert window._preview_artifact is None
    assert not scratch.exists()
    _dispose(window)


def test_failed_new_build_keeps_existing_preview(project, monkeypatch, tmp_path):
    root, _ = project
    source = _source(root, slug="keep-old")
    window = QtEditorWindow(markdown_path=source, project_root=root)

    class FakeProcess:
        terminated = False

        def poll(self):
            return None

        def terminate(self):
            self.terminated = True

    old_process = FakeProcess()
    old_scratch = tmp_path / "old-still-open"
    old_scratch.mkdir()
    old_artifact = PreviewArtifact(
        old_scratch,
        old_scratch / "index.html",
        old_scratch / "pointer",
    )
    window._preview_process = old_process
    window._preview_artifact = old_artifact
    monkeypatch.setattr(window, "request_live_config", lambda: 31)
    monkeypatch.setattr(
        window_module,
        "build_preview_artifact",
        lambda *args, **kwargs: (_ for _ in ()).throw(PreviewBuildError("échec")),
    )
    errors = []
    monkeypatch.setattr(window, "_show_preview_error", errors.append)

    window._request_html_preview()
    window._on_preview_config_ready(31, ProjectConfig())

    assert errors == ["échec"]
    assert window._preview_process is old_process
    assert not old_process.terminated
    assert old_scratch.exists()
    _dispose(window)


def test_failed_new_preview_launch_keeps_existing_preview(monkeypatch, tmp_path):
    window = QtEditorWindow()

    class FakeProcess:
        def __init__(self):
            self.terminated = False

        def poll(self):
            return None

        def terminate(self):
            self.terminated = True

    old_process = FakeProcess()
    old_scratch = tmp_path / "old-preview"
    new_scratch = tmp_path / "new-preview"
    old_scratch.mkdir()
    new_scratch.mkdir()
    old_artifact = PreviewArtifact(
        old_scratch,
        old_scratch / "index.html",
        old_scratch / "pointer",
    )
    new_artifact = PreviewArtifact(
        new_scratch,
        new_scratch / "index.html",
        new_scratch / "pointer",
    )
    window._preview_process = old_process
    window._preview_artifact = old_artifact
    monkeypatch.setattr(window_module, "pywebview_available", lambda: True)

    def fail_to_launch(_artifact):
        raise PreviewBuildError("échec du lancement")

    monkeypatch.setattr(window_module, "launch_preview_process", fail_to_launch)

    with pytest.raises(PreviewBuildError, match="échec du lancement"):
        window._activate_preview_artifact(new_artifact)

    assert window._preview_process is old_process
    assert window._preview_artifact is old_artifact
    assert not old_process.terminated
    assert old_scratch.exists()
    assert not new_scratch.exists()
    _dispose(window)
