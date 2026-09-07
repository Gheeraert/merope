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
    # Remote files under config.remote_dir that no longer correspond to
    # any file in this build — only populated when detect_stale_files is
    # requested, and only once the whole transfer succeeded (an
    # incomplete "current" set is not a trustworthy basis for deciding
    # what's obsolete). Never deleted automatically here — see
    # delete_remote_files, called separately once the caller has shown
    # this list to the user and gotten explicit confirmation.
    stale_remote: list[str] = field(default_factory=list)
    # Set when detect_stale_files was requested but listing the remote
    # directory failed (e.g. the server doesn't support MLSD) — the
    # publish itself still succeeded, this only means "couldn't check".
    stale_remote_error: str | None = None

    @property
    def ok(self) -> bool:
        return not self.failed


def publish_directory(
    local_dir: Path,
    config: FtpConfig,
    *,
    progress: ProgressCallback | None = None,
    should_cancel: Callable[[], bool] | None = None,
    detect_stale_files: bool = False,
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

        result = PublishResult(total=total, transferred=transferred, failed=failed)
        if detect_stale_files and result.ok:
            try:
                ftp.cwd(publish_root)
                remote_files = _list_remote_files(ftp, publish_root)
                local_files = set(transferred)
                result.stale_remote = sorted(name for name in remote_files if name not in local_files)
            except ftplib.all_errors as exc:
                result.stale_remote_error = str(exc)
        return result
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


def _cwd_strict(ftp: ftplib.FTP, path: str) -> None:
    """Like ``_ensure_and_cwd``, but never creates a missing directory —
    used when deleting, where a directory that no longer exists just
    means there is nothing left there to delete, not something to
    recreate."""
    path = path.strip()
    if not path or path == ".":
        return
    if path.startswith("/"):
        ftp.cwd("/")
    for part in (segment for segment in path.split("/") if segment):
        ftp.cwd(part)


def _list_remote_files(ftp: ftplib.FTP, root: str) -> list[str]:
    """Recursively lists every file under ``root`` (an absolute path,
    already the current directory), as POSIX-style paths relative to it.

    Requires MLSD (RFC 3659) support on the server — raises whatever
    ``ftplib`` error that command produces if it's missing, letting the
    caller treat "can't tell what's stale" as distinct from "nothing is
    stale".  Navigates by absolute path at every step (rather than
    ``cwd("..")``) so a server's exact handling of ".." never matters.
    """
    files: list[str] = []

    def walk(dir_path: str, prefix: str) -> None:
        ftp.cwd(dir_path)
        for name, facts in ftp.mlsd():
            if name in (".", ".."):
                continue
            entry_type = facts.get("type", "")
            child_path = f"{dir_path.rstrip('/')}/{name}"
            if entry_type == "dir":
                walk(child_path, f"{prefix}{name}/")
            elif entry_type == "file":
                files.append(f"{prefix}{name}")

    walk(root, "")
    return files


@dataclass(slots=True)
class DeleteResult:
    """Outcome of :func:`delete_remote_files` — same shape/rationale as
    :class:`PublishResult`: every path is attempted even after an earlier
    failure."""

    deleted: list[str] = field(default_factory=list)
    failed: list[FailedTransfer] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.failed


def delete_remote_files(
    config: FtpConfig,
    relative_paths: list[str],
    *,
    progress: ProgressCallback | None = None,
) -> DeleteResult:
    """Deletes the given ``config.remote_dir``-relative files from the
    server. Meant to run only after the caller has shown these exact
    paths (typically ``PublishResult.stale_remote``) to the user and
    gotten explicit confirmation — this function itself deletes
    unconditionally, no confirmation of its own.
    """
    if not relative_paths:
        return DeleteResult()

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
        total = len(relative_paths)
        deleted: list[str] = []
        failed: list[FailedTransfer] = []

        for index, relative in enumerate(sorted(relative_paths), start=1):
            subdir, _, filename = relative.rpartition("/")
            try:
                ftp.cwd(publish_root)
                _cwd_strict(ftp, subdir)
                ftp.delete(filename)
                deleted.append(relative)
            except ftplib.all_errors as exc:
                failed.append(FailedTransfer(relative, str(exc)))

            if progress is not None:
                progress(index, total, relative)

        return DeleteResult(deleted=deleted, failed=failed)
    finally:
        try:
            ftp.quit()
        except Exception:
            try:
                ftp.close()
            except Exception:
                pass
