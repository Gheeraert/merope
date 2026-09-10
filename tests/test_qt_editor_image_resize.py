from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QPoint, QSize, Qt, QUrl
from PySide6.QtGui import QColor, QImage, QTextCursor, QTextDocument
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from bloggen.content.writer import read_content_file, write_content_file
from bloggen.markdown.rich_text_import import markdown_to_blocks
from bloggen.markdown.rich_text_model import PARAGRAPH, Block, InlineRun
from bloggen.ui.qt_editor.document_adapter import extract_blocks, populate_document
from bloggen.ui.qt_editor.file_io import load_content_document
from bloggen.ui.qt_editor.image_dialog import ImageMetadataDialog
from bloggen.ui.qt_editor.image_resize import (
    MIN_IMAGE_SIZE,
    ratio_preserving_size,
)
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


def _write_image(path, width: int = 420, height: int = 280) -> bytes:
    image = QImage(width, height, QImage.Format.Format_RGB32)
    image.fill(QColor("steelblue"))
    assert image.save(str(path), "PNG")
    return path.read_bytes()


def _select(editor: MeropeTextEdit, start: int, end: int | None = None) -> None:
    cursor = QTextCursor(editor.document())
    cursor.setPosition(start)
    if end is not None:
        cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
    editor.setTextCursor(cursor)
    QApplication.processEvents()


def _renderable_editor(tmp_path, run: InlineRun) -> MeropeTextEdit:
    _write_image(tmp_path / run.image_src)
    editor = MeropeTextEdit()
    editor.document().setBaseUrl(QUrl.fromLocalFile(f"{tmp_path}{os.sep}"))
    populate_document(editor.document(), [Block(kind=PARAGRAPH, runs=[run])])
    editor.resize(700, 440)
    editor.show()
    _select(editor, 0, 1)
    editor.document().setModified(False)
    return editor


def _drag_handle(editor: MeropeTextEdit, delta: QPoint) -> QSize:
    geometry = editor.image_resize_geometry()
    assert geometry is not None
    expected = ratio_preserving_size(geometry.image_rect.size(), delta)
    origin = geometry.handle_rect.center()
    destination = origin + delta
    QTest.mousePress(editor.viewport(), Qt.MouseButton.LeftButton, pos=origin)
    QTest.mouseMove(editor.viewport(), destination, delay=1)
    QTest.mouseRelease(
        editor.viewport(), Qt.MouseButton.LeftButton, pos=destination
    )
    QApplication.processEvents()
    return expected


def test_handle_requires_one_exact_renderable_image_selection(tmp_path):
    run = InlineRun(image_src="image.png", image_width="420", image_height="280")
    editor = _renderable_editor(tmp_path, run)

    assert editor.image_resize_geometry() is not None
    _select(editor, 0)
    assert editor.image_resize_geometry() is None

    populate_document(
        editor.document(),
        [Block(kind=PARAGRAPH, runs=[InlineRun(text="A"), run, InlineRun(text="B")])],
    )
    _select(editor, 0, 1)
    assert editor.image_resize_geometry() is None

    two_images = [run, InlineRun(image_src="image.png", image_alt="B")]
    populate_document(editor.document(), [Block(kind=PARAGRAPH, runs=two_images)])
    _select(editor, 0, 2)
    assert editor.image_resize_geometry() is None
    editor.close()


def test_pointer_uses_resize_cursor_only_over_handle(tmp_path):
    run = InlineRun(image_src="image.png", image_width="420", image_height="280")
    editor = _renderable_editor(tmp_path, run)
    geometry = editor.image_resize_geometry()
    assert geometry is not None

    QTest.mouseMove(editor.viewport(), geometry.handle_rect.center())
    assert editor.viewport().cursor().shape() == Qt.CursorShape.SizeFDiagCursor
    QTest.mouseMove(editor.viewport(), QPoint(1, 1))
    assert editor.viewport().cursor().shape() == Qt.CursorShape.IBeamCursor
    editor.close()


def test_missing_image_remains_selectable_but_has_no_resize_handle():
    run = InlineRun(
        image_src="missing.png", image_width="420", image_height="280"
    )
    editor = MeropeTextEdit()
    populate_document(editor.document(), [Block(kind=PARAGRAPH, runs=[run])])
    _select(editor, 0, 1)

    assert targeted_merope_image(editor.textCursor()).run == run
    assert editor.image_resize_geometry() is None


def test_ratio_calculation_uses_one_scale_and_preserves_minimum():
    assert ratio_preserving_size(QSize(420, 280), QPoint(-120, -80)) == QSize(
        300, 200
    )
    assert ratio_preserving_size(QSize(420, 280), QPoint(-1000, -1000)) == QSize(
        60, MIN_IMAGE_SIZE
    )
    assert ratio_preserving_size(QSize(300, 200), QPoint(0, 100)) == QSize(450, 300)


