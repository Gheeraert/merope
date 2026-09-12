from __future__ import annotations

import os
from dataclasses import replace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QByteArray, QEvent, QMimeData, Qt
from PySide6.QtGui import QKeyEvent, QTextCursor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

from bloggen.content.footnotes import separate_footnote_definitions
from bloggen.content.writer import read_content_file, write_content_file
from bloggen.markdown.rich_text_export import blocks_to_markdown
from bloggen.markdown.rich_text_import import markdown_to_blocks
from bloggen.markdown.rich_text_model import (
    BULLET_LIST,
    FOOTNOTE_DEFINITION,
    LIST_ITEM,
    PARAGRAPH,
    Block,
    InlineRun,
)
from bloggen.markdown.typography import NBSP
from bloggen.ui.qt_editor import window as window_module
from bloggen.ui.qt_editor.clipboard_fragment import MEROPE_FRAGMENT_MIME
from bloggen.ui.qt_editor.document_adapter import extract_blocks, populate_document
from bloggen.ui.qt_editor.footnote_editor import (
    FootnoteEditorDialog,
    FootnoteTextEdit,
    InvalidFootnoteDefinition,
    footnote_runs_semantically_equal,
    footnote_runs_from_blocks,
    footnote_runs_from_document,
    validate_footnote_runs,
)
from bloggen.ui.qt_editor.formatting import (
    set_link,
    toggle_bold,
    toggle_italic,
    toggle_strikethrough,
    toggle_superscript,
    toggle_underline,
)
from bloggen.ui.qt_editor.text_edit import MeropeTextEdit, blocks_from_rich_mime_data
from bloggen.ui.qt_editor.window import QtEditorWindow


@pytest.fixture(scope="module")
def qapplication():
    app = QApplication.instance() or QApplication([])
    yield app
    app.clipboard().clear()


@pytest.fixture(autouse=True)
def clean_clipboard(qapplication):
    qapplication.clipboard().clear()
    yield
    qapplication.clipboard().clear()
    for widget in qapplication.topLevelWidgets():
        widget.hide()
    qapplication.processEvents()


def _select(editor, start: int, end: int) -> None:
    cursor = QTextCursor(editor.document())
    cursor.setPosition(start)
    cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
    editor.setTextCursor(cursor)


def _select_all(editor) -> None:
    _select(editor, 0, editor.document().characterCount() - 1)


def _set_cursor(editor, position: int) -> None:
    cursor = QTextCursor(editor.document())
    cursor.setPosition(position)
    editor.setTextCursor(cursor)


def _type(editor: FootnoteTextEdit, text: str) -> None:
    for char in text:
        event = QKeyEvent(
            QEvent.Type.KeyPress,
            Qt.Key.Key_unknown,
            Qt.KeyboardModifier.NoModifier,
            char,
        )
        QApplication.sendEvent(editor, event)
    QApplication.processEvents()


def _dialog(runs: list[InlineRun]) -> FootnoteEditorDialog:
    return FootnoteEditorDialog(runs)


@pytest.mark.parametrize(
    "runs",
    [
        [InlineRun(text="Simple")],
        [InlineRun(text="Gras", bold=True)],
        [InlineRun(text="Italique", italic=True)],
        [InlineRun(text="Souligné", underline=True)],
        [InlineRun(text="Barré", strikethrough=True)],
        [InlineRun(text="Exposant", superscript=True)],
        [InlineRun(text="Lien", link_href="../page.html#section")],
        [
            InlineRun(text="Bossuet", bold=True, italic=True),
            InlineRun(text=" à "),
            InlineRun(
                text="Meaux",
                bold=True,
                link_href="https://example.org",
            ),
        ],
    ],
)
def test_dialog_loads_and_extracts_supported_rich_runs_exactly(runs):
    dialog = _dialog(runs)

    assert footnote_runs_from_document(dialog.editor.document()) == runs
    assert dialog.editor.document().blockCount() == 1
    assert not dialog.editor.document().isModified()


