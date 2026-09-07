"""Autosave / crash-recovery wiring in ContentEditorWindow — a second
external audit's "il n'y a toujours ni sauvegarde automatique ni
récupération après crash", explicitly out of scope in an earlier pass,
now implemented.
"""

from __future__ import annotations

import pytest

from bloggen.ui import content_editor as content_editor_module
from bloggen.ui.content_editor import ContentEditorWindow
from bloggen.ui.editor_recovery import RecoveryDraft, load_draft, recovery_file_path, save_draft


@pytest.fixture
def project(tmp_path):
    (tmp_path / "content" / "pages").mkdir(parents=True)
    (tmp_path / "content" / "posts").mkdir(parents=True)
    return tmp_path


@pytest.fixture
def editor(tk_root, project):
    window = ContentEditorWindow(
        tk_root,
        pages_dir=project / "content" / "pages",
        posts_dir=project / "content" / "posts",
        images_dir=project / "assets" / "images",
        slugify_mode="ascii",
        project_root=project,
    )
    yield window
    window.destroy()


def _no_recovery_prompt(*_a, **_k):
    raise AssertionError("no draft exists yet — the recovery prompt must not appear")


# -- autosave -----------------------------------------------------------------


def test_autosave_writes_a_draft_when_dirty(editor, project):
    editor.metadata = {"title": "Brouillon", "slug": "brouillon", "type": "page"}
    editor.current_kind = "page"
    editor.text.insert("insert", "Texte en cours de rédaction.")
    editor.update()
    assert editor._dirty is True

    editor._autosave_tick()

    draft = load_draft(project)
    assert draft is not None
    assert draft.metadata == {"title": "Brouillon", "slug": "brouillon", "type": "page"}
    assert "Texte en cours de rédaction." in draft.body_markdown
    assert draft.current_path is None  # never saved to the project


def test_autosave_does_nothing_when_the_editor_is_clean(editor, project):
    editor._autosave_tick()
    assert not recovery_file_path(project).exists()


def test_autosave_records_the_project_relative_path_of_an_existing_file(editor, project, monkeypatch):
    monkeypatch.setattr(content_editor_module.messagebox, "showinfo", lambda *a, **k: None)
    editor.metadata = {"title": "Existant", "slug": "existant", "type": "page"}
    editor.current_kind = "page"
    editor._save()
    assert editor.current_path is not None

    editor.text.insert("insert", "Une modification après enregistrement.")
    editor.update()
    assert editor._dirty is True

    editor._autosave_tick()

    draft = load_draft(project)
    assert draft.current_path == "content/pages/existant.md"


def test_autosave_reschedules_itself(editor):
    first_id = editor._autosave_after_id
    editor._autosave_tick()
    assert editor._autosave_after_id is not None
    assert editor._autosave_after_id != first_id


# -- draft cleared once it is no longer relevant -------------------------------


def test_save_clears_the_draft(editor, project, monkeypatch):
    monkeypatch.setattr(content_editor_module.messagebox, "showinfo", lambda *a, **k: None)
    editor.metadata = {"title": "T", "slug": "t", "type": "page"}
    editor.current_kind = "page"
    editor.text.insert("insert", "Contenu.")
    editor.update()
    editor._autosave_tick()
    assert load_draft(project) is not None

    editor._save()

    assert load_draft(project) is None


def test_new_document_clears_a_stale_draft_from_the_previous_document(editor, project, monkeypatch):
    editor.text.insert("insert", "Ancien brouillon.")
    editor.update()
    editor._autosave_tick()
    assert load_draft(project) is not None

    monkeypatch.setattr(content_editor_module.messagebox, "askyesno", lambda *a, **k: True)
    assert editor._new_document("page") is True

    assert load_draft(project) is None


def test_open_selected_clears_a_stale_draft_from_the_previous_document(editor, project, monkeypatch):
    other_page = editor.pages_dir / "autre.md"
    other_page.write_text(
        '---\ntitle: "Autre"\nslug: "autre"\ntype: "page"\n---\n\nContenu.\n', encoding="utf-8"
    )
    editor._refresh_file_list()

    editor.text.insert("insert", "Ancien brouillon.")
    editor.update()
    editor._autosave_tick()
    assert load_draft(project) is not None

    monkeypatch.setattr(content_editor_module.messagebox, "askyesno", lambda *a, **k: True)
    editor.file_listbox.selection_set(0)
    editor._open_selected()

    assert load_draft(project) is None


def test_close_request_clears_the_draft_on_a_confirmed_close(editor, project, monkeypatch):
    editor.text.insert("insert", "Contenu non enregistré.")
    editor.update()
    editor._autosave_tick()
    assert load_draft(project) is not None

    monkeypatch.setattr(content_editor_module.messagebox, "askyesno", lambda *a, **k: True)
    monkeypatch.setattr(editor, "destroy", lambda: None)

    editor._on_close_request()

    assert load_draft(project) is None


