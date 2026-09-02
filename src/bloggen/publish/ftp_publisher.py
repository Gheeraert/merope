"""Publishes a built site directory to a remote server over FTP or FTPS."""

from __future__ import annotations

import ftplib
from collections.abc import Callable
from pathlib import Path

from bloggen.config.models import FtpConfig

ProgressCallback = Callable[[int, int, str], None]
"""Called after each file transfer with (files_done, files_total, relative_path)."""


class FtpPublishError(RuntimeError):
    """Raised when the connection or the transfer to the FTP server fails."""


def publish_directory(
    local_dir: Path,
    config: FtpConfig,
    *,
    progress: ProgressCallback | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> int:
    """Uploads every file under ``local_dir`` to ``config.remote_dir`` on the
    configured FTP(S) server, preserving the relative directory structure and
    creating remote subdirectories as needed. Returns the number of files
    transferred.
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
        ftp.connect(config.host, config.port or 21)
        ftp.login(config.username, config.password)
        if config.use_tls:
            ftp.prot_p()
        ftp.set_pasv(config.passive_mode)

        _ensure_and_cwd(ftp, config.remote_dir)
        publish_root = ftp.pwd()

        last_subdir: str | None = None
        for index, file_path in enumerate(files, start=1):
            if should_cancel is not None and should_cancel():
                raise FtpPublishError("Transfert annulé.")

            relative = file_path.relative_to(local_dir).as_posix()
            subdir, _, filename = relative.rpartition("/")
            if subdir != last_subdir:
                ftp.cwd(publish_root)
                _ensure_and_cwd(ftp, subdir)
                last_subdir = subdir

            with file_path.open("rb") as handle:
                ftp.storbinary(f"STOR {filename}", handle)

            if progress is not None:
                progress(index, total, relative)

        return total
    except ftplib.all_errors as exc:
        raise FtpPublishError(f"Erreur FTP : {exc}") from exc
    finally:
        try:
            ftp.quit()
        except Exception:
            try:
                ftp.close()
            except Exception:
                pass


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
