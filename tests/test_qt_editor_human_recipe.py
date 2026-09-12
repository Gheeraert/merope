from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QMimeData, QPoint, QPointF, QRect, Qt
from PySide6.QtGui import QAction, QWheelEvent, QTextCursor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox

from bloggen.content.writer import write_content_file
from bloggen.markdown.rich_text_model import PARAGRAPH, Block, InlineRun
from bloggen.ui.qt_editor.clipboard_fragment import MEROPE_FRAGMENT_MIME
from bloggen.ui.qt_editor.document_adapter import extract_blocks, populate_document
from bloggen.ui.qt_editor.formatting import toggle_bold
from bloggen.ui.qt_editor.text_edit import MeropeTextEdit
from bloggen.ui.qt_editor.window import QtEditorWindow


@pytest.fixture(scope="module", autouse=True)
def qapplication():
    app = QApplication.instance() or QApplication([])
    yield app
    app.clipboard().clear()


def _wheel_event(*, control: bool, delta: int) -> QWheelEvent:
    return QWheelEvent(
        QPointF(8, 8),
        QPointF(8, 8),
        QPoint(),
        QPoint(0, delta),
        Qt.MouseButton.NoButton,
        (
            Qt.KeyboardModifier.ControlModifier
            if control
            else Qt.KeyboardModifier.NoModifier
        ),
        Qt.ScrollPhase.ScrollUpdate,
        False,
    )


def _show_with_editor_focus(window: QtEditorWindow) -> None:
    window.show()
    window.activateWindow()
    window.raise_()
    window.editor.setFocus()
    QApplication.processEvents()


def _select(editor: MeropeTextEdit, start: int, end: int) -> None:
    cursor = QTextCursor(editor.document())
    cursor.setPosition(start)
    cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
    editor.setTextCursor(cursor)


def _action(window: QtEditorWindow, label: str) -> QAction:
    return next(action for action in window.findChildren(QAction) if action.text() == label)


def test_ctrl_wheel_is_caught_on_real_viewport_and_plain_wheel_scrolls():
    editor = MeropeTextEdit()
    populate_document(
        editor.document(),
        [
            Block(kind=PARAGRAPH, runs=[InlineRun(text=f"Ligne {index}")])
            for index in range(100)
        ],
    )
    editor.document().setModified(False)
    editor.resize(320, 160)
    editor.show()
    QApplication.processEvents()
    scroll = editor.verticalScrollBar()
    assert scroll.maximum() > 0
    scroll.setValue(scroll.maximum() // 2)
    scroll_before = scroll.value()
    semantic_before = extract_blocks(editor.document())

    ctrl_event = _wheel_event(control=True, delta=15)
    QApplication.sendEvent(editor.viewport(), ctrl_event)

    assert ctrl_event.isAccepted()
    assert editor.zoom_percent == 110
    assert scroll.value() == scroll_before
    assert extract_blocks(editor.document()) == semantic_before
    assert not editor.document().isModified()
    assert not editor.document().isUndoAvailable()

    plain_event = _wheel_event(control=False, delta=-40)
    QApplication.sendEvent(editor.viewport(), plain_event)
    QApplication.processEvents()
    assert editor.zoom_percent == 110
    assert scroll.value() != scroll_before
    editor.close()


def test_real_format_nbsp_undo_redo_shortcuts_with_editor_focus():
    window = QtEditorWindow()
    populate_document(
        window.editor.document(),
        [Block(kind=PARAGRAPH, runs=[InlineRun(text="Bossuet")])],
    )
    window.editor.document().setModified(False)
    _show_with_editor_focus(window)

    _select(window.editor, 0, 7)
    QTest.keyClick(
        window.editor, Qt.Key.Key_I, Qt.KeyboardModifier.ControlModifier
    )
    assert extract_blocks(window.editor.document())[0].runs == [
        InlineRun(text="Bossuet", italic=True)
    ]

    QTest.keyClick(
        window.editor, Qt.Key.Key_G, Qt.KeyboardModifier.ControlModifier
    )
    assert extract_blocks(window.editor.document())[0].runs[0].bold
    QTest.keyClick(
        window.editor, Qt.Key.Key_B, Qt.KeyboardModifier.ControlModifier
    )
    assert not extract_blocks(window.editor.document())[0].runs[0].bold

    QTest.keyClick(
        window.editor, Qt.Key.Key_U, Qt.KeyboardModifier.ControlModifier
    )
    assert extract_blocks(window.editor.document())[0].runs == [
        InlineRun(text="Bossuet", italic=True, underline=True)
    ]
    assert window.italic_action.isChecked()
    assert window.underline_action.isChecked()
    assert not window.bold_action.isChecked()

    cursor = window.editor.textCursor()
    cursor.clearSelection()
    cursor.movePosition(QTextCursor.MoveOperation.End)
    window.editor.setTextCursor(cursor)
    QTest.keyClick(
        window.editor, Qt.Key.Key_Space, Qt.KeyboardModifier.ControlModifier
    )
    assert extract_blocks(window.editor.document())[0].runs[-1].text.endswith("\u00a0")

    QTest.keyClick(
        window.editor, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier
    )
    assert not extract_blocks(window.editor.document())[0].runs[-1].text.endswith("\u00a0")
    QTest.keyClick(
        window.editor, Qt.Key.Key_Y, Qt.KeyboardModifier.ControlModifier
    )
    assert extract_blocks(window.editor.document())[0].runs[-1].text.endswith("\u00a0")
    QTest.keyClick(
        window.editor, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier
    )
    QTest.keyClick(
        window.editor,
        Qt.Key.Key_Z,
        Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier,
    )
    assert extract_blocks(window.editor.document())[0].runs[-1].text.endswith("\u00a0")

    window.editor.document().setModified(False)
    window.close()


def test_real_copy_cut_paste_and_plain_paste_use_merope_paths():
    window = QtEditorWindow()
    populate_document(
        window.editor.document(),
        [
            Block(
                kind=PARAGRAPH,
                runs=[
                    InlineRun(text="A"),
                    InlineRun(footnote_ref="1"),
                    InlineRun(text="B"),
                ],
            )
        ],
    )
    window.editor.document().setModified(False)
    _show_with_editor_focus(window)

    _select(window.editor, 2, 3)  # only the digit inside [1]
    QTest.keyClick(
        window.editor, Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier
    )
    assert QApplication.clipboard().mimeData().hasFormat(MEROPE_FRAGMENT_MIME)
    cursor = window.editor.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.End)
    window.editor.setTextCursor(cursor)
    QTest.keyClick(
        window.editor, Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier
    )
    assert [
        run.footnote_ref
        for run in extract_blocks(window.editor.document())[0].runs
        if run.footnote_ref is not None
    ] == ["1", "1"]

    _select(window.editor, 2, 3)
    QTest.keyClick(
        window.editor, Qt.Key.Key_X, Qt.KeyboardModifier.ControlModifier
    )
    assert len(
        [
            run
            for run in extract_blocks(window.editor.document())[0].runs
            if run.footnote_ref is not None
        ]
    ) == 1

    mime = QMimeData()
    mime.setText(" brut")
    mime.setHtml("<strong> riche</strong>")
    QApplication.clipboard().setMimeData(mime)
    cursor = window.editor.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.End)
    window.editor.setTextCursor(cursor)
    QTest.keyClick(
        window.editor,
        Qt.Key.Key_V,
        Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier,
    )
    assert window.editor.toPlainText().endswith(" brut")
    assert not extract_blocks(window.editor.document())[0].runs[-1].bold

    window.editor.document().setModified(False)
    QApplication.clipboard().clear()
    window.close()


