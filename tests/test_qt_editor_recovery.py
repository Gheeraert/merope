from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QApplication, QMessageBox

from bloggen.content.footnotes import separate_footnote_definitions
from bloggen.content.writer import write_content_file
from bloggen.markdown.rich_text_import import markdown_to_blocks
from bloggen.markdown.rich_text_model import PARAGRAPH, Block, InlineRun
from bloggen.ui.editor_recovery import (
    RecoveryDraft,
    load_draft,
    recovery_file_path,
    save_draft,
)
from bloggen.ui.qt_editor import __main__ as qt_main_module
from bloggen.ui.qt_editor import window as window_module
from bloggen.ui.qt_editor.document_adapter import extract_blocks, populate_document
from bloggen.ui.qt_editor.recovery import AUTOSAVE_INTERVAL_MS
from bloggen.ui.qt_editor.window import QtEditorWindow


@pytest.fixture(scope="module", autouse=True)
def qapplication():
    yield QApplication.instance() or QApplication([])


def _dispose(window: QtEditorWindow) -> None:
    window.autosave_timer.stop()
    window.deleteLater()
    QApplication.processEvents()


def _dirty_body(window: QtEditorWindow, text: str = "Modification") -> None:
    cursor = QTextCursor(window.editor.document())
    cursor.movePosition(QTextCursor.MoveOperation.End)
    cursor.insertText(text)


def _path(project_root: Path, name: str = "article.md") -> Path:
    return write_content_file(
        project_root / "content" / "pages",
        name,
        {"title": "Original", "slug": Path(name).stem},
        "Corps original.\n",
    )


class _CloseEvent:
    accepted = False
    ignored = False

    def accept(self) -> None:
        self.accepted = True

    def ignore(self) -> None:
        self.ignored = True


def test_project_root_none_disables_recovery_timer_and_tick(tmp_path):
    window = QtEditorWindow()
    _dirty_body(window)

    window._autosave_tick()

    assert window.project_root is None
    assert not window.autosave_timer.isActive()
    assert not recovery_file_path(tmp_path).exists()
    _dispose(window)


def test_project_recovery_timer_uses_historical_interval(tmp_path):
    window = QtEditorWindow(project_root=tmp_path)

    assert window.autosave_timer.parent() is window
    assert window.autosave_timer.interval() == AUTOSAVE_INTERVAL_MS == 30_000
    assert window.autosave_timer.isActive()
    _dispose(window)


def test_clean_tick_does_not_write_recovery_file(tmp_path):
    window = QtEditorWindow(project_root=tmp_path)

    window._autosave_tick()

    assert not recovery_file_path(tmp_path).exists()
    _dispose(window)


def test_body_dirty_tick_writes_real_shared_json(tmp_path):
    window = QtEditorWindow(project_root=tmp_path)
    window.metadata = {"title": "Brouillon", "slug": "brouillon"}
    _dirty_body(window, "Texte en cours.")

    window._autosave_tick()

    draft_path = recovery_file_path(tmp_path)
    assert draft_path.is_file()
    payload = json.loads(draft_path.read_text(encoding="utf-8"))
    assert payload["metadata"] == {"title": "Brouillon", "slug": "brouillon"}
    assert payload["current_path"] is None
    assert payload["current_kind"] is None
    assert "Texte en cours." in payload["body_markdown"]
    assert load_draft(tmp_path) == RecoveryDraft(**payload)
    _dispose(window)


def test_store_only_dirty_tick_writes_definitions_without_dirtying_body(tmp_path):
    window = QtEditorWindow(project_root=tmp_path)
    window.footnote_store.load({"1": [InlineRun(text="Initiale")]})
    window.footnote_store.update("1", [InlineRun(text="Modifiée", bold=True)])

    assert not window.editor.document().isModified()
    assert window.footnote_store.modified
    window._autosave_tick()

    draft = load_draft(tmp_path)
    assert draft is not None
    body, definitions = separate_footnote_definitions(
        markdown_to_blocks(draft.body_markdown)
    )
    assert body == []
    assert definitions == {"1": [InlineRun(text="Modifiée", bold=True)]}
    _dispose(window)


