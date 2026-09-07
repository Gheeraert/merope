"""Shared pytest fixtures.

A single ``tk.Tk()`` interpreter is created once per test session and
reused by every Tkinter-heavy test module (test_menu_link_dialog.py,
test_banner_panel.py, test_notes_panel.py, test_content_editor_paste.py).
Creating and destroying the Tcl/Tk interpreter itself repeatedly within
one process is what makes these tests flaky (Tcl/Tk can end up in a
broken state under that churn) — a single shared interpreter, with each
test module's own widgets as children of it, avoids the problem entirely.
"""

from __future__ import annotations

import tkinter as tk

import pytest


@pytest.fixture(scope="session")
def tk_root():
    window = tk.Tk()
    window.withdraw()
    yield window
    window.destroy()
