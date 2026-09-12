from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QEvent, QPoint, QPointF, QSize, Qt, QUrl
from PySide6.QtGui import QColor, QImage, QMouseEvent, QTextCursor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMenu

from bloggen.content.image_size import resize_to_width
from bloggen.content.writer import read_content_file, write_content_file
from bloggen.markdown.rich_text_model import PARAGRAPH, Block, InlineRun
from bloggen.ui.qt_editor.document_adapter import extract_blocks, populate_document
from bloggen.ui.qt_editor.image_dialog import ImageMetadataDialog
from bloggen.ui.qt_editor.image_resize import (
    column_width,
    displayed_size,
    dragged_width,
    ghost_rect,
    size_label,
)
from bloggen.ui.qt_editor.image_selection import targeted_merope_image
from bloggen.ui.qt_editor.text_edit import MeropeTextEdit
from bloggen.ui.qt_editor.window import QtEditorWindow


@pytest.fixture(scope="module", autouse=True)
def qapplication():
    app = QApplication.instance() or QApplication([])
    yield app


def _write_image(path, width: int = 1600, height: int = 1000) -> bytes:
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


def _renderable_editor(tmp_path, run: InlineRun, *, size=(1600, 1000)) -> MeropeTextEdit:
    _write_image(tmp_path / run.image_src, *size)
    editor = MeropeTextEdit()
    editor.document().setBaseUrl(QUrl.fromLocalFile(f"{tmp_path}{os.sep}"))
    populate_document(editor.document(), [Block(kind=PARAGRAPH, runs=[run])])
    editor.resize(700, 900)
    editor.show()
    _select(editor, 0, 1)
    editor.document().setModified(False)
    return editor


def _move(widget, point: QPoint, modifiers=Qt.KeyboardModifier.NoModifier) -> None:
    event = QMouseEvent(
        QEvent.Type.MouseMove,
        QPointF(point),
        widget.mapToGlobal(QPointF(point)),
        Qt.MouseButton.NoButton,
        Qt.MouseButton.LeftButton,
        modifiers,
    )
    QApplication.sendEvent(widget, event)


def _drag(editor: MeropeTextEdit, handle: str, delta: QPoint, modifiers=Qt.KeyboardModifier.NoModifier):
    geometry = editor.image_resize_geometry()
    assert geometry is not None
    origin = geometry.handles[handle].center()
    viewport = editor.viewport()
    QTest.mousePress(viewport, Qt.MouseButton.LeftButton, modifiers, origin)
    _move(viewport, origin + delta, modifiers)
    QTest.mouseRelease(viewport, Qt.MouseButton.LeftButton, modifiers, origin + delta)
    QApplication.processEvents()
    return geometry


def _expected(editor, geometry, handle, delta, *, snap=True, align=None):
    return resize_to_width(
        dragged_width(geometry.image_rect.size(), delta, handle),
        column_width=column_width(editor.document()),
        natural_width=1600,
        align=align,
        snap=snap,
    )


# -- pure helpers ----------------------------------------------------------------


def test_dragged_width_follows_dominant_axis_for_each_corner():
    initial = QSize(400, 200)

    assert dragged_width(initial, QPoint(100, 0), "se") == 500
    assert dragged_width(initial, QPoint(100, 0), "sw") == 300
    assert dragged_width(initial, QPoint(0, 100), "se") == 600
    assert dragged_width(initial, QPoint(0, -50), "ne") == 500
    assert dragged_width(initial, QPoint(-5000, 0), "se") == 1


def test_ghost_keeps_the_opposite_corner_fixed_and_label_describes_result():
    from PySide6.QtCore import QRect

    image = QRect(100, 50, 400, 200)
    assert ghost_rect(image, "se", QSize(200, 100)) == QRect(100, 50, 200, 100)
    assert ghost_rect(image, "nw", QSize(200, 100)) == QRect(300, 150, 200, 100)

    outcome = resize_to_width(300, column_width=600, natural_width=1600)
    size = displayed_size(outcome, QSize(1600, 1000), 600, None)
    assert size == QSize(300, 188)
    assert size_label(outcome, size) == "50 % de la colonne · 300 × 188 px"


# -- interaction -----------------------------------------------------------------


def test_handle_requires_one_exact_renderable_image_selection(tmp_path):
    run = InlineRun(image_src="image.png")
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


def test_four_corner_handles_show_matching_cursors(tmp_path):
    editor = _renderable_editor(tmp_path, InlineRun(image_src="image.png", image_width="50%"))
    geometry = editor.image_resize_geometry()
    assert set(geometry.handles) == {"nw", "ne", "sw", "se"}

    expected = {
        "nw": Qt.CursorShape.SizeFDiagCursor,
        "se": Qt.CursorShape.SizeFDiagCursor,
        "ne": Qt.CursorShape.SizeBDiagCursor,
        "sw": Qt.CursorShape.SizeBDiagCursor,
    }
    for handle, shape in expected.items():
        QTest.mouseMove(editor.viewport(), geometry.handles[handle].center())
        assert editor.viewport().cursor().shape() == shape
    QTest.mouseMove(editor.viewport(), geometry.image_rect.bottomRight() + QPoint(60, 60))
    assert editor.viewport().cursor().shape() == Qt.CursorShape.IBeamCursor
    editor.close()


