from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QByteArray, QMimeData, QPoint, QPointF, Qt
from PySide6.QtGui import QImage, QTextCursor, QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from bloggen.content.writer import write_content_file
from bloggen.markdown.rich_text_model import (
    PARAGRAPH,
    TABLE,
    TABLE_CELL,
    TABLE_ROW,
    VERBATIM,
    Block,
    InlineRun,
)
from bloggen.ui.qt_editor.clipboard_fragment import MEROPE_FRAGMENT_MIME
from bloggen.ui.qt_editor.constants import (
    RAW_BLOCK_GROUP_PROPERTY,
    RAW_BLOCK_KIND_PROPERTY,
)
from bloggen.ui.qt_editor.document_adapter import extract_blocks, populate_document
from bloggen.ui.qt_editor.find_replace import find_next, replace_all, replace_current
from bloggen.ui.qt_editor.text_edit import MeropeTextEdit
from bloggen.ui.qt_editor.window import QtEditorWindow


@pytest.fixture(scope="module", autouse=True)
def qapplication():
    app = QApplication.instance() or QApplication([])
    yield app
    app.clipboard().clear()


def _editor(blocks: list[Block]) -> MeropeTextEdit:
    editor = MeropeTextEdit()
    populate_document(editor.document(), blocks)
    editor.document().setModified(False)
    return editor


def _select(editor: MeropeTextEdit, start: int, end: int) -> None:
    cursor = QTextCursor(editor.document())
    cursor.setPosition(start)
    cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
    editor.setTextCursor(cursor)


def _table(value: str = "Bossuet") -> Block:
    return Block(
        kind=TABLE,
        children=[
            Block(
                kind=TABLE_ROW,
                children=[Block(kind=TABLE_CELL, runs=[InlineRun(text="Nom")])],
            ),
            Block(
                kind=TABLE_ROW,
                children=[Block(kind=TABLE_CELL, runs=[InlineRun(text=value)])],
            ),
        ],
    )


def _action(window: QtEditorWindow, label: str):
    return next(
        action
        for action in window.findChildren(type(window.save_action))
        if action.text() == label
    )


def test_find_next_wraps_and_honours_case_without_dirtying():
    editor = _editor(
        [Block(kind=PARAGRAPH, runs=[InlineRun(text="Bossuet bossuet BOSSUET")])]
    )
    before_undo = editor.document().isUndoAvailable()

    assert find_next(editor, "Bossuet", case_sensitive=True) is not None
    assert editor.textCursor().selectedText() == "Bossuet"
    assert find_next(editor, "Bossuet", case_sensitive=True) is not None
    assert editor.textCursor().selectionStart() == 0
    assert find_next(editor, "bossuet", case_sensitive=False) is not None
    assert editor.textCursor().selectionStart() == 8
    assert find_next(editor, "absent") is None

    assert not editor.document().isModified()
    assert editor.document().isUndoAvailable() == before_undo


def test_find_uses_qt_utf16_positions_for_astral_unicode():
    editor = _editor(
        [Block(kind=PARAGRAPH, runs=[InlineRun(text="📚 Bossuet 📚 Bossuet")])]
    )

    first = find_next(editor, "Bossuet")
    second = find_next(editor, "Bossuet")

    assert first is not None and first.start == 3
    assert second is not None and second.start == 14
    assert editor.textCursor().selectedText() == "Bossuet"


def test_find_never_matches_across_qtextblocks():
    editor = _editor(
        [
            Block(kind=PARAGRAPH, runs=[InlineRun(text="Boss")]),
            Block(kind=PARAGRAPH, runs=[InlineRun(text="uet")]),
        ]
    )

    assert find_next(editor, "Bossuet") is None
    assert not editor.document().isModified()


def test_replace_current_preserves_rich_format_and_undo():
    original = Block(
        kind=PARAGRAPH,
        runs=[
            InlineRun(
                text="Bossuet",
                bold=True,
                italic=True,
                strikethrough=True,
                superscript=True,
                link_href="https://example.org",
            ),
            InlineRun(text=" parle"),
        ],
    )
    editor = _editor([original])
    assert find_next(editor, "Bossuet") is not None

    assert replace_current(editor, "Bossuet", "Fénelon")
    assert extract_blocks(editor.document()) == [
        Block(
            kind=PARAGRAPH,
            runs=[
                InlineRun(
                    text="Fénelon",
                    bold=True,
                    italic=True,
                    strikethrough=True,
                    superscript=True,
                    link_href="https://example.org",
                ),
                InlineRun(text=" parle"),
            ],
        )
    ]
    assert editor.document().isModified()
    editor.undo()
    assert extract_blocks(editor.document()) == [original]


