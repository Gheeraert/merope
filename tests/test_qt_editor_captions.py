"""Image captions typed directly below a standalone image in the Qt editor."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QMimeData, Qt
from PySide6.QtGui import QTextCursor, QTextDocument
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from bloggen.content.writer import read_content_file, write_content_file
from bloggen.markdown.rich_text_model import HEADING, PARAGRAPH, Block, InlineRun
from bloggen.ui.qt_editor.clipboard_fragment import (
    MEROPE_FRAGMENT_MIME,
    decode_markdown_fragment,
    encode_selection_as_markdown,
)
from bloggen.ui.qt_editor.document_adapter import (
    UnsupportedDocumentError,
    caption_block_for_selection,
    extract_blocks,
    figure_caption_block,
    insert_blocks,
    insert_footnote_reference,
    is_caption_block,
    normalize_figure_captions,
    populate_document,
    selection_crosses_caption_boundary,
)
from bloggen.ui.qt_editor.formatting import set_heading, toggle_bold, toggle_underline
from bloggen.ui.qt_editor.image_selection import targeted_merope_image
from bloggen.ui.qt_editor.text_edit import MeropeTextEdit
from bloggen.ui.qt_editor.window import QtEditorWindow


@pytest.fixture(scope="module", autouse=True)
def qapplication():
    app = QApplication.instance() or QApplication([])
    yield app
    app.clipboard().clear()


@pytest.fixture(autouse=True)
def clean_clipboard(qapplication):
    # The offscreen clipboard crashes the interpreter at exit if it still
    # holds data (same convention as test_qt_editor_footnote_clipboard).
    qapplication.clipboard().clear()
    yield
    qapplication.clipboard().clear()


def _figure(alt: str | None = "**Bossuet** à *Meaux*") -> InlineRun:
    return InlineRun(image_src="missing.png", image_alt=alt)


def _blocks_with_figure(alt: str | None = "**Bossuet** à *Meaux*") -> list[Block]:
    return [
        Block(kind=PARAGRAPH, runs=[InlineRun(text="Avant")]),
        Block(kind=PARAGRAPH, runs=[_figure(alt)]),
        Block(kind=PARAGRAPH, runs=[InlineRun(text="Après")]),
    ]


def _qt_blocks(document: QTextDocument) -> list:
    blocks = []
    block = document.begin()
    while block.isValid():
        blocks.append(block)
        block = block.next()
    return blocks


def _editor(blocks: list[Block]) -> MeropeTextEdit:
    editor = MeropeTextEdit()
    populate_document(editor.document(), blocks)
    editor.resize(700, 500)
    editor.show()
    QApplication.processEvents()
    return editor


def _caption(document: QTextDocument):
    return next(block for block in _qt_blocks(document) if is_caption_block(block))


def _caret(editor: MeropeTextEdit, position: int, anchor: int | None = None) -> None:
    cursor = QTextCursor(editor.document())
    cursor.setPosition(position if anchor is None else anchor)
    if anchor is not None:
        cursor.setPosition(position, QTextCursor.MoveMode.KeepAnchor)
    editor.setTextCursor(cursor)


def _settle() -> None:
    QApplication.processEvents()
    QApplication.processEvents()


def _alt(document: QTextDocument) -> str | None:
    for block in extract_blocks(document):
        for run in block.runs:
            if run.image_src is not None:
                return run.image_alt
    raise AssertionError("aucune image")


# -- model round trip ------------------------------------------------------------


@pytest.mark.parametrize(
    "alt",
    ["**Bossuet** à *Meaux*", None, "", "a**b", "***Tout***", "5 * 3"],
)
def test_standalone_image_gets_an_editable_caption_and_round_trips(alt):
    document = QTextDocument()
    blocks = _blocks_with_figure(alt)

    populate_document(document, blocks)

    qt_blocks = _qt_blocks(document)
    assert [is_caption_block(block) for block in qt_blocks] == [False, False, True, False]
    assert extract_blocks(document) == blocks
    assert not document.isModified()


def test_caption_shows_markers_as_bold_and_italic_text():
    document = QTextDocument()
    populate_document(document, _blocks_with_figure())

    caption = _caption(document)

    assert caption.text() == "Bossuet à Meaux"
    formats = []
    iterator = caption.begin()
    while not iterator.atEnd():
        fragment = iterator.fragment()
        formats.append((fragment.text(), fragment.charFormat().fontWeight() > 400,
                        fragment.charFormat().fontItalic()))
        iterator += 1
    assert formats == [("Bossuet", True, False), (" à ", False, False), ("Meaux", False, True)]


def test_image_among_text_has_no_caption_block():
    document = QTextDocument()
    blocks = [Block(kind=PARAGRAPH, runs=[InlineRun(text="Voir "), _figure(), InlineRun(text=".")])]

    populate_document(document, blocks)

    assert not any(is_caption_block(block) for block in _qt_blocks(document))
    assert extract_blocks(document) == blocks


# -- typing in the caption ---------------------------------------------------------


def test_typing_in_caption_changes_alt_text_and_undoes_in_one_step():
    editor = _editor(_blocks_with_figure("Portrait"))
    caption = _caption(editor.document())
    _caret(editor, caption.position() + len("Portrait"))

    QTest.keyClicks(editor, " de Bossuet")
    _settle()

    assert _alt(editor.document()) == "Portrait de Bossuet"
    assert editor.document().isModified()
    editor.undo()
    _settle()
    assert _alt(editor.document()) == "Portrait"
    editor.close()


def test_bold_in_caption_is_saved_as_markers_but_underline_is_not_offered():
    editor = _editor(_blocks_with_figure("Portrait de Bossuet"))
    caption = _caption(editor.document())
    start = caption.position() + len("Portrait de ")
    _caret(editor, start + len("Bossuet"), anchor=start)

    toggle_bold(editor)
    toggle_underline(editor)
    set_heading(editor, 1)
    _settle()

    assert _alt(editor.document()) == "Portrait de **Bossuet**"
    assert is_caption_block(_caption(editor.document()))
    editor.close()


def test_enter_in_caption_opens_a_paragraph_after_the_figure():
    editor = _editor(_blocks_with_figure("Portrait"))
    caption = _caption(editor.document())
    _caret(editor, caption.position() + 3)

    QTest.keyClick(editor, Qt.Key.Key_Return)
    QTest.keyClicks(editor, "Suite")
    _settle()

    blocks = extract_blocks(editor.document())
    assert [block.runs[0].text or block.runs[0].image_alt for block in blocks] == [
        "Avant", "Portrait", "Suite", "Après"
    ]
    editor.close()


def test_backspace_and_delete_never_merge_a_caption():
    editor = _editor(_blocks_with_figure("Portrait"))
    document = editor.document()
    original = extract_blocks(document)
    caption = _caption(document)
    image_block = caption.previous()
    after = caption.next()

    _caret(editor, caption.position())
    QTest.keyClick(editor, Qt.Key.Key_Backspace)
    _caret(editor, caption.position() + caption.length() - 1)
    QTest.keyClick(editor, Qt.Key.Key_Delete)
    _caret(editor, after.position())
    QTest.keyClick(editor, Qt.Key.Key_Backspace)
    assert editor.textCursor().position() == caption.position() + caption.length() - 1
    _caret(editor, image_block.position() + image_block.length() - 1)
    QTest.keyClick(editor, Qt.Key.Key_Delete)
    assert editor.textCursor().position() == caption.position()
    _settle()

    assert extract_blocks(document) == original
    assert not document.isModified()
    editor.close()


def test_enter_after_the_image_opens_a_paragraph_below_the_caption():
    editor = _editor(_blocks_with_figure("Portrait"))
    caption = _caption(editor.document())
    image_block = caption.previous()
    _caret(editor, image_block.position() + 1)

    QTest.keyClick(editor, Qt.Key.Key_Return)
    _settle()

    assert editor.textCursor().block().previous() == _caption(editor.document())
    assert _alt(editor.document()) == "Portrait"
    editor.close()


def test_selection_straddling_a_caption_edge_is_refused():
    editor = _editor(_blocks_with_figure("Portrait"))
    document = editor.document()
    original = extract_blocks(document)
    caption = _caption(document)
    after = caption.next()
    _caret(editor, after.position() + 2, anchor=caption.position() + 3)

    assert selection_crosses_caption_boundary(editor.textCursor())
    QTest.keyClick(editor, Qt.Key.Key_Delete)
    QTest.keyClicks(editor, "x")
    _settle()

    assert extract_blocks(document) == original
    editor.close()


def test_real_backspace_inside_caption_after_century_deletes_without_control():
    editor = _editor(_blocks_with_figure("XVIIe siècle abc"))
    caption = _caption(editor.document())
    _caret(editor, caption.position() + caption.length() - 1)

    QTest.keyClick(editor, Qt.Key.Key_Backspace)
    _settle()

    assert _alt(editor.document()) == "XVIIe siècle ab"
    assert "\x08" not in caption.text()
    assert "\x7f" not in caption.text()
    editor.close()


@pytest.mark.parametrize("reverse_selection", [False, True])
def test_ctrl_space_refuses_caption_paragraph_boundary_without_undo(
    reverse_selection,
):
    window = QtEditorWindow()
    populate_document(window.editor.document(), _blocks_with_figure("Légende"))
    document = window.editor.document()
    document.setModified(False)
    caption = _caption(document)
    after = caption.next()
    separator = after.position() - 1
    start, end = (
        (after.position(), separator)
        if reverse_selection
        else (separator, after.position())
    )
    _caret(window.editor, end, anchor=start)
    before = extract_blocks(document)
    assert window.editor.textCursor().selectedText() == "\u2029"
    assert selection_crosses_caption_boundary(window.editor.textCursor())
    window.show()
    window.editor.setFocus()
    _settle()

    QTest.keyClick(
        window.editor,
        Qt.Key.Key_Space,
        Qt.KeyboardModifier.ControlModifier,
    )
    _settle()

    assert extract_blocks(document) == before
    assert not document.isModified()
    assert not document.isUndoAvailable()
    window.close()


def test_selection_covering_whole_figure_can_be_deleted():
    editor = _editor(_blocks_with_figure("Portrait"))
    document = editor.document()
    first = _qt_blocks(document)[0]
    after = _caption(document).next()
    _caret(editor, after.position() + 2, anchor=first.position() + 2)

    assert not selection_crosses_caption_boundary(editor.textCursor())
    QTest.keyClick(editor, Qt.Key.Key_Delete)
    _settle()

    assert extract_blocks(document) == [
        Block(kind=PARAGRAPH, runs=[InlineRun(text="Avrès")])
    ]
    assert not any(is_caption_block(block) for block in _qt_blocks(document))
    editor.close()


def test_paste_into_caption_keeps_only_flattened_text():
    editor = _editor(_blocks_with_figure("Portrait"))
    caption = _caption(editor.document())
    _caret(editor, caption.position() + len("Portrait"))
    mime = QMimeData()
    mime.setHtml("<p>de <b>Bossuet</b></p><p>à Meaux</p>")
    mime.setText(" de Bossuet\nà Meaux")

    editor.insertFromMimeData(mime)
    _settle()

    assert _alt(editor.document()) == "Portrait de Bossuet à Meaux"
    assert is_caption_block(_caption(editor.document()).previous()) is False
    editor.close()


def test_notes_and_structured_content_cannot_enter_a_caption():
    document = QTextDocument()
    populate_document(document, _blocks_with_figure("Portrait"))
    cursor = QTextCursor(document)
    cursor.setPosition(_caption(document).position() + 2)

    assert caption_block_for_selection(cursor) is not None
    with pytest.raises(UnsupportedDocumentError):
        insert_footnote_reference(cursor, "1")
    with pytest.raises(UnsupportedDocumentError):
        insert_blocks(cursor, [Block(kind=PARAGRAPH, runs=[_figure()])])


# -- keeping image and caption together ----------------------------------------------


def test_deleting_the_image_removes_its_caption_and_undo_restores_both():
    editor = _editor(_blocks_with_figure("Portrait"))
    document = editor.document()
    original = extract_blocks(document)
    image_block = _caption(document).previous()
    _caret(editor, image_block.position() + 1, anchor=image_block.position())

    QTest.keyClick(editor, Qt.Key.Key_Delete)
    _settle()

    assert not any(is_caption_block(block) for block in _qt_blocks(document))
    assert [block.runs[0].text for block in extract_blocks(document)] == ["Avant", "", "Après"]
    editor.undo()
    _settle()
    assert extract_blocks(document) == original
    assert is_caption_block(_caption(document))
    editor.close()


def test_text_typed_beside_the_image_turns_caption_into_alt_text():
    editor = _editor(_blocks_with_figure("Portrait"))
    document = editor.document()
    image_block = _caption(document).previous()
    _caret(editor, image_block.position() + 1)

    QTest.keyClicks(editor, " voir")
    _settle()

    assert not any(is_caption_block(block) for block in _qt_blocks(document))
    paragraph = extract_blocks(document)[1]
    assert paragraph.runs[0].image_alt == "Portrait"
    assert paragraph.runs[1].text == " voir"
    editor.close()


def test_image_left_alone_in_its_paragraph_gets_a_caption_back():
    editor = _editor(
        [Block(kind=PARAGRAPH, runs=[InlineRun(text="x"), _figure("Portrait")])]
    )
    document = editor.document()
    assert not any(is_caption_block(block) for block in _qt_blocks(document))
    _caret(editor, 1)

    QTest.keyClick(editor, Qt.Key.Key_Backspace)
    _settle()

    assert _caption(document).text() == "Portrait"
    assert _alt(document) == "Portrait"
    editor.undo()
    _settle()
    assert not any(is_caption_block(block) for block in _qt_blocks(document))
    editor.close()


def test_inserting_a_figure_brings_its_caption_in_the_same_undo_step():
    document = QTextDocument()
    populate_document(document, [])

    insert_blocks(QTextCursor(document), [Block(kind=PARAGRAPH, runs=[_figure("Vue")])])

    assert _caption(document).text() == "Vue"
    document.undo()
    assert not any(is_caption_block(block) for block in _qt_blocks(document))
    assert not document.isUndoAvailable()


def test_normalization_repairs_any_broken_pairing_and_is_idempotent():
    document = QTextDocument()
    populate_document(
        document,
        [Block(kind=HEADING, level=2, runs=[InlineRun(text="Titre")]), *_blocks_with_figure("A")],
    )
    caption = _caption(document)
    cursor = QTextCursor(caption)
    cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock)
    cursor.insertBlock(caption.blockFormat(), caption.charFormat())
    cursor.insertText("B")

    assert normalize_figure_captions(document)
    assert not normalize_figure_captions(document)
    assert _alt(document) == "A B"


# -- clipboard, dialog, saving ----------------------------------------------------------


def test_copying_the_image_alone_carries_its_current_caption():
    editor = _editor(_blocks_with_figure("Portrait"))
    caption = _caption(editor.document())
    _caret(editor, caption.position() + len("Portrait"))
    # (QTest.keyClicks aborts the process on non-ASCII characters.)
    QTest.keyClicks(editor, " revu")
    image_block = caption.previous()
    _caret(editor, image_block.position() + 1, anchor=image_block.position())

    editor.copy()

    payload = QApplication.clipboard().mimeData().data(MEROPE_FRAGMENT_MIME)
    (block,) = decode_markdown_fragment(payload)
    assert block.runs[0].image_alt == "Portrait revu"
    editor.close()


def test_cut_image_pastes_back_as_a_captioned_figure():
    editor = _editor(_blocks_with_figure("Portrait"))
    document = editor.document()
    image_block = _caption(document).previous()
    _caret(editor, image_block.position() + 1, anchor=image_block.position())

    editor.cut()
    _settle()
    assert not any(is_caption_block(block) for block in _qt_blocks(document))
    editor.paste()
    _settle()

    assert _caption(document).text() == "Portrait"
    assert _alt(document) == "Portrait"
    editor.close()


def test_copied_caption_words_stay_text():
    document = QTextDocument()
    populate_document(document, _blocks_with_figure("Portrait de Bossuet"))
    caption = _caption(document)
    cursor = QTextCursor(document)
    cursor.setPosition(caption.position())
    cursor.setPosition(caption.position() + len("Portrait"), QTextCursor.MoveMode.KeepAnchor)

    assert encode_selection_as_markdown(cursor).decode("utf-8").strip() == "Portrait"


def test_image_targets_and_dialog_see_the_typed_caption():
    editor = _editor(_blocks_with_figure("Portrait"))
    caption = _caption(editor.document())
    _caret(editor, caption.position() + len("Portrait"))
    QTest.keyClicks(editor, " nouveau")
    image_block = caption.previous()
    _caret(editor, image_block.position() + 1, anchor=image_block.position())

    target = targeted_merope_image(editor.textCursor())

    assert target.run.image_alt == "Portrait nouveau"
    editor.close()


def test_context_menu_caption_entry_moves_into_the_caption():
    editor = _editor(_blocks_with_figure("Portrait"))
    image_block = _caption(editor.document()).previous()

    assert editor.edit_figure_caption(image_block.position())

    selection = editor.textCursor()
    assert selection.selectedText() == "Portrait"
    assert caption_block_for_selection(selection) is not None
    editor.close()


def test_empty_caption_placeholder_paints_without_touching_the_document():
    editor = _editor(_blocks_with_figure(None))

    editor.viewport().repaint()
    editor.grab()

    assert extract_blocks(editor.document()) == _blocks_with_figure(None)
    assert not editor.document().isModified()
    editor.close()


def test_edited_caption_is_saved_as_alt_text_and_reopened(tmp_path):
    path = write_content_file(
        tmp_path / "content" / "pages",
        "article.md",
        {"title": "Article"},
        "Texte.\n\n![Portrait](../../assets/images/p.png)\n\nSuite.\n",
    )
    window = QtEditorWindow(path)
    window.show()
    _settle()
    caption = _caption(window.editor.document())
    cursor = QTextCursor(window.editor.document())
    cursor.setPosition(caption.position())
    cursor.setPosition(caption.position() + caption.length() - 1, QTextCursor.MoveMode.KeepAnchor)
    window.editor.setTextCursor(cursor)
    QTest.keyClicks(window.editor, "Portrait de ")
    start = window.editor.textCursor().position()
    QTest.keyClicks(window.editor, "Bossuet")
    _caret(window.editor, window.editor.textCursor().position(), anchor=start)
    toggle_bold(window.editor)
    _settle()

    assert window.save_document()

    _metadata, body = read_content_file(path)
    assert "![Portrait de **Bossuet**](../../assets/images/p.png)" in body
    reopened = QtEditorWindow(path)
    assert _caption(reopened.editor.document()).text() == "Portrait de Bossuet"
    reopened.close()
    window.close()


def test_ctrl_space_inside_caption_round_trips_and_undoes(tmp_path):
    path = write_content_file(
        tmp_path / "content" / "pages",
        "article.md",
        {"title": "Article"},
        "![Portrait de Bossuet](../../assets/images/p.png)\n",
    )
    window = QtEditorWindow(path)
    window.show()
    _settle()
    caption = _caption(window.editor.document())
    space = caption.position() + len("Portrait")
    _caret(window.editor, space + 1, anchor=space)
    window.editor.setFocus()

    QTest.keyClick(
        window.editor,
        Qt.Key.Key_Space,
        Qt.KeyboardModifier.ControlModifier,
    )
    _settle()

    expected_alt = f"Portrait\u00a0de Bossuet"
    assert _alt(window.editor.document()) == expected_alt
    assert is_caption_block(_caption(window.editor.document()))
    window.editor.undo()
    assert _alt(window.editor.document()) == "Portrait de Bossuet"
    window.editor.redo()
    assert _alt(window.editor.document()) == expected_alt
    assert window.save_document()

    reopened = QtEditorWindow(path)
    assert _alt(reopened.editor.document()) == expected_alt
    assert _caption(reopened.editor.document()).text() == expected_alt
    reopened.close()
    window.close()


def test_figure_caption_block_is_only_found_for_real_figures():
    document = QTextDocument()
    populate_document(document, _blocks_with_figure("A"))
    blocks = _qt_blocks(document)

    assert figure_caption_block(blocks[1]) == blocks[2]
    assert figure_caption_block(blocks[0]) is None
    assert figure_caption_block(blocks[2]) is None
