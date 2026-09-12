from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QMimeData
from PySide6.QtGui import QColor, QImage, QTextCursor, QTextDocument, QTextImageFormat
from PySide6.QtWidgets import QApplication, QFileDialog

from bloggen.content.writer import read_content_file, write_content_file
from bloggen.markdown.rich_text_import import markdown_to_blocks
from bloggen.markdown.rich_text_model import PARAGRAPH, Block, InlineRun
from bloggen.ui.qt_editor.document_adapter import (
    UnsupportedInlineError,
    extract_blocks,
    populate_document,
)
from bloggen.ui.qt_editor.file_io import load_content_document
from bloggen.ui.qt_editor.image_selection import (
    replace_merope_image,
    targeted_merope_image,
)
from bloggen.ui.qt_editor.text_edit import MeropeTextEdit
from bloggen.ui.qt_editor.window import QtEditorWindow


@pytest.fixture(scope="module", autouse=True)
def qapplication():
    app = QApplication.instance() or QApplication([])
    yield app


def _write_image(path, color: str = "steelblue", size=(640, 480)) -> bytes:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = QImage(size[0], size[1], QImage.Format.Format_RGB32)
    image.fill(QColor(color))
    assert image.save(str(path), "PNG")
    return path.read_bytes()


def _select(editor: MeropeTextEdit, start: int, end: int | None = None) -> None:
    cursor = QTextCursor(editor.document())
    cursor.setPosition(start)
    if end is not None:
        cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
    editor.setTextCursor(cursor)
    QApplication.processEvents()


def _image_format(document: QTextDocument) -> QTextImageFormat:
    block = document.begin()
    while block.isValid():
        iterator = block.begin()
        while not iterator.atEnd():
            fragment = iterator.fragment()
            if fragment.isValid() and fragment.charFormat().isImageFormat():
                return QTextImageFormat(fragment.charFormat())
            iterator += 1
        block = block.next()
    raise AssertionError("Aucune image Qt")


def _window_with_image(tmp_path, run: InlineRun) -> tuple[QtEditorWindow, Path]:
    pages = tmp_path / "content" / "pages"
    images = tmp_path / "assets" / "images"
    path = write_content_file(pages, "article.md", {"title": "Article"}, "")
    window = QtEditorWindow(path, images_dir=images)
    populate_document(
        window.editor.document(),
        [Block(kind=PARAGRAPH, runs=[run])],
    )
    window.editor.document().setModified(False)
    _select(window.editor, 0, 1)
    return window, path


def test_source_change_requires_explicit_document_api_opt_in():
    old = InlineRun(image_src="old.png", image_alt="Image")
    new = replace(old, image_src="new.png")
    document = QTextDocument()
    populate_document(document, [Block(kind=PARAGRAPH, runs=[old])])
    cursor = QTextCursor(document)
    cursor.setPosition(0)
    cursor.setPosition(1, QTextCursor.MoveMode.KeepAnchor)
    target = targeted_merope_image(cursor)

    with pytest.raises(UnsupportedInlineError, match="src"):
        replace_merope_image(document, target, new)

    selected = replace_merope_image(
        document,
        target,
        new,
        allow_source_change=True,
    )
    assert targeted_merope_image(selected).run == new


def test_replacement_changes_only_source_and_is_one_native_undo(tmp_path):
    run = InlineRun(
        image_src="../../assets/images/ancien.png",
        image_alt="**Bossuet** à *Meaux*",
        image_width="300",
        image_height="200",
        image_align="center",
    )
    window, _path = _window_with_image(tmp_path, run)
    _write_image(tmp_path / "assets" / "images" / "ancien.png", "navy")
    source = tmp_path / "imports" / "nouveau.png"
    source_bytes = _write_image(source, "gold", (800, 300))
    window.resize(720, 480)
    window.show()

    assert window.replace_targeted_image_file(source)
    QApplication.processEvents()

    changed = targeted_merope_image(window.editor.textCursor()).run
    assert changed == replace(run, image_src="../../assets/images/nouveau.png")
    assert (tmp_path / "assets" / "images" / "nouveau.png").read_bytes() == source_bytes
    image_format = _image_format(window.editor.document())
    assert image_format.name() == "../../assets/images/nouveau.png"
    assert (image_format.width(), image_format.height()) == (300, 200)
    geometry = window.editor.image_resize_geometry()
    assert geometry is not None
    assert (geometry.image_rect.width(), geometry.image_rect.height()) == (300, 200)
    assert window.editor.document().isModified()
    assert window.windowTitle().endswith("*")

    window.editor.undo()
    assert extract_blocks(window.editor.document()) == [
        Block(kind=PARAGRAPH, runs=[run])
    ]
    assert not window.editor.document().isUndoAvailable()
    assert (tmp_path / "assets" / "images" / "nouveau.png").exists()
    window.editor.redo()
    assert targeted_merope_image(window.editor.textCursor()).run == changed
    window.editor.document().setModified(False)
    window.close()


