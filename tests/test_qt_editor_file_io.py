from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtGui import QTextCursor, QTextDocument
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

from bloggen.content.writer import read_content_file, write_content_file
from bloggen.markdown.rich_text_import import markdown_to_blocks
from bloggen.ui.qt_editor.document_adapter import (
    extract_blocks,
)
from bloggen.ui.qt_editor.file_io import (
    load_content_document,
    save_content_document,
)
from bloggen.ui.qt_editor import window as qt_window_module
from bloggen.ui.qt_editor.window import QtEditorWindow
from bloggen.ui.qt_editor.text_edit import MeropeTextEdit


@pytest.fixture(scope="module", autouse=True)
def qapplication():
    app = QApplication.instance() or QApplication([])
    yield app


def _metadata() -> dict[str, str]:
    return {
        "title": "Document Qt",
        "slug": "document-qt",
        "type": "page",
        "description": "Métadonnées préservées",
    }


def _supported_markdown() -> str:
    return (
        "# Titre\n\n"
        "«\u00a0Bossuet\u00a0»\u00a0: ***texte*** et "
        "[lien](https://example.org).\n\n"
        "> Une citation.\n"
    )


def test_window_uses_merope_text_edit():
    window = QtEditorWindow()

    assert isinstance(window.editor, MeropeTextEdit)
    window.close()


def test_window_displays_rich_paste_refusal(monkeypatch):
    messages = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda *args, **kwargs: messages.append(args[2]),
    )
    window = QtEditorWindow()

    window.editor.pasteRefused.emit("La structure HTML <img> n’est pas prise en charge")

    assert len(messages) == 1
    assert "éviter une perte de données" in messages[0]
    assert "<img>" in messages[0]
    window.close()


def test_disk_open_edit_save_reopen_roundtrip(tmp_path):
    metadata = _metadata()
    path = write_content_file(tmp_path, "document.md", metadata, _supported_markdown())
    original_bytes = path.read_bytes()
    document = QTextDocument()

    loaded = load_content_document(path, document)

    assert loaded.metadata == metadata
    assert document.isModified() is False
    paragraph = document.begin().next()
    cursor = QTextCursor(paragraph)
    cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock)
    cursor.insertText(" Ajout.")
    assert document.isModified() is True

    expected = extract_blocks(document)
    result = save_content_document(path, loaded.metadata, document)

    assert document.isModified() is False
    assert result.archive.archived_path is not None
    assert result.archive.archived_path.read_bytes() == original_bytes
    saved_metadata, saved_body = read_content_file(path)
    assert saved_metadata == metadata
    assert markdown_to_blocks(saved_body) == expected
    assert "\u00a0" in saved_body

    cursor = QTextCursor(document)
    cursor.movePosition(QTextCursor.MoveOperation.End)
    cursor.insertText(" Suite.")
    assert document.isModified() is True
    second = save_content_document(path, loaded.metadata, document)
    assert second.archive.archived_path.name == "document.v2.md"
    assert document.isModified() is False

    reopened = QTextDocument()
    load_content_document(path, reopened)
    assert extract_blocks(reopened) == extract_blocks(document)


@pytest.mark.parametrize(
    "unsupported_body",
    [
        "| Colonne |\n| --- |\n| Valeur |\n",
        "<section>Bloc brut</section>\n",
        "Texte avec une note[^1].\n\n[^1]: Note.\n",
        "Texte avec ![image](assets/image.jpg).\n",
    ],
)
def test_unsupported_file_cannot_replace_or_retarget_editable_document(
    tmp_path, monkeypatch, unsupported_body: str
):
    safe_path = write_content_file(
        tmp_path,
        "safe.md",
        _metadata(),
        "Texte sûr.\n",
    )
    unsupported_path = write_content_file(
        tmp_path,
        "unsupported.md",
        {**_metadata(), "slug": "unsupported"},
        unsupported_body,
    )
    unsupported_bytes = unsupported_path.read_bytes()
    window = QtEditorWindow(safe_path)
    previous_blocks = extract_blocks(window.editor.document())
    errors = []
    monkeypatch.setattr(
        QMessageBox,
        "critical",
        lambda *args: errors.append(args[-1]),
    )

    assert window.open_document(unsupported_path) is False

    assert errors
    assert window.current_path == safe_path
    assert extract_blocks(window.editor.document()) == previous_blocks
    assert unsupported_path.read_bytes() == unsupported_bytes
    assert not (tmp_path / ".versions" / "unsupported.v1.md").exists()