def test_replace_skips_semantic_objects_and_cross_format_occurrences():
    editor = _editor(
        [
            Block(
                kind=PARAGRAPH,
                runs=[
                    InlineRun(text="Bos", bold=True),
                    InlineRun(text="suet", italic=True),
                    InlineRun(text=" "),
                    InlineRun(footnote_ref="1"),
                    InlineRun(text=" Bossuet "),
                    InlineRun(image_src="missing.png", image_alt=""),
                ],
            )
        ]
    )

    match = find_next(editor, "Bossuet")
    assert match is not None
    assert editor.textCursor().selectionStart() > 7
    assert replace_current(editor, "Bossuet", "Fénelon")
    assert find_next(editor, "[1]") is None
    assert find_next(editor, "\ufffc") is None
    blocks = extract_blocks(editor.document())
    assert blocks[0].runs[:2] == [
        InlineRun(text="Bos", bold=True),
        InlineRun(text="suet", italic=True),
    ]
    assert any(run.footnote_ref == "1" for run in blocks[0].runs)
    assert any(run.image_src == "missing.png" for run in blocks[0].runs)


def test_replace_all_normal_and_raw_is_one_undo_step():
    original = [
        Block(kind=PARAGRAPH, runs=[InlineRun(text="Bossuet Bossuet")]),
        Block(kind=VERBATIM, raw_text="**Bossuet**"),
        _table(),
    ]
    editor = _editor(original)

    assert replace_all(editor, "Bossuet", "Fénelon") == 4
    assert extract_blocks(editor.document()) == [
        Block(kind=PARAGRAPH, runs=[InlineRun(text="Fénelon Fénelon")]),
        Block(kind=VERBATIM, raw_text="**Fénelon**"),
        _table("Fénelon"),
    ]
    raw_formats = [
        editor.document().findBlockByNumber(number).blockFormat()
        for number in range(1, editor.document().blockCount())
    ]
    assert all(fmt.hasProperty(RAW_BLOCK_KIND_PROPERTY) for fmt in raw_formats)
    assert all(fmt.hasProperty(RAW_BLOCK_GROUP_PROPERTY) for fmt in raw_formats)

    editor.undo()
    assert extract_blocks(editor.document()) == original
    assert not editor.document().isUndoAvailable()
    editor.redo()
    assert extract_blocks(editor.document())[0].runs == [InlineRun(text="Fénelon Fénelon")]


def test_identical_replace_is_a_clean_no_op():
    editor = _editor([Block(kind=PARAGRAPH, runs=[InlineRun(text="Bossuet")])])
    assert find_next(editor, "Bossuet") is not None

    assert not replace_current(editor, "Bossuet", "Bossuet")
    assert replace_all(editor, "Bossuet", "Bossuet") == 0
    assert not editor.document().isModified()
    assert not editor.document().isUndoAvailable()


@pytest.mark.parametrize("rich_kind", ["html", "merope", "image"])
def test_plain_paste_uses_only_clipboard_text(rich_kind: str):
    editor = _editor([Block(kind=PARAGRAPH, runs=[InlineRun(text="Avant ")])])
    cursor = editor.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.End)
    editor.setTextCursor(cursor)
    mime = QMimeData()
    mime.setText("texte brut")
    if rich_kind == "html":
        mime.setHtml("<strong>HTML riche</strong>")
    elif rich_kind == "merope":
        mime.setData(MEROPE_FRAGMENT_MIME, QByteArray(b"**Merope riche**\n"))
    else:
        mime.setImageData(QImage(2, 2, QImage.Format.Format_ARGB32))
    QApplication.clipboard().setMimeData(mime)

    assert editor.paste_plain_text()
    assert extract_blocks(editor.document()) == [
        Block(kind=PARAGRAPH, runs=[InlineRun(text="Avant texte brut")])
    ]
    editor.undo()
    assert extract_blocks(editor.document()) == [
        Block(kind=PARAGRAPH, runs=[InlineRun(text="Avant ")])
    ]


