"""bloggen.publish.ftp_credentials: the OS credential store wrapper that
keeps the FTP password out of site.json. Faked at the ``keyring`` module
boundary so the suite never touches the real Windows Credential Manager.
"""

from __future__ import annotations

import keyring.errors
import pytest

from bloggen.publish import ftp_credentials


class FakeKeyring:
    def __init__(self) -> None:
        self.store: dict[tuple[str, str], str] = {}

    def get_password(self, service, account):
        return self.store.get((service, account))

    def set_password(self, service, account, password):
        self.store[(service, account)] = password

    def delete_password(self, service, account):
        try:
            del self.store[(service, account)]
        except KeyError:
            raise keyring.errors.PasswordDeleteError("not found")


@pytest.fixture
def fake_backend(monkeypatch):
    fake = FakeKeyring()
    monkeypatch.setattr(ftp_credentials.keyring, "get_password", fake.get_password)
    monkeypatch.setattr(ftp_credentials.keyring, "set_password", fake.set_password)
    monkeypatch.setattr(ftp_credentials.keyring, "delete_password", fake.delete_password)
    return fake


def test_save_and_load_round_trip(fake_backend):
    ftp_credentials.save_password("ftp.example.org", "alice", "s3cret")
    assert ftp_credentials.load_password("ftp.example.org", "alice") == "s3cret"


def test_load_missing_password_returns_empty_string(fake_backend):
    assert ftp_credentials.load_password("ftp.example.org", "alice") == ""


def test_saving_an_empty_password_deletes_any_existing_one(fake_backend):
    ftp_credentials.save_password("ftp.example.org", "alice", "s3cret")
    ftp_credentials.save_password("ftp.example.org", "alice", "")
    assert ftp_credentials.load_password("ftp.example.org", "alice") == ""


def test_deleting_a_password_that_was_never_stored_does_not_raise(fake_backend):
    ftp_credentials.delete_password("ftp.example.org", "alice")


def test_credentials_are_scoped_by_host_and_username(fake_backend):
    ftp_credentials.save_password("ftp.example.org", "alice", "alice-secret")
    ftp_credentials.save_password("ftp.example.org", "bob", "bob-secret")
    ftp_credentials.save_password("ftp.other.org", "alice", "other-secret")

    assert ftp_credentials.load_password("ftp.example.org", "alice") == "alice-secret"
    assert ftp_credentials.load_password("ftp.example.org", "bob") == "bob-secret"
    assert ftp_credentials.load_password("ftp.other.org", "alice") == "other-secret"


@pytest.mark.parametrize(
    ("host", "username"),
    [("", ""), ("ftp.example.org", ""), ("", "alice")],
)
def test_operations_are_no_ops_without_both_host_and_username(fake_backend, host, username):
    # A non-empty password with no host/username to key it by can't be
    # stored anywhere — save_password must report that honestly (False),
    # not claim success while silently dropping it.
    assert ftp_credentials.save_password(host, username, "secret") is False
    assert ftp_credentials.load_password(host, username) == ""
    ftp_credentials.delete_password(host, username)  # must not raise
    assert fake_backend.store == {}


def test_saving_an_empty_password_with_no_host_or_username_is_a_true_no_op(fake_backend):
    # Nothing to store either way — this is the "no password entered
    # yet" case, not a failure to persist one.
    assert ftp_credentials.save_password("", "", "") is True
    assert fake_backend.store == {}


def test_load_degrades_to_empty_string_when_the_backend_is_unavailable(monkeypatch):
    def broken(*_a, **_k):
        raise keyring.errors.NoKeyringError("no backend configured")

    monkeypatch.setattr(ftp_credentials.keyring, "get_password", broken)
    assert ftp_credentials.load_password("ftp.example.org", "alice") == ""


def test_save_degrades_silently_when_the_backend_is_unavailable(monkeypatch):
    def broken(*_a, **_k):
        raise keyring.errors.NoKeyringError("no backend configured")

    monkeypatch.setattr(ftp_credentials.keyring, "set_password", broken)
    # Must not raise, but must report the failure via its return value —
    # callers that would otherwise discard their own copy of the
    # password rely on this (see test_config_ftp_password.py).
    assert ftp_credentials.save_password("ftp.example.org", "alice", "secret") is False
