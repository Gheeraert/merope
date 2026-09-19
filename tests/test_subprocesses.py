from __future__ import annotations

import subprocess

import pytest

from bloggen.utils.subprocesses import (
    DEFAULT_COMMAND_TIMEOUT_SECONDS,
    CommandExecutionError,
    CommandNotFoundError,
    CommandTimeoutError,
    run_command,
)


def test_default_timeout_is_a_finite_positive_number():
    assert DEFAULT_COMMAND_TIMEOUT_SECONDS is not None
    assert DEFAULT_COMMAND_TIMEOUT_SECONDS > 0


def test_run_command_passes_the_default_timeout_to_subprocess_run(monkeypatch: pytest.MonkeyPatch):
    captured = {}

    def fake_run(command, **kwargs):
        captured.update(kwargs)
        return subprocess.CompletedProcess(command, 0, "ok", "")

    monkeypatch.setattr("bloggen.utils.subprocesses.subprocess.run", fake_run)

    run_command(["echo", "hi"])

    assert captured["timeout"] == DEFAULT_COMMAND_TIMEOUT_SECONDS


def test_run_command_passes_an_overridden_timeout(monkeypatch: pytest.MonkeyPatch):
    captured = {}

    def fake_run(command, **kwargs):
        captured.update(kwargs)
        return subprocess.CompletedProcess(command, 0, "ok", "")

    monkeypatch.setattr("bloggen.utils.subprocesses.subprocess.run", fake_run)

    run_command(["echo", "hi"], timeout=12.5)

    assert captured["timeout"] == 12.5


def test_run_command_can_explicitly_disable_the_timeout(monkeypatch: pytest.MonkeyPatch):
    captured = {}

    def fake_run(command, **kwargs):
        captured.update(kwargs)
        return subprocess.CompletedProcess(command, 0, "ok", "")

    monkeypatch.setattr("bloggen.utils.subprocesses.subprocess.run", fake_run)

    run_command(["echo", "hi"], timeout=None)

    assert captured["timeout"] is None


@pytest.mark.parametrize("bad_timeout", [0, -1, -0.5])
def test_run_command_rejects_non_positive_timeout(bad_timeout):
    with pytest.raises(ValueError):
        run_command(["echo", "hi"], timeout=bad_timeout)


def test_run_command_converts_timeout_expired_into_command_timeout_error(
    monkeypatch: pytest.MonkeyPatch,
):
    def fake_run(command, **kwargs):
        raise subprocess.TimeoutExpired(cmd=command, timeout=kwargs["timeout"])

    monkeypatch.setattr("bloggen.utils.subprocesses.subprocess.run", fake_run)

    with pytest.raises(CommandTimeoutError, match=r"pandoc.*délai"):
        run_command(["pandoc", "--to=tei"], timeout=5)


def test_timeout_expired_message_includes_partial_stderr_when_available(
    monkeypatch: pytest.MonkeyPatch,
):
    def fake_run(command, **kwargs):
        raise subprocess.TimeoutExpired(
            cmd=command, timeout=kwargs["timeout"], output="partial stdout", stderr="partial stderr"
        )

    monkeypatch.setattr("bloggen.utils.subprocesses.subprocess.run", fake_run)

    with pytest.raises(CommandTimeoutError, match="partial stderr"):
        run_command(["pandoc"], timeout=5)


def test_run_command_reports_missing_executable(monkeypatch: pytest.MonkeyPatch):
    def fake_run(*_args, **_kwargs):
        raise FileNotFoundError("pandoc")

    monkeypatch.setattr("bloggen.utils.subprocesses.subprocess.run", fake_run)

    with pytest.raises(CommandNotFoundError):
        run_command(["pandoc"])


def test_run_command_check_false_returns_a_failed_result_without_raising(
    monkeypatch: pytest.MonkeyPatch,
):
    def fake_run(command, **_kwargs):
        return subprocess.CompletedProcess(command, 1, "out", "boom")

    monkeypatch.setattr("bloggen.utils.subprocesses.subprocess.run", fake_run)

    result = run_command(["pandoc"], check=False)

    assert result.success is False
    assert result.returncode == 1
    assert result.stdout == "out"
    assert result.stderr == "boom"


def test_run_command_check_true_raises_on_nonzero_exit(monkeypatch: pytest.MonkeyPatch):
    def fake_run(command, **_kwargs):
        return subprocess.CompletedProcess(command, 1, "out", "boom")

    monkeypatch.setattr("bloggen.utils.subprocesses.subprocess.run", fake_run)

    with pytest.raises(CommandExecutionError, match="boom"):
        run_command(["pandoc"], check=True)


def test_run_command_captures_stdout_and_stderr_on_success(monkeypatch: pytest.MonkeyPatch):
    def fake_run(command, **_kwargs):
        return subprocess.CompletedProcess(command, 0, "hello", "")

    monkeypatch.setattr("bloggen.utils.subprocesses.subprocess.run", fake_run)

    result = run_command(["echo", "hello"])

    assert result.success is True
    assert result.stdout == "hello"
    assert result.stderr == ""
