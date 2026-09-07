from __future__ import annotations

import ftplib
from pathlib import Path

import pytest

from bloggen.config.models import FtpConfig
from bloggen.publish import ftp_publisher as module
from bloggen.publish.ftp_publisher import FtpPublishError, publish_directory


class FakeFTP:
    """Minimal in-memory stand-in for ftplib.FTP/FTP_TLS, just enough to
    drive publish_directory(): a virtual directory tree, cwd/mkd/pwd, and
    storbinary recording what got "uploaded" where.
    """

    def __init__(self, *, timeout=None) -> None:
        self.timeout = timeout
        self.dirs: set[str] = {"/"}
        self.cwd_path = "/"
        self.stored: list[str] = []
        self.fail_files: set[str] = set()
        self.die_after: str | None = None
        self._alive = True

    # -- connection lifecycle -------------------------------------------------
    def connect(self, host: str, port: int) -> None:
        pass

    def login(self, user: str, password: str) -> None:
        pass

    def prot_p(self) -> None:
        pass

    def set_pasv(self, flag: bool) -> None:
        pass

    def quit(self) -> None:
        pass

    def close(self) -> None:
        pass

    # -- filesystem-ish behavior -----------------------------------------------
    def _resolve(self, segment: str) -> str:
        return f"/{segment}" if self.cwd_path == "/" else f"{self.cwd_path}/{segment}"

    def cwd(self, path: str) -> None:
        if path == "/":
            self.cwd_path = "/"
            return
        resolved = path if path.startswith("/") else self._resolve(path)
        if resolved not in self.dirs:
            raise ftplib.error_perm(f"550 {path}: No such directory")
        self.cwd_path = resolved

    def mkd(self, path: str) -> str:
        resolved = self._resolve(path)
        self.dirs.add(resolved)
        return resolved

    def pwd(self) -> str:
        return self.cwd_path

    def storbinary(self, cmd: str, handle) -> None:
        if not self._alive:
            raise OSError("connexion perdue")
        filename = cmd.split(" ", 1)[1]
        key = self._resolve(filename)
        if key in self.fail_files:
            raise ftplib.error_perm("550 Permission refusée")
        handle.read()
        self.stored.append(key)
        if self.die_after == key:
            self._alive = False

    def voidcmd(self, _cmd: str) -> str:
        if not self._alive:
            raise OSError("connexion perdue")
        return "200 OK"


def _make_ftp_factory():
    created: list[FakeFTP] = []

    def factory(*, timeout=None):
        instance = FakeFTP(timeout=timeout)
        created.append(instance)
        return instance

    factory.created = created
    return factory


def _config(**overrides) -> FtpConfig:
    base = dict(
        host="ftp.example.org",
        port=21,
        username="user",
        password="secret",
        remote_dir="/www",
        use_tls=False,
        passive_mode=True,
        site_url="",
    )
    base.update(overrides)
    return FtpConfig(**base)


def _make_site(tmp_path: Path) -> Path:
    site = tmp_path / "site"
    (site / "billets" / "premier").mkdir(parents=True)
    (site / "index.html").write_text("accueil", encoding="utf-8")
    (site / "billets" / "premier" / "index.html").write_text("billet", encoding="utf-8")
    return site


def test_publish_uploads_every_file_and_creates_nested_remote_dirs(tmp_path, monkeypatch):
    factory = _make_ftp_factory()
    monkeypatch.setattr(module.ftplib, "FTP", factory)

    site = _make_site(tmp_path)
    result = publish_directory(site, _config())

    ftp = factory.created[0]
    assert result.ok is True
    assert result.total == 2
    assert sorted(result.transferred) == ["billets/premier/index.html", "index.html"]
    assert result.failed == []
    assert "/www" in ftp.dirs
    assert "/www/billets" in ftp.dirs
    assert "/www/billets/premier" in ftp.dirs
    assert sorted(ftp.stored) == ["/www/billets/premier/index.html", "/www/index.html"]


def test_publish_continues_past_a_single_file_failure_and_reports_it(tmp_path, monkeypatch):
    factory = _make_ftp_factory()
    monkeypatch.setattr(module.ftplib, "FTP", factory)

    site = _make_site(tmp_path)
    # The one file that will be rejected by the (fake) server, identified by
    # its eventual remote path.
    real_index_path = "/www/index.html"

    def factory_with_failure(*, timeout=None):
        instance = FakeFTP(timeout=timeout)
        instance.fail_files.add(real_index_path)
        factory.created.append(instance)
        return instance

    monkeypatch.setattr(module.ftplib, "FTP", factory_with_failure)

    result = publish_directory(site, _config())

    assert result.ok is False
    assert result.total == 2
    assert result.transferred == ["billets/premier/index.html"]
    assert len(result.failed) == 1
    assert result.failed[0].relative_path == "index.html"
    assert "Permission" in result.failed[0].message


def test_publish_marks_remaining_files_failed_once_connection_is_lost(tmp_path, monkeypatch):
    site = tmp_path / "site"
    site.mkdir()
    # Alphabetical order matters: publish_directory sorts files, so "a.html"
    # is attempted (and kills the connection) before "b.html"/"c.html".
    (site / "a.html").write_text("a", encoding="utf-8")
    (site / "b.html").write_text("b", encoding="utf-8")
    (site / "c.html").write_text("c", encoding="utf-8")

    def factory(*, timeout=None):
        instance = FakeFTP(timeout=timeout)
        instance.die_after = "/www/a.html"
        return instance

    monkeypatch.setattr(module.ftplib, "FTP", factory)

    result = publish_directory(site, _config())

    assert result.ok is False
    assert result.transferred == ["a.html"]
    failed_paths = {item.relative_path for item in result.failed}
    assert failed_paths == {"b.html", "c.html"}
    # The two files after the connection died must not each pay their own
    # network attempt/timeout — they're recorded straight away.
    assert any("non transféré" in item.message for item in result.failed)


def test_publish_raises_on_connection_failure(tmp_path, monkeypatch):
    class FailingLoginFTP(FakeFTP):
        def login(self, user, password):
            raise ftplib.error_perm("530 Login incorrect")

    monkeypatch.setattr(module.ftplib, "FTP", FailingLoginFTP)

    site = _make_site(tmp_path)
    with pytest.raises(FtpPublishError, match="Connexion FTP impossible"):
        publish_directory(site, _config())


def test_publish_raises_on_cancellation(tmp_path, monkeypatch):
    factory = _make_ftp_factory()
    monkeypatch.setattr(module.ftplib, "FTP", factory)

    site = _make_site(tmp_path)
    with pytest.raises(FtpPublishError, match="annulé"):
        publish_directory(site, _config(), should_cancel=lambda: True)

    assert factory.created[0].stored == []


def test_publish_raises_when_local_dir_is_missing(tmp_path):
    with pytest.raises(FtpPublishError, match="introuvable"):
        publish_directory(tmp_path / "does-not-exist", _config())


def test_publish_raises_when_local_dir_is_empty(tmp_path):
    empty = tmp_path / "site"
    empty.mkdir()
    with pytest.raises(FtpPublishError, match="aucun fichier"):
        publish_directory(empty, _config())