def test_dialog_formatting_uses_shared_commands_and_local_undo_redo():
    dialog = _dialog([InlineRun(text="Bossuet Meaux")])
    editor = dialog.editor
    _select(editor, 0, 7)
    toggle_bold(editor)
    toggle_italic(editor)
    toggle_underline(editor)
    _select(editor, 8, 13)
    toggle_strikethrough(editor)
    toggle_superscript(editor)
    set_link(editor, "https://example.org")

    assert footnote_runs_from_document(editor.document()) == [
        InlineRun(text="Bossuet", bold=True, italic=True, underline=True),
        InlineRun(text=" "),
        InlineRun(
            text="Meaux",
            strikethrough=True,
            superscript=True,
            link_href="https://example.org",
        ),
    ]

    editor.undo()
    assert footnote_runs_from_document(editor.document())[-1].link_href is None
    editor.redo()
    assert footnote_runs_from_document(editor.document())[-1].link_href == (
        "https://example.org"
    )

    _select(editor, 8, 13)
    set_link(editor, None)
    assert footnote_runs_from_document(editor.document())[-1].link_href is None


def test_dialog_toolbar_shortcuts_target_its_local_document():
    dialog = _dialog([InlineRun(text="Locale")])
    dialog.show()
    QApplication.processEvents()
    dialog.activateWindow()
    dialog.editor.setFocus()
    QApplication.processEvents()
    _select_all(dialog.editor)

    QTest.keyClick(
        dialog.editor,
        Qt.Key.Key_G,
        Qt.KeyboardModifier.ControlModifier,
    )
    QTest.keyClick(
        dialog.editor,
        Qt.Key.Key_I,
        Qt.KeyboardModifier.ControlModifier,
    )
    QTest.keyClick(
        dialog.editor,
        Qt.Key.Key_U,
        Qt.KeyboardModifier.ControlModifier,
    )
    QApplication.processEvents()
    assert footnote_runs_from_document(dialog.editor.document()) == [
        InlineRun(text="Locale", bold=True, italic=True, underline=True)
    ]

    QTest.keyClick(
        dialog.editor,
        Qt.Key.Key_Z,
        Qt.KeyboardModifier.ControlModifier,
    )
    assert footnote_runs_from_document(dialog.editor.document()) == [
        InlineRun(text="Locale", bold=True, italic=True)
    ]
    QTest.keyClick(
        dialog.editor,
        Qt.Key.Key_Y,
        Qt.KeyboardModifier.ControlModifier,
    )
    assert footnote_runs_from_document(dialog.editor.document()) == [
        InlineRun(text="Locale", bold=True, italic=True, underline=True)
    ]


def test_dialog_typography_reuses_merope_text_edit_rules():
    dialog = _dialog([])
    _type(dialog.editor, '"Bossuet" : oeuvre p. 12 XVIIe')

    runs = footnote_runs_from_document(dialog.editor.document())
    assert "".join(run.text for run in runs) == (
        f"«{NBSP}Bossuet{NBSP}»{NBSP}: œuvre p.{NBSP}12 XVIIe"
    )
    assert runs[-1] == InlineRun(text="e", superscript=True)


def test_dialog_typography_command_preserves_rich_runs():
    dialog = _dialog(
        [
            InlineRun(text='"Bossuet"', bold=True),
            InlineRun(text=" : oeuvre", italic=True),
        ]
    )
    _select_all(dialog.editor)

    assert dialog.editor.apply_typography_to_selection()

    runs = footnote_runs_from_document(dialog.editor.document())
    assert "".join(run.text for run in runs) == f"«{NBSP}Bossuet{NBSP}»{NBSP}: oeuvre"
    assert any(run.bold and "Bossuet" in run.text for run in runs)
    assert any(run.italic and "oeuvre" in run.text for run in runs)


@pytest.mark.parametrize("modifiers", [Qt.KeyboardModifier.NoModifier, Qt.KeyboardModifier.ShiftModifier])
def test_enter_and_shift_enter_are_noops(modifiers):
    dialog = _dialog([InlineRun(text="Un paragraphe")])
    editor = dialog.editor
    _set_cursor(editor, 2)
    editor.document().setModified(False)

    QTest.keyClick(editor, Qt.Key.Key_Return, modifiers)

    assert editor.document().blockCount() == 1
    assert footnote_runs_from_document(editor.document()) == [
        InlineRun(text="Un paragraphe")
    ]
    assert not editor.document().isModified()


