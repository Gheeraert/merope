"""Publishes a built site directory to a remote server over FTP or FTPS."""

from __future__ import annotations

import ftplib
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from bloggen.config.models import FtpConfig

ProgressCallback = Callable[[int, int, str], None]
"""Called after each file transfer attempt with (files_done, files_total, relative_path)."""


class FtpPublishError(RuntimeError):
    """Raised when the connection to the FTP server fails, or the transfer
    is cancelled — either way, nothing (or an unknown amount) was
    transferred. A single file's own transfer error, once connected, does
    NOT raise this: see :class:`PublishResult`.
    """


@dataclass(slots=True)
class FailedTransfer:
    relative_path: str
    message: str


@dataclass(slots=True)
class PublishResult:
    """Outcome of a publish run that did establish a connection.

    Every file is attempted even if an earlier one failed — a bad
    permission or a transient network blip on one file must not silently
    abort (or silently "succeed" short of) publishing the rest of the
    site. ``failed`` lists exactly which files didn't make it and why, so
    the caller can tell a full success from a partial one instead of
    guessing from a file count alone.
    """

    total: int
    transferred: list[str] = field(default_factory=list)
    failed: list[FailedTransfer] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.failed


def publish_directory(
    local_dir: Path,
    config: FtpConfig,
    *,
    progress: ProgressCallback | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> PublishResult:
    """Uploads every file under ``local_dir`` to ``config.remote_dir`` on the
    configured FTP(S) server, preserving the relative directory structure and
    creating remote subdirectories as needed.

    Connecting/logging in/creating the remote root still raises
    ``FtpPublishError`` immediately (nothing can proceed without it), as
    does an explicit cancellation. Once connected, an individual file's
    transfer error is recorded in the returned :class:`PublishResult`
    instead of aborting the run — every other file is still attempted. If
    the connection itself appears to have died (checked with a NOOP right
    after a failure), the remaining files are recorded as failed without
    each one paying its own timeout.
    """
    if not local_dir.is_dir():
        raise FtpPublishError(f"Le dossier à publier est introuvable : {local_dir}")

    files = sorted(p for p in local_dir.rglob("*") if p.is_file())
    total = len(files)
    if total == 0:
        raise FtpPublishError("Le dossier à publier ne contient aucun fichier à transférer.")

    ftp_cls = ftplib.FTP_TLS if config.use_tls else ftplib.FTP
    ftp = ftp_cls(timeout=30)
    try:
        try:
            ftp.connect(config.host, config.port or 21)
            ftp.login(config.username, config.password)
            if config.use_tls:
                ftp.prot_p()
            ftp.set_pasv(config.passive_mode)
            _ensure_and_cwd(ftp, config.remote_dir)
        except ftplib.all_errors as exc:
            raise FtpPublishError(f"Connexion FTP impossible : {exc}") from exc

        publish_root = ftp.pwd()
        transferred: list[str] = []
        failed: list[FailedTransfer] = []
        connection_lost = False

        last_subdir: str | None = None
        for index, file_path in enumerate(files, start=1):
            if should_cancel is not None and should_cancel():
                raise FtpPublishError("Transfert annulé.")

            relative = file_path.relative_to(local_dir).as_posix()

            if connection_lost:
                failed.append(FailedTransfer(relative, "Connexion perdue : fichier non transféré."))
            else:
                subdir, _, filename = relative.rpartition("/")
                try:
                    if subdir != last_subdir:
                        ftp.cwd(publish_root)
                        _ensure_and_cwd(ftp, subdir)
                        last_subdir = subdir

                    with file_path.open("rb") as handle:
                        ftp.storbinary(f"STOR {filename}", handle)
                    transferred.append(relative)
                except ftplib.all_errors as exc:
                    failed.append(FailedTransfer(relative, str(exc)))
                    last_subdir = None
                    if not _connection_alive(ftp):
                        connection_lost = True

            if progress is not None:
                progress(index, total, relative)

        return PublishResult(total=total, transferred=transferred, failed=failed)
    finally:
        try:
            ftp.quit()
        except Exception:
            try:
                ftp.close()
            except Exception:
                pass


def _connection_alive(ftp: ftplib.FTP) -> bool:
    try:
        ftp.voidcmd("NOOP")
        return True
    except ftplib.all_errors:
        return False


def _ensure_and_cwd(ftp: ftplib.FTP, path: str) -> None:
    """Changes into ``path`` on the server, creating any missing directory
    segment along the way. An absolute path (leading "/") is resolved from
    the server root; otherwise it is resolved relative to the current
    directory."""
    path = path.strip()
    if not path or path == ".":
        return
    if path.startswith("/"):
        ftp.cwd("/")
    for part in (segment for segment in path.split("/") if segment):
        try:
            ftp.cwd(part)
        except ftplib.error_perm:
            ftp.mkd(part)
            ftp.cwd(part)
