from __future__ import annotations

import os
from pathlib import Path

import pytest
from PIL import Image

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QUrl
from PySide6.QtGui import QTextCursor, QTextDocument
from PySide6.QtWidgets import QApplication, QFileDialog, QInputDialog, QMessageBox

from bloggen.content.writer import read_content_file, write_content_file
from bloggen.markdown.rich_text_import import markdown_to_blocks
from bloggen.markdown.rich_text_model import PARAGRAPH, Block, InlineRun
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


def test_image_file_open_save_reopen_preserves_semantics_and_base_url(tmp_path):
    doc_dir = tmp_path / "content" / "pages"
    images_dir = tmp_path / "assets" / "images"
    images_dir.mkdir(parents=True)
    image_path = images_dir / "bossuet.png"
    Image.new("RGB", (12, 8), color="navy").save(image_path)
    body = (
        "Avant.\n\n"
        "![**Bossuet** à Meaux](../../assets/images/bossuet.png)"
        "{width=420 height=300 align=center}\n\n"
        "Après.\n"
    )
    path = write_content_file(doc_dir, "article.md", _metadata(), body)
    document = QTextDocument()

    loaded = load_content_document(path, document)

    assert loaded.path == path
    assert document.baseUrl().isLocalFile()
    assert Path(document.baseUrl().toLocalFile()).resolve() == doc_dir.resolve()
    image_run = extract_blocks(document)[1].runs[0]
    assert image_run == InlineRun(
        image_src="../../assets/images/bossuet.png",
        image_alt="**Bossuet** à Meaux",
        image_width="420",
        image_height="300",
        image_align="center",
    )
    resolved = document.baseUrl().resolved(QUrl(image_run.image_src))
    assert Path(resolved.toLocalFile()).resolve() == image_path.resolve()

    result = save_content_document(path, loaded.metadata, document)

    assert result.markdown_body == body
    _metadata_read, saved_body = read_content_file(path)
    assert markdown_to_blocks(saved_body) == markdown_to_blocks(body)
    reopened = QTextDocument()
    load_content_document(path, reopened)
    assert extract_blocks(reopened) == extract_blocks(document)


def test_missing_image_remains_openable_and_roundtrips_without_loss(tmp_path):
    path = write_content_file(
        tmp_path,
        "missing.md",
        _metadata(),
        "![Absente](../images/absente.png){width=240 align=right}\n",
    )
    document = QTextDocument()

    loaded = load_content_document(path, document)
    expected = extract_blocks(document)
    result = save_content_document(path, loaded.metadata, document)

    assert expected == [
        Block(
            kind=PARAGRAPH,
            runs=[
                InlineRun(
                    image_src="../images/absente.png",
                    image_alt="Absente",
                    image_width="240",
                    image_align="right",
                )
            ],
        )
    ]
    assert result.markdown_body == (
        "![Absente](../images/absente.png){width=240 align=right}\n"
    )


def test_rejected_file_does_not_change_existing_document_base_url(tmp_path):
    safe_dir = tmp_path / "safe"
    refused_dir = tmp_path / "refused"
    safe = write_content_file(safe_dir, "safe.md", _metadata(), "Texte.\n")
    refused = write_content_file(
        refused_dir,
        "table.md",
        _metadata(),
        "| A |\n|---|\n| B |\n",
    )
    document = QTextDocument()
    load_content_document(safe, document)
    previous_url = document.baseUrl()
    previous_blocks = extract_blocks(document)

    with pytest.raises(ValueError):
        load_content_document(refused, document)

    assert document.baseUrl() == previous_url
    assert extract_blocks(document) == previous_blocks


