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
        self.file_contents: dict[str, bytes] = {}
        self.fail_files: set[str] = set()
        self.die_after: str | None = None
        self._alive = True
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
        content = handle.read()
        if key not in self.stored:
            self.stored.append(key)
        self.file_contents[key] = content
        if self.die_after == key:
            self._alive = False

    def retrbinary(self, cmd: str, callback) -> None:
        filename = cmd.split(" ", 1)[1]
        key = self._resolve(filename)
        if key not in self.file_contents:
            raise ftplib.error_perm(f"550 {filename}: No such file")
        callback(self.file_contents[key])

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
        self.file_contents.pop(key, None)


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


def _seed_manifest(instance: FakeFTP, publish_root: str, relative_paths: list[str]) -> None:
    """Simulates a MEROPE manifest left over from a previous successful
    publish to this same remote_dir — the baseline stale-file detection
    reads back and diffs against the current build."""
    import json as _json

    key = f"{publish_root.rstrip('/')}/{module._MANIFEST_FILENAME}"
    instance.file_contents[key] = _json.dumps(relative_paths).encode("utf-8")


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
#
# Detection is manifest-based: a small JSON file MEROPE itself writes to
# the remote publish root after every fully successful publish, listing
# exactly the files it deployed. Stale = present in that PREVIOUS
# manifest but not in the CURRENT build — never "any remote file this
# build doesn't have", which would also flag an unrelated application's
# files sharing the same remote_dir (see the external audit).


def test_detect_stale_files_finds_files_the_previous_merope_manifest_no_longer_has(
    tmp_path, monkeypatch
):
    factory = _make_ftp_factory()

    def factory_with_previous_manifest(*, timeout=None):
        instance = FakeFTP(timeout=timeout)
        _seed_manifest(
            instance,
            "/www",
            ["index.html", "billets/premier/index.html", "old-post/index.html", "billets/premier/stray.jpg"],
        )
        factory.created.append(instance)
        return instance

    monkeypatch.setattr(module.ftplib, "FTP", factory_with_previous_manifest)

    site = _make_site(tmp_path)
    result = publish_directory(site, _config(), detect_stale_files=True)

    assert result.ok is True
    assert result.stale_remote_error is None
    assert result.stale_remote_manifest_missing is False
    assert sorted(result.stale_remote) == ["billets/premier/stray.jpg", "old-post/index.html"]


def test_detect_stale_files_ignores_a_remote_file_never_listed_in_a_merope_manifest(
    tmp_path, monkeypatch
):
    """A file physically present on the server but absent from every
    MEROPE manifest (an unrelated application's file sharing remote_dir,
    or something a human FTP'd in by hand) must never be proposed for
    deletion, even if it isn't part of this build."""
    factory = _make_ftp_factory()

    def factory_with_foreign_file(*, timeout=None):
        instance = FakeFTP(timeout=timeout)
        _seed_manifest(instance, "/www", ["index.html", "billets/premier/index.html"])
        _seed_remote(instance, ["/www/other-app/config.php"])
        factory.created.append(instance)
        return instance

    monkeypatch.setattr(module.ftplib, "FTP", factory_with_foreign_file)

    site = _make_site(tmp_path)
    result = publish_directory(site, _config(), detect_stale_files=True)

    assert result.ok is True
    assert result.stale_remote == []


def test_a_manifest_containing_an_unsafe_path_is_treated_as_no_baseline(tmp_path, monkeypatch):
    """A manifest with even one path traversal ("../..."), absolute path,
    or backslash entry is entirely untrustworthy — not filtered down to
    just its safe entries. Reached only via a compromised/malicious FTP
    account or a MITM on unencrypted FTP (this same server round-trips
    its own manifest), but delete_remote_files performs unconfirmed
    per-item deletions on this baseline, so nothing here is worth
    partially trusting."""
    factory = _make_ftp_factory()

    def factory_with_poisoned_manifest(*, timeout=None):
        instance = FakeFTP(timeout=timeout)
        _seed_manifest(
            instance,
            "/www",
            ["index.html", "../../etc/passwd"],
        )
        factory.created.append(instance)
        return instance

    monkeypatch.setattr(module.ftplib, "FTP", factory_with_poisoned_manifest)

    site = _make_site(tmp_path)
    result = publish_directory(site, _config(), detect_stale_files=True)

    assert result.ok is True
    assert result.stale_remote == []
    assert result.stale_remote_manifest_missing is True