def test_replacement_uses_shared_collision_and_relative_path_rules(tmp_path):
    run = InlineRun(image_src="../../assets/images/ancien.png", image_alt="Image")
    window, _path = _window_with_image(tmp_path, run)
    images = tmp_path / "assets" / "images"
    _write_image(images / "photo.png", "red")
    source = tmp_path / "imports" / "photo.png"
    _write_image(source, "green")

    assert window.replace_targeted_image_file(source)

    changed = targeted_merope_image(window.editor.textCursor()).run
    assert changed.image_src == "../../assets/images/photo-2.png"
    assert (images / "photo.png").is_file()
    assert (images / "photo-2.png").is_file()
    window.editor.document().setModified(False)
    window.close()


def test_missing_image_can_be_replaced_without_losing_metadata(tmp_path):
    run = InlineRun(
        image_src="../../assets/images/introuvable.png",
        image_alt="Légende",
        image_width="50%",
        image_height=None,
        image_align="right",
    )
    window, _path = _window_with_image(tmp_path, run)
    source = tmp_path / "imports" / "reparation.png"
    _write_image(source)

    assert window.replace_targeted_image_file(source)

    assert targeted_merope_image(window.editor.textCursor()).run == replace(
        run,
        image_src="../../assets/images/reparation.png",
    )
    window.editor.document().setModified(False)
    window.close()


def test_two_occurrences_of_same_source_are_replaced_by_range_not_src(tmp_path):
    image_a = InlineRun(image_src="../../assets/images/photo.png", image_alt="A")
    image_b = InlineRun(image_src="../../assets/images/photo.png", image_alt="B")
    window, _path = _window_with_image(tmp_path, image_a)
    blocks = [
        Block(
            kind=PARAGRAPH,
            runs=[image_a, InlineRun(text=" milieu "), image_b],
        )
    ]
    populate_document(window.editor.document(), blocks)
    window.editor.document().setModified(False)
    _select(window.editor, 0, 1)
    source = tmp_path / "imports" / "nouvelle.png"
    _write_image(source)

    assert window.replace_targeted_image_file(source)

    changed_a = replace(image_a, image_src="../../assets/images/nouvelle.png")
    assert extract_blocks(window.editor.document()) == [
        Block(
            kind=PARAGRAPH,
            runs=[changed_a, InlineRun(text=" milieu "), image_b],
        )
    ]
    window.editor.undo()
    assert extract_blocks(window.editor.document()) == blocks
    window.close()


def test_replacement_survives_save_and_reopen_with_front_matter(tmp_path):
    pages = tmp_path / "content" / "pages"
    images = tmp_path / "assets" / "images"
    body = (
        "![**Bossuet**](../../assets/images/ancien.png)"
        "{width=300 height=200 align=center}\n"
    )
    path = write_content_file(pages, "article.md", {"title": "Article"}, body)
    window = QtEditorWindow(path, images_dir=images)
    _select(window.editor, 0, 1)
    source = tmp_path / "imports" / "nouveau.png"
    _write_image(source, size=(900, 300))

    assert window.replace_targeted_image_file(source)
    changed = targeted_merope_image(window.editor.textCursor()).run
    assert window.save_document()

    metadata, saved = read_content_file(path)
    assert metadata == {"title": "Article"}
    assert saved.strip() == (
        "![**Bossuet**](../../assets/images/nouveau.png)"
        "{width=300 height=200 align=center}"
    )
    assert markdown_to_blocks(saved) == [Block(kind=PARAGRAPH, runs=[changed])]
    reopened = QTextDocument()
    load_content_document(path, reopened)
    assert extract_blocks(reopened) == [Block(kind=PARAGRAPH, runs=[changed])]
    window.close()


def test_dialog_cancellation_does_not_copy_or_dirty_document(tmp_path, monkeypatch):
    run = InlineRun(image_src="../../assets/images/ancien.png")
    window, _path = _window_with_image(tmp_path, run)
    images = tmp_path / "assets" / "images"
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args: ("", ""))

    assert window._replace_image_from_dialog() is False

    assert extract_blocks(window.editor.document()) == [
        Block(kind=PARAGRAPH, runs=[run])
    ]
    assert not window.editor.document().isModified()
    assert not images.exists()
    window.close()


