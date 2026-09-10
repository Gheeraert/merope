"""Standard-library launcher for the isolated PySide6 editor process.

This module is safe to import from Tkinter: it never imports the Qt package or
any module below ``bloggen.ui.qt_editor``.
"""

from __future__ import annotations

import queue
import subprocess
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence, TextIO

from bloggen.ui.qt_editor_protocol import ProtocolError, ProtocolEvent, parse_event_line


@dataclass(frozen=True, slots=True)
class QtEditorLaunchContext:
    project_root: Path
    pages_dir: Path
    posts_dir: Path
    images_dir: Path
    slugify_mode: str


@dataclass(frozen=True, slots=True)
class ProtocolDiagnostic:
    message: str
    line: str


@dataclass(frozen=True, slots=True)
class StderrOutput:
    line: str


@dataclass(frozen=True, slots=True)
class ProcessExited:
    returncode: int
    before_ready: bool


LauncherNotification = ProtocolEvent | ProtocolDiagnostic | StderrOutput | ProcessExited


class QtEditorLaunchError(RuntimeError):
    """The operating system could not create the child process."""


class QtEditorAlreadyRunning(RuntimeError):
    """A second experimental editor was requested while one is active."""


def build_qt_editor_command(
    context: QtEditorLaunchContext,
    *,
    executable: str | None = None,
) -> list[str]:
    """Build the exact child command without importing any Qt module."""

    return [
        executable or sys.executable,
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
        context.slugify_mode,
    ]


class QtEditorLauncher:
    """Own one child process and expose thread-safe queued notifications."""

    def __init__(
        self,
        context: QtEditorLaunchContext,
        *,
        popen_factory: Callable[..., subprocess.Popen[str]] = subprocess.Popen,
    ) -> None:
        self.context = context
        self._popen_factory = popen_factory
        self._process: subprocess.Popen[str] | None = None
        self._notifications: queue.SimpleQueue[
            tuple[int, LauncherNotification]
        ] = queue.SimpleQueue()
        self._generation = 0
        self._ready = False
        self._returncode: int | None = None

    @property
    def is_running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    @property
    def ready(self) -> bool:
        return self._ready

    @property
    def returncode(self) -> int | None:
        return self._returncode

    def start(self, *, command: Sequence[str] | None = None) -> subprocess.Popen[str]:
        """Start asynchronously; stream handling happens only in daemon threads."""

        if self.is_running:
            raise QtEditorAlreadyRunning("L’éditeur Qt est déjà ouvert")

        child_command = list(command or build_qt_editor_command(self.context))
        try:
            process = self._popen_factory(
                child_command,
                cwd=str(self.context.project_root),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )
        except OSError as exc:
            raise QtEditorLaunchError(f"Impossible de lancer l’éditeur Qt : {exc}") from exc

        if process.stdout is None or process.stderr is None:
            raise QtEditorLaunchError("Les flux du processus Qt n’ont pas pu être ouverts")

        self._generation += 1
        generation = self._generation
        self._process = process
        self._ready = False
        self._returncode = None
        ready_seen = threading.Event()
        stdout_thread = threading.Thread(
            target=self._read_stdout,
            args=(process.stdout, generation, ready_seen),
            daemon=True,
            name="merope-qt-stdout",
        )
        stderr_thread = threading.Thread(
            target=self._read_stderr,
            args=(process.stderr, generation),
            daemon=True,
            name="merope-qt-stderr",
        )
        stdout_thread.start()
        stderr_thread.start()
        threading.Thread(
            target=self._wait_for_exit,
            args=(process, stdout_thread, stderr_thread, ready_seen, generation),
            daemon=True,
            name="merope-qt-process",
        ).start()
        return process

    def drain_notifications(self) -> list[LauncherNotification]:
        """Drain on the Tk thread; reader threads never invoke GUI callbacks."""

        notifications: list[LauncherNotification] = []
        while True:
            try:
                generation, notification = self._notifications.get_nowait()
            except queue.Empty:
                break
            if generation != self._generation:
                continue
            if isinstance(notification, ProtocolEvent) and notification.type == "ready":
                self._ready = True
            elif isinstance(notification, ProcessExited):
                self._returncode = notification.returncode
            notifications.append(notification)
        return notifications

    def _read_stdout(
        self,
        stream: TextIO,
        generation: int,
        ready_seen: threading.Event,
    ) -> None:
        for raw_line in stream:
            line = raw_line.rstrip("\r\n")
            try:
                event = parse_event_line(line)
            except ProtocolError as exc:
                self._notifications.put(
                    (generation, ProtocolDiagnostic(message=str(exc), line=line))
                )
                continue
            if event.type == "ready":
                ready_seen.set()
            self._notifications.put((generation, event))

    def _wait_for_exit(
        self,
        process: subprocess.Popen[str],
        stdout_thread: threading.Thread,
        stderr_thread: threading.Thread,
        ready_seen: threading.Event,
        generation: int,
    ) -> None:
        returncode = process.wait()
        stdout_thread.join()
        stderr_thread.join()
        self._notifications.put(
            (
                generation,
                ProcessExited(returncode=returncode, before_ready=not ready_seen.is_set()),
            )
        )

    def _read_stderr(self, stream: TextIO, generation: int) -> None:
        for raw_line in stream:
            self._notifications.put(
                (generation, StderrOutput(line=raw_line.rstrip("\r\n")))
            )
