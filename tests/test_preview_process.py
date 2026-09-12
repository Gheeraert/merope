from __future__ import annotations

import sys
from types import SimpleNamespace

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