def test_dialog_uses_image_filter_and_replacement_workflow(tmp_path, monkeypatch):
    run = InlineRun(image_src="../../assets/images/ancien.png", image_alt="Image")
    window, _path = _window_with_image(tmp_path, run)
    source = tmp_path / "imports" / "nouveau.png"
    _write_image(source)

    def choose_image(parent, title, directory, file_filter):
        assert parent is window
        assert title == "Choisir la nouvelle image"
        assert directory == str(window.current_path.parent)
        for extension in ("*.jpg", "*.jpeg", "*.png", "*.gif", "*.webp"):
            assert extension in file_filter
        return str(source), ""

    monkeypatch.setattr(QFileDialog, "getOpenFileName", choose_image)

    assert window._replace_image_from_dialog()
    assert targeted_merope_image(window.editor.textCursor()).run == replace(
        run,
        image_src="../../assets/images/nouveau.png",
    )
    window.editor.document().setModified(False)
    window.close()


def test_replacement_requires_open_document(tmp_path):
    source = tmp_path / "source.png"
    _write_image(source)
    window = QtEditorWindow(images_dir=tmp_path / "images")
    run = InlineRun(image_src="missing.png")
    populate_document(window.editor.document(), [Block(kind=PARAGRAPH, runs=[run])])
    window.editor.document().setModified(False)
    _select(window.editor, 0, 1)

    with pytest.raises(ValueError, match="fichier Mérope"):
        window.replace_targeted_image_file(source)

    assert not (tmp_path / "images").exists()
    window.close()


def test_replacement_requires_configured_images_directory(tmp_path):
    run = InlineRun(image_src="missing.png")
    window, _path = _window_with_image(tmp_path, run)
    window.images_dir = None
    source = tmp_path / "source.png"
    _write_image(source)

    with pytest.raises(ValueError, match="n’est pas configuré"):
        window.replace_targeted_image_file(source)

    assert extract_blocks(window.editor.document()) == [
        Block(kind=PARAGRAPH, runs=[run])
    ]
    window.close()


def test_same_resolved_source_is_noop_without_dirty_or_undo(tmp_path):
    images = tmp_path / "assets" / "images"
    source = images / "photo.png"
    _write_image(source)
    run = InlineRun(image_src="../../assets/images/photo.png", image_alt="Image")
    window, _path = _window_with_image(tmp_path, run)

    assert window.replace_targeted_image_file(source) is False

    assert extract_blocks(window.editor.document()) == [
        Block(kind=PARAGRAPH, runs=[run])
    ]
    assert not window.editor.document().isModified()
    assert not window.editor.document().isUndoAvailable()
    window.close()


def test_unreadable_replacement_is_rejected_before_copy(tmp_path):
    run = InlineRun(image_src="missing.png")
    window, _path = _window_with_image(tmp_path, run)
    source = tmp_path / "not-an-image.png"
    source.write_text("not an image", encoding="utf-8")

    with pytest.raises(ValueError, match="lisible par Qt"):
        window.replace_targeted_image_file(source)

    assert not (tmp_path / "assets" / "images").exists()
    assert not window.editor.document().isModified()
    window.close()


def test_replace_action_is_enabled_only_for_unambiguous_image_target(tmp_path):
    image = InlineRun(image_src="missing.png")
    window, _path = _window_with_image(tmp_path, image)

    window._update_image_action()
    assert window.replace_image_action.isEnabled()
    populate_document(
        window.editor.document(),
        [Block(kind=PARAGRAPH, runs=[image, InlineRun(text="X")])],
    )
    window.editor.document().setModified(False)
    _select(window.editor, 2)
    window._update_image_action()
    assert window.replace_image_action.isEnabled() is False
    window.close()


def test_html_and_bitmap_image_paste_without_document_context_remains_refused():
    editor = MeropeTextEdit()
    original = [Block(kind=PARAGRAPH, runs=[InlineRun(text="Avant")])]
    populate_document(editor.document(), original)
    editor.document().setModified(False)
    mime = QMimeData()
    mime.setHtml('<p>Texte <img src="data:image/png;base64,AAAA"></p>')
    mime.setText("Texte Image")

    editor.insertFromMimeData(mime)

    assert extract_blocks(editor.document()) == original
    assert not editor.document().isModified()

    bitmap = QMimeData()
    bitmap.setImageData(QImage(10, 10, QImage.Format.Format_RGB32))
    assert editor.canInsertFromMimeData(bitmap) is True
    editor.insertFromMimeData(bitmap)
    assert extract_blocks(editor.document()) == original