@pytest.mark.parametrize(
    "blocks",
    [
        [
            Block(kind=PARAGRAPH, runs=[InlineRun(text="A")]),
            Block(kind=PARAGRAPH, runs=[InlineRun(text="B")]),
        ],
        [
            Block(
                kind=BULLET_LIST,
                children=[Block(kind=LIST_ITEM, runs=[InlineRun(text="A")])],
            )
        ],
        [Block(kind=PARAGRAPH, runs=[InlineRun(image_src="image.png")])],
        [Block(kind=PARAGRAPH, runs=[InlineRun(footnote_ref="1")])],
    ],
)
def test_definition_validation_refuses_multiblock_lists_images_and_nested_notes(blocks):
    with pytest.raises(InvalidFootnoteDefinition):
        footnote_runs_from_blocks(blocks)


@pytest.mark.parametrize(
    "runs",
    [[], [InlineRun(text="")], [InlineRun(text="  \t")], [InlineRun(text=NBSP)]],
)
def test_empty_or_whitespace_only_definition_is_refused_at_commit(runs):
    with pytest.raises(InvalidFootnoteDefinition, match="vide"):
        validate_footnote_runs(runs)


def test_semantic_run_comparison_ignores_only_adjacent_fragmentation_and_empty_runs():
    fragmented = [
        InlineRun(text="Une ", bold=True),
        InlineRun(text="note", bold=True),
        InlineRun(text=""),
    ]
    merged = [InlineRun(text="Une note", bold=True)]

    assert footnote_runs_semantically_equal(fragmented, merged)
    assert not footnote_runs_semantically_equal(
        fragmented,
        [InlineRun(text="Une note", italic=True)],
    )


def test_dialog_accept_keeps_open_on_invalid_document(monkeypatch):
    dialog = _dialog([InlineRun(text="Valide")])
    cursor = QTextCursor(dialog.editor.document())
    cursor.movePosition(QTextCursor.MoveOperation.End)
    cursor.insertBlock()
    cursor.insertText("Second bloc")
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warnings.append(args))

    dialog.accept()

    assert dialog.result() == QDialog.DialogCode.Rejected
    assert warnings
    with pytest.raises(RuntimeError):
        dialog.result_runs()


def test_dialog_cancel_never_mutates_initial_runs():
    initial = [InlineRun(text="Bossuet", bold=True)]
    dialog = _dialog(initial)
    cursor = QTextCursor(dialog.editor.document())
    cursor.movePosition(QTextCursor.MoveOperation.End)
    cursor.insertText(" modifié")
    dialog.reject()

    assert initial == [InlineRun(text="Bossuet", bold=True)]
    assert dialog.result() == QDialog.DialogCode.Rejected


def test_dialog_valid_ok_returns_canonical_runs_only_after_accept():
    dialog = _dialog([InlineRun(text="Avant")])
    _set_cursor(dialog.editor, 5)
    dialog.editor.insertPlainText(" après")

    dialog.accept()

    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.result_runs() == [InlineRun(text="Avant après")]


def test_rich_html_paste_is_canonical_and_multiblock_is_atomic():
    editor = FootnoteTextEdit()
    populate_document(
        editor.document(),
        [Block(kind=PARAGRAPH, runs=[InlineRun(text="Avant")])],
    )
    _set_cursor(editor, 5)
    mime = QMimeData()
    mime.setHtml("<p><strong> Bossuet</strong> à <em>Meaux</em></p>")
    mime.setText("fallback")

    editor.insertFromMimeData(mime)

    assert footnote_runs_from_document(editor.document()) == [
        InlineRun(text="Avant"),
        InlineRun(text=" Bossuet", bold=True),
        InlineRun(text=" à "),
        InlineRun(text="Meaux", italic=True),
    ]

    before = footnote_runs_from_document(editor.document())
    refused = []
    editor.pasteRefused.connect(refused.append)
    mime.setHtml("<p>A</p><p>B</p>")
    editor.insertFromMimeData(mime)
    assert footnote_runs_from_document(editor.document()) == before
    assert refused