def test_real_mouse_drag_updates_only_dimensions_and_is_one_undo(tmp_path):
    run = InlineRun(
        image_src="image.png",
        image_alt="**Bossuet** à *Meaux*",
        image_width="420",
        image_height="280",
        image_align="center",
    )
    original = [Block(kind=PARAGRAPH, runs=[run])]
    editor = _renderable_editor(tmp_path, run)
    bitmap_before = (tmp_path / "image.png").read_bytes()
    geometry = editor.image_resize_geometry()
    assert geometry is not None
    origin = geometry.handle_rect.center()
    final_delta = QPoint(-120, -80)
    expected = ratio_preserving_size(geometry.image_rect.size(), final_delta)

    QTest.mousePress(editor.viewport(), Qt.MouseButton.LeftButton, pos=origin)
    for delta in (QPoint(-40, -20), QPoint(-80, -50), final_delta):
        QTest.mouseMove(editor.viewport(), origin + delta, delay=1)
    QTest.mouseRelease(
        editor.viewport(), Qt.MouseButton.LeftButton, pos=origin + final_delta
    )
    QApplication.processEvents()

    resized = targeted_merope_image(editor.textCursor()).run
    assert resized == InlineRun(
        image_src=run.image_src,
        image_alt=run.image_alt,
        image_width=str(expected.width()),
        image_height=str(expected.height()),
        image_align=run.image_align,
    )
    assert editor.document().isModified()
    assert (tmp_path / "image.png").read_bytes() == bitmap_before

    editor.undo()
    assert extract_blocks(editor.document()) == original
    assert not editor.document().isUndoAvailable()
    editor.redo()
    assert extract_blocks(editor.document()) == [Block(kind=PARAGRAPH, runs=[resized])]
    editor.close()


def test_activated_drag_keeps_following_pointer_back_below_threshold(tmp_path):
    run = InlineRun(image_src="image.png", image_width="420", image_height="280")
    original = [Block(kind=PARAGRAPH, runs=[run])]
    editor = _renderable_editor(tmp_path, run)
    geometry = editor.image_resize_geometry()
    assert geometry is not None
    origin = geometry.handle_rect.center()

    QTest.mousePress(editor.viewport(), Qt.MouseButton.LeftButton, pos=origin)
    QTest.mouseMove(editor.viewport(), origin + QPoint(-120, -80), delay=1)
    intermediate = targeted_merope_image(editor.textCursor()).run
    final_delta = QPoint(-1, -1)
    QTest.mouseMove(editor.viewport(), origin + final_delta, delay=1)
    QTest.mouseRelease(
        editor.viewport(), Qt.MouseButton.LeftButton, pos=origin + final_delta
    )

    expected = ratio_preserving_size(geometry.image_rect.size(), final_delta)
    final = targeted_merope_image(editor.textCursor()).run
    assert final != intermediate
    assert (final.image_width, final.image_height) == (
        str(expected.width()),
        str(expected.height()),
    )
    editor.undo()
    assert extract_blocks(editor.document()) == original
    assert not editor.document().isUndoAvailable()
    editor.redo()
    assert targeted_merope_image(editor.textCursor()).run == final
    editor.close()


def test_activated_drag_returning_to_origin_restores_original_metadata(tmp_path):
    run = InlineRun(
        image_src="image.png",
        image_alt="Légende",
        image_width="50%",
        image_height=None,
        image_align="center",
    )
    original = [Block(kind=PARAGRAPH, runs=[run])]
    editor = _renderable_editor(tmp_path, run)
    geometry = editor.image_resize_geometry()
    assert geometry is not None
    origin = geometry.handle_rect.center()

    QTest.mousePress(editor.viewport(), Qt.MouseButton.LeftButton, pos=origin)
    QTest.mouseMove(editor.viewport(), origin + QPoint(-120, -80), delay=1)
    assert targeted_merope_image(editor.textCursor()).run != run
    QTest.mouseMove(editor.viewport(), origin, delay=1)
    QTest.mouseRelease(editor.viewport(), Qt.MouseButton.LeftButton, pos=origin)

    assert extract_blocks(editor.document()) == original
    assert editor.document().isUndoAvailable()
    editor.undo()
    assert extract_blocks(editor.document()) == original
    assert not editor.document().isUndoAvailable()
    editor.redo()
    assert extract_blocks(editor.document()) == original
    editor.close()


def test_resize_converts_non_numeric_dimensions_to_explicit_pixels(tmp_path):
    run = InlineRun(
        image_src="image.png",
        image_alt="Image",
        image_width="50%",
        image_height=None,
        image_align="left",
    )
    editor = _renderable_editor(tmp_path, run)

    expected = _drag_handle(editor, QPoint(-60, -40))

    resized = targeted_merope_image(editor.textCursor()).run
    assert resized.image_width == str(expected.width())
    assert resized.image_height == str(expected.height())
    assert resized.image_src == run.image_src
    assert resized.image_alt == run.image_alt
    assert resized.image_align == run.image_align
    editor.close()


