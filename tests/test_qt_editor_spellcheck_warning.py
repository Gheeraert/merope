"""FrenchSpellChecker degrades silently (no exception, nothing underlined)
when pyspellchecker or its French dictionary can't be loaded — see
bloggen.ui.qt_editor.spellcheck. QtEditorWindow surfaces that as a
one-time startup warning instead, since an editor with a genuinely clean
document and one with a broken spellchecker would otherwise look
identical.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QMessageBox

from bloggen.ui.qt_editor.window import QtEditorWindow


@pytest.fixture(scope="module", autouse=True)
def qapplication():
    app = QApplication.instance() or QApplication([])
    yield app


def test_warns_once_at_startup_when_the_checker_is_unavailable(monkeypatch):
    warnings: list[tuple] = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warnings.append(args))
    monkeypatch.setattr(
        "bloggen.ui.qt_editor.spellcheck.FrenchSpellChecker.available",
        property(lambda self: False),
    )

    QtEditorWindow()

    assert len(warnings) == 1
    _parent, title, message = warnings[0]
    assert "orthographique" in title.lower()
    assert "qt_editor" in message


def test_does_not_warn_when_the_checker_is_available(monkeypatch):
    warnings: list[tuple] = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warnings.append(args))
    monkeypatch.setattr(
        "bloggen.ui.qt_editor.spellcheck.FrenchSpellChecker.available",
        property(lambda self: True),
    )

    QtEditorWindow()

    assert warnings == []
