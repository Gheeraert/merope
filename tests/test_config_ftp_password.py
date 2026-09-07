"""The FTP password must never land in site.json (previously stored in
clear text right there — see the external audit). It's persisted to the
OS credential store instead (bloggen.config.io <-> ftp_credentials) and
only ever held in memory on the loaded ProjectConfig.

All tests here fake out bloggen.publish.ftp_credentials so the suite
never touches the real OS credential store.
"""

from __future__ import annotations

import json

import pytest

from bloggen.config.defaults import build_default_config
from bloggen.config import io as config_io
from bloggen.config.io import load_config, save_config


@pytest.fixture
def fake_keyring(monkeypatch):
    store: dict[tuple[str, str], str] = {}

    def fake_save(host, username, password):
        if password:
            store[(host, username)] = password
        else:
            store.pop((host, username), None)

    def fake_load(host, username):
        return store.get((host, username), "")

    monkeypatch.setattr(config_io.ftp_credentials, "save_password", fake_save)
    monkeypatch.setattr(config_io.ftp_credentials, "load_password", fake_load)
    return store


def test_save_config_never_writes_the_password_to_disk(tmp_path, fake_keyring):
    config = build_default_config()
    config.ftp.host = "ftp.example.org"
    config.ftp.username = "alice"
    config.ftp.password = "s3cret"

    path = tmp_path / "site.json"
    save_config(config, path)

    on_disk = json.loads(path.read_text(encoding="utf-8"))
    assert on_disk["ftp"]["password"] == ""
    assert fake_keyring[("ftp.example.org", "alice")] == "s3cret"


def test_load_config_hydrates_the_password_from_the_credential_store(tmp_path, fake_keyring):
    config = build_default_config()
    config.ftp.host = "ftp.example.org"
    config.ftp.username = "alice"
    config.ftp.password = "s3cret"
    path = tmp_path / "site.json"
    save_config(config, path)  # writes password="" to disk, stores it in fake_keyring

    reloaded = load_config(path)

    assert reloaded.ftp.password == "s3cret"


def test_load_config_migrates_a_legacy_plaintext_password_into_the_credential_store(
    tmp_path, fake_keyring
):
    config = build_default_config()
    config.ftp.host = "ftp.example.org"
    config.ftp.username = "alice"
    path = tmp_path / "site.json"
    save_config(config, path)

    # Simulate an old site.json written before this fix, with the
    # password still sitting in the file.
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["ftp"]["password"] = "legacy-plaintext"
    path.write_text(json.dumps(raw), encoding="utf-8")

    reloaded = load_config(path)

    assert reloaded.ftp.password == "legacy-plaintext"
    assert fake_keyring[("ftp.example.org", "alice")] == "legacy-plaintext"

    # And the very next save leaves it out of the file for good.
    save_config(reloaded, path)
    on_disk = json.loads(path.read_text(encoding="utf-8"))
    assert on_disk["ftp"]["password"] == ""


def test_password_persistence_delegates_host_and_username_as_is(tmp_path, fake_keyring):
    """config/io.py itself applies no host/username guard — whether a
    blank host/username should skip storage is bloggen.publish.
    ftp_credentials's own call to make (see test_ftp_credentials.py)."""
    config = build_default_config()
    config.ftp.password = "orphaned"  # host/username left blank

    save_config(config, tmp_path / "site.json")

    assert fake_keyring == {("", ""): "orphaned"}