def test_missing_image_remains_selectable_but_has_no_resize_handle():
    run = InlineRun(image_src="missing.png", image_width="50%")
    editor = MeropeTextEdit()
    populate_document(editor.document(), [Block(kind=PARAGRAPH, runs=[run])])
    _select(editor, 0, 1)

    assert targeted_merope_image(editor.textCursor()).run == run
    assert editor.image_resize_geometry() is None


def test_drag_shows_a_ghost_and_writes_once_on_release(tmp_path):
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
    origin = geometry.handles["se"].center()
    delta = QPoint(-120, -80)
    expected = _expected(editor, geometry, "se", delta)

    QTest.mousePress(editor.viewport(), Qt.MouseButton.LeftButton, pos=origin)
    _move(editor.viewport(), origin + QPoint(-40, -20))
    _move(editor.viewport(), origin + delta)
    # While dragging, only the ghost moves: the document is untouched.
    assert extract_blocks(editor.document()) == original
    assert not editor.document().isModified()
    state = editor._image_resize_state
    assert state is not None and state.ghost is not None
    assert "% de la colonne" in state.label
    QTest.mouseRelease(editor.viewport(), Qt.MouseButton.LeftButton, pos=origin + delta)
    QApplication.processEvents()

    resized = targeted_merope_image(editor.textCursor()).run
    assert resized == InlineRun(
        image_src=run.image_src,
        image_alt=run.image_alt,
        image_width=expected.width_value,
        image_height=None,
        image_align=run.image_align,
    )
    assert resized.image_width.endswith("%")
    assert editor.document().isModified()
    assert (tmp_path / "image.png").read_bytes() == bitmap_before

    editor.undo()
    assert extract_blocks(editor.document()) == original
    assert not editor.document().isUndoAvailable()
    editor.redo()
    assert extract_blocks(editor.document()) == [Block(kind=PARAGRAPH, runs=[resized])]
    editor.close()


def test_every_corner_resizes_and_snapping_can_be_disabled_with_alt(tmp_path):
    editor = _renderable_editor(tmp_path, InlineRun(image_src="image.png", image_width="80%"))
    geometry = editor.image_resize_geometry()
    column = column_width(editor.document())
    # Aim a couple of pixels away from exactly 50 %.
    target_width = column * 0.5 + 6
    delta = QPoint(round(geometry.image_rect.width() - target_width), 0)

    _drag(editor, "nw", delta)
    snapped = targeted_merope_image(editor.textCursor()).run
    assert snapped.image_width == "50%"

    editor.undo()
    _select(editor, 0, 1)
    geometry = _drag(editor, "sw", delta, Qt.KeyboardModifier.AltModifier)
    free = targeted_merope_image(editor.textCursor()).run
    expected = _expected(editor, geometry, "sw", delta, snap=False)
    assert free.image_width == expected.width_value
    assert free.image_width != "50%"
    editor.close()


def test_small_image_cannot_be_enlarged_and_returns_to_natural_size(tmp_path):
    run = InlineRun(image_src="image.png", image_width="30%")
    editor = _renderable_editor(tmp_path, run, size=(300, 200))

    _drag(editor, "se", QPoint(900, 0))

    resized = targeted_merope_image(editor.textCursor()).run
    assert resized.image_width is None
    assert resized.image_height is None
    editor.close()


def test_floated_image_is_capped_at_half_the_column(tmp_path):
    run = InlineRun(image_src="image.png", image_width="30%", image_align="left")
    editor = _renderable_editor(tmp_path, run)

    _drag(editor, "se", QPoint(2000, 0))

    assert targeted_merope_image(editor.textCursor()).run.image_width == "50%"
    editor.close()


def test_escape_cancels_a_drag_without_touching_the_document(tmp_path):
    run = InlineRun(image_src="image.png", image_width="80%")
    editor = _renderable_editor(tmp_path, run)
    geometry = editor.image_resize_geometry()
    origin = geometry.handles["se"].center()

    QTest.mousePress(editor.viewport(), Qt.MouseButton.LeftButton, pos=origin)
    _move(editor.viewport(), origin + QPoint(-200, 0))
    QTest.keyClick(editor, Qt.Key.Key_Escape)
    QTest.mouseRelease(editor.viewport(), Qt.MouseButton.LeftButton, pos=origin + QPoint(-200, 0))

    assert extract_blocks(editor.document()) == [Block(kind=PARAGRAPH, runs=[run])]
    assert not editor.document().isModified()
    editor.close()