def test_undo_history_retains_twenty_five_distinct_actions_and_redo_alias():
    window = QtEditorWindow()
    populate_document(
        window.editor.document(),
        [Block(kind=PARAGRAPH, runs=[InlineRun(text="x" * 25)])],
    )
    window.editor.document().setModified(False)
    _show_with_editor_focus(window)

    for position in range(25):
        _select(window.editor, position, position + 1)
        toggle_bold(window.editor)
    assert all(run.bold for run in extract_blocks(window.editor.document())[0].runs)

    for _ in range(25):
        QTest.keyClick(
            window.editor, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier
        )
    assert extract_blocks(window.editor.document())[0].runs == [
        InlineRun(text="x" * 25)
    ]
    assert not window.editor.document().isUndoAvailable()

    for _ in range(25):
        QTest.keyClick(
            window.editor, Qt.Key.Key_Y, Qt.KeyboardModifier.ControlModifier
        )
    assert all(run.bold for run in extract_blocks(window.editor.document())[0].runs)

    window.editor.document().setModified(False)
    window.close()


def test_ordinary_save_preserves_undo_history_without_note_renumbering(
    tmp_path, monkeypatch
):
    path = write_content_file(
        tmp_path,
        "article.md",
        {"title": "Article", "slug": "article", "type": "page"},
        "Avant\n",
    )
    window = QtEditorWindow(path)
    cursor = window.editor.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.End)
    cursor.insertText(" après")
    window.editor.setTextCursor(cursor)
    assert window.editor.document().isUndoAvailable()
    _show_with_editor_focus(window)
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )

    QTest.keyClick(
        window.editor, Qt.Key.Key_S, Qt.KeyboardModifier.ControlModifier
    )
    QApplication.processEvents()
    assert window.editor.document().isUndoAvailable()
    saved = path.read_text(encoding="utf-8")
    assert "Avant après" in saved
    QTest.keyClick(
        window.editor, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier
    )
    assert window.editor.toPlainText() == "Avant"
    assert path.read_text(encoding="utf-8") == saved

    window.editor.document().setModified(False)
    window.close()


def test_responsive_toolbar_wraps_without_losing_actions_or_shortcuts():
    window = QtEditorWindow()
    toolbar = window.toolbar
    expected_actions = list(toolbar.actions_in_order)
    row_counts = []

    window.resize(920, 700)
    window.show()
    QApplication.processEvents()
    assert toolbar.width() > 800
    assert window.editor.height() > 100
    assert all(button.geometry().right() < toolbar.width() for button in toolbar.buttons)
    assert all(button.geometry().bottom() < toolbar.height() for button in toolbar.buttons)

    for width in (1200, 800, 500, 350):
        height = toolbar.heightForWidth(width)
        toolbar.resize(width, height)
        toolbar.flow_layout.setGeometry(QRect(0, 0, width, height))
        row_counts.append(toolbar.row_count_for_width(width))
        assert all(
            button.geometry().left() >= 0
            and button.geometry().right() < width
            for button in toolbar.buttons
        )

    assert row_counts == sorted(row_counts)
    assert row_counts[-1] > row_counts[0]
    assert toolbar.actions_in_order == expected_actions
    assert len(toolbar.buttons) == len(expected_actions)
    assert all(button.toolTip() for button in toolbar.buttons)
    assert all(not action.icon().isNull() for action in expected_actions)
    assert {sequence.toString() for sequence in _action(window, "Gras").shortcuts()} == {
        "Ctrl+G",
        "Ctrl+B",
    }
    assert {sequence.toString() for sequence in _action(window, "Retablir").shortcuts()} == {
        "Ctrl+Y",
        "Ctrl+Shift+Z",
    }
    window.close()