# -- crash recovery on the next window ------------------------------------------


def test_no_recovery_prompt_when_no_draft_exists(tk_root, project, monkeypatch):
    monkeypatch.setattr(content_editor_module.messagebox, "askyesno", _no_recovery_prompt)
    window = ContentEditorWindow(
        tk_root,
        pages_dir=project / "content" / "pages",
        posts_dir=project / "content" / "posts",
        images_dir=project / "assets" / "images",
        slugify_mode="ascii",
        project_root=project,
    )
    window.destroy()


def test_recovery_prompt_restores_the_draft_on_accept(tk_root, project, monkeypatch):
    save_draft(
        project,
        RecoveryDraft(
            current_path=None,
            current_kind="post",
            metadata={"title": "Récupéré", "slug": "recupere", "type": "post", "date": "2026-04-23"},
            body_markdown="# Récupéré\n\nContenu perdu puis retrouvé.\n",
        ),
    )
    monkeypatch.setattr(content_editor_module.messagebox, "askyesno", lambda *a, **k: True)

    window = ContentEditorWindow(
        tk_root,
        pages_dir=project / "content" / "pages",
        posts_dir=project / "content" / "posts",
        images_dir=project / "assets" / "images",
        slugify_mode="ascii",
        project_root=project,
    )
    try:
        assert window.metadata["title"] == "Récupéré"
        assert window.current_kind == "post"
        assert "Contenu perdu puis retrouvé." in window.text.get("1.0", "end")
        # Restored, unsaved content must be treated as dirty — closing
        # right away must still warn, not silently drop it again.
        assert window._dirty is True
        assert load_draft(project) is None  # consumed, not left dangling
    finally:
        window.destroy()


def test_recovery_prompt_discards_the_draft_on_decline(tk_root, project, monkeypatch):
    save_draft(
        project,
        RecoveryDraft(current_path=None, current_kind="page", metadata={"title": "X"}, body_markdown="Y"),
    )
    monkeypatch.setattr(content_editor_module.messagebox, "askyesno", lambda *a, **k: False)

    window = ContentEditorWindow(
        tk_root,
        pages_dir=project / "content" / "pages",
        posts_dir=project / "content" / "posts",
        images_dir=project / "assets" / "images",
        slugify_mode="ascii",
        project_root=project,
    )
    try:
        assert window.metadata == {}
        assert window._dirty is False
        assert load_draft(project) is None
    finally:
        window.destroy()


def test_recovery_resolves_an_existing_current_path_when_the_file_still_exists(tk_root, project, monkeypatch):
    saved_file = project / "content" / "pages" / "existant.md"
    saved_file.write_text(
        '---\ntitle: "Existant"\nslug: "existant"\ntype: "page"\n---\n\nVersion enregistrée.\n',
        encoding="utf-8",
    )
    save_draft(
        project,
        RecoveryDraft(
            current_path="content/pages/existant.md",
            current_kind="page",
            metadata={"title": "Existant modifié", "slug": "existant", "type": "page"},
            body_markdown="Version modifiée non enregistrée.",
        ),
    )
    monkeypatch.setattr(content_editor_module.messagebox, "askyesno", lambda *a, **k: True)

    window = ContentEditorWindow(
        tk_root,
        pages_dir=project / "content" / "pages",
        posts_dir=project / "content" / "posts",
        images_dir=project / "assets" / "images",
        slugify_mode="ascii",
        project_root=project,
    )
    try:
        assert window.current_path == saved_file.resolve()
    finally:
        window.destroy()


def test_recovery_falls_back_to_no_path_when_the_original_file_is_gone(tk_root, project, monkeypatch):
    save_draft(
        project,
        RecoveryDraft(
            current_path="content/pages/disparu.md",
            current_kind="page",
            metadata={"title": "Disparu"},
            body_markdown="Contenu.",
        ),
    )
    monkeypatch.setattr(content_editor_module.messagebox, "askyesno", lambda *a, **k: True)

    window = ContentEditorWindow(
        tk_root,
        pages_dir=project / "content" / "pages",
        posts_dir=project / "content" / "posts",
        images_dir=project / "assets" / "images",
        slugify_mode="ascii",
        project_root=project,
    )
    try:
        assert window.current_path is None
    finally:
        window.destroy()


# -- destroy() must never leave a dangling autosave callback --------------------


def test_direct_destroy_cancels_the_autosave_timer(tk_root, project):
    window = ContentEditorWindow(
        tk_root,
        pages_dir=project / "content" / "pages",
        posts_dir=project / "content" / "posts",
        images_dir=project / "assets" / "images",
        slugify_mode="ascii",
        project_root=project,
    )
    assert window._autosave_after_id is not None

    window.destroy()  # bypasses _on_close_request, as a test fixture teardown does

    assert window._autosave_after_id is None
