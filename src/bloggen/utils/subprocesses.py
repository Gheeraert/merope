"""Small subprocess wrapper for predictable command execution."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess
from typing import Mapping

# Every current production caller of run_command() (only Pandoc, via
# bloggen.tei.pandoc_converter) is a one-shot, bounded conversion — nothing
# in Mérope uses this wrapper for a legitimately long-running/background
# process. 120s is generous for a single document's Pandoc conversion while
# still turning a hung/misbehaving external command into a bounded,
# explicit failure instead of blocking the build indefinitely.
DEFAULT_COMMAND_TIMEOUT_SECONDS: float = 120.0


@dataclass(slots=True)
class CommandResult:
    command: list[str]
    returncode: int
    stdout: str
    stderr: str

    @property
    def success(self) -> bool:
        return self.returncode == 0


class CommandError(RuntimeError):
    """Base class for subprocess execution errors."""


class CommandNotFoundError(CommandError):
    """Raised when the executable cannot be found."""


class CommandExecutionError(CommandError):
    """Raised when a command exits with a non-zero return code and check=True."""


class CommandTimeoutError(CommandError):
    """Raised when a command does not finish within its allotted timeout.

    Replaces a raw ``subprocess.TimeoutExpired`` — callers should never see
    that exception directly, only this one.
    """


def run_command(
    command: list[str],
    *,
    cwd: str | Path | None = None,
    env: Mapping[str, str] | None = None,
    check: bool = False,
    timeout: float | None = DEFAULT_COMMAND_TIMEOUT_SECONDS,
) -> CommandResult:
    """Run ``command`` and capture its output, bounded by ``timeout`` seconds.

    ``timeout=None`` explicitly disables the bound — no current production
    caller does this; it exists for a future caller with a documented
    reason to run something unbounded. Any other non-positive value is
    rejected outright rather than silently reinterpreted (e.g. as "no
    timeout" or "return immediately").
    """
    if timeout is not None and timeout <= 0:
        raise ValueError(f"timeout doit être strictement positif ou None, reçu: {timeout!r}")

    try:
        completed = subprocess.run(
            command,
            cwd=str(cwd) if cwd is not None else None,
            env=dict(env) if env is not None else None,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        executable = command[0] if command else "<empty>"
        raise CommandNotFoundError(f"Commande introuvable: {executable}") from exc
    except subprocess.TimeoutExpired as exc:
        executable = command[0] if command else "<empty>"
        # subprocess.run() has already killed the process by the time this
        # exception reaches us — nothing is left running.
        partial_stderr = exc.stderr.strip() if isinstance(exc.stderr, str) and exc.stderr.strip() else ""
        detail = f"\n{partial_stderr}" if partial_stderr else ""
        raise CommandTimeoutError(
            f"La commande « {executable} » a dépassé le délai maximal de {timeout} s.{detail}"
        ) from exc

    result = CommandResult(
        command=list(command),
        returncode=completed.returncode,
        stdout=completed.stdout or "",
        stderr=completed.stderr or "",
    )

    if check and not result.success:
        stderr = result.stderr.strip() or "Aucun détail stderr."
        raise CommandExecutionError(
            f"La commande a échoué (code {result.returncode}): {' '.join(command)}\n{stderr}"
        )
    return result
