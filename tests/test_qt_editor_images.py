from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor, QTextDocument, QTextImageFormat
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog

from bloggen.content.writer import read_content_file, write_content_file
from bloggen.markdown.rich_text_import import markdown_to_blocks
from bloggen.markdown.rich_text_model import PARAGRAPH, Block, InlineRun
from bloggen.ui.qt_editor.document_adapter import (
    UnsupportedInlineError,
    extract_blocks,
    populate_document,
)
from bloggen.ui.qt_editor.file_io import load_content_document
from bloggen.ui.qt_editor.image_dialog import ImageMetadataDialog
from bloggen.ui.qt_editor.image_selection import (
    merope_image_at_position,
    merope_images_in_selection,
    replace_merope_image,
    targeted_merope_image,
)
from bloggen.ui.qt_editor.text_edit import MeropeTextEdit
from bloggen.ui.qt_editor import window as window_module
from bloggen.ui.qt_editor.window import QtEditorWindow


@pytest.fixture(scope="module", autouse=True)
def qapplication():
    app = QApplication.instance() or QApplication([])
    yield app


def _editor(blocks: list[Block]) -> MeropeTextEdit:
    editor = MeropeTextEdit()
    populate_document(editor.document(), blocks)
    editor.document().setModified(False)
    return editor


def _select(editor: MeropeTextEdit, start: int, end: int | None = None) -> None:
    cursor = QTextCursor(editor.document())
    cursor.setPosition(start)
    if end is not None:
        cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
    editor.setTextCursor(cursor)


def _first_image_format(document: QTextDocument) -> QTextImageFormat:
    iterator = document.begin().begin()
    while not iterator.atEnd():
        fragment = iterator.fragment()
        if fragment.isValid() and fragment.charFormat().isImageFormat():
            return QTextImageFormat(fragment.charFormat())
        iterator += 1
    raise AssertionError("Aucune image Qt")


def _mixed_image_block() -> tuple[list[Block], InlineRun]:
    image = InlineRun(
        image_src="missing.png",
        image_alt="**Bossuet** à *Meaux*",
        image_width="40",
        image_height="20",
        image_align="center",
    )
    return [
        Block(
            kind=PARAGRAPH,
            runs=[InlineRun(text="A"), image, InlineRun(text="B")],
        )
    ], image


def test_image_position_and_exact_or_mixed_selection_are_resolved():
    blocks, image = _mixed_image_block()
    editor = _editor(blocks)

    assert merope_image_at_position(editor.document(), 0) is None
    target = merope_image_at_position(editor.document(), 1)
    assert target is not None
    assert (target.start, target.end, target.run) == (1, 2, image)

    _select(editor, 1)
    assert targeted_merope_image(editor.textCursor()) == target
    _select(editor, 2)
    assert targeted_merope_image(editor.textCursor()) == target
    _select(editor, 1, 2)
    assert targeted_merope_image(editor.textCursor()) == target
    _select(editor, 0, 2)
    assert targeted_merope_image(editor.textCursor()) == target


def test_two_adjacent_images_are_unambiguous_only_when_exactly_selected():
    image_a = InlineRun(image_src="a.png", image_alt="A")
    image_b = InlineRun(image_src="b.png", image_alt="B")
    editor = _editor([Block(kind=PARAGRAPH, runs=[image_a, image_b])])

    _select(editor, 1)
    assert targeted_merope_image(editor.textCursor()) is None
    _select(editor, 0, 1)
    assert targeted_merope_image(editor.textCursor()).run == image_a
    _select(editor, 1, 2)
    assert targeted_merope_image(editor.textCursor()).run == image_b
    _select(editor, 0, 2)
    assert targeted_merope_image(editor.textCursor()) is None
    assert len(merope_images_in_selection(editor.textCursor())) == 2
    assert extract_blocks(editor.document())[0].runs == [image_a, image_b]


def test_two_identical_adjacent_images_remain_two_semantic_runs():
    image = InlineRun(image_src="same.png", image_alt="Même image")
    editor = _editor([Block(kind=PARAGRAPH, runs=[image, image])])

    assert extract_blocks(editor.document())[0].runs == [image, image]


def test_foreign_qt_image_is_not_recognized_as_merope():
    document = QTextDocument()
    cursor = QTextCursor(document)
    cursor.insertImage("foreign.png")

    with pytest.raises(UnsupportedInlineError, match="etrangere"):
        merope_image_at_position(document, 0)