@pytest.mark.parametrize(
    "html",
    [
        '<p>Texte<img src="image.png"></p>',
        "<table><tr><td>cellule</td></tr></table>",
        "<pre>verbatim</pre>",
    ],
)
def test_note_rich_paste_refuses_unsupported_html_without_fallback(html):
    editor = FootnoteTextEdit()
    populate_document(
        editor.document(),
        [Block(kind=PARAGRAPH, runs=[InlineRun(text="Stable")])],
    )
    mime = QMimeData()
    mime.setHtml(html)
    mime.setText("fallback interdit")
    refused = []
    editor.pasteRefused.connect(refused.append)

    editor.insertFromMimeData(mime)

    assert footnote_runs_from_document(editor.document()) == [InlineRun(text="Stable")]
    assert refused


def test_plain_text_with_newline_is_refused_without_mutation():
    editor = FootnoteTextEdit()
    populate_document(
        editor.document(),
        [Block(kind=PARAGRAPH, runs=[InlineRun(text="Stable")])],
    )
    mime = QMimeData()
    mime.setText("A\nB")
    refused = []
    editor.pasteRefused.connect(refused.append)

    editor.insertFromMimeData(mime)

    assert footnote_runs_from_document(editor.document()) == [InlineRun(text="Stable")]
    assert refused


def test_internal_multiblock_nested_note_and_image_pastes_are_refused():
    editor = FootnoteTextEdit()
    populate_document(
        editor.document(),
        [Block(kind=PARAGRAPH, runs=[InlineRun(text="Stable")])],
    )
    refused = []
    editor.pasteRefused.connect(refused.append)
    payloads = [
        "A\n\nB\n",
        "Appel[^1]\n",
        "![Image](image.png)\n",
    ]

    for markdown in payloads:
        mime = QMimeData()
        mime.setData(MEROPE_FRAGMENT_MIME, QByteArray(markdown.encode("utf-8")))
        mime.setText("fallback interdit")
        editor.insertFromMimeData(mime)

    assert footnote_runs_from_document(editor.document()) == [InlineRun(text="Stable")]
    assert len(refused) == 3


def test_real_clipboard_note_to_body_preserves_rich_runs():
    note = FootnoteTextEdit()
    rich = [
        InlineRun(text="Bossuet", bold=True),
        InlineRun(text=" à "),
        InlineRun(
            text="Meaux",
            italic=True,
            link_href="https://example.org",
        ),
    ]
    populate_document(note.document(), [Block(kind=PARAGRAPH, runs=rich)])
    note.show()
    note.setFocus()
    _select_all(note)
    note.copy()
    QApplication.processEvents()
    note_mime = QApplication.clipboard().mimeData()
    assert note_mime.hasFormat(MEROPE_FRAGMENT_MIME)
    assert note_mime.hasText() and note_mime.text() == "Bossuet à Meaux"
    assert note_mime.hasHtml()

    body = MeropeTextEdit()
    populate_document(body.document(), [])
    body.paste()

    assert extract_blocks(body.document()) == [
        Block(kind=PARAGRAPH, runs=rich, alignment="justify")
    ]


def test_real_clipboard_body_to_note_accepts_one_rich_paragraph():
    body = MeropeTextEdit()
    rich = [
        InlineRun(text="Texte "),
        InlineRun(text="gras", bold=True),
        InlineRun(text=" et "),
        InlineRun(text="lié", italic=True, link_href="../cible.html"),
    ]
    populate_document(body.document(), [Block(kind=PARAGRAPH, runs=rich)])
    body.show()
    body.setFocus()
    _select_all(body)
    body.copy()
    QApplication.processEvents()
    clipboard_mime = QApplication.clipboard().mimeData()
    assert clipboard_mime.hasText(), clipboard_mime.formats()
    assert clipboard_mime.hasHtml(), clipboard_mime.formats()
    assert blocks_from_rich_mime_data(clipboard_mime) == [
        Block(kind=PARAGRAPH, runs=rich)
    ]

    note = FootnoteTextEdit()
    populate_document(note.document(), [Block(kind=PARAGRAPH, runs=[])])
    note.show()
    note.setFocus()
    note.paste()

    assert footnote_runs_from_document(note.document()) == rich


def test_real_clipboard_body_footnote_reference_is_refused_in_note():
    body = MeropeTextEdit()
    populate_document(
        body.document(),
        [Block(kind=PARAGRAPH, runs=[InlineRun(footnote_ref="1")])],
    )
    _select_all(body)
    body.copy()

    note = FootnoteTextEdit()
    populate_document(
        note.document(),
        [Block(kind=PARAGRAPH, runs=[InlineRun(text="Stable")])],
    )
    refused = []
    note.pasteRefused.connect(refused.append)
    note.paste()

    assert footnote_runs_from_document(note.document()) == [InlineRun(text="Stable")]
    assert refused


