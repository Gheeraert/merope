from __future__ import annotations

from dataclasses import replace
import os
from pathlib import Path

import pytest
from PIL import Image

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtGui import QTextCursor, QTextDocument
from PySide6.QtWidgets import QApplication, QDialog

from bloggen.content.writer import read_content_file, write_content_file
from bloggen.markdown.rich_text_export import blocks_to_markdown
from bloggen.markdown.rich_text_import import markdown_to_blocks
from bloggen.markdown.rich_text_model import PARAGRAPH, Block, InlineRun
from bloggen.ui.qt_editor import window as window_module
from bloggen.ui.qt_editor.document_adapter import extract_blocks
from bloggen.ui.qt_editor.file_io import load_content_document
from bloggen.ui.qt_editor.image_adjust_dialog import ImageAdjustmentRequest
from bloggen.ui.qt_editor.window import QtEditorWindow


@pytest.fixture(scope="module", autouse=True)
def qapplication():
    app = QApplication.instance() or QApplication([])
    yield app


def _write_image(path, *, mode="RGBA", size=(100, 80), color=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    if color is None:
        color = (40, 100, 180, 127) if mode == "RGBA" else (40, 100, 180)
    Image.new(mode, size, color).save(path)
    return path.read_bytes()


def _select_image(window: QtEditorWindow) -> None:
    cursor = QTextCursor(window.editor.document())
    cursor.setPosition(0)
    cursor.setPosition(1, QTextCursor.MoveMode.KeepAnchor)
    window.editor.setTextCursor(cursor)
    QApplication.processEvents()


def _window_with_run(tmp_path, run: InlineRun) -> tuple[QtEditorWindow, Path]:
    pages = tmp_path / "content" / "pages"
    body = blocks_to_markdown([Block(kind=PARAGRAPH, runs=[run])])
    path = write_content_file(pages, "article.md", {"title": "Article"}, body)
    window = QtEditorWindow(path)
    _select_image(window)
    return window, path


def _close_without_prompt(window: QtEditorWindow) -> None:
    window.editor.document().setModified(False)
    window.close()


def test_adjust_action_is_enabled_only_for_readable_local_target(tmp_path):
    source = tmp_path / "assets" / "images" / "photo.png"
    _write_image(source)
    local = InlineRun(image_src="../../assets/images/photo.png")
    window, _path = _window_with_run(tmp_path, local)

    window._update_image_action()
    assert window.adjust_image_action.isEnabled()
    assert not window.adjust_image_action.icon().isNull()
    _close_without_prompt(window)

    for image_src in (
        "../../assets/images/missing.png",
        "https://example.test/photo.png",
    ):
        unavailable, _path = _window_with_run(
            tmp_path,
            InlineRun(image_src=image_src),
        )
        unavailable._update_image_action()
        assert not unavailable.adjust_image_action.isEnabled()
        _close_without_prompt(unavailable)

    unreadable_path = tmp_path / "assets" / "images" / "not-an-image.png"
    unreadable_path.write_text("pas une image", encoding="utf-8")
    unreadable, _path = _window_with_run(
        tmp_path,
        InlineRun(image_src="../../assets/images/not-an-image.png"),
    )
    unreadable._update_image_action()
    assert not unreadable.adjust_image_action.isEnabled()
    _close_without_prompt(unreadable)

    plain, _path = _window_with_run(tmp_path, InlineRun(text="Texte"))
    plain._update_image_action()
    assert not plain.adjust_image_action.isEnabled()
    _close_without_prompt(plain)


def test_adjust_dialog_cancel_and_identity_are_clean_noops(tmp_path, monkeypatch):
    source = tmp_path / "assets" / "images" / "photo.png"
    _write_image(source)
    run = InlineRun(image_src="../../assets/images/photo.png", image_alt="")
    window, _path = _window_with_run(tmp_path, run)

    class Dialog:
        result = QDialog.DialogCode.Rejected

        def __init__(self, source_path, parent):
            assert source_path == source.resolve()
            assert parent is window

        def exec(self):
            return self.result

        def request(self):
            return ImageAdjustmentRequest(0, 0)

    monkeypatch.setattr(window_module, "AdjustImageDialog", Dialog)
    window.adjust_image_action.trigger()
    assert list(source.parent.glob("photo-adjust*.png")) == []
    assert extract_blocks(window.editor.document()) == [Block(kind=PARAGRAPH, runs=[run])]
    assert not window.editor.document().isModified()
    assert not window.editor.document().isUndoAvailable()

    Dialog.result = QDialog.DialogCode.Accepted
    window.adjust_image_action.trigger()
    assert list(source.parent.glob("photo-adjust*.png")) == []
    assert extract_blocks(window.editor.document()) == [Block(kind=PARAGRAPH, runs=[run])]
    assert not window.editor.document().isModified()
    assert not window.editor.document().isUndoAvailable()
    _close_without_prompt(window)


def test_toolbar_adjust_action_applies_accepted_request(tmp_path, monkeypatch):
    source = tmp_path / "assets" / "images" / "photo.png"
    _write_image(source)
    run = InlineRun(image_src="../../assets/images/photo.png", image_alt="")
    window, _path = _window_with_run(tmp_path, run)

    class Dialog:
        def __init__(self, source_path, parent):
            assert source_path == source.resolve()
            assert parent is window

        def exec(self):
            return QDialog.DialogCode.Accepted

        def request(self):
            return ImageAdjustmentRequest(25, -10)

    monkeypatch.setattr(window_module, "AdjustImageDialog", Dialog)

    window.adjust_image_action.trigger()

    changed = replace(run, image_src="../../assets/images/photo-adjust1.png")
    assert extract_blocks(window.editor.document()) == [
        Block(kind=PARAGRAPH, runs=[changed])
    ]
    assert source.with_name("photo-adjust1.png").is_file()
    assert window.editor.document().isUndoAvailable()
    _close_without_prompt(window)


@pytest.mark.parametrize(("suffix", "mode"), [("png", "RGBA"), ("jpg", "RGB")])
def test_adjust_apply_writes_derivative_preserves_dimensions_and_undo_redo(
    tmp_path,
    suffix,
    mode,
):
    source = tmp_path / "assets" / "images" / f"photo.{suffix}"
    original_bytes = _write_image(source, mode=mode)
    run = InlineRun(
        image_src=f"../../assets/images/photo.{suffix}",
        image_alt="Légende",
        image_width="50%",
        image_height="80",
        image_align="right",
    )
    window, _path = _window_with_run(tmp_path, run)

    assert window.adjust_targeted_image(brightness=30, contrast=-20)

    adjusted_src = f"../../assets/images/photo-adjust1.{suffix}"
    adjusted_run = replace(run, image_src=adjusted_src)
    assert extract_blocks(window.editor.document()) == [
        Block(kind=PARAGRAPH, runs=[adjusted_run])
    ]
    assert source.read_bytes() == original_bytes
    assert source.with_name(f"photo-adjust1.{suffix}").is_file()
    assert window.editor.document().isModified()

    window.editor.undo()
    assert extract_blocks(window.editor.document()) == [Block(kind=PARAGRAPH, runs=[run])]
    assert source.with_name(f"photo-adjust1.{suffix}").is_file()
    assert not window.editor.document().isUndoAvailable()
    window.editor.redo()
    assert extract_blocks(window.editor.document()) == [
        Block(kind=PARAGRAPH, runs=[adjusted_run])
    ]
    _close_without_prompt(window)


def test_adjust_transparent_png_preserves_alpha(tmp_path):
    source = tmp_path / "assets" / "images" / "logo.png"
    source.parent.mkdir(parents=True)
    image = Image.new("RGBA", (4, 1))
    image.putdata([(20, 40, 60, alpha) for alpha in (0, 32, 128, 255)])
    image.save(source)
    run = InlineRun(image_src="../../assets/images/logo.png")
    window, _path = _window_with_run(tmp_path, run)

    assert window.adjust_targeted_image(brightness=60, contrast=30)

    with Image.open(source.with_name("logo-adjust1.png")) as adjusted:
        assert adjusted.getchannel("A").tobytes() == image.getchannel("A").tobytes()
    _close_without_prompt(window)


def test_adjust_write_failure_leaves_document_clean(tmp_path, monkeypatch):
    source = tmp_path / "assets" / "images" / "photo.png"
    _write_image(source)
    run = InlineRun(image_src="../../assets/images/photo.png", image_alt="")
    window, _path = _window_with_run(tmp_path, run)

    def fail_write(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(window_module, "write_adjusted_copy", fail_write)

    with pytest.raises(OSError, match="disk full"):
        window.adjust_targeted_image(brightness=10, contrast=0)
    assert extract_blocks(window.editor.document()) == [Block(kind=PARAGRAPH, runs=[run])]
    assert not window.editor.document().isModified()
    assert not window.editor.document().isUndoAvailable()
    _close_without_prompt(window)


def test_adjust_replace_failure_removes_only_new_derivative(tmp_path, monkeypatch):
    source = tmp_path / "assets" / "images" / "photo.png"
    original_bytes = _write_image(source)
    run = InlineRun(image_src="../../assets/images/photo.png", image_alt="")
    window, _path = _window_with_run(tmp_path, run)

    def fail_replace(*_args, **_kwargs):
        raise window_module.UnsupportedDocumentError("late failure")

    monkeypatch.setattr(window_module, "replace_merope_image", fail_replace)

    with pytest.raises(window_module.UnsupportedDocumentError, match="late failure"):
        window.adjust_targeted_image(brightness=10, contrast=0)
    assert source.read_bytes() == original_bytes
    assert list(source.parent.glob("photo-adjust*.png")) == []
    assert extract_blocks(window.editor.document()) == [Block(kind=PARAGRAPH, runs=[run])]
    assert not window.editor.document().isModified()
    assert not window.editor.document().isUndoAvailable()
    _close_without_prompt(window)


def test_adjusted_image_survives_save_and_reopen(tmp_path):
    source = tmp_path / "assets" / "images" / "photo.png"
    _write_image(source)
    run = InlineRun(
        image_src="../../assets/images/photo.png",
        image_alt="",
        image_width="42%",
    )
    window, path = _window_with_run(tmp_path, run)

    assert window.adjust_targeted_image(brightness=-15, contrast=25)
    changed = replace(run, image_src="../../assets/images/photo-adjust1.png")
    assert window.save_document()

    metadata, body = read_content_file(path)
    assert metadata == {"title": "Article"}
    assert markdown_to_blocks(body) == [Block(kind=PARAGRAPH, runs=[changed])]
    reopened = QTextDocument()
    load_content_document(path, reopened)
    assert extract_blocks(reopened) == [Block(kind=PARAGRAPH, runs=[changed])]
    window.close()
