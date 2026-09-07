"""Stores the FTP publishing password in the OS credential store (Windows
Credential Manager, macOS Keychain, or the platform ``keyring`` backend)
instead of in the project's ``site.json``, which is plain, often
version-controlled JSON.

Keyed by host + username, since the same MEROPE install can publish
several different projects to different servers.
"""

from __future__ import annotations

import keyring
import keyring.errors

_SERVICE_NAME = "MEROPE FTP"


def _account(host: str, username: str) -> str:
    return f"{host}|{username}"


def load_password(host: str, username: str) -> str:
    """Returns the stored password, or "" if there is none — or if the
    credential store itself is unavailable (headless CI, no backend
    configured): a missing secret must degrade to "not authenticated",
    never raise and block an otherwise unrelated config load."""
    if not host or not username:
        return ""
    try:
        return keyring.get_password(_SERVICE_NAME, _account(host, username)) or ""
    except keyring.errors.KeyringError:
        return ""


def save_password(host: str, username: str, password: str) -> None:
    """No-ops (rather than raising) when the credential store is
    unavailable — the password then simply isn't persisted between runs,
    same as if the user had left it blank, instead of blocking a save."""
    if not host or not username:
        return
    try:
        if password:
            keyring.set_password(_SERVICE_NAME, _account(host, username), password)
        else:
            delete_password(host, username)
    except keyring.errors.KeyringError:
        pass


def delete_password(host: str, username: str) -> None:
    if not host or not username:
        return
    try:
        keyring.delete_password(_SERVICE_NAME, _account(host, username))
    except keyring.errors.KeyringError:
        pass