def test_real_clipboard_body_image_is_refused_in_note():
    body = MeropeTextEdit()
    populate_document(
        body.document(),
        [Block(kind=PARAGRAPH, runs=[InlineRun(image_src="image.png")])],
    )
    _select_all(body)
    body.copy()
    assert QApplication.clipboard().mimeData().hasFormat(MEROPE_FRAGMENT_MIME)

    note = FootnoteTextEdit()
    populate_document(
        note.document(),
        [Block(kind=PARAGRAPH, runs=[InlineRun(text="Stable")])],
    )
    refused = []
    note.pasteRefused.connect(refused.append)
    note.paste()

    assert footnote_runs_from_document(note.document()) == [InlineRun(text="Stable")]
    assert refused


def test_modal_clipboard_shortcuts_and_undo_are_local():
    editor = FootnoteTextEdit()
    populate_document(
        editor.document(),
        [Block(kind=PARAGRAPH, runs=[InlineRun(text="Riche", bold=True)])],
    )
    _select_all(editor)

    QTest.keyClick(editor, Qt.Key.Key_X, Qt.KeyboardModifier.ControlModifier)
    assert "".join(run.text for run in extract_blocks(editor.document())[0].runs) == ""
    QTest.keyClick(editor, Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier)
    assert footnote_runs_from_document(editor.document()) == [
        InlineRun(text="Riche", bold=True)
    ]

    editor.undo()
    assert "".join(run.text for run in extract_blocks(editor.document())[0].runs) == ""
    editor.redo()
    assert footnote_runs_from_document(editor.document()) == [
        InlineRun(text="Riche", bold=True)
    ]


class _FakeFootnoteDialog:
    result_code = QDialog.DialogCode.Rejected
    runs: list[InlineRun] = []

    def __init__(self, initial_runs, *args, **kwargs):
        self.initial_runs = [replace(run) for run in initial_runs]

    def exec(self):
        return self.result_code

    def result_runs(self):
        return [replace(run) for run in self.runs]


def test_window_cancel_and_identical_ok_are_store_noops(monkeypatch):
    window = QtEditorWindow()
    initial = [InlineRun(text="Bossuet", bold=True)]
    window.footnote_store.load({"1": initial})
    window.editor.document().setModified(False)
    before_panel = window.footnote_panel.toPlainText()
    monkeypatch.setattr(window_module, "FootnoteEditorDialog", _FakeFootnoteDialog)

    _FakeFootnoteDialog.result_code = QDialog.DialogCode.Rejected
    assert not window._edit_selected_footnote()
    assert window.footnote_definitions == {"1": initial}
    assert not window.document_has_unsaved_changes
    assert window.footnote_panel.toPlainText() == before_panel

    _FakeFootnoteDialog.runs = initial
    _FakeFootnoteDialog.result_code = QDialog.DialogCode.Accepted
    assert not window._edit_selected_footnote()
    assert window.footnote_definitions == {"1": initial}
    assert not window.document_has_unsaved_changes

    window.footnote_store.load(
        {"1": [InlineRun(text="Bossuet ", bold=True), InlineRun(text="Meaux", bold=True)]}
    )
    before_panel = window.footnote_panel.toPlainText()
    _FakeFootnoteDialog.runs = [InlineRun(text="Bossuet Meaux", bold=True)]
    assert not window._edit_selected_footnote()
    assert window.footnote_definitions == {
        "1": [InlineRun(text="Bossuet ", bold=True), InlineRun(text="Meaux", bold=True)]
    }
    assert not window.document_has_unsaved_changes
    assert window.footnote_panel.toPlainText() == before_panel