@pytest.mark.parametrize("delta", [QPoint(), QPoint(1, 1)])
def test_handle_click_without_effective_movement_is_a_clean_noop(tmp_path, delta):
    run = InlineRun(image_src="image.png", image_width="420", image_height="280")
    editor = _renderable_editor(tmp_path, run)
    geometry = editor.image_resize_geometry()
    point = geometry.handles["se"].center()

    QTest.mousePress(editor.viewport(), Qt.MouseButton.LeftButton, pos=point)
    if not delta.isNull():
        _move(editor.viewport(), point + delta)
    QTest.mouseRelease(editor.viewport(), Qt.MouseButton.LeftButton, pos=point + delta)

    assert extract_blocks(editor.document()) == [Block(kind=PARAGRAPH, runs=[run])]
    assert not editor.document().isModified()
    assert not editor.document().isUndoAvailable()
    editor.close()


def test_double_click_on_a_handle_restores_natural_size(tmp_path):
    run = InlineRun(image_src="image.png", image_width="40%", image_height="300")
    editor = _renderable_editor(tmp_path, run)
    geometry = editor.image_resize_geometry()

    QTest.mouseDClick(
        editor.viewport(), Qt.MouseButton.LeftButton, pos=geometry.handles["ne"].center()
    )

    resized = targeted_merope_image(editor.textCursor()).run
    assert (resized.image_width, resized.image_height) == (None, None)
    editor.close()


def test_size_menu_offers_column_shares_and_marks_current(tmp_path):
    run = InlineRun(image_src="image.png", image_width="50%")
    editor = _renderable_editor(tmp_path, run)
    target = targeted_merope_image(editor.textCursor())
    menu = QMenu()

    editor._add_image_size_menu(menu, target)

    size_menu = menu.actions()[0].menu()
    labels = [action.text() for action in size_menu.actions() if action.text()]
    assert labels == [
        "25 % de la colonne",
        "33 % de la colonne",
        "50 % de la colonne",
        "75 % de la colonne",
        "100 % de la colonne",
        "Taille réelle (limitée à la colonne)",
    ]
    checked = [action.text() for action in size_menu.actions() if action.isChecked()]
    assert checked == ["50 % de la colonne"]

    size_menu.actions()[0].trigger()
    assert targeted_merope_image(editor.textCursor()).run.image_width == "25%"
    assert editor.document().isModified()
    editor.close()


def test_size_menu_of_floated_image_stops_at_half(tmp_path):
    run = InlineRun(image_src="image.png", image_align="right")
    editor = _renderable_editor(tmp_path, run)
    menu = QMenu()

    editor._add_image_size_menu(menu, targeted_merope_image(editor.textCursor()))

    labels = [a.text() for a in menu.actions()[0].menu().actions() if a.text()]
    assert "75 % de la colonne" not in labels
    assert "50 % de la colonne" in labels
    editor.close()


def test_percent_width_renders_as_share_of_column(tmp_path):
    editor = _renderable_editor(tmp_path, InlineRun(image_src="image.png", image_width="50%"))
    geometry = editor.image_resize_geometry()

    column = column_width(editor.document())
    assert geometry.image_rect.width() == pytest.approx(column / 2, abs=2)
    editor.close()


def test_dialog_reads_percentage_produced_by_mouse_resize(tmp_path):
    editor = _renderable_editor(tmp_path, InlineRun(image_src="image.png", image_width="80%"))
    _drag(editor, "se", QPoint(-150, 0))
    resized = targeted_merope_image(editor.textCursor()).run

    dialog = ImageMetadataDialog(resized)

    assert f"{dialog.width_spin.value()}%" == resized.image_width
    assert not dialog.natural_check.isChecked()
    editor.close()


def test_resize_marks_window_dirty_and_survives_save_reopen(tmp_path):
    pages = tmp_path / "content" / "pages"
    images = tmp_path / "assets" / "images"
    images.mkdir(parents=True)
    _write_image(images / "photo.png")
    path = write_content_file(
        pages,
        "article.md",
        {"title": "Article"},
        "![Légende](../../assets/images/photo.png){width=420 height=280}\n",
    )
    window = QtEditorWindow(path, images_dir=images)
    window.resize(1800, 900)
    window.show()
    _select(window.editor, 0, 1)
    QApplication.processEvents()

    _drag(window.editor, "se", QPoint(-100, 0))
    resized = targeted_merope_image(window.editor.textCursor()).run
    assert window.windowTitle().endswith("*")
    assert window.save_document()

    _metadata, body = read_content_file(path)
    assert body.strip() == f"![Légende](../../assets/images/photo.png){{width={resized.image_width}}}"
    window.close()


def test_scroll_resize_and_repaint_never_mutate_image_data(tmp_path):
    run = InlineRun(image_src="image.png", image_width="50%")
    editor = _renderable_editor(tmp_path, run)

    editor.verticalScrollBar().setValue(20)
    editor.resize(500, 400)
    editor.viewport().repaint()
    QApplication.processEvents()

    assert extract_blocks(editor.document()) == [Block(kind=PARAGRAPH, runs=[run])]
    assert not editor.document().isModified()
    editor.close()