@pytest.mark.parametrize(
    "unsupported_body",
    [
        "| Colonne |\n| --- |\n| Valeur |\n",
        "<section>Bloc brut</section>\n",
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


def test_insert_image_file_uses_shared_copy_service_and_native_undo_redo(tmp_path):
    doc_dir = tmp_path / "content" / "pages"
    images_dir = tmp_path / "assets" / "images"
    path = write_content_file(doc_dir, "article.md", _metadata(), "Avant après\n")
    source = tmp_path / "incoming" / "photo.png"
    source.parent.mkdir()
    Image.new("RGB", (10, 6), color="red").save(source)
    window = QtEditorWindow(path, images_dir=images_dir)
    original = extract_blocks(window.editor.document())
    cursor = window.editor.textCursor()
    cursor.setPosition(len("Avant "))
    window.editor.setTextCursor(cursor)

    inserted = window.insert_image_file(source, image_alt="**Légende**")

    expected_src = "../../assets/images/photo.png"
    assert inserted == InlineRun(image_src=expected_src, image_alt="**Légende**")
    assert (images_dir / "photo.png").is_file()
    pasted = extract_blocks(window.editor.document())
    assert pasted == [
        Block(
            kind=PARAGRAPH,
            runs=[
                InlineRun(text="Avant "),
                inserted,
                InlineRun(text="après"),
            ],
        )
    ]

    window.editor.undo()
    assert extract_blocks(window.editor.document()) == original
    assert (images_dir / "photo.png").is_file()
    window.editor.redo()
    assert extract_blocks(window.editor.document()) == pasted


def test_insert_image_file_uses_collision_free_name(tmp_path):
    doc_dir = tmp_path / "content" / "pages"
    images_dir = tmp_path / "assets" / "images"
    images_dir.mkdir(parents=True)
    Image.new("RGB", (2, 2), color="blue").save(images_dir / "photo.png")
    source = tmp_path / "incoming" / "photo.png"
    source.parent.mkdir()
    Image.new("RGB", (3, 3), color="green").save(source)
    path = write_content_file(doc_dir, "article.md", _metadata(), "\n")
    window = QtEditorWindow(path, images_dir=images_dir)

    inserted = window.insert_image_file(source)

    assert inserted.image_src == "../../assets/images/photo-2.png"
    assert (images_dir / "photo-2.png").is_file()


def test_insert_image_dialog_requires_an_open_document(tmp_path, monkeypatch):
    warnings = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda *args: warnings.append(args[2]),
    )
    monkeypatch.setattr(
        QFileDialog,
        "getOpenFileName",
        lambda *args: pytest.fail("Le sélecteur ne doit pas être ouvert"),
    )
    window = QtEditorWindow(images_dir=tmp_path / "images")

    window._insert_image_from_dialog()

    assert warnings and "Ouvrez d’abord" in warnings[0]


def test_insert_image_dialog_collects_file_and_caption(tmp_path, monkeypatch):
    doc_dir = tmp_path / "content" / "pages"
    images_dir = tmp_path / "assets" / "images"
    source = tmp_path / "incoming" / "photo.png"
    source.parent.mkdir()
    Image.new("RGB", (4, 4), color="yellow").save(source)
    path = write_content_file(doc_dir, "article.md", _metadata(), "\n")
    window = QtEditorWindow(path, images_dir=images_dir)
    monkeypatch.setattr(
        QFileDialog,
        "getOpenFileName",
        lambda *args: (str(source), "Images"),
    )
    monkeypatch.setattr(
        QInputDialog,
        "getText",
        lambda *args: ("Ma légende", True),
    )

    window._insert_image_from_dialog()

    assert extract_blocks(window.editor.document()) == [
        Block(
            kind=PARAGRAPH,
            runs=[
                InlineRun(
                    image_src="../../assets/images/photo.png",
                    image_alt="Ma légende",
                )
            ],
        )
    ]


def test_run_emits_ready_then_closed_around_qt_event_loop(monkeypatch):
    events = []

    class FakeApplication:
        def exec(self):
            events.append("exec")
            return 0

    class FakeWindow:
        def __init__(self, **kwargs):
            assert kwargs["ipc"] is True
            assert kwargs["images_dir"] == Path("images")
            assert kwargs["project_root"] == Path("project")

        def show(self):
            events.append("show")

        def _emit(self, event_type, **kwargs):
            events.append(event_type)

    monkeypatch.setattr(qt_window_module.QApplication, "instance", lambda: FakeApplication())
    monkeypatch.setattr(qt_window_module, "QtEditorWindow", FakeWindow)

    assert qt_window_module.run(
        project_root=Path("project"),
        images_dir=Path("images"),
        ipc=True,
    ) == 0
    assert events == ["show", "ready", "exec", "closed"]