def test_window_rich_ok_commits_only_store_and_refreshes_panel(monkeypatch):
    window = QtEditorWindow()
    populate_document(
        window.editor.document(),
        [Block(kind=PARAGRAPH, runs=[InlineRun(footnote_ref="1")])],
    )
    window.editor.document().setModified(False)
    window.footnote_store.load({"1": [InlineRun(text="Simple")]})
    updated = [
        InlineRun(text="Note", bold=True),
        InlineRun(text=" liée", link_href="https://example.org"),
    ]
    _FakeFootnoteDialog.runs = updated
    _FakeFootnoteDialog.result_code = QDialog.DialogCode.Accepted
    monkeypatch.setattr(window_module, "FootnoteEditorDialog", _FakeFootnoteDialog)

    assert window._edit_selected_footnote()

    assert window.footnote_definitions == {"1": updated}
    assert window.footnote_store.modified
    assert window.document_has_unsaved_changes
    assert not window.editor.document().isModified()
    assert window.windowTitle().endswith("*")
    assert "Note liée" in window.footnote_panel.toPlainText()
    assert window.footnote_panel.selected_note_id == "1"


def test_window_insert_action_uses_rich_dialog_result(monkeypatch):
    window = QtEditorWindow()
    populate_document(
        window.editor.document(),
        [Block(kind=PARAGRAPH, runs=[InlineRun(text="Corps")])],
    )
    _set_cursor(window.editor, 5)
    rich = [InlineRun(text="Note", bold=True), InlineRun(text=" riche", italic=True)]
    _FakeFootnoteDialog.runs = rich
    _FakeFootnoteDialog.result_code = QDialog.DialogCode.Accepted
    monkeypatch.setattr(window_module, "FootnoteEditorDialog", _FakeFootnoteDialog)

    assert window._insert_footnote_from_dialog()

    assert window.footnote_definitions == {"1": rich}
    assert extract_blocks(window.editor.document())[0].runs[-1] == InlineRun(
        footnote_ref="1"
    )


def test_window_inserts_rich_note_and_rolls_store_back_on_marker_failure(monkeypatch):
    window = QtEditorWindow()
    populate_document(
        window.editor.document(),
        [Block(kind=PARAGRAPH, runs=[InlineRun(text="Corps")])],
    )
    _set_cursor(window.editor, 5)
    rich = [InlineRun(text="Riche", bold=True), InlineRun(text=" note", italic=True)]

    note_id = window.insert_footnote(rich)
    assert note_id == "1"
    assert window.footnote_definitions == {"1": rich}
    assert extract_blocks(window.editor.document())[0].runs[-1] == InlineRun(
        footnote_ref="1"
    )

    second = QtEditorWindow()
    populate_document(
        second.editor.document(),
        [Block(kind=PARAGRAPH, runs=[InlineRun(text="Corps")])],
    )
    monkeypatch.setattr(
        window_module,
        "insert_footnote_reference",
        lambda *args: (_ for _ in ()).throw(RuntimeError("échec simulé")),
    )
    with pytest.raises(RuntimeError, match="échec simulé"):
        second.insert_footnote(rich)
    assert second.footnote_definitions == {}


def test_rich_definition_save_reopen_preserves_runs_front_matter_and_renumbering(tmp_path):
    original = [
        Block(
            kind=PARAGRAPH,
            runs=[InlineRun(text="Bossuet"), InlineRun(footnote_ref="3")],
        ),
        Block(
            kind=FOOTNOTE_DEFINITION,
            footnote_id="3",
            runs=[InlineRun(text="Initiale")],
        ),
    ]
    path = write_content_file(
        tmp_path,
        "rich-note.md",
        {"title": "Notes riches", "slug": "notes-riches"},
        blocks_to_markdown(original),
    )
    window = QtEditorWindow(path)
    updated = [
        InlineRun(text="Une "),
        InlineRun(text="note importante", bold=True),
        InlineRun(text=" avec "),
        InlineRun(text="un lien", link_href="https://example.org"),
        InlineRun(text=" et "),
        InlineRun(text="Meaux", italic=True),
        InlineRun(text=" puis "),
        InlineRun(text="e", superscript=True),
        InlineRun(text="."),
    ]
    assert window.edit_footnote_definition("3", updated)

    assert window.save_document()

    metadata, markdown = read_content_file(path)
    body, definitions = separate_footnote_definitions(markdown_to_blocks(markdown))
    assert metadata == {"title": "Notes riches", "slug": "notes-riches"}
    assert body[0].runs[-1] == InlineRun(footnote_ref="1")
    assert definitions == {"1": updated}
    reopened = QtEditorWindow(path)
    assert reopened.footnote_definitions == {"1": updated}
    assert not reopened.document_has_unsaved_changes
