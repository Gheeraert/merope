"""Headless tests for the "perte possible de travail" fix flagged by the
external audit: opening another file, starting a new document, or closing
the editor window used to discard the current content outright, with no
dirty flag, no confirmation, and no way back.
"""

from __future__ import annotations

import pytest

from bloggen.ui import content_editor as content_editor_module
from bloggen.ui.content_editor import ContentEditorWindow


@pytest.fixture
def editor(tk_root, tmp_path):
    pages_dir = tmp_path / "content" / "pages"
    posts_dir = tmp_path / "content" / "posts"
    images_dir = tmp_path / "assets" / "images"
    pages_dir.mkdir(parents=True)
    posts_dir.mkdir(parents=True)

    window = ContentEditorWindow(
        tk_root, pages_dir=pages_dir, posts_dir=posts_dir, images_dir=images_dir, slugify_mode="ascii"
    )
    yield window
    window.destroy()


def test_typing_marks_the_editor_dirty(editor):
    assert editor._dirty is False
    editor.text.insert("insert", "Bonjour")
    editor.update()
    assert editor._dirty is True


def test_new_document_is_not_dirty(editor, monkeypatch):
    editor.text.insert("insert", "Bonjour")
    editor.update()
    monkeypatch.setattr(content_editor_module.messagebox, "askyesno", lambda *a, **k: True)
    assert editor._new_document("page") is True
    assert editor._dirty is False
    assert editor.text.get("1.0", "end").strip() == ""


def test_new_document_asks_for_confirmation_when_dirty_and_respects_a_decline(editor, monkeypatch):
    editor.text.insert("insert", "Travail non enregistré")
    editor.update()
    assert editor._dirty is True

    asked = []
    monkeypatch.setattr(
        content_editor_module.messagebox,
        "askyesno",
        lambda *a, **k: asked.append(1) or False,
    )

    proceeded = editor._new_document("page")

    assert asked  # the dialog was actually shown
    assert proceeded is False
    assert editor._dirty is True
    assert "Travail non enregistré" in editor.text.get("1.0", "end")


def test_new_document_proceeds_when_confirmation_is_accepted(editor, monkeypatch):
    editor.text.insert("insert", "Travail non enregistré")
    editor.update()

    monkeypatch.setattr(content_editor_module.messagebox, "askyesno", lambda *a, **k: True)

    proceeded = editor._new_document("page")

    assert proceeded is True
    assert editor._dirty is False
    assert editor.text.get("1.0", "end").strip() == ""


def test_new_document_does_not_prompt_when_nothing_is_unsaved(editor, monkeypatch):
    monkeypatch.setattr(
        content_editor_module.messagebox,
        "askyesno",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not be asked")),
    )

    assert editor._new_document("page") is True


def test_open_selected_respects_a_decline(editor, monkeypatch):
    other_page = editor.pages_dir / "autre.md"
    other_page.write_text(
        '---\ntitle: "Autre"\nslug: "autre"\ntype: "page"\n---\n\nContenu de l\'autre page.\n',
        encoding="utf-8",
    )
    editor._refresh_file_list()

    editor.text.insert("insert", "Travail non enregistré")
    editor.update()

    monkeypatch.setattr(content_editor_module.messagebox, "askyesno", lambda *a, **k: False)
    editor.file_listbox.selection_set(0)

    editor._open_selected()

    assert editor.current_path is None  # still the unsaved blank document
    assert "Travail non enregistré" in editor.text.get("1.0", "end")


def test_import_markdown_file_does_not_discard_unsaved_work_on_decline(editor, monkeypatch, tmp_path):
    editor.text.insert("insert", "Travail non enregistré")
    editor.update()

    imported = tmp_path / "externe.md"
    imported.write_text(
        '---\ntitle: "Externe"\nslug: "externe"\ntype: "page"\n---\n\nContenu externe.\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        content_editor_module.filedialog, "askopenfilename", lambda *a, **k: str(imported)
    )
    monkeypatch.setattr(content_editor_module.messagebox, "askyesno", lambda *a, **k: False)

    editor._import_markdown_file()

    assert "Travail non enregistré" in editor.text.get("1.0", "end")
    assert "Contenu externe" not in editor.text.get("1.0", "end")


def test_importing_a_file_marks_the_editor_dirty(editor, monkeypatch, tmp_path):
    """A second external audit finding: _populate_from_blocks() marks the
    editor clean (correct for opening an already-saved file), but an
    import has no corresponding file in the project yet — closing right
    after import previously lost it silently. Confirmed with a
    metadata-only import (empty body: no text-widget edit event at all,
    so no accidental self-correction from a later <<Modified>> event
    either)."""
    imported = tmp_path / "externe_metadata_only.md"
    imported.write_text(
        '---\ntitle: "Externe important"\nslug: "externe-important"\ntype: "page"\n---\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        content_editor_module.filedialog, "askopenfilename", lambda *a, **k: str(imported)
    )
    monkeypatch.setattr(content_editor_module.messagebox, "showinfo", lambda *a, **k: None)

    editor._import_markdown_file()

    assert editor._dirty is True


def test_closing_right_after_import_asks_for_confirmation(editor, monkeypatch, tmp_path):
    imported = tmp_path / "externe_metadata_only.md"
    imported.write_text(
        '---\ntitle: "Externe important"\nslug: "externe-important"\ntype: "page"\n---\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        content_editor_module.filedialog, "askopenfilename", lambda *a, **k: str(imported)
    )
    monkeypatch.setattr(content_editor_module.messagebox, "showinfo", lambda *a, **k: None)
    editor._import_markdown_file()

    asked = []
    monkeypatch.setattr(
        content_editor_module.messagebox,
        "askyesno",
        lambda *a, **k: asked.append(1) or False,
    )
    destroyed = []
    monkeypatch.setattr(editor, "destroy", lambda: destroyed.append(1))

    editor._on_close_request()

    assert asked  # the confirmation dialog was actually shown
    assert destroyed == []


def test_save_clears_the_dirty_flag(editor, monkeypatch):
    editor.text.insert("insert", "Un contenu")
    editor.update()
    editor.metadata = {"title": "T", "slug": "t", "type": "page"}
    editor.current_kind = "page"
    monkeypatch.setattr(content_editor_module.messagebox, "showinfo", lambda *a, **k: None)

    editor._save()

    assert editor._dirty is False


def test_close_request_respects_a_decline(editor, monkeypatch):
    editor.text.insert("insert", "Travail non enregistré")
    editor.update()

    monkeypatch.setattr(content_editor_module.messagebox, "askyesno", lambda *a, **k: False)
    destroyed = []
    monkeypatch.setattr(editor, "destroy", lambda: destroyed.append(1))

    editor._on_close_request()

    assert destroyed == []


def test_close_request_proceeds_when_nothing_is_unsaved(editor, monkeypatch):
    destroyed = []
    monkeypatch.setattr(editor, "destroy", lambda: destroyed.append(1))

    editor._on_close_request()

    assert destroyed == [1]