def test_autosave_preserves_body_rich_note_image_and_deferred_shortcut(tmp_path):
    path = _path(tmp_path)
    original_file = path.read_bytes()
    window = QtEditorWindow(path, project_root=tmp_path)
    body = [
        Block(
            kind=PARAGRAPH,
            runs=[
                InlineRun(text="Corps"),
                InlineRun(footnote_ref="3"),
                InlineRun(text=" et ((note différée))."),
            ],
        ),
        Block(
            kind=PARAGRAPH,
            runs=[
                InlineRun(
                    image_src="../../assets/images/bossuet.png",
                    image_alt="**Bossuet**",
                    image_width="300",
                    image_align="center",
                )
            ],
        ),
    ]
    populate_document(window.editor.document(), body)
    window.footnote_store.load(
        {
            "3": [
                InlineRun(text="Une "),
                InlineRun(text="note riche", bold=True),
            ],
            "8": [InlineRun(text="Orpheline", italic=True)],
        }
    )
    window.editor.document().setModified(True)

    window._autosave_tick()

    draft = load_draft(tmp_path)
    assert draft is not None
    assert draft.current_path == "content/pages/article.md"
    recovered_body, definitions = separate_footnote_definitions(
        markdown_to_blocks(draft.body_markdown)
    )
    assert recovered_body == body
    assert definitions == window.footnote_definitions
    assert "((note différée))" in draft.body_markdown
    assert path.read_bytes() == original_file
    assert not (path.parent / ".versions").exists()
    _dispose(window)


def test_external_current_path_is_never_written_to_draft(tmp_path):
    project_root = tmp_path / "project"
    outside = tmp_path / "outside.md"
    outside.write_text("extérieur", encoding="utf-8")
    window = QtEditorWindow(project_root=project_root)
    window.current_path = outside
    _dirty_body(window)

    window._autosave_tick()

    draft = load_draft(project_root)
    assert draft is not None
    assert draft.current_path is None
    _dispose(window)


def test_autosave_failure_is_silent_and_preserves_dirty_state(
    tmp_path,
    monkeypatch,
    capsys,
):
    window = QtEditorWindow(project_root=tmp_path)
    _dirty_body(window)
    monkeypatch.setattr(
        window_module,
        "save_draft",
        lambda *args: (_ for _ in ()).throw(OSError("disque indisponible")),
    )

    window._autosave_tick()

    assert window.document_has_unsaved_changes
    assert window.autosave_timer.isActive()
    assert "Autosauvegarde" in capsys.readouterr().err
    _dispose(window)


def test_successful_save_clears_draft(tmp_path):
    path = _path(tmp_path)
    window = QtEditorWindow(path, project_root=tmp_path)
    _dirty_body(window)
    window._autosave_tick()
    assert load_draft(tmp_path) is not None

    assert window.save_document()

    assert load_draft(tmp_path) is None
    assert not window.document_has_unsaved_changes
    _dispose(window)


def test_failed_save_keeps_existing_draft(tmp_path, monkeypatch):
    path = _path(tmp_path)
    window = QtEditorWindow(path, project_root=tmp_path)
    _dirty_body(window)
    window._autosave_tick()
    original_draft = recovery_file_path(tmp_path).read_bytes()
    monkeypatch.setattr(
        window_module,
        "save_content_document",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("échec")),
    )
    monkeypatch.setattr(QMessageBox, "critical", lambda *args: None)

    assert not window.save_document()

    assert recovery_file_path(tmp_path).read_bytes() == original_draft
    assert window.document_has_unsaved_changes
    _dispose(window)


