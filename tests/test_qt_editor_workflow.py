from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QApplication, QMessageBox

from bloggen.content.catalog import ContentCatalogEntry
from bloggen.content.writer import read_content_file, write_content_file
from bloggen.markdown.rich_text_import import markdown_to_blocks
from bloggen.markdown.rich_text_model import PARAGRAPH, Block, InlineRun
from bloggen.ui.editor_recovery import load_draft
from bloggen.ui.qt_editor import __main__ as qt_main_module
from bloggen.ui.qt_editor import window as window_module
from bloggen.ui.qt_editor.document_adapter import extract_blocks, populate_document
from bloggen.ui.qt_editor.window import QtEditorWindow


@pytest.fixture(scope="module", autouse=True)
def qapplication():
    yield QApplication.instance() or QApplication([])


@pytest.fixture
def project(tmp_path):
    pages = tmp_path / "content" / "pages"
    posts = tmp_path / "content" / "posts"
    images = tmp_path / "assets" / "images"
    pages.mkdir(parents=True)
    posts.mkdir(parents=True)
    images.mkdir(parents=True)
    return tmp_path, pages, posts, images


def _window(project, path=None):
    root, pages, posts, images = project
    return QtEditorWindow(
        path,
        project_root=root,
        pages_dir=pages,
        posts_dir=posts,
        images_dir=images,
        slugify_mode="ascii",
    )


def _dispose(window):
    window.autosave_timer.stop()
    window.deleteLater()
    QApplication.processEvents()


def _page(pages: Path, name="original.md", **metadata):
    values = {"title": "Original", "slug": "original", "type": "page"}
    values.update(metadata)
    return write_content_file(pages, name, values, "Corps.\n")


def test_context_actions_and_content_browser_scan(project):
    _root, pages, posts, _images = project
    page = _page(pages)
    post = write_content_file(
        posts,
        "2026-01-02-billet.md",
        {"title": "Billet", "slug": "billet", "type": "post", "date": "2026-01-02"},
        "Texte.\n",
    )
    window = _window(project)

    entries = window.refresh_content_browser()

    assert {(entry.kind, entry.path) for entry in entries} == {("page", page), ("post", post)}
    assert window.project_workflow_available
    assert all(button.isEnabled() for button in window.content_browser.project_buttons)
    _dispose(window)


def test_standalone_keeps_manual_open_but_disables_project_workflow(tmp_path):
    path = write_content_file(
        tmp_path,
        "page.md",
        {"title": "Page", "slug": "page", "type": "page"},
        "Texte.\n",
    )
    window = QtEditorWindow(path)

    assert window.current_path == path
    assert window.save_action.isEnabled()
    assert not window.project_workflow_available
    assert not any(button.isEnabled() for button in window.content_browser.project_buttons)
    with pytest.raises(ValueError, match="contexte projet"):
        window.import_markdown(path)
    _dispose(window)


def test_new_document_resets_session_clean_and_disables_image_context(project, monkeypatch):
    _root, pages, _posts, _images = project
    path = _page(pages)
    window = _window(project, path)
    window.footnote_store.register("Note")
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda *args, **kwargs: QMessageBox.StandardButton.Discard,
    )

    assert window.new_document("post")

    assert window.current_kind == "post"
    assert window.current_path is None
    assert window.metadata == {}
    assert window.footnote_store.definitions == {}
    assert extract_blocks(window.editor.document()) == []
    assert not window.document_has_unsaved_changes
    assert window.save_action.isEnabled()
    assert window.editor.external_paste_context is None
    _dispose(window)


def test_new_document_cancel_preserves_dirty_session(project, monkeypatch):
    window = _window(project)
    window.new_document("page")
    cursor = QTextCursor(window.editor.document())
    cursor.insertText("mémoire")
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: QMessageBox.StandardButton.Cancel)

    assert not window.new_document("post")
    assert window.current_kind == "page"
    assert extract_blocks(window.editor.document())[0].runs[0].text == "mémoire"
    _dispose(window)


