"""Encadré (BOX) in the Qt editor: adapter, toolbar action, boundary guards."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QMimeData, Qt
from PySide6.QtGui import QTextCursor, QTextDocument, QTextFrameFormat
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog

from bloggen.markdown.rich_text_export import blocks_to_markdown
from bloggen.markdown.rich_text_import import markdown_to_blocks
from bloggen.markdown.rich_text_model import (
    BLOCKQUOTE,
    BOX,
    BULLET_LIST,
    HEADING,
    LIST_ITEM,
    PARAGRAPH,
    VERBATIM,
    Block,
    InlineRun,
)
from bloggen.ui.qt_editor.box_structure import can_insert_box, insert_empty_box
from bloggen.ui.qt_editor.constants import (
    BLOCK_KIND_PROPERTY,
    BOX_BORDER_WIDTH,
    BOX_TITLE_KIND,
    MEROPE_BOX_PROPERTY,
)
from bloggen.ui.qt_editor.document_adapter import (
    UnsupportedBlockError,
    box_frame_at,
    extract_blocks,
    insert_blocks,
    is_merope_box_frame,
    populate_document,
    validate_block_insertion,
)
from bloggen.ui.qt_editor.formatting import set_heading
from bloggen.ui.qt_editor.text_edit import MeropeTextEdit
from bloggen.ui.qt_editor.window import QtEditorWindow
import bloggen.ui.qt_editor.window as window_module

_WIDGETS = []


@pytest.fixture(scope="module", autouse=True)
def qapplication():
    app = QApplication.instance() or QApplication([])
    yield app
    app.clipboard().clear()


@pytest.fixture(autouse=True)
def close_widgets(qapplication):
    yield
    for widget in _WIDGETS:
        if isinstance(widget, QtEditorWindow):
            widget.autosave_timer.stop()
        widget.hide()
        widget.deleteLater()
    _WIDGETS.clear()
    qapplication.processEvents()


def _p(text: str) -> Block:
    return Block(kind=PARAGRAPH, runs=[InlineRun(text=text)])


def _box(title: str | None, *children: Block) -> Block:
    return Block(
        kind=BOX,
        runs=[InlineRun(text=title)] if title else [],
        children=list(children),
    )


def _editor(blocks: list[Block]) -> MeropeTextEdit:
    editor = MeropeTextEdit()
    _WIDGETS.append(editor)
    populate_document(editor.document(), blocks)
    editor.show()
    editor.activateWindow()
    editor.setFocus()
    QApplication.processEvents()
    return editor


def _window(blocks: list[Block] | None = None) -> QtEditorWindow:
    window = QtEditorWindow()
    _WIDGETS.append(window)
    if blocks is not None:
        populate_document(window.editor.document(), blocks)
    window.show()
    window.activateWindow()
    window.editor.setFocus()
    QApplication.processEvents()
    return window


def _caret(editor, position: int) -> None:
    cursor = QTextCursor(editor.document())
    cursor.setPosition(position)
    editor.setTextCursor(cursor)
    QApplication.processEvents()


def _select(editor, start: int, end: int) -> None:
    cursor = QTextCursor(editor.document())
    cursor.setPosition(start)
    cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
    editor.setTextCursor(cursor)
    QApplication.processEvents()


def _position_of(editor, text: str, *, end: bool = False) -> int:
    # Real document positions: frame delimiters count, plain text hides them.
    found = editor.document().find(text)
    assert not found.isNull()
    return found.selectionEnd() if end else found.selectionStart()


def _box_frame(document: QTextDocument):
    frames = [f for f in document.rootFrame().childFrames() if is_merope_box_frame(f)]
    assert len(frames) == 1
    return frames[0]


# --- adapter round trip -----------------------------------------------------


@pytest.mark.parametrize(
    "blocks",
    [
        [_box("À retenir", _p("Un."), _p("Deux."))],
        [_box(None, _p("Seul."))],
        [_p("Avant"), _box("T", _p("x")), _p("Après")],
        [_box("A", _p("a")), _box(None, _p("b"))],
        [
            _box(
                "Mixte",
                Block(kind=PARAGRAPH, runs=[InlineRun(text="gras", bold=True)]),
                Block(kind=BLOCKQUOTE, runs=[InlineRun(text="Citation")]),
                Block(
                    kind=BULLET_LIST,
                    children=[Block(kind=LIST_ITEM, runs=[InlineRun(text="a")])],
                ),
                _p("Fin."),
            )
        ],
        [_box("T", Block(kind=PARAGRAPH, runs=[InlineRun(footnote_ref="1")]))],
    ],
)
def test_box_round_trips_through_the_qt_document(blocks):
    document = QTextDocument()
    populate_document(document, blocks)

    assert extract_blocks(document) == blocks


def test_qt_to_markdown_and_back_is_equivalent():
    blocks = [_p("Avant"), _box("Titre", _p("Un."), _p("Deux.")), _p("Après")]
    document = QTextDocument()
    populate_document(document, blocks)

    markdown = blocks_to_markdown(extract_blocks(document))
    again = QTextDocument()
    populate_document(again, markdown_to_blocks(markdown))

    assert extract_blocks(again) == blocks


def test_frame_carries_merope_properties_and_reflects_the_theme_look():
    document = QTextDocument()
    populate_document(document, [_box("Titre", _p("Corps"))])

    frame = _box_frame(document)
    frame_format = frame.frameFormat()
    assert frame_format.property(MEROPE_BOX_PROPERTY) is True
    assert frame_format.border() == BOX_BORDER_WIDTH == 1.0
    assert frame_format.borderStyle() == QTextFrameFormat.BorderStyle.BorderStyle_Solid
    assert frame_format.leftMargin() > 0 and frame_format.rightMargin() > 0
    assert frame_format.padding() > 0
    title = document.findBlock(frame.firstPosition())
    assert title.blockFormat().property(BLOCK_KIND_PROPERTY) == BOX_TITLE_KIND
    assert title.blockFormat().alignment() == Qt.AlignmentFlag.AlignHCenter
    # Purely visual: the semantic bold flag is not set on the title.
    assert extract_blocks(document)[0].runs[0].bold is False


def test_foreign_frames_are_still_refused_even_if_they_look_like_a_box():
    document = QTextDocument()
    cursor = QTextCursor(document)
    cursor.insertText("Avant")
    lookalike = QTextFrameFormat()
    lookalike.setBorder(1.0)
    lookalike.setPadding(12.0)
    lookalike.setBorderStyle(QTextFrameFormat.BorderStyle.BorderStyle_Solid)
    cursor.insertFrame(lookalike)
    cursor.insertText("Dedans")

    with pytest.raises(UnsupportedBlockError):
        extract_blocks(document)


def test_marker_is_required_not_appearance():
    document = QTextDocument()
    populate_document(document, [_box("T", _p("x"))])
    frame = _box_frame(document)
    unmarked = frame.frameFormat()
    unmarked.clearProperty(MEROPE_BOX_PROPERTY)
    frame.setFrameFormat(unmarked)

    assert not is_merope_box_frame(frame)
    with pytest.raises(UnsupportedBlockError):
        extract_blocks(document)


@pytest.mark.parametrize(
    "child",
    [
        Block(kind=HEADING, level=2, runs=[InlineRun(text="H")]),
        Block(kind=VERBATIM, raw_text="```\ncode\n```"),
        _p("x"),
    ],
)
def test_box_content_outside_the_supported_subset_is_refused(child):
    document = QTextDocument()
    box = _box("T", child)
    if child.kind == PARAGRAPH:
        box = _box("T", Block(kind=PARAGRAPH, runs=[InlineRun(image_src="a.png")]))
    with pytest.raises(UnsupportedBlockError):
        populate_document(document, [box])


def test_nested_box_and_multiline_title_are_refused():
    document = QTextDocument()
    with pytest.raises(UnsupportedBlockError):
        populate_document(document, [_box("T", _box("U", _p("x")))])
    with pytest.raises(UnsupportedBlockError):
        populate_document(document, [_box("a\nb", _p("x"))])


# --- toolbar action ------------------------------------------------------------


class _AcceptedBoxDialog:
    def __init__(self, parent=None, title: str = "À retenir") -> None:
        self._title = title

    def exec(self):
        return QDialog.DialogCode.Accepted

    def title(self) -> str:
        return self._title


class _RejectedBoxDialog(_AcceptedBoxDialog):
    def exec(self):
        return QDialog.DialogCode.Rejected


def test_toolbar_action_exists_with_icon_and_inserts_a_titled_box(monkeypatch):
    monkeypatch.setattr(window_module, "BoxInsertDialog", _AcceptedBoxDialog)
    window = _window([_p("Avant")])
    _caret(window.editor, len("Avant"))
    action = window.insert_box_action

    assert action.text() == "Insérer un encadré…"
    assert action.isEnabled() and not action.icon().isNull()
    action.trigger()
    QApplication.processEvents()

    assert extract_blocks(window.editor.document()) == [
        _p("Avant"),
        Block(kind=BOX, runs=[InlineRun(text="À retenir")], children=[_p("")]),
    ]
    assert box_frame_at(window.editor.textCursor()) is not None
    assert window.editor.document().isModified()
    window.editor.undo()
    assert extract_blocks(window.editor.document()) == [_p("Avant")]
    window.editor.redo()
    assert len(extract_blocks(window.editor.document())) == 2


def test_the_title_is_optional(monkeypatch):
    monkeypatch.setattr(
        window_module, "BoxInsertDialog", lambda parent: _AcceptedBoxDialog(parent, "")
    )
    window = _window()

    window.insert_box_action.trigger()

    assert extract_blocks(window.editor.document()) == [
        Block(kind=BOX, runs=[], children=[_p("")])
    ]
    assert box_frame_at(window.editor.textCursor()) is not None


def test_cancelled_dialog_does_not_mutate(monkeypatch):
    monkeypatch.setattr(window_module, "BoxInsertDialog", _RejectedBoxDialog)
    window = _window([_p("Texte")])

    window.insert_box_action.trigger()

    assert extract_blocks(window.editor.document()) == [_p("Texte")]
    assert not window.editor.document().isModified()


def test_user_can_type_several_paragraphs_after_insertion(monkeypatch):
    monkeypatch.setattr(window_module, "BoxInsertDialog", _AcceptedBoxDialog)
    window = _window()
    window.insert_box_action.trigger()

    QTest.keyClicks(window.editor, "Premier")
    QTest.keyClick(window.editor, Qt.Key.Key_Return)
    QTest.keyClicks(window.editor, "Deuxieme")

    assert extract_blocks(window.editor.document()) == [
        _box("À retenir", _p("Premier"), _p("Deuxieme"))
    ]


def test_insertion_is_disabled_or_refused_where_it_cannot_be_preserved(monkeypatch):
    window = _window([_box("T", _p("Corps"))])
    _caret(window.editor, _position_of(window.editor, "Corps", end=True))

    assert not window.insert_box_action.isEnabled()  # nested
    before = extract_blocks(window.editor.document())
    with pytest.raises(UnsupportedBlockError):
        insert_empty_box(window.editor.textCursor(), "x")
    assert extract_blocks(window.editor.document()) == before


def test_insertion_refused_in_caption_raw_block_and_table_cell():
    from bloggen.markdown.rich_text_model import TABLE, TABLE_CELL, TABLE_ROW

    table = Block(
        kind=TABLE,
        children=[
            Block(kind=TABLE_ROW, children=[Block(kind=TABLE_CELL, runs=[InlineRun(text="c")])])
        ],
    )
    raw = Block(kind=VERBATIM, raw_text="```\ncode\n```")
    image = Block(kind=PARAGRAPH, runs=[InlineRun(image_src="a.png", image_alt="Légende")])
    editor = _editor([table, raw, image])
    for needle in ("c", "code", "Légende"):
        cursor = QTextCursor(editor.document())
        cursor.setPosition(_position_of(editor, needle, end=True))
        assert not can_insert_box(cursor), needle
        with pytest.raises(UnsupportedBlockError):
            validate_block_insertion(cursor, [_box("T", _p("x"))])


def test_insertion_replaces_an_ordinary_selection_like_a_table_does(monkeypatch):
    monkeypatch.setattr(window_module, "BoxInsertDialog", _AcceptedBoxDialog)
    window = _window([_p("Avant supprimer Après")])
    _select(window.editor, len("Avant "), len("Avant supprimer "))

    window.insert_box_action.trigger()

    assert extract_blocks(window.editor.document()) == [
        _p("Avant "),
        Block(kind=BOX, runs=[InlineRun(text="À retenir")], children=[_p("")]),
        _p("Après"),
    ]


# --- boundary guards ------------------------------------------------------------


def _boxed_editor() -> MeropeTextEdit:
    return _editor(
        [_p("Avant"), _box("Titre", _p("Un."), _p("Deux.")), _p("Après")]
    )


def _snapshot(editor):
    return extract_blocks(editor.document())


def _assert_box_never_half_destroyed(editor, before):
    """Qt widens a selection that touches a frame edge to enclose the whole
    frame, so a "crossing" edit either leaves the encadré intact or removes it
    atomically; it must never leave a fragment, and undo must restore all."""

    after = extract_blocks(editor.document())  # raises on any broken structure
    boxes_before = [block for block in before if block.kind == BOX]
    boxes_after = [block for block in after if block.kind == BOX]
    assert boxes_after in (boxes_before, [])
    editor.undo()
    while editor.document().isUndoAvailable() and extract_blocks(editor.document()) != before:
        editor.undo()
    assert extract_blocks(editor.document()) == before


@pytest.mark.parametrize("key", [Qt.Key.Key_Delete, Qt.Key.Key_Backspace, Qt.Key.Key_Return])
def test_selection_touching_the_box_edge_never_leaves_a_broken_box(key):
    editor = _boxed_editor()
    before = _snapshot(editor)
    _select(editor, _position_of(editor, "Avant", end=True) - 2, _position_of(editor, "Un.", end=True))

    QTest.keyClick(editor, key)

    _assert_box_never_half_destroyed(editor, before)


def test_typing_or_pasting_over_a_selection_touching_the_edge_never_breaks_the_box():
    for action in ("type", "paste", "cut"):
        editor = _boxed_editor()
        before = _snapshot(editor)
        _select(editor, _position_of(editor, "Deux."), _position_of(editor, "Après", end=True))
        if action == "type":
            QTest.keyClicks(editor, "x")
        elif action == "paste":
            mime = QMimeData()
            mime.setText("remplacement")
            editor.insertFromMimeData(mime)
        else:
            editor.cut()
        _assert_box_never_half_destroyed(editor, before)


def test_crossing_predicate_is_false_inside_one_box_or_wholly_outside():
    from bloggen.ui.qt_editor.document_adapter import selection_crosses_box_boundary

    editor = _boxed_editor()
    _select(editor, _position_of(editor, "Un."), _position_of(editor, "Deux.", end=True))
    assert not selection_crosses_box_boundary(editor.textCursor())
    _select(editor, _position_of(editor, "Avant"), _position_of(editor, "Avant", end=True))
    assert not selection_crosses_box_boundary(editor.textCursor())


def test_deleting_text_wholly_inside_the_box_is_allowed():
    editor = _boxed_editor()
    _select(editor, _position_of(editor, "Un."), _position_of(editor, "Un.", end=True))

    QTest.keyClick(editor, Qt.Key.Key_Delete)

    assert extract_blocks(editor.document())[1].children == [_p(""), _p("Deux.")]


def test_selection_wholly_containing_the_box_deletes_it_cleanly():
    editor = _boxed_editor()
    _select(editor, 0, editor.document().characterCount() - 1)

    QTest.keyClick(editor, Qt.Key.Key_Delete)

    assert all(block.kind != BOX for block in extract_blocks(editor.document()))


def test_enter_at_end_of_title_opens_a_body_paragraph_not_a_second_title():
    editor = _boxed_editor()
    _caret(editor, _position_of(editor, "Titre", end=True))

    QTest.keyClick(editor, Qt.Key.Key_Return)
    QTest.keyClicks(editor, "Nouveau")

    assert extract_blocks(editor.document())[1] == _box(
        "Titre", _p("Nouveau"), _p("Un."), _p("Deux.")
    )


def test_enter_inside_the_title_does_not_split_it():
    editor = _boxed_editor()
    before = _snapshot(editor)
    _caret(editor, _position_of(editor, "Titre") + 2)

    QTest.keyClick(editor, Qt.Key.Key_Return)

    assert _snapshot(editor) == before


def test_backspace_at_start_of_first_body_block_does_not_merge_into_title():
    editor = _boxed_editor()
    before = _snapshot(editor)
    _caret(editor, _position_of(editor, "Un."))

    QTest.keyClick(editor, Qt.Key.Key_Backspace)

    assert _snapshot(editor) == before


def test_delete_at_end_of_title_does_not_merge_body_into_it():
    editor = _boxed_editor()
    before = _snapshot(editor)
    _caret(editor, _position_of(editor, "Titre", end=True))

    QTest.keyClick(editor, Qt.Key.Key_Delete)

    assert _snapshot(editor) == before


def test_backspace_and_delete_at_the_outer_edges_keep_the_structure():
    editor = _boxed_editor()
    before = _snapshot(editor)
    _caret(editor, _position_of(editor, "Titre"))
    QTest.keyClick(editor, Qt.Key.Key_Backspace)
    _caret(editor, _position_of(editor, "Deux.", end=True))
    QTest.keyClick(editor, Qt.Key.Key_Delete)

    assert _snapshot(editor) == before


def test_plain_multiline_paste_into_the_title_stays_on_one_line():
    editor = _boxed_editor()
    _caret(editor, _position_of(editor, "Titre", end=True))
    mime = QMimeData()
    mime.setText(" suite\nautre")

    editor.insertFromMimeData(mime)

    assert extract_blocks(editor.document())[1].runs == [InlineRun(text="Titre suite autre")]


def test_multiline_paste_into_the_body_creates_paragraphs_inside_the_box():
    editor = _boxed_editor()
    _caret(editor, _position_of(editor, "Deux.", end=True))
    mime = QMimeData()
    mime.setText("\nTrois")

    editor.insertFromMimeData(mime)

    assert extract_blocks(editor.document())[1].children == [
        _p("Un."),
        _p("Deux."),
        _p("Trois"),
    ]


def test_rich_paste_of_unsupported_structure_into_the_box_is_refused_before_mutation():
    editor = _boxed_editor()
    before = _snapshot(editor)
    _caret(editor, _position_of(editor, "Un.", end=True))
    cursor = editor.textCursor()

    for blocks in (
        [Block(kind=HEADING, level=2, runs=[InlineRun(text="H")])],
        [Block(kind=VERBATIM, raw_text="```\nx\n```")],
        [_box("N", _p("x"))],
        [_p("a"), Block(kind=PARAGRAPH, runs=[InlineRun(image_src="a.png")])],
    ):
        with pytest.raises(UnsupportedBlockError):
            insert_blocks(cursor, blocks)
    assert _snapshot(editor) == before


def test_rich_multiblock_paste_into_the_title_is_refused():
    editor = _boxed_editor()
    before = _snapshot(editor)
    _caret(editor, _position_of(editor, "Titre", end=True))

    with pytest.raises(UnsupportedBlockError):
        insert_blocks(editor.textCursor(), [_p("a"), _p("b")])
    assert _snapshot(editor) == before


def test_heading_style_is_refused_inside_a_box_but_quote_is_fine():
    from bloggen.ui.qt_editor.formatting import set_blockquote

    editor = _boxed_editor()
    _caret(editor, _position_of(editor, "Un."))

    set_heading(editor, 2)
    assert all(child.kind != HEADING for child in extract_blocks(editor.document())[1].children)
    set_blockquote(editor)
    assert extract_blocks(editor.document())[1].children[0].kind == BLOCKQUOTE


def test_typing_in_the_box_applies_french_typography_and_stays_valid():
    editor = _boxed_editor()
    _caret(editor, _position_of(editor, "Deux.", end=True))

    QTest.keyClicks(editor, " Ecole ")

    assert extract_blocks(editor.document())[1].children[-1] == _p("Deux. École ")


# --- persistence: save / reopen / build --------------------------------------


def _metadata() -> dict[str, str]:
    return {
        "title": "Essai",
        "slug": "essai",
        "type": "post",
        "date": "2026-01-01",
    }


def test_box_survives_save_and_reopen_and_stays_editable(tmp_path, monkeypatch):
    from bloggen.content.writer import read_content_file, write_content_file

    monkeypatch.setattr(window_module, "BoxInsertDialog", _AcceptedBoxDialog)
    path = write_content_file(tmp_path, "document.md", _metadata(), "Avant.\n\nAprès.\n")
    window = QtEditorWindow(path)
    _WIDGETS.append(window)
    window.show()
    _caret(window.editor, _position_of(window.editor, "Avant.", end=True))

    window.insert_box_action.trigger()
    QTest.keyClicks(window.editor, "Premier")
    QTest.keyClick(window.editor, Qt.Key.Key_Return)
    QTest.keyClicks(window.editor, "Second")
    assert window.save_document() is True

    _metadata_read, body = read_content_file(path)
    assert ":::: {.merope-encadre}" in body
    assert "::: {.merope-encadre-titre}\nÀ retenir\n:::" in body
    assert "Premier\n\nSecond\n::::" in body

    reopened = QtEditorWindow(path)
    _WIDGETS.append(reopened)
    reopened.show()
    assert extract_blocks(reopened.editor.document()) == [
        _p("Avant."),
        _box("À retenir", _p("Premier"), _p("Second")),
        _p("Après."),
    ]
    _caret(reopened.editor, _position_of(reopened.editor, "Second", end=True))
    QTest.keyClicks(reopened.editor, " ok")
    assert extract_blocks(reopened.editor.document())[1].children[-1] == _p("Second ok")
    assert reopened.save_document() is True
    assert (
        markdown_to_blocks(read_content_file(path)[1])
        == extract_blocks(reopened.editor.document())
    )


def test_qt_saved_box_builds_valid_commons_publishing_tei(tmp_path, monkeypatch):
    import shutil

    if shutil.which("pandoc") is None:
        pytest.skip("Pandoc requis")
    from bloggen.content.writer import write_content_file
    from bloggen.tei.commons_publishing import validate_commons_publishing_file
    from bloggen.tei.pandoc_converter import convert_markdown_file_to_tei

    monkeypatch.setattr(window_module, "BoxInsertDialog", _AcceptedBoxDialog)
    path = write_content_file(tmp_path, "document.md", _metadata(), "## Section\n\nTexte.\n")
    window = QtEditorWindow(path)
    _WIDGETS.append(window)
    window.show()
    _caret(window.editor, _position_of(window.editor, "Texte.", end=True))
    window.insert_box_action.trigger()
    QTest.keyClicks(window.editor, "Dedans")
    assert window.save_document() is True

    result = convert_markdown_file_to_tei(path, tmp_path / "document.xml")

    assert result.success, result.message
    from lxml import etree

    tree = etree.parse(str(result.tei_file))
    tei = {"t": "http://www.tei-c.org/ns/1.0"}
    assert tree.xpath("//t:floatingText/t:body/t:div/t:p", namespaces=tei)
    assert validate_commons_publishing_file(result.tei_file).valid is True


# --- interactions with other editor features ----------------------------------


def test_replace_all_never_splits_the_single_line_title():
    from bloggen.ui.qt_editor.find_replace import replace_all

    editor = _editor([_box("Titre", _p("Un Titre"))])

    assert replace_all(editor, "Titre", "a\nb") == 2

    box = extract_blocks(editor.document())[0]
    assert box.runs == [InlineRun(text="a b")]
    assert [child.runs[0].text for child in box.children] == ["Un a", "b"]


def test_table_cannot_be_inserted_in_a_box():
    from bloggen.ui.qt_editor.table_structure import can_insert_empty_table

    editor = _editor([_box("T", _p("Corps"))])
    cursor = editor.document().find("Corps")
    cursor.setPosition(cursor.selectionEnd())

    assert not can_insert_empty_table(cursor)


def test_spelling_underlines_and_zoom_work_inside_a_box():
    from PySide6.QtGui import QTextCharFormat

    editor = _editor([_box("T", _p("Ceci est un texe."))])
    editor.adjust_zoom(2)

    block = editor.document().find("texe").block()
    underlined = [
        block.text()[f.start : f.start + f.length]
        for f in block.layout().formats()
        if f.format.underlineStyle() == QTextCharFormat.UnderlineStyle.SpellCheckUnderline
    ]
    assert underlined == ["texe"]
    assert extract_blocks(editor.document()) == [_box("T", _p("Ceci est un texe."))]
    assert not editor.document().isModified()


def test_footnote_renumbering_reaches_references_inside_a_box():
    from bloggen.ui.qt_editor.document_adapter import renumber_footnote_references

    document = QTextDocument()
    populate_document(
        document,
        [_box("T", Block(kind=PARAGRAPH, runs=[InlineRun(text="x"), InlineRun(footnote_ref="2")]))],
    )

    assert renumber_footnote_references(document, {"2": "1"}) is True

    assert extract_blocks(document)[0].children[0].runs[-1].footnote_ref == "1"


def test_copying_a_selection_enclosing_a_box_pastes_a_whole_box():
    editor = _editor([_p("Avant"), _box("T", _p("Corps")), _p("Après")])
    _select(editor, _position_of(editor, "Avant", end=True), _position_of(editor, "Après"))
    editor.copy()
    cursor = QTextCursor(editor.document())
    cursor.movePosition(QTextCursor.MoveOperation.End)
    editor.setTextCursor(cursor)

    editor.paste()

    kinds = [block.kind for block in extract_blocks(editor.document())]
    assert kinds.count(BOX) == 2
    assert all(
        block.children == [_p("Corps")] for block in extract_blocks(editor.document()) if block.kind == BOX
    )
