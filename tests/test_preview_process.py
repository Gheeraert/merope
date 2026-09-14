from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from bloggen.ui import preview_process
from bloggen.ui.preview_protocol import PREVIEW_READY_MARKER


def test_ready_marker_is_emitted_from_webview_start_hook(
    tmp_path, monkeypatch, capsys
):
    html = tmp_path / "index.html"
    html.write_text("<html></html>", encoding="utf-8")
    pointer = tmp_path / "_current.txt"
    pointer.write_text(str(html), encoding="utf-8")
    window = object()
    calls = []

    class FakeThread:
        def __init__(self, *, target, args, daemon):
            calls.append(("thread", target, args, daemon))

        def start(self):
            calls.append(("thread-start",))

    def create_window(*args, **kwargs):
        calls.append(("create", args, kwargs))
        assert capsys.readouterr().out == ""
        return window

    def start(*, func):
        calls.append(("start",))
        assert capsys.readouterr().out == ""
        func()

    monkeypatch.setitem(
        sys.modules,
        "webview",
        SimpleNamespace(create_window=create_window, start=start),
    )
    monkeypatch.setattr(preview_process.threading, "Thread", FakeThread)
    monkeypatch.setattr(sys, "argv", ["preview_process", str(pointer)])

    preview_process.main()

    assert capsys.readouterr().out == f"{PREVIEW_READY_MARKER}\n"
    assert calls[0][0] == "create"
    assert calls[1] == ("start",)
    assert calls[-1] == ("thread-start",)


def test_stable_pointer_reloads_a_new_path_in_the_same_window(
    tmp_path, monkeypatch
):
    first = tmp_path / "revision-000001" / "index.html"
    second = tmp_path / "revision-000002" / "index.html"
    first.parent.mkdir()
    second.parent.mkdir()
    first.write_text("first", encoding="utf-8")
    second.write_text("second", encoding="utf-8")
    pointer = tmp_path / "_current.txt"
    pointer.write_text(str(first), encoding="utf-8")
    loaded = []

    class StopWatcher(Exception):
        pass

    sleeps = 0

    def advance_pointer(_seconds):
        nonlocal sleeps
        sleeps += 1
        if sleeps == 1:
            pointer.write_text(str(second), encoding="utf-8")
        else:
            raise StopWatcher

    window = SimpleNamespace(load_url=loaded.append)
    monkeypatch.setattr(preview_process.time, "sleep", advance_pointer)

    with pytest.raises(StopWatcher):
        preview_process._watch_and_reload(window, pointer, str(first))

    assert loaded == [second.as_uri()]