@pytest.mark.parametrize(
    ("kind", "metadata", "expected_name"),
    [
        ("page", {"title": "Nouvelle", "slug": "nouvelle", "type": "page"}, "nouvelle.md"),
        (
            "post",
            {"title": "Billet", "slug": "billet", "type": "post", "date": "2026-09-12"},
            "2026-09-12-billet.md",
        ),
    ],
)
def test_first_save_creates_canonical_project_file_without_archive(
    project, kind, metadata, expected_name
):
    _root, pages, posts, _images = project
    window = _window(project)
    assert window.new_document(kind)
    window.metadata = dict(metadata)
    populate_document(
        window.editor.document(),
        [Block(kind=PARAGRAPH, runs=[InlineRun(text="Contenu")])],
    )
    window.editor.document().setModified(True)

    assert window.save_document()

    expected = (pages if kind == "page" else posts) / expected_name
    assert window.current_path == expected
    assert expected.exists()
    assert not (expected.parent / ".versions").exists()
    assert not window.document_has_unsaved_changes
    assert window.editor.external_paste_context is not None
    assert window.editor.document().baseUrl().toLocalFile()
    assert any(entry.path == expected for entry in window.refresh_content_browser())
    _dispose(window)


def test_first_save_collision_is_atomic(project, monkeypatch):
    _root, pages, _posts, _images = project
    existing = _page(pages, "collision.md", title="Existant", slug="collision")
    before = existing.read_bytes()
    window = _window(project)
    window.new_document("page")
    window.metadata = {"title": "Nouveau", "slug": "collision", "type": "page"}
    window._clean_metadata = dict(window.metadata)
    window._session_unsaved = True
    monkeypatch.setattr(QMessageBox, "critical", lambda *args, **kwargs: None)
    monkeypatch.setattr(window, "_existing_slugs", lambda: set())

    assert not window.save_document()
    assert existing.read_bytes() == before
    assert window.current_path is None
    assert window.document_has_unsaved_changes
    assert not (pages / ".versions").exists()
    _dispose(window)


def test_first_save_preserves_image_and_footnote_models(project):
    _root, pages, _posts, _images = project
    window = _window(project)
    window.new_document("page")
    window.metadata = {"title": "Riche", "slug": "riche", "type": "page"}
    populate_document(
        window.editor.document(),
        [
            Block(
                kind=PARAGRAPH,
                runs=[InlineRun(text="Texte"), InlineRun(footnote_ref="9")],
            ),
            Block(
                kind=PARAGRAPH,
                runs=[
                    InlineRun(
                        image_src="../../assets/images/absente.png",
                        image_alt="**Légende**",
                        image_width="300",
                    )
                ],
            ),
        ],
    )
    window.footnote_store.load({"9": [InlineRun(text="Note "), InlineRun(text="riche", bold=True)]})
    window._session_unsaved = True

    assert window.save_document()

    reopened = _window(project, pages / "riche.md")
    assert extract_blocks(reopened.editor.document())[1].runs[0].image_alt == "**Légende**"
    assert reopened.footnote_store.definition("1")[1].bold
    assert extract_blocks(reopened.editor.document())[0].runs[1].footnote_ref == "1"
    _dispose(reopened)
    _dispose(window)


def test_metadata_only_dirty_autosaves_and_saves_without_body_change(project):
    root, pages, _posts, _images = project
    path = _page(pages)
    window = _window(project, path)
    body_before = extract_blocks(window.editor.document())
    window.metadata["description"] = "Nouvelle description"
    window._update_window_title()

    assert window.metadata_modified
    assert window.document_has_unsaved_changes
    assert "*" in window.windowTitle()
    window._autosave_tick()
    assert load_draft(root).metadata["description"] == "Nouvelle description"
    assert window.save_document()
    assert read_content_file(path)[0]["description"] == "Nouvelle description"
    assert extract_blocks(window.editor.document()) == body_before
    assert not window.document_has_unsaved_changes
    _dispose(window)


def test_metadata_dialog_cancel_and_identical_acceptance_are_clean(project, monkeypatch):
    _root, pages, _posts, _images = project
    path = _page(pages)
    window = _window(project, path)

    class CancelDialog:
        def __init__(self, **kwargs):
            pass

        def exec(self):
            return 0

    monkeypatch.setattr(window_module, "ContentMetadataDialog", CancelDialog)
    assert not window._edit_metadata_from_dialog()
    assert not window.document_has_unsaved_changes

    class IdenticalDialog(CancelDialog):
        def exec(self):
            return 1

        def result_metadata(self):
            return dict(window.metadata)

    monkeypatch.setattr(window_module, "ContentMetadataDialog", IdenticalDialog)
    assert not window._edit_metadata_from_dialog()
    assert not window.document_has_unsaved_changes
    _dispose(window)


