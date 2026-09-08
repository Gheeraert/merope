"""Publishes a built site directory to a remote server over FTP or FTPS."""

from __future__ import annotations

import ftplib
import io
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from bloggen.config.models import FtpConfig

ProgressCallback = Callable[[int, int, str], None]
"""Called after each file transfer attempt with (files_done, files_total, relative_path)."""

# Written to the remote publish root after every fully successful publish:
# the exact set of relative paths MEROPE itself deployed. The next publish
# reads it back as the baseline for "what's stale" — anything MEROPE
# previously deployed but no longer in the current build. This is
# deliberately never a directory listing of the whole remote folder: a
# remote_dir shared with another application (or files a human FTP'd in by
# hand) must never be treated as MEROPE's to delete just because they
# aren't part of this build (see the external audit).
_MANIFEST_FILENAME = ".merope-manifest.json"


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
    # Files listed in MEROPE's own manifest from the previous publish
    # that are no longer part of this build — only populated when
    # detect_stale_files is requested, only once the whole transfer
    # succeeded (an incomplete "current" set is not a trustworthy basis
    # for deciding what's obsolete), AND only when a previous manifest
    # was actually found (see stale_remote_manifest_missing). Deliberately
    # restricted to files MEROPE itself previously deployed — never "any
    # remote file not in this build", which would also catch an unrelated
    # application's files sharing the same remote_dir. Never deleted
    # automatically here — see delete_remote_files, called separately
    # once the caller has shown this list to the user and gotten explicit
    # confirmation.
    stale_remote: list[str] = field(default_factory=list)
    # True when detect_stale_files was requested and the transfer
    # succeeded, but no previous MEROPE manifest could be found/read on
    # the server (first publish with this feature, or a remote_dir never
    # published to by MEROPE before) — there is then no trustworthy
    # baseline, so stale_remote is deliberately left empty rather than
    # falling back to a directory listing. A fresh manifest is still
    # written from this publish, so the next one has a baseline.
    stale_remote_manifest_missing: bool = False
    # Set when detect_stale_files was requested but the updated manifest
    # could not be written back to the server after a successful publish
    # (connection/permission issue) — the publish itself still succeeded,
    # this only means the next publish won't have an up-to-date baseline.
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
            ftp.cwd(publish_root)
            previous_manifest = _download_manifest(ftp)
            if previous_manifest is None:
                result.stale_remote_manifest_missing = True
            else:
                result.stale_remote = sorted(previous_manifest - set(transferred))
            try:
                ftp.cwd(publish_root)
                _upload_manifest(ftp, transferred)
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


def _is_safe_manifest_path(path: str) -> bool:
    """True when ``path`` is safe to treat as a ``remote_dir``-relative
    path: not absolute, no "."/".." segment (which ``_cwd_strict`` would
    otherwise walk as a real directory change — an FTP server resolves
    ".." the same way a filesystem does), no backslash (a Windows-style
    separator an FTP server would treat as a literal filename character,
    letting a segment like "..\\.." hide from the "/"-only checks above),
    no NUL byte, and no empty segment (double slash)."""
    if not path or path.startswith("/") or path.endswith("/"):
        return False
    if "\\" in path or "\x00" in path:
        return False
    return all(segment not in ("", ".", "..") for segment in path.split("/"))


def _download_manifest(ftp: ftplib.FTP) -> set[str] | None:
    """Returns the set of relative paths MEROPE deployed on the previous
    successful publish, read back from the manifest it wrote then — or
    None if there is no trustworthy baseline (no manifest file, a read
    error, content that doesn't parse as the expected JSON list, or a
    list containing even one path that isn't safely remote_dir-relative
    — see _is_safe_manifest_path — since delete_remote_files acts on
    this set, unconfirmed per-item, once the caller has shown the user
    the resulting stale-file list and gotten one blanket confirmation).

    Deliberately treats every failure as "unknown baseline" rather than
    raising: the caller must never fall back to guessing staleness from
    a full directory listing (see PublishResult.stale_remote_manifest_missing).
    """
    buffer = bytearray()
    try:
        ftp.retrbinary(f"RETR {_MANIFEST_FILENAME}", buffer.extend)
    except ftplib.all_errors:
        return None
    try:
        data = json.loads(bytes(buffer).decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None
    if not isinstance(data, list):
        return None
    paths = [str(item) for item in data]
    if not all(_is_safe_manifest_path(path) for path in paths):
        return None
    return set(paths)


def _upload_manifest(ftp: ftplib.FTP, relative_paths: list[str]) -> None:
    """Writes the manifest that the next publish will use as its
    "previously deployed by MEROPE" baseline."""
    payload = json.dumps(sorted(relative_paths), ensure_ascii=False).encode("utf-8")
    ftp.storbinary(f"STOR {_MANIFEST_FILENAME}", io.BytesIO(payload))


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

    A path that isn't safely remote_dir-relative (see
    _is_safe_manifest_path — absolute, "..", a backslash...) is refused
    without ever reaching the server, recorded as a failure rather than
    silently skipped: _download_manifest already filters these out of
    its own trusted baseline, so reaching this function's caller with
    such a path at all means it came from somewhere else (a hand-edited
    ``relative_paths`` argument, a future caller that doesn't go through
    the manifest) and deserves to be visible, not quietly dropped.
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
            if not _is_safe_manifest_path(relative):
                failed.append(FailedTransfer(relative, "Chemin non sûr : suppression refusée."))
                if progress is not None:
                    progress(index, total, relative)
                continue

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
