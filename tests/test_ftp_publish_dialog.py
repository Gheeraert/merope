"""FtpPublishDialog: the GUI confirmation gate for publishing over plain,
unencrypted FTP. The connection/transfer logic itself lives in
ftp_publisher.py and is tested there — this module only exercises the
UI-level decision of whether a publish attempt is even started.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from bloggen.config.models import FtpConfig
from bloggen.ui import ftp_publish_dialog as module
from bloggen.ui.ftp_publish_dialog import FtpPublishDialog


@pytest.fixture
def root(tk_root):
    return tk_root


def _dialog(root, tmp_path: Path, *, use_tls: bool) -> FtpPublishDialog:
    config = FtpConfig(
        host="ftp.example.org",
        port=21,
        username="alice",
        password="secret",
        remote_dir="/www",
        use_tls=use_tls,
        passive_mode=True,
        site_url="",
    )
    dialog = FtpPublishDialog(
        root,
        ftp_config=config,
        output_dir=tmp_path,
        on_config_changed=lambda _config: None,
    )
    dialog.use_tls_var.set(use_tls)
    return dialog


def test_plain_ftp_publish_asks_for_explicit_confirmation(tmp_path, root, monkeypatch):
    dialog = _dialog(root, tmp_path, use_tls=False)
    try:
        asked = {}

        def fake_askyesno(title, message, **kwargs):
            asked["title"] = title
            asked["message"] = message
            return True

        monkeypatch.setattr(module.messagebox, "askyesno", fake_askyesno)
        started = {"value": False}
        monkeypatch.setattr(dialog, "_worker", None)

        def fake_start(*args, **kwargs):
            started["value"] = True

        # Stub out everything past the confirmation gate: this test only
        # cares whether the gate itself fires, not the transfer.
        monkeypatch.setattr(dialog, "_set_inputs_enabled", lambda *_: None)
        monkeypatch.setattr(dialog, "_on_config_changed", lambda *_: None)

        class FakeThread:
            def __init__(self, target, daemon=True):
                started["value"] = True

            def start(self):
                pass

        monkeypatch.setattr(module.threading, "Thread", FakeThread)
        monkeypatch.setattr(dialog, "after", lambda *_a, **_k: None)

        dialog._start_publish()

        assert asked, "Aucune confirmation n'a été demandée avant une publication FTP en clair."
        assert "chiffr" in asked["message"].lower() or "clair" in asked["message"].lower()
        assert started["value"] is True
    finally:
        dialog.destroy()


def test_declining_the_confirmation_prevents_the_publish_attempt(tmp_path, root, monkeypatch):
    dialog = _dialog(root, tmp_path, use_tls=False)
    try:
        monkeypatch.setattr(module.messagebox, "askyesno", lambda *a, **k: False)

        class FailingThread:
            def __init__(self, *args, **kwargs):
                pytest.fail("La publication ne doit pas démarrer sans confirmation.")

        monkeypatch.setattr(module.threading, "Thread", FailingThread)

        dialog._start_publish()
    finally:
        dialog.destroy()


def test_ftps_publish_does_not_prompt_for_plain_ftp_confirmation(tmp_path, root, monkeypatch):
    dialog = _dialog(root, tmp_path, use_tls=True)
    try:
        monkeypatch.setattr(
            module.messagebox,
            "askyesno",
            lambda *a, **k: pytest.fail("FTPS ne doit pas déclencher l'avertissement FTP en clair."),
        )
        monkeypatch.setattr(dialog, "_set_inputs_enabled", lambda *_: None)
        monkeypatch.setattr(dialog, "_on_config_changed", lambda *_: None)
        monkeypatch.setattr(dialog, "after", lambda *_a, **_k: None)

        class FakeThread:
            def __init__(self, target, daemon=True):
                pass

            def start(self):
                pass

        monkeypatch.setattr(module.threading, "Thread", FakeThread)

        dialog._start_publish()
    finally:
        dialog.destroy()