def test_import_valid_is_unsaved_even_when_empty_and_preserves_unknown(project, tmp_path):
    external = write_content_file(
        tmp_path / "external",
        "import.md",
        {"title": "Import", "slug": "import", "custom-field": "exact"},
        "",
    )
    window = _window(project)

    assert window.import_markdown(external)

    assert window.current_path is None
    assert window.current_kind == "page"
    assert window.metadata["custom-field"] == "exact"
    assert extract_blocks(window.editor.document()) == []
    assert window.document_has_unsaved_changes
    assert window.editor.external_paste_context is None
    _dispose(window)


def test_import_preserves_footnotes_and_image_semantics_then_first_save(project, tmp_path):
    _root, pages, _posts, _images = project
    external = write_content_file(
        tmp_path / "external-rich",
        "import.md",
        {"title": "Import riche", "slug": "import-riche", "custom": "oui"},
        "Texte[^4].\n\n![Alt](image.png){width=50%}\n\n[^4]: Note **riche**.\n",
    )
    window = _window(project)

    assert window.import_markdown(external)
    assert window.footnote_store.definition("4")[1].bold
    assert extract_blocks(window.editor.document())[1].runs[0].image_width == "50%"
    assert window.save_document()
    assert window.current_path == pages / "import-riche.md"
    assert read_content_file(window.current_path)[0]["custom"] == "oui"
    _dispose(window)


def test_invalid_import_leaves_previous_session_intact(project, tmp_path):
    _root, pages, _posts, _images = project
    current = _page(pages)
    invalid = tmp_path / "table.md"
    invalid.write_text("| A |\n|---|\n| B |\n", encoding="utf-8")
    window = _window(project, current)
    before = extract_blocks(window.editor.document())

    with pytest.raises(ValueError):
        window.import_markdown(invalid)

    assert window.current_path == current
    assert extract_blocks(window.editor.document()) == before
    _dispose(window)


def test_open_rejects_location_metadata_contradiction_transactionally(project, monkeypatch):
    _root, pages, posts, _images = project
    current = _page(pages)
    contradictory = write_content_file(
        pages,
        "bad.md",
        {"title": "Bad", "slug": "bad", "type": "post", "date": "2026-01-01"},
        "Bad.\n",
    )
    window = _window(project, current)
    before = extract_blocks(window.editor.document())
    monkeypatch.setattr(QMessageBox, "critical", lambda *args, **kwargs: None)

    assert not window.open_document(contradictory)
    assert window.current_path == current
    assert extract_blocks(window.editor.document()) == before
    _dispose(window)


def test_convert_page_to_post_and_back_reloads_current(project):
    _root, pages, posts, _images = project
    path = _page(pages)
    window = _window(project, path)
    entry = ContentCatalogEntry("page", "Original", path)

    post_path = window.convert_content_entry(entry, date_value="2026-09-12")

    assert post_path == posts / "2026-09-12-original.md"
    assert not path.exists()
    assert window.current_path == post_path
    assert window.current_kind == "post"
    assert window.metadata["date"] == "2026-09-12"
    page_path = window.convert_content_entry(
        ContentCatalogEntry("post", "Original", post_path)
    )
    assert page_path == pages / "original.md"
    assert "date" not in window.metadata
    assert not window.document_has_unsaved_changes
    _dispose(window)


def test_convert_other_file_does_not_mutate_session(project):
    _root, pages, posts, _images = project
    current = _page(pages, "current.md", title="Courant", slug="current")
    other = _page(pages, "other.md", title="Autre", slug="other")
    window = _window(project, current)
    before = extract_blocks(window.editor.document())

    converted = window.convert_content_entry(
        ContentCatalogEntry("page", "Autre", other), date_value="2026-01-03"
    )

    assert converted == posts / "2026-01-03-other.md"
    assert window.current_path == current
    assert extract_blocks(window.editor.document()) == before
    _dispose(window)


