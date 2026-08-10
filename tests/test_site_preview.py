from __future__ import annotations

import urllib.request
from pathlib import Path

from bloggen.ui.site_preview import SitePreviewServer


def test_open_in_browser_serves_the_directory_over_http(tmp_path: Path, monkeypatch):
    (tmp_path / "index.html").write_text("<h1>Bonjour</h1>", encoding="utf-8")

    opened_urls: list[str] = []
    monkeypatch.setattr("bloggen.ui.site_preview.webbrowser.open", opened_urls.append)

    server = SitePreviewServer()
    try:
        url = server.open_in_browser(tmp_path)
        assert opened_urls == [url]
        with urllib.request.urlopen(url, timeout=5) as response:
            body = response.read().decode("utf-8")
        assert "Bonjour" in body
    finally:
        server.stop()


def test_reopening_the_same_directory_reuses_the_running_server(tmp_path: Path, monkeypatch):
    (tmp_path / "index.html").write_text("ok", encoding="utf-8")
    monkeypatch.setattr("bloggen.ui.site_preview.webbrowser.open", lambda url: None)

    server = SitePreviewServer()
    try:
        first_url = server.open_in_browser(tmp_path)
        first_port = server.port
        second_url = server.open_in_browser(tmp_path)
        assert second_url == first_url
        assert server.port == first_port
    finally:
        server.stop()


def test_opening_a_different_directory_restarts_the_server(tmp_path: Path, monkeypatch):
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"
    first_dir.mkdir()
    second_dir.mkdir()
    (first_dir / "index.html").write_text("first", encoding="utf-8")
    (second_dir / "index.html").write_text("second", encoding="utf-8")
    monkeypatch.setattr("bloggen.ui.site_preview.webbrowser.open", lambda url: None)

    server = SitePreviewServer()
    try:
        server.open_in_browser(first_dir)
        second_url = server.open_in_browser(second_dir)
        with urllib.request.urlopen(second_url, timeout=5) as response:
            body = response.read().decode("utf-8")
        assert body == "second"
    finally:
        server.stop()


def test_stop_is_safe_to_call_when_nothing_is_running():
    server = SitePreviewServer()
    server.stop()
    assert server.port is None