def test_plain_paste_raw_multiline_preserves_group():
    editor = _editor([Block(kind=VERBATIM, raw_text="avant")])
    cursor = editor.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.End)
    editor.setTextCursor(cursor)
    group = editor.document().begin().blockFormat().property(RAW_BLOCK_GROUP_PROPERTY)

    assert editor.paste_plain_text("\nligne 2")
    assert extract_blocks(editor.document()) == [
        Block(kind=VERBATIM, raw_text="avant\nligne 2")
    ]
    assert (
        editor.document().findBlockByNumber(1).blockFormat().property(
            RAW_BLOCK_GROUP_PROPERTY
        )
        == group
    )


def test_plain_paste_expands_partial_footnote_and_refuses_raw_boundary():
    editor = _editor(
        [
            Block(
                kind=PARAGRAPH,
                runs=[InlineRun(text="A"), InlineRun(footnote_ref="12"), InlineRun(text="B")],
            )
        ]
    )
    _select(editor, 2, 3)
    assert editor.paste_plain_text("X")
    assert extract_blocks(editor.document()) == [
        Block(kind=PARAGRAPH, runs=[InlineRun(text="AXB")])
    ]

    guarded = _editor(
        [
            Block(kind=PARAGRAPH, runs=[InlineRun(text="normal")]),
            Block(kind=VERBATIM, raw_text="brut"),
        ]
    )
    left = guarded.document().begin()
    separator = left.position() + left.length() - 1
    _select(guarded, separator, left.next().position())
    before = extract_blocks(guarded.document())
    assert not guarded.paste_plain_text("X")
    assert extract_blocks(guarded.document()) == before
    assert not guarded.document().isUndoAvailable()


def test_nbsp_normal_selection_raw_and_semantic_protections():
    editor = _editor([Block(kind=PARAGRAPH, runs=[InlineRun(text="AB")])])
    _select(editor, 1, 2)
    assert editor.insert_nbsp()
    assert extract_blocks(editor.document()) == [
        Block(kind=PARAGRAPH, runs=[InlineRun(text="A\u00a0")])
    ]
    editor.undo()
    assert extract_blocks(editor.document())[0].runs == [InlineRun(text="AB")]

    raw = _editor([Block(kind=VERBATIM, raw_text="AB")])
    _select(raw, 1, 2)
    group = raw.document().begin().blockFormat().property(RAW_BLOCK_GROUP_PROPERTY)
    assert raw.insert_nbsp()
    assert extract_blocks(raw.document()) == [Block(kind=VERBATIM, raw_text="A\u00a0")]
    assert raw.document().begin().blockFormat().property(RAW_BLOCK_GROUP_PROPERTY) == group

    image = _editor(
        [Block(kind=PARAGRAPH, runs=[InlineRun(image_src="missing.png", image_alt="")])]
    )
    _select(image, 0, 1)
    assert not image.insert_nbsp()
    assert extract_blocks(image.document())[0].runs[0].image_src == "missing.png"
    assert not image.document().isUndoAvailable()


def test_nbsp_expands_footnote_and_refuses_raw_boundary():
    editor = _editor(
        [Block(kind=PARAGRAPH, runs=[InlineRun(footnote_ref="12")])]
    )
    _select(editor, 1, 2)
    assert editor.insert_nbsp()
    assert extract_blocks(editor.document()) == [
        Block(kind=PARAGRAPH, runs=[InlineRun(text="\u00a0")])
    ]

    guarded = _editor(
        [
            Block(kind=VERBATIM, raw_text="brut"),
            Block(kind=PARAGRAPH, runs=[InlineRun(text="normal")]),
        ]
    )
    left = guarded.document().begin()
    _select(
        guarded,
        left.position() + left.length() - 1,
        left.next().position(),
    )
    before = extract_blocks(guarded.document())
    assert not guarded.insert_nbsp()
    assert extract_blocks(guarded.document()) == before
    assert not guarded.document().isUndoAvailable()


def test_nbsp_survives_save_and_reopen(tmp_path):
    pages = tmp_path / "content" / "pages"
    path = write_content_file(
        pages,
        "article.md",
        {"title": "Article", "slug": "article", "type": "page"},
        "Avant après\n",
    )
    window = QtEditorWindow(path, pages_dir=pages, posts_dir=tmp_path / "posts")
    _select(window.editor, 5, 6)
    assert window.editor.insert_nbsp()
    assert window.save_document()
    assert "\u00a0" in path.read_text(encoding="utf-8")

    reopened = QtEditorWindow(path, pages_dir=pages, posts_dir=tmp_path / "posts")
    assert extract_blocks(reopened.editor.document())[0].runs == [
        InlineRun(text="Avant\u00a0après")
    ]
    window.close()
    reopened.close()


