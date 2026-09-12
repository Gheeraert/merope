"""Side panels must stay slim, give room to the text, and remember widths."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import QApplication

from bloggen.content.writer import write_content_file
from bloggen.ui.qt_editor import window as window_module
from bloggen.ui.qt_editor.window import (
    CONTENT_DOCK_WIDTH,
    FOOTNOTE_DOCK_WIDTH,
    QtEditorWindow,
)


@pytest.fixture(scope="module", autouse=True)
def qapplication():
    yield QApplication.instance() or QApplication([])


def _window(tmp_path) -> QtEditorWindow:
    path = write_content_file(
        tmp_path / "content" / "pages", "a.md", {"title": "A"}, "Texte[^1].\n\n[^1]: Note.\n"
    )
    window = QtEditorWindow(path)
    window.resize(1400, 800)
    window.show()
    QApplication.processEvents()
    return window


def _two_widest(buttons) -> int:
    widths = sorted(button.sizeHint().width() for button in buttons)
    return widths[-1] + widths[-2]


def test_button_rows_wrap_so_panels_can_be_narrower_than_two_buttons(tmp_path):
    window = _window(tmp_path)
    browser = window.content_browser
    notes_buttons = [window.edit_footnote_button, window.delete_footnote_button]

    # Formerly two columns of buttons side by side set the minimum width.
    assert browser.minimumSizeHint().width() < _two_widest(browser.project_buttons)
    assert (
        window.footnote_dock.minimumSizeHint().width() < _two_widest(notes_buttons)
    )
    assert browser.minimumSizeHint().width() >= max(
        button.sizeHint().width() for button in browser.project_buttons
    )
    window.close()


def test_panels_start_slim_and_keep_width_when_window_grows(tmp_path):
    window = _window(tmp_path)

    def expected(dock, target):
        return max(target, dock.minimumSizeHint().width())

    content = window.content_dock
    notes = window.footnote_dock
    assert content.width() == pytest.approx(expected(content, CONTENT_DOCK_WIDTH), abs=2)
    assert notes.width() == pytest.approx(expected(notes, FOOTNOTE_DOCK_WIDTH), abs=2)
    editor_before = window.editor.width()

    window.resize(1700, 800)
    QApplication.processEvents()

    assert window.editor.width() == pytest.approx(editor_before + 300, abs=2)
    window.close()


def test_plain_windows_never_touch_user_settings(tmp_path, monkeypatch):
    monkeypatch.setattr(
        window_module,
        "editor_layout_settings",
        lambda: pytest.fail("un éditeur de test ne doit pas lire les réglages"),
    )
    window = _window(tmp_path)
    window.close()


def test_panel_widths_and_window_size_are_restored_next_session(tmp_path):
    ini = tmp_path / "layout.ini"
    first = _window(tmp_path)
    first.restore_layout(QSettings(str(ini), QSettings.Format.IniFormat))
    first.resizeDocks([first.content_dock], [300], Qt.Orientation.Horizontal)
    first.resize(1300, 760)
    QApplication.processEvents()
    saved_width = first.content_dock.width()
    first.close()
    assert ini.is_file()

    second = QtEditorWindow()
    second.restore_layout(QSettings(str(ini), QSettings.Format.IniFormat))
    second.show()
    QApplication.processEvents()

    assert second.content_dock.width() == pytest.approx(saved_width, abs=4)
    # restoreGeometry keeps the window on the current screen.
    screen_width = second.screen().availableGeometry().width()
    assert second.width() == pytest.approx(min(1300, screen_width), abs=4)
    second.close()


def test_closed_panels_can_always_be_reopened_from_toolbar_or_keys(tmp_path):
    window = _window(tmp_path)
    contents = window.panel_actions["contents"]
    notes = window.panel_actions["notes"]
    assert contents in window.toolbar.actions_in_order
    assert notes in window.toolbar.actions_in_order
    assert (contents.shortcut().toString(), notes.shortcut().toString()) == ("F8", "F9")

    window.content_dock.close()
    window.footnote_dock.close()
    QApplication.processEvents()
    assert not contents.isChecked() and not notes.isChecked()

    contents.trigger()
    notes.trigger()
    QApplication.processEvents()
    assert window.content_dock.isVisible() and window.footnote_dock.isVisible()
    window.close()


def test_corrupt_saved_layout_is_ignored(tmp_path):
    ini = tmp_path / "layout.ini"
    settings = QSettings(str(ini), QSettings.Format.IniFormat)
    settings.setValue("fenetre/geometrie", "n'importe quoi")
    settings.setValue("fenetre/panneaux", 42)
    settings.sync()

    window = QtEditorWindow()
    window.restore_layout(QSettings(str(ini), QSettings.Format.IniFormat))
    window.show()
    QApplication.processEvents()

    assert window.content_dock.isVisible()
    window.close()