def test_mouse_click_on_image_selects_exact_object(qapplication):
    blocks, image = _mixed_image_block()
    editor = _editor(blocks)
    editor.resize(360, 120)
    editor.show()
    qapplication.processEvents()
    start = QTextCursor(editor.document())
    start.setPosition(1)
    end = QTextCursor(editor.document())
    end.setPosition(2)
    start_rect = editor.cursorRect(start)
    end_rect = editor.cursorRect(end)
    point = start_rect.center()
    point.setX((start_rect.center().x() + end_rect.center().x()) // 2)

    QTest.mouseClick(editor.viewport(), Qt.MouseButton.LeftButton, pos=point)

    target = targeted_merope_image(editor.textCursor())
    assert target is not None
    assert target.run == image
    assert (editor.textCursor().selectionStart(), editor.textCursor().selectionEnd()) == (
        1,
        2,
    )
    editor.close()


def test_click_in_text_keeps_normal_qtextedit_selection(qapplication):
    blocks, _image = _mixed_image_block()
    editor = _editor(blocks)
    editor.resize(360, 120)
    editor.show()
    qapplication.processEvents()
    text_cursor = QTextCursor(editor.document())
    text_cursor.setPosition(0)
    point = editor.cursorRect(text_cursor).center()

    QTest.mouseClick(editor.viewport(), Qt.MouseButton.LeftButton, pos=point)

    assert not editor.textCursor().hasSelection()
    editor.close()


@pytest.mark.parametrize(
    "run",
    [
        InlineRun(
            image_src="image.png",
            image_alt="",
            image_width="50%",
            image_height=None,
            image_align=None,
        ),
        InlineRun(
            image_src="image.png",
            image_alt=None,
            image_width="",
            image_height="",
            image_align="left",
        ),
    ],
)
def test_dialog_preserves_untouched_none_and_empty_values_exactly(run):
    dialog = ImageMetadataDialog(run)

    assert dialog.src_edit.isReadOnly()
    assert dialog.image_run() == run


def test_dialog_modifies_caption_dimensions_and_alignment_without_parsing_markdown():
    run = InlineRun(
        image_src="image.png",
        image_alt="Ancienne",
        image_width="420",
        image_height="300",
        image_align="center",
    )
    dialog = ImageMetadataDialog(run)

    dialog.alt_edit.setText("**Bossuet** à *Meaux*")
    dialog.width_edit.setText("50%")
    dialog.height_edit.clear()
    dialog.align_combo.setCurrentIndex(dialog.align_combo.findData("right"))

    assert dialog.image_run() == InlineRun(
        image_src="image.png",
        image_alt="**Bossuet** à *Meaux*",
        image_width="50%",
        image_height=None,
        image_align="right",
    )


@pytest.mark.parametrize("alignment", [None, "left", "center", "right"])
def test_dialog_maps_every_alignment_value_exactly(alignment):
    dialog = ImageMetadataDialog(InlineRun(image_src="image.png"))
    dialog.align_combo.setCurrentIndex(dialog.align_combo.findData(alignment))

    assert dialog.image_run().image_align == alignment


def test_dialog_explicitly_cleared_dimensions_become_none_and_caption_becomes_empty():
    dialog = ImageMetadataDialog(
        InlineRun(
            image_src="image.png",
            image_alt="Légende",
            image_width="420",
            image_height="300",
        )
    )

    dialog.alt_edit.clear()
    dialog.width_edit.clear()
    dialog.height_edit.clear()

    result = dialog.image_run()
    assert result.image_alt == ""
    assert result.image_width is None
    assert result.image_height is None


def test_replacement_uses_fresh_format_clears_visual_size_and_is_one_undo():
    old = InlineRun(
        image_src="missing.png",
        image_alt="Ancienne",
        image_width="420",
        image_height="300",
        image_align="center",
    )
    new = InlineRun(
        image_src="missing.png",
        image_alt="Nouvelle",
        image_width="50%",
        image_height=None,
        image_align="right",
    )
    original = [Block(kind=PARAGRAPH, runs=[old])]
    editor = _editor(original)
    _select(editor, 0, 1)
    target = targeted_merope_image(editor.textCursor())

    editor.setTextCursor(replace_merope_image(editor.document(), target, new))

    assert extract_blocks(editor.document()) == [Block(kind=PARAGRAPH, runs=[new])]
    image_format = _first_image_format(editor.document())
    assert image_format.width() == 0
    assert image_format.height() == 0
    editor.undo()
    assert extract_blocks(editor.document()) == original
    editor.redo()
    assert extract_blocks(editor.document()) == [Block(kind=PARAGRAPH, runs=[new])]


def test_numeric_dimension_update_refreshes_native_image_size():
    old = InlineRun(image_src="missing.png", image_width="420", image_height="300")
    new = InlineRun(image_src="missing.png", image_width="300", image_height="180")
    editor = _editor([Block(kind=PARAGRAPH, runs=[old])])
    _select(editor, 0, 1)

    target = targeted_merope_image(editor.textCursor())
    editor.setTextCursor(replace_merope_image(editor.document(), target, new))

    image_format = _first_image_format(editor.document())
    assert image_format.width() == 300
    assert image_format.height() == 180
    assert extract_blocks(editor.document()) == [Block(kind=PARAGRAPH, runs=[new])]


def test_unchanged_replacement_is_noop_without_dirty_or_undo():
    run = InlineRun(image_src="missing.png", image_alt="")
    editor = _editor([Block(kind=PARAGRAPH, runs=[run])])
    _select(editor, 0, 1)
    target = targeted_merope_image(editor.textCursor())

    editor.setTextCursor(replace_merope_image(editor.document(), target, run))

    assert editor.document().isModified() is False
    assert editor.document().isUndoAvailable() is False


def test_window_modifies_only_targeted_image_and_updates_action_state():
    image_a = InlineRun(image_src="a.png", image_alt="A")
    image_b = InlineRun(image_src="b.png", image_alt="B")
    window = QtEditorWindow()
    populate_document(
        window.editor.document(),
        [
            Block(
                kind=PARAGRAPH,
                runs=[image_a, InlineRun(text=" milieu "), image_b],
            )
        ],
    )
    _select(window.editor, 0, 1)
    window._update_image_action()
    replacement = InlineRun(image_src="a.png", image_alt="A modifiée", image_align="left")

    assert window.image_action.isEnabled()
    assert window.replace_targeted_image(replacement) is True
    assert extract_blocks(window.editor.document())[0].runs == [
        replacement,
        InlineRun(text=" milieu "),
        image_b,
    ]
    _select(window.editor, 0, window.editor.document().characterCount() - 1)
    window._update_image_action()
    assert window.image_action.isEnabled() is False
    assert window._edit_targeted_image() is False


def test_window_image_action_uses_dialog_result(monkeypatch):
    old = InlineRun(image_src="a.png", image_alt="Ancienne", image_width="420")
    new = InlineRun(image_src="a.png", image_alt="Bossuet", image_width="300")
    window = QtEditorWindow()
    populate_document(
        window.editor.document(),
        [Block(kind=PARAGRAPH, runs=[old])],
    )
    _select(window.editor, 0, 1)

    class FakeDialog:
        def __init__(self, run, parent):
            assert run == old
            assert parent is window

        def exec(self):
            return QDialog.DialogCode.Accepted

        def image_run(self):
            return new

    monkeypatch.setattr(window_module, "ImageMetadataDialog", FakeDialog)

    assert window._edit_targeted_image() is True
    assert extract_blocks(window.editor.document())[0].runs == [new]


def test_missing_image_metadata_edit_sets_dirty_saves_and_reopens(tmp_path):
    body = (
        "![**Bossuet** à Meaux](../../assets/images/missing.jpg)"
        "{width=420 align=center}\n"
    )
    path = write_content_file(tmp_path / "content" / "pages", "article.md", {}, body)
    window = QtEditorWindow(path)
    _select(window.editor, 0, 1)
    new = InlineRun(
        image_src="../../assets/images/missing.jpg",
        image_alt="Bossuet à Meaux",
        image_width="300",
        image_align="right",
    )

    assert window.replace_targeted_image(new) is True
    assert window.editor.document().isModified()
    assert window.windowTitle().endswith("*")
    assert window.save_document() is True

    _metadata, saved_body = read_content_file(path)
    assert saved_body.strip() == (
        "![Bossuet à Meaux](../../assets/images/missing.jpg)"
        "{width=300 align=right}"
    )
    assert markdown_to_blocks(saved_body) == [Block(kind=PARAGRAPH, runs=[new])]
    reopened = QTextDocument()
    load_content_document(path, reopened)
    assert extract_blocks(reopened) == [Block(kind=PARAGRAPH, runs=[new])]
    assert window.editor.document().isModified() is False


@pytest.mark.parametrize("key", [Qt.Key.Key_Delete, Qt.Key.Key_Backspace])
def test_selected_image_delete_undo_redo_keeps_physical_file(tmp_path, key):
    physical = tmp_path / "image.png"
    physical.write_bytes(b"not deleted")
    image = InlineRun(image_src="image.png", image_alt="Image")
    original = [Block(kind=PARAGRAPH, runs=[image])]
    editor = _editor(original)
    editor.show()
    _select(editor, 0, 1)

    QTest.keyClick(editor, key)

    empty = [Block(kind=PARAGRAPH, runs=[InlineRun(text="")])]
    assert extract_blocks(editor.document()) == empty
    assert physical.is_file()
    editor.undo()
    assert extract_blocks(editor.document()) == original
    editor.redo()
    assert extract_blocks(editor.document()) == empty
    assert physical.is_file()
    editor.close()