def test_zoom_is_visual_bounded_and_semantically_inert():
    original = [
        Block(
            kind=PARAGRAPH,
            runs=[
                InlineRun(text="Avant"),
                InlineRun(
                    image_src="missing.png",
                    image_alt="Image",
                    image_width="300",
                    image_height="200",
                    image_align="center",
                ),
            ],
        ),
        Block(kind=VERBATIM, raw_text="**brut**"),
    ]
    editor = _editor(original)
    raw_before = editor.document().findBlockByNumber(1).blockFormat()
    before_modified = editor.document().isModified()
    before_undo = editor.document().isUndoAvailable()
    before_redo = editor.document().isRedoAvailable()

    assert editor.adjust_zoom(1)
    assert editor.zoom_percent == 110
    assert editor.adjust_zoom(100)
    assert editor.zoom_percent == 300
    assert not editor.adjust_zoom(1)
    assert editor.adjust_zoom(-100)
    assert editor.zoom_percent == 50
    assert not editor.adjust_zoom(-1)

    assert extract_blocks(editor.document()) == original
    assert editor.document().isModified() == before_modified
    assert editor.document().isUndoAvailable() == before_undo
    assert editor.document().isRedoAvailable() == before_redo
    raw_after = editor.document().findBlockByNumber(1).blockFormat()
    assert raw_after.property(RAW_BLOCK_KIND_PROPERTY) == raw_before.property(
        RAW_BLOCK_KIND_PROPERTY
    )
    assert raw_after.property(RAW_BLOCK_GROUP_PROPERTY) == raw_before.property(
        RAW_BLOCK_GROUP_PROPERTY
    )


def test_ctrl_wheel_changes_zoom_without_document_mutation():
    original = [Block(kind=PARAGRAPH, runs=[InlineRun(text="Texte")])]
    editor = _editor(original)
    event = QWheelEvent(
        QPointF(5, 5),
        QPointF(5, 5),
        QPoint(),
        QPoint(0, 120),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.ControlModifier,
        Qt.ScrollPhase.ScrollUpdate,
        False,
    )

    editor.wheelEvent(event)

    assert event.isAccepted()
    assert editor.zoom_percent == 110
    assert extract_blocks(editor.document()) == original
    assert not editor.document().isModified()
    assert not editor.document().isUndoAvailable()


def test_window_reuses_find_dialog_and_registers_daily_shortcuts():
    window = QtEditorWindow()
    window._show_find_dialog()
    find_dialog = window._find_replace_dialog
    assert find_dialog is not None
    assert not find_dialog.replace_edit.isVisible()
    find_dialog.search_edit.setText("absent")
    QTest.keyClick(find_dialog.search_edit, Qt.Key.Key_Return)
    assert find_dialog.status_label.text() == "Aucune occurrence trouvée."
    window._show_replace_dialog()
    assert window._find_replace_dialog is find_dialog
    assert find_dialog.replace_edit.isVisible()

    shortcuts = {
        label: {sequence.toString() for sequence in _action(window, label).shortcuts()}
        for label in (
            "Rechercher",
            "Remplacer",
            "Coller en texte brut",
            "Espace insécable",
            "Barre",
            "Exposant",
            "Justifier gauche/plein",
        )
    }
    assert shortcuts == {
        "Rechercher": {"Ctrl+F"},
        "Remplacer": {"Ctrl+H"},
        "Coller en texte brut": {"Ctrl+Shift+V"},
        "Espace insécable": {"Ctrl+Space", "Alt+Space"},
        "Barre": {"Ctrl+Shift+S"},
        "Exposant": {"Ctrl+Shift+="},
        "Justifier gauche/plein": {"Alt+J"},
    }
    populate_document(
        window.editor.document(),
        [Block(kind=PARAGRAPH, runs=[InlineRun(text="Texte")])],
    )
    _action(window, "Justifier gauche/plein").trigger()
    assert extract_blocks(window.editor.document())[0].alignment == "justify"
    window.editor.undo()
    assert extract_blocks(window.editor.document())[0].alignment == "left"

    QTest.keyClick(find_dialog, Qt.Key.Key_Escape)
    QApplication.processEvents()
    assert window._find_replace_dialog is None
    window.close()