@pytest.mark.parametrize(
    "unsafe_path",
    [
        "../outside.html",
        "/etc/passwd",
        "a/../../outside.html",
        "a\\..\\..\\outside.html",
        "a//b.html",
        "",
    ],
)
def test_delete_remote_files_refuses_an_unsafe_path_without_touching_the_server(
    tmp_path, monkeypatch, unsafe_path
):
    """Defense in depth even though _download_manifest already filters
    these out of its own baseline: delete_remote_files is the actually
    destructive function and must never trust a path it's handed,
    regardless of caller."""
    factory = _make_ftp_factory()

    def factory_with_leftovers(*, timeout=None):
        instance = FakeFTP(timeout=timeout)
        _seed_remote(instance, ["/www/stray.jpg"])
        factory.created.append(instance)
        return instance

    monkeypatch.setattr(module.ftplib, "FTP", factory_with_leftovers)

    result = delete_remote_files(_config(), [unsafe_path, "stray.jpg"])

    assert result.deleted == ["stray.jpg"]
    assert len(result.failed) == 1
    assert result.failed[0].relative_path == unsafe_path
    assert "sûr" in result.failed[0].message.lower()


def test_detect_stale_files_is_empty_when_remote_matches_local(tmp_path, monkeypatch):
    factory = _make_ftp_factory()

    def factory_with_matching_manifest(*, timeout=None):
        instance = FakeFTP(timeout=timeout)
        _seed_manifest(instance, "/www", ["index.html", "billets/premier/index.html"])
        factory.created.append(instance)
        return instance

    monkeypatch.setattr(module.ftplib, "FTP", factory_with_matching_manifest)

    site = _make_site(tmp_path)
    result = publish_directory(site, _config(), detect_stale_files=True)

    assert result.stale_remote == []
    assert result.stale_remote_error is None
    assert result.stale_remote_manifest_missing is False


def test_detect_stale_files_is_skipped_by_default(tmp_path, monkeypatch):
    factory = _make_ftp_factory()

    def factory_with_previous_manifest(*, timeout=None):
        instance = FakeFTP(timeout=timeout)
        _seed_manifest(instance, "/www", ["old-post/index.html"])
        factory.created.append(instance)
        return instance

    monkeypatch.setattr(module.ftplib, "FTP", factory_with_previous_manifest)

    site = _make_site(tmp_path)
    result = publish_directory(site, _config())  # detect_stale_files defaults to False

    assert result.stale_remote == []


def test_detect_stale_files_is_skipped_when_the_publish_itself_failed(tmp_path, monkeypatch):
    factory_calls: list[FakeFTP] = []

    def factory(*, timeout=None):
        instance = FakeFTP(timeout=timeout)
        instance.fail_files.add("/www/index.html")
        _seed_manifest(instance, "/www", ["old-post/index.html"])
        factory_calls.append(instance)
        return instance

    monkeypatch.setattr(module.ftplib, "FTP", factory)

    site = _make_site(tmp_path)
    result = publish_directory(site, _config(), detect_stale_files=True)

    assert result.ok is False
    # An incomplete transfer is not a trustworthy basis for "what's stale".
    assert result.stale_remote == []
    assert result.stale_remote_error is None
    assert result.stale_remote_manifest_missing is False


def test_detect_stale_files_reports_no_baseline_when_no_previous_manifest_exists(
    tmp_path, monkeypatch
):
    """First publish to a remote_dir (with this feature, or ever): there
    is no MEROPE manifest to diff against yet, so nothing is proposed
    for deletion — a full directory listing would risk catching another
    application's files. A manifest is still written for next time."""
    factory = _make_ftp_factory()

    def factory_with_leftovers_but_no_manifest(*, timeout=None):
        instance = FakeFTP(timeout=timeout)
        _seed_remote(instance, ["/www/old-post/index.html"])
        factory.created.append(instance)
        return instance

    monkeypatch.setattr(module.ftplib, "FTP", factory_with_leftovers_but_no_manifest)

    site = _make_site(tmp_path)
    result = publish_directory(site, _config(), detect_stale_files=True)

    assert result.ok is True  # the publish itself still succeeded
    assert result.stale_remote == []
    assert result.stale_remote_manifest_missing is True
    assert result.stale_remote_error is None

    ftp = factory.created[0]
    manifest_key = "/www/" + module._MANIFEST_FILENAME
    assert manifest_key in ftp.file_contents


def test_a_successful_publish_writes_a_fresh_manifest_for_the_next_one(tmp_path, monkeypatch):
    factory = _make_ftp_factory()
    monkeypatch.setattr(module.ftplib, "FTP", factory)

    site = _make_site(tmp_path)
    publish_directory(site, _config(), detect_stale_files=True)

    ftp = factory.created[0]
    manifest_key = "/www/" + module._MANIFEST_FILENAME
    import json as _json

    written = _json.loads(ftp.file_contents[manifest_key].decode("utf-8"))
    assert sorted(written) == ["billets/premier/index.html", "index.html"]


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