@pytest.mark.parametrize(
    ("answer", "cleared", "timer_active"),
    [
        (QMessageBox.StandardButton.Discard, True, False),
        (QMessageBox.StandardButton.Cancel, False, True),
    ],
)
def test_close_discard_clears_but_cancel_keeps_recovery(
    tmp_path,
    monkeypatch,
    answer,
    cleared,
    timer_active,
):
    window = QtEditorWindow(project_root=tmp_path)
    _dirty_body(window)
    window._autosave_tick()
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: answer)
    event = _CloseEvent()

    window.closeEvent(event)

    assert (load_draft(tmp_path) is None) is cleared
    assert window.autosave_timer.isActive() is timer_active
    assert event.accepted is cleared
    assert event.ignored is not cleared
    _dispose(window)


def test_restore_accept_recovers_complete_model_and_remains_dirty(
    tmp_path,
    monkeypatch,
):
    path = _path(tmp_path)
    draft = RecoveryDraft(
        current_path="content/pages/article.md",
        current_kind="page",
        metadata={"title": "Récupéré", "slug": "recupere", "type": "page"},
        body_markdown=(
            "Corps[^3] et ((note différée)).\n\n"
            "![**Bossuet**](../../assets/images/bossuet.png)"
            "{width=300 align=center}\n\n"
            "[^3]: Une **note riche**.\n\n"
            "[^8]: Une *orpheline*.\n"
        ),
    )
    save_draft(tmp_path, draft)
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args: QMessageBox.StandardButton.Yes,
    )

    window = QtEditorWindow(path, project_root=tmp_path)

    blocks = extract_blocks(window.editor.document())
    assert window.metadata == draft.metadata
    assert window.current_path == path.resolve()
    assert window.current_kind == "page"
    assert window.footnote_definitions == {
        "3": [
            InlineRun(text="Une "),
            InlineRun(text="note riche", bold=True),
            InlineRun(text="."),
        ],
        "8": [
            InlineRun(text="Une "),
            InlineRun(text="orpheline", italic=True),
            InlineRun(text="."),
        ],
    }
    assert any(run.footnote_ref == "3" for run in blocks[0].runs)
    assert "((note différée))" in "".join(run.text for run in blocks[0].runs)
    assert blocks[1].runs == [
        InlineRun(
            image_src="../../assets/images/bossuet.png",
            image_alt="**Bossuet**",
            image_width="300",
            image_align="center",
        )
    ]
    assert window.editor.document().isModified()
    assert not window.footnote_store.modified
    assert window.document_has_unsaved_changes
    assert window.windowTitle().endswith("*")
    assert load_draft(tmp_path) == draft
    assert window.editor.document().baseUrl().toLocalFile().rstrip("/\\").endswith(
        "content/pages"
    )
    _dispose(window)


def test_save_after_restore_writes_canonical_content_cleans_both_states_and_draft(
    tmp_path,
    monkeypatch,
):
    path = _path(tmp_path)
    save_draft(
        tmp_path,
        RecoveryDraft(
            current_path="content/pages/article.md",
            current_kind="page",
            metadata={"title": "Récupéré", "slug": "article", "type": "page"},
            body_markdown=(
                "Corps[^3] et ((note différée)).\n\n"
                "[^3]: Une **note riche**.\n"
            ),
        ),
    )
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args: QMessageBox.StandardButton.Yes,
    )
    window = QtEditorWindow(path, project_root=tmp_path)

    assert window.document_has_unsaved_changes
    assert window.save_document()

    assert not window.editor.document().isModified()
    assert not window.footnote_store.modified
    assert not window.document_has_unsaved_changes
    assert load_draft(tmp_path) is None
    reopened = QtEditorWindow(path)
    assert "((note différée))" in "".join(
        run.text for run in extract_blocks(reopened.editor.document())[0].runs
    )
    assert reopened.footnote_definitions == {
        "1": [
            InlineRun(text="Une "),
            InlineRun(text="note riche", bold=True),
            InlineRun(text="."),
        ]
    }
    _dispose(reopened)
    _dispose(window)