def test_window_uses_qt_modified_state_and_save_cycle(tmp_path):
    path = write_content_file(tmp_path, "document.md", _metadata(), "Corps.\n")
    window = QtEditorWindow(path)

    assert window.editor.document().isModified() is False
    assert not window.windowTitle().endswith("*")

    cursor = QTextCursor(window.editor.document())
    cursor.movePosition(QTextCursor.MoveOperation.End)
    cursor.insertText(" Modifié.")

    assert window.editor.document().isModified() is True
    assert window.windowTitle().endswith("*")
    assert window.save_document() is True
    assert window.current_path == path
    assert window.editor.document().isModified() is False
    assert not window.windowTitle().endswith("*")

    cursor.insertText(" Encore.")
    assert window.editor.document().isModified() is True
    assert window.save_document() is True
    assert window.editor.document().isModified() is False
    assert (tmp_path / ".versions" / "document.v2.md").exists()


@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        (QMessageBox.StandardButton.Discard, True),
        (QMessageBox.StandardButton.Cancel, False),
    ],
)
def test_unsaved_changes_prompt_honors_discard_and_cancel(
    monkeypatch, answer, expected: bool
):
    window = QtEditorWindow()
    QTextCursor(window.editor.document()).insertText("Modifié")
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: answer)

    assert window._confirm_unsaved_changes() is expected


def test_unsaved_changes_prompt_saves_when_requested(monkeypatch):
    window = QtEditorWindow()
    QTextCursor(window.editor.document()).insertText("Modifié")
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda *args: QMessageBox.StandardButton.Save,
    )
    saves = []
    monkeypatch.setattr(window, "save_document", lambda: saves.append(True) or True)

    assert window._confirm_unsaved_changes() is True
    assert saves == [True]


def test_opening_another_file_can_be_cancelled_when_modified(tmp_path, monkeypatch):
    first = write_content_file(tmp_path, "first.md", _metadata(), "Premier.\n")
    second = write_content_file(
        tmp_path,
        "second.md",
        {**_metadata(), "slug": "second"},
        "Second.\n",
    )
    window = QtEditorWindow(first)
    QTextCursor(window.editor.document()).insertText("X")
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda *args: QMessageBox.StandardButton.Cancel,
    )

    assert window.open_document(second) is False
    assert window.current_path == first


def test_close_event_is_cancelled_when_unsaved_prompt_is_cancelled(monkeypatch):
    window = QtEditorWindow()
    QTextCursor(window.editor.document()).insertText("Modifié")
    monkeypatch.setattr(window, "_confirm_unsaved_changes", lambda: False)

    class Event:
        accepted = False
        ignored = False

        def accept(self):
            self.accepted = True

        def ignore(self):
            self.ignored = True

    event = Event()
    window.closeEvent(event)

    assert event.accepted is False
    assert event.ignored is True


def test_ipc_window_emits_opened_and_saved_events(tmp_path, monkeypatch):
    path = write_content_file(tmp_path, "document.md", _metadata(), "Corps.\n")
    events = []
    monkeypatch.setattr(
        qt_window_module,
        "emit_event",
        lambda event_type, **fields: events.append((event_type, fields)) or True,
    )
    window = QtEditorWindow(initial_directory=tmp_path, ipc=True)

    window.load_markdown(path)
    QTextCursor(window.editor.document()).insertText("Ajout ")
    assert window.save_document() is True

    assert events == [
        ("opened", {"path": path, "message": None}),
        ("saved", {"path": path, "message": None}),
    ]


def test_project_pages_directory_is_used_as_initial_open_location(
    tmp_path, monkeypatch
):
    locations = []
    monkeypatch.setattr(
        QFileDialog,
        "getOpenFileName",
        lambda parent, title, location, file_filter: locations.append(location) or ("", ""),
    )
    window = QtEditorWindow(initial_directory=tmp_path)

    window._open_from_dialog()

    assert locations == [str(tmp_path)]


def test_run_emits_ready_then_closed_around_qt_event_loop(monkeypatch):
    events = []

    class FakeApplication:
        def exec(self):
            events.append("exec")
            return 0

    class FakeWindow:
        def __init__(self, **kwargs):
            assert kwargs["ipc"] is True

        def show(self):
            events.append("show")

        def _emit(self, event_type, **kwargs):
            events.append(event_type)

    monkeypatch.setattr(qt_window_module.QApplication, "instance", lambda: FakeApplication())
    monkeypatch.setattr(qt_window_module, "QtEditorWindow", FakeWindow)

    assert qt_window_module.run(ipc=True) == 0
    assert events == ["show", "ready", "exec", "closed"]