def test_drag_is_clamped_without_distorting_ratio(tmp_path):
    run = InlineRun(image_src="image.png", image_width="420", image_height="280")
    editor = _renderable_editor(tmp_path, run)

    _drag_handle(editor, QPoint(-1000, -1000))

    resized = targeted_merope_image(editor.textCursor()).run
    assert (resized.image_width, resized.image_height) == ("60", "40")
    editor.close()


@pytest.mark.parametrize("delta", [QPoint(), QPoint(1, 1)])
def test_handle_click_without_effective_movement_is_a_clean_noop(tmp_path, delta):
    run = InlineRun(image_src="image.png", image_width="420", image_height="280")
    editor = _renderable_editor(tmp_path, run)
    geometry = editor.image_resize_geometry()
    assert geometry is not None
    point = geometry.handle_rect.center()

    QTest.mousePress(editor.viewport(), Qt.MouseButton.LeftButton, pos=point)
    if not delta.isNull():
        QTest.mouseMove(editor.viewport(), point + delta, delay=1)
    QTest.mouseRelease(
        editor.viewport(), Qt.MouseButton.LeftButton, pos=point + delta
    )

    assert extract_blocks(editor.document()) == [Block(kind=PARAGRAPH, runs=[run])]
    assert not editor.document().isModified()
    assert not editor.document().isUndoAvailable()
    assert editor.viewport().cursor().shape() == Qt.CursorShape.IBeamCursor
    editor.close()


def test_dialog_reads_dimensions_produced_by_mouse_resize(tmp_path):
    run = InlineRun(image_src="image.png", image_width="420", image_height="280")
    editor = _renderable_editor(tmp_path, run)
    expected = _drag_handle(editor, QPoint(-120, -80))

    dialog = ImageMetadataDialog(targeted_merope_image(editor.textCursor()).run)

    assert dialog.width_edit.text() == str(expected.width())
    assert dialog.height_edit.text() == str(expected.height())
    editor.close()


def test_dialog_dimension_update_repositions_handle_from_canonical_format(tmp_path):
    run = InlineRun(image_src="image.png", image_width="420", image_height="280")
    editor = _renderable_editor(tmp_path, run)
    target = targeted_merope_image(editor.textCursor())
    dialog = ImageMetadataDialog(run)
    dialog.width_edit.setText("300")
    dialog.height_edit.setText("200")

    editor.setTextCursor(
        replace_merope_image(editor.document(), target, dialog.image_run())
    )
    QApplication.processEvents()

    geometry = editor.image_resize_geometry()
    assert geometry is not None
    assert geometry.image_rect.size() == QSize(300, 200)
    editor.close()


def test_resize_marks_window_dirty_and_survives_save_reopen(tmp_path):
    pages = tmp_path / "content" / "pages"
    image_path = pages / "image.png"
    pages.mkdir(parents=True)
    _write_image(image_path)
    body = "![**Bossuet**](image.png){width=420 height=280 align=center}\n"
    path = write_content_file(pages, "article.md", {"title": "Article"}, body)
    window = QtEditorWindow(path)
    window.resize(760, 520)
    window.show()
    _select(window.editor, 0, 1)

    expected = _drag_handle(window.editor, QPoint(-120, -80))
    resized = targeted_merope_image(window.editor.textCursor()).run

    assert window.editor.document().isModified()
    assert window.windowTitle().endswith("*")
    assert window.save_document()
    _metadata, saved = read_content_file(path)
    assert saved.strip() == (
        "![**Bossuet**](image.png)"
        f"{{width={expected.width()} height={expected.height()} align=center}}"
    )
    assert markdown_to_blocks(saved) == [Block(kind=PARAGRAPH, runs=[resized])]

    reopened = QTextDocument()
    load_content_document(path, reopened)
    assert extract_blocks(reopened) == [Block(kind=PARAGRAPH, runs=[resized])]
    window.close()


def test_scroll_resize_and_repaint_never_mutate_image_data(tmp_path):
    run = InlineRun(
        image_src="image.png",
        image_alt="Légende",
        image_width="420",
        image_height="280",
        image_align="right",
    )
    _write_image(tmp_path / "image.png")
    editor = MeropeTextEdit()
    editor.document().setBaseUrl(QUrl.fromLocalFile(f"{tmp_path}{os.sep}"))
    blocks = [
        *[
            Block(kind=PARAGRAPH, runs=[InlineRun(text=f"Paragraphe {index}")])
            for index in range(30)
        ],
        Block(kind=PARAGRAPH, runs=[run]),
    ]
    populate_document(editor.document(), blocks)
    editor.document().setModified(False)
    editor.resize(500, 180)
    editor.show()
    image_start = editor.document().lastBlock().position()
    _select(editor, image_start, image_start + 1)
    before = extract_blocks(editor.document())

    editor.verticalScrollBar().setValue(0)
    editor.viewport().update()
    editor.viewport().repaint()
    editor.resize(560, 220)
    QApplication.processEvents()

    assert extract_blocks(editor.document()) == before
    assert not editor.document().isModified()
    editor.close()