def test_restore_declined_deletes_draft_and_keeps_opened_document(
    tmp_path,
    monkeypatch,
):
    path = _path(tmp_path)
    save_draft(
        tmp_path,
        RecoveryDraft(None, None, {"title": "Draft"}, "Brouillon.\n"),
    )
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args: QMessageBox.StandardButton.No,
    )

    window = QtEditorWindow(path, project_root=tmp_path)

    assert window.current_path == path
    assert window.metadata["title"] == "Original"
    assert extract_blocks(window.editor.document()) == [
        Block(kind=PARAGRAPH, runs=[InlineRun(text="Corps original.")])
    ]
    assert not window.document_has_unsaved_changes
    assert load_draft(tmp_path) is None
    _dispose(window)


@pytest.mark.parametrize(
    "stored_path",
    ["content/pages/disparu.md", "../hors-projet.md"],
)
def test_restore_missing_or_unsafe_path_keeps_content_but_detaches_file(
    tmp_path,
    monkeypatch,
    stored_path,
):
    save_draft(
        tmp_path,
        RecoveryDraft(stored_path, None, {"title": "Récupéré"}, "Contenu.\n"),
    )
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args: QMessageBox.StandardButton.Yes,
    )

    window = QtEditorWindow(project_root=tmp_path)

    assert window.current_path is None
    assert extract_blocks(window.editor.document()) == [
        Block(kind=PARAGRAPH, runs=[InlineRun(text="Contenu.")])
    ]
    assert window.document_has_unsaved_changes
    assert not window.save_action.isEnabled()
    assert load_draft(tmp_path) is not None
    _dispose(window)


def test_unsupported_recovery_draft_leaves_current_document_and_draft_intact(
    tmp_path,
    monkeypatch,
):
    path = _path(tmp_path)
    draft = RecoveryDraft(
        None,
        None,
        {"title": "Titre refusé"},
        "##### Titre non pris en charge\n",
    )
    save_draft(tmp_path, draft)
    warnings = []
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args: QMessageBox.StandardButton.Yes,
    )
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda *args: warnings.append(args[2]),
    )

    window = QtEditorWindow(path, project_root=tmp_path)

    assert window.current_path == path
    assert window.metadata["title"] == "Original"
    assert extract_blocks(window.editor.document()) == [
        Block(kind=PARAGRAPH, runs=[InlineRun(text="Corps original.")])
    ]
    assert not window.document_has_unsaved_changes
    assert load_draft(tmp_path) == draft
    assert warnings and "document courant reste intact" in warnings[0]
    event = _CloseEvent()
    window.closeEvent(event)
    assert event.accepted
    assert load_draft(tmp_path) == draft
    _dispose(window)


@pytest.mark.parametrize(
    ("answer", "opened", "draft_remains"),
    [
        (QMessageBox.StandardButton.Discard, True, False),
        (QMessageBox.StandardButton.Cancel, False, True),
    ],
)
def test_open_other_file_clears_recovery_only_after_guard_allows_replacement(
    tmp_path,
    monkeypatch,
    answer,
    opened,
    draft_remains,
):
    first = _path(tmp_path, "first.md")
    second = _path(tmp_path, "second.md")
    window = QtEditorWindow(first, project_root=tmp_path)
    _dirty_body(window)
    window._autosave_tick()
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: answer)

    assert window.open_document(second) is opened

    assert (load_draft(tmp_path) is not None) is draft_remains
    assert window.current_path == (second if opened else first)
    _dispose(window)


def test_accepted_close_stops_timer_so_no_late_tick_is_scheduled(tmp_path):
    window = QtEditorWindow(project_root=tmp_path)
    assert window.autosave_timer.isActive()
    event = _CloseEvent()

    window.closeEvent(event)

    assert event.accepted
    assert not window.autosave_timer.isActive()
    _dispose(window)


def test_cli_passes_explicit_project_root_to_run(tmp_path, monkeypatch):
    captured = {}

    def fake_run(markdown=None, **kwargs):
        captured["markdown"] = markdown
        captured.update(kwargs)
        return 0

    monkeypatch.setattr(window_module, "run", fake_run)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "qt-editor",
            "document.md",
            "--project-root",
            str(tmp_path),
        ],
    )

    assert qt_main_module.main() == 0
    assert captured["markdown"] == Path("document.md")
    assert captured["project_root"] == tmp_path
