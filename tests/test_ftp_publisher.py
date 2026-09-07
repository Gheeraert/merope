from __future__ import annotations

import ftplib
from pathlib import Path

import pytest

from bloggen.config.models import FtpConfig
from bloggen.publish import ftp_publisher as module
from bloggen.publish.ftp_publisher import FtpPublishError, delete_remote_files, publish_directory


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
        self.supports_mlsd = True
        self.delete_fail_files: set[str] = set()

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

    def delete(self, filename: str) -> None:
        key = self._resolve(filename)
        if key in self.delete_fail_files:
            raise ftplib.error_perm("550 Permission refusée")
        if key not in self.stored:
            raise ftplib.error_perm(f"550 {filename}: No such file")
        self.stored.remove(key)

    def mlsd(self, path: str = ""):
        if not self.supports_mlsd:
            raise ftplib.error_perm("502 Command not implemented")
        base = self.cwd_path if not path else (path if path.startswith("/") else self._resolve(path))
        seen_dirs: set[str] = set()
        for d in self.dirs:
            if d == base:
                continue
            parent = d.rsplit("/", 1)[0] or "/"
            if parent != base:
                continue
            name = d.rsplit("/", 1)[1]
            if name and name not in seen_dirs:
                seen_dirs.add(name)
                yield name, {"type": "dir"}
        for f in self.stored:
            parent = f.rsplit("/", 1)[0] or "/"
            if parent == base:
                yield f.rsplit("/", 1)[1], {"type": "file"}


def _make_ftp_factory():
    created: list[FakeFTP] = []

    def factory(*, timeout=None):
        instance = FakeFTP(timeout=timeout)
        created.append(instance)
        return instance

    factory.created = created
    return factory


def _seed_remote(instance: FakeFTP, absolute_paths: list[str]) -> None:
    """Pre-populates a FakeFTP with files (and their parent directories)
    already "on the server", to simulate leftovers from a previous
    publish that the current local build no longer contains."""
    for path in absolute_paths:
        instance.stored.append(path)
        parts = [p for p in path.split("/") if p][:-1]
        prefix = ""
        for part in parts:
            prefix = f"{prefix}/{part}"
            instance.dirs.add(prefix)


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


# -- stale remote file detection / deletion ----------------------------------


def test_detect_stale_files_finds_remote_leftovers_not_in_the_local_build(tmp_path, monkeypatch):
    factory = _make_ftp_factory()

    def factory_with_leftovers(*, timeout=None):
        instance = FakeFTP(timeout=timeout)
        _seed_remote(instance, ["/www/old-post/index.html", "/www/billets/premier/stray.jpg"])
        factory.created.append(instance)
        return instance

    monkeypatch.setattr(module.ftplib, "FTP", factory_with_leftovers)

    site = _make_site(tmp_path)
    result = publish_directory(site, _config(), detect_stale_files=True)

    assert result.ok is True
    assert result.stale_remote_error is None
    assert sorted(result.stale_remote) == ["billets/premier/stray.jpg", "old-post/index.html"]


def test_detect_stale_files_is_empty_when_remote_matches_local(tmp_path, monkeypatch):
    factory = _make_ftp_factory()
    monkeypatch.setattr(module.ftplib, "FTP", factory)

    site = _make_site(tmp_path)
    result = publish_directory(site, _config(), detect_stale_files=True)

    assert result.stale_remote == []
    assert result.stale_remote_error is None


def test_detect_stale_files_is_skipped_by_default(tmp_path, monkeypatch):
    factory = _make_ftp_factory()

    def factory_with_leftovers(*, timeout=None):
        instance = FakeFTP(timeout=timeout)
        _seed_remote(instance, ["/www/old-post/index.html"])
        factory.created.append(instance)
        return instance

    monkeypatch.setattr(module.ftplib, "FTP", factory_with_leftovers)

    site = _make_site(tmp_path)
    result = publish_directory(site, _config())  # detect_stale_files defaults to False

    assert result.stale_remote == []


def test_detect_stale_files_is_skipped_when_the_publish_itself_failed(tmp_path, monkeypatch):
    factory_calls: list[FakeFTP] = []

    def factory(*, timeout=None):
        instance = FakeFTP(timeout=timeout)
        instance.fail_files.add("/www/index.html")
        _seed_remote(instance, ["/www/old-post/index.html"])
        factory_calls.append(instance)
        return instance

    monkeypatch.setattr(module.ftplib, "FTP", factory)

    site = _make_site(tmp_path)
    result = publish_directory(site, _config(), detect_stale_files=True)

    assert result.ok is False
    # An incomplete transfer is not a trustworthy basis for "what's stale".
    assert result.stale_remote == []
    assert result.stale_remote_error is None


def test_detect_stale_files_reports_when_the_server_lacks_mlsd_support(tmp_path, monkeypatch):
    factory = _make_ftp_factory()

    def factory_no_mlsd(*, timeout=None):
        instance = FakeFTP(timeout=timeout)
        instance.supports_mlsd = False
        factory.created.append(instance)
        return instance

    monkeypatch.setattr(module.ftplib, "FTP", factory_no_mlsd)

    site = _make_site(tmp_path)
    result = publish_directory(site, _config(), detect_stale_files=True)

    assert result.ok is True  # the publish itself still succeeded
    assert result.stale_remote == []
    assert result.stale_remote_error is not None


def test_delete_remote_files_removes_the_given_paths(tmp_path, monkeypatch):
    factory = _make_ftp_factory()

    def factory_with_leftovers(*, timeout=None):
        instance = FakeFTP(timeout=timeout)
        _seed_remote(instance, ["/www/old-post/index.html", "/www/stray.jpg"])
        factory.created.append(instance)
        return instance

    monkeypatch.setattr(module.ftplib, "FTP", factory_with_leftovers)

    result = delete_remote_files(_config(), ["old-post/index.html", "stray.jpg"])

    assert result.ok is True
    assert sorted(result.deleted) == ["old-post/index.html", "stray.jpg"]
    assert factory.created[0].stored == []


def test_delete_remote_files_reports_a_failure_without_aborting_the_rest(tmp_path, monkeypatch):
    factory = _make_ftp_factory()

    def factory_with_leftovers(*, timeout=None):
        instance = FakeFTP(timeout=timeout)
        _seed_remote(instance, ["/www/old-post/index.html", "/www/stray.jpg"])
        instance.delete_fail_files.add("/www/stray.jpg")
        factory.created.append(instance)
        return instance

    monkeypatch.setattr(module.ftplib, "FTP", factory_with_leftovers)

    result = delete_remote_files(_config(), ["old-post/index.html", "stray.jpg"])

    assert result.ok is False
    assert result.deleted == ["old-post/index.html"]
    assert len(result.failed) == 1
    assert result.failed[0].relative_path == "stray.jpg"


def test_delete_remote_files_with_empty_list_does_not_connect(tmp_path, monkeypatch):
    factory = _make_ftp_factory()
    monkeypatch.setattr(module.ftplib, "FTP", factory)

    result = delete_remote_files(_config(), [])

    assert result == module.DeleteResult()
    assert factory.created == []


def test_delete_remote_files_raises_on_connection_failure(monkeypatch):
    class FailingLoginFTP(FakeFTP):
        def login(self, user, password):
            raise ftplib.error_perm("530 Login incorrect")

    monkeypatch.setattr(module.ftplib, "FTP", FailingLoginFTP)

    with pytest.raises(FtpPublishError, match="Connexion FTP impossible"):
        delete_remote_files(_config(), ["stray.jpg"])
