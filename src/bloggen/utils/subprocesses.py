"""Small subprocess wrapper for predictable command execution."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess
from typing import Mapping


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


def run_command(
    command: list[str],
    *,
    cwd: str | Path | None = None,
    env: Mapping[str, str] | None = None,
    check: bool = False,
) -> CommandResult:
    try:
        completed = subprocess.run(
            command,
            cwd=str(cwd) if cwd is not None else None,
            env=dict(env) if env is not None else None,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as exc:
        executable = command[0] if command else "<empty>"
        raise CommandNotFoundError(f"Commande introuvable: {executable}") from exc

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
