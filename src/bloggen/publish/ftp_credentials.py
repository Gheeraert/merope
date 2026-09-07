"""Stores the FTP publishing password in the OS credential store (Windows
Credential Manager, macOS Keychain, or the platform ``keyring`` backend)
instead of in the project's ``site.json``, which is plain, often
version-controlled JSON.

Keyed by host + username, since the same MEROPE install can publish
several different projects to different servers.
"""

from __future__ import annotations

try:
    import keyring
    import keyring.errors
except ImportError:
    # config/io.py imports this module unconditionally on every config
    # load/save, including a plain build with no FTP publishing
    # configured at all — the keyring *package* itself missing (as
    # opposed to no backend being configured, handled below via
    # KeyringError) must degrade the same way a missing backend does,
    # not blow up an otherwise unrelated build.
    keyring = None

_SERVICE_NAME = "MEROPE FTP"


def _account(host: str, username: str) -> str:
    return f"{host}|{username}"


def load_password(host: str, username: str) -> str:
    """Returns the stored password, or "" if there is none — or if the
    credential store itself is unavailable (headless CI, no backend
    configured, or the keyring package isn't installed at all): a
    missing secret must degrade to "not authenticated", never raise and
    block an otherwise unrelated config load."""
    if not host or not username or keyring is None:
        return ""
    try:
        return keyring.get_password(_SERVICE_NAME, _account(host, username)) or ""
    except keyring.errors.KeyringError:
        return ""


def save_password(host: str, username: str, password: str) -> bool:
    """No-ops (rather than raising) when the credential store is
    unavailable — the password then simply isn't persisted between runs,
    same as if the user had left it blank, instead of blocking a save.

    Returns True when there was nothing to do (no password, or no
    host/username to key it by) or the store confirmed the write; False
    when a non-empty password could NOT be confirmed stored (including
    when the keyring package itself isn't installed). Callers that would
    otherwise discard their own copy of the password (e.g. stripping it
    from a JSON config file once "persisted") must check this — a silent
    False here previously meant the secret was dropped on the floor: not
    in the credential store, and no longer on disk either."""
    if not password:
        if host and username:
            delete_password(host, username)
        return True
    if not host or not username or keyring is None:
        return False
    try:
        keyring.set_password(_SERVICE_NAME, _account(host, username), password)
        return True
    except keyring.errors.KeyringError:
        return False


def delete_password(host: str, username: str) -> None:
    if not host or not username or keyring is None:
        return
    try:
        keyring.delete_password(_SERVICE_NAME, _account(host, username))
    except keyring.errors.KeyringError:
        pass