@pytest.mark.parametrize(
    ("answer", "converted", "memory_survives"),
    [
        (QMessageBox.StandardButton.Cancel, False, True),
        (QMessageBox.StandardButton.Discard, True, False),
        (QMessageBox.StandardButton.Save, True, True),
    ],
)
def test_convert_current_dirty_honors_save_discard_cancel(
    project, monkeypatch, answer, converted, memory_survives
):
    _root, pages, posts, _images = project
    path = _page(pages)
    window = _window(project, path)
    cursor = QTextCursor(window.editor.document())
    cursor.movePosition(QTextCursor.MoveOperation.End)
    cursor.insertText(" mémoire")
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: answer)

    if converted:
        target = window.convert_content_entry(
            ContentCatalogEntry("page", "Original", path),
            date_value="2026-02-03",
        )
        assert target == posts / "2026-02-03-original.md"
        saved_body = read_content_file(target)[1]
        assert ("mémoire" in saved_body) is memory_survives
    else:
        with pytest.raises(RuntimeError, match="annulée"):
            window.convert_content_entry(
                ContentCatalogEntry("page", "Original", path),
                date_value="2026-02-03",
            )
        assert path.exists()
        assert "mémoire" in extract_blocks(window.editor.document())[0].runs[-1].text
    _dispose(window)


def test_conversion_rejects_invalid_date_and_target_collision(project):
    _root, pages, posts, _images = project
    path = _page(pages)
    window = _window(project, path)
    entry = ContentCatalogEntry("page", "Original", path)
    with pytest.raises(ValueError, match="AAAA-MM-JJ"):
        window.convert_content_entry(entry, date_value="demain")

    collision = write_content_file(
        posts,
        "2026-01-01-original.md",
        {"title": "Collision", "slug": "collision", "type": "post", "date": "2026-01-01"},
        "",
    )
    with pytest.raises(FileExistsError):
        window.convert_content_entry(entry, date_value="2026-01-01")
    assert collision.exists() and path.exists()
    _dispose(window)


def test_refresh_does_not_reload_current_document(project):
    _root, pages, _posts, _images = project
    path = _page(pages)
    window = _window(project, path)
    cursor = QTextCursor(window.editor.document())
    cursor.movePosition(QTextCursor.MoveOperation.End)
    cursor.insertText(" non enregistré")

    window.refresh_content_browser()

    assert "non enregistré" in extract_blocks(window.editor.document())[0].runs[-1].text
    assert window.document_has_unsaved_changes
    _dispose(window)


def test_delete_other_then_current_keeps_versions(project):
    _root, pages, _posts, _images = project
    current = _page(pages, "current.md", title="Courant", slug="current")
    other = _page(pages, "other.md", title="Autre", slug="other")
    versions = pages / ".versions"
    versions.mkdir()
    archived = versions / "current.v1.md"
    archived.write_text("archive", encoding="utf-8")
    window = _window(project, current)

    assert window.delete_content_entry(ContentCatalogEntry("page", "Autre", other))
    assert not other.exists()
    assert window.current_path == current
    assert window.delete_content_entry(ContentCatalogEntry("page", "Courant", current))
    assert not current.exists()
    assert archived.exists()
    assert window.current_path is None
    assert window.current_kind == "page"
    assert not window.document_has_unsaved_changes
    _dispose(window)


def test_cli_passes_complete_structural_context(tmp_path, monkeypatch):
    captured = {}
    pages = tmp_path / "pages"
    posts = tmp_path / "posts"
    images = tmp_path / "images"

    def fake_run(markdown=None, **kwargs):
        captured.update(kwargs)
        return 0

    monkeypatch.setattr("bloggen.ui.qt_editor.window.run", fake_run)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "qt-editor",
            "--project-root", str(tmp_path),
            "--pages-dir", str(pages),
            "--posts-dir", str(posts),
            "--images-dir", str(images),
            "--slugify-mode", "unicode",
        ],
    )

    assert qt_main_module.main() == 0
    assert captured["pages_dir"] == pages
    assert captured["posts_dir"] == posts
    assert captured["images_dir"] == images
    assert captured["slugify_mode"] == "unicode"
