from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QApplication, QInputDialog, QMessageBox

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
from bloggen.ui.qt_editor import window as window_module
from bloggen.ui.qt_editor.document_adapter import (
    extract_blocks,
    populate_document,
    renumber_footnote_references,
)
from bloggen.ui.qt_editor.footnote_selection import merope_footnote_at_position
from bloggen.ui.qt_editor.window import QtEditorWindow


@pytest.fixture(scope="module", autouse=True)
def qapplication():
    yield QApplication.instance() or QApplication([])


def _targets(window: QtEditorWindow):
    targets = {}
    document = window.editor.document()
    for position in range(document.characterCount() - 1):
        target = merope_footnote_at_position(document, position)
        if target is not None:
            targets[target.start] = target
    return list(targets.values())


def _set_cursor(window: QtEditorWindow, position: int) -> None:
    cursor = QTextCursor(window.editor.document())
    cursor.setPosition(position)
    window.editor.setTextCursor(cursor)


def _select(window: QtEditorWindow, start: int, end: int) -> None:
    cursor = QTextCursor(window.editor.document())
    cursor.setPosition(start)
    cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
    window.editor.setTextCursor(cursor)


def _load_model(
    window: QtEditorWindow,
    body: list[Block],
    definitions: dict[str, list[InlineRun]] | None = None,
) -> None:
    populate_document(window.editor.document(), body)
    window.editor.document().setModified(False)
    window.footnote_store.load(definitions or {})


@pytest.mark.parametrize("position", [3, 6])
def test_insert_note_at_middle_and_end_of_paragraph(position):
    window = QtEditorWindow()
    _load_model(
        window,
        [Block(kind=PARAGRAPH, runs=[InlineRun(text="Milieu")])],
    )
    _set_cursor(window, position)

    note_id = window.insert_footnote("Définition")

    assert note_id == "1"
    assert window.footnote_definitions == {
        "1": [InlineRun(text="Définition")]
    }
    assert [run.footnote_ref for run in extract_blocks(window.editor.document())[0].runs].count(
        "1"
    ) == 1
    assert _targets(window)[0].start == position
    assert window.footnote_panel.toPlainText() == "[1] Définition"


def test_insert_note_in_simple_list_item():
    window = QtEditorWindow()
    blocks = [
        Block(
            kind=BULLET_LIST,
            children=[Block(kind=LIST_ITEM, runs=[InlineRun(text="Élément")])],
        )
    ]
    _load_model(window, blocks)
    block = window.editor.document().begin()
    _set_cursor(window, block.position() + 3)

    window.insert_footnote("Dans la liste")

    extracted = extract_blocks(window.editor.document())
    assert extracted[0].kind == BULLET_LIST
    assert extracted[0].children[0].runs[1] == InlineRun(footnote_ref="1")


def test_insert_between_two_references_and_allocate_first_free_id():
    window = QtEditorWindow()
    body = [
        Block(
            kind=PARAGRAPH,
            runs=[InlineRun(footnote_ref="1"), InlineRun(footnote_ref="3")],
        )
    ]
    definitions = {
        "1": [InlineRun(text="Une")],
        "3": [InlineRun(text="Trois")],
    }
    _load_model(window, body, definitions)
    _set_cursor(window, _targets(window)[0].end)

    note_id = window.insert_footnote("Deux")

    assert note_id == "2"
    assert [run.footnote_ref for run in extract_blocks(window.editor.document())[0].runs] == [
        "1",
        "2",
        "3",
    ]


def test_inserted_reference_does_not_inherit_bold_or_link_format():
    window = QtEditorWindow()
    _load_model(
        window,
        [
            Block(
                kind=PARAGRAPH,
                runs=[
                    InlineRun(
                        text="Gras",
                        bold=True,
                        link_href="https://example.org",
                    )
                ],
            )
        ],
    )
    _set_cursor(window, 2)

    window.insert_footnote("Neutre")

    runs = extract_blocks(window.editor.document())[0].runs
    marker = next(run for run in runs if run.footnote_ref is not None)
    assert marker == InlineRun(footnote_ref="1")


def test_insert_with_selection_is_refused_without_replacing_text_or_store():
    window = QtEditorWindow()
    original = [Block(kind=PARAGRAPH, runs=[InlineRun(text="Sélection")])]
    _load_model(window, original)
    _select(window, 0, 4)

    with pytest.raises(ValueError, match="Désélectionnez"):
        window.insert_footnote("Note")

    assert extract_blocks(window.editor.document()) == original
    assert window.footnote_definitions == {}


def test_empty_insert_is_refused_and_dialog_cancellation_is_noop(monkeypatch):
    window = QtEditorWindow()
    monkeypatch.setattr(QInputDialog, "getText", lambda *args: ("", False))

    assert not window._insert_footnote_from_dialog()
    assert window.footnote_definitions == {}
    with pytest.raises(ValueError, match="vide"):
        window.insert_footnote("")


def test_undo_inserted_reference_keeps_orphan_definition_and_global_dirty():
    window = QtEditorWindow()
    _load_model(window, [Block(kind=PARAGRAPH, runs=[InlineRun(text="Corps")])])
    _set_cursor(window, 5)
    window.insert_footnote("Orpheline après undo")

    window.editor.undo()

    assert extract_blocks(window.editor.document()) == [
        Block(kind=PARAGRAPH, runs=[InlineRun(text="Corps")])
    ]
    assert window.footnote_definitions == {
        "1": [InlineRun(text="Orpheline après undo")]
    }
    assert window.document_has_unsaved_changes
    assert window.windowTitle().endswith("*")


def test_inserted_definition_is_saved_and_reopened(tmp_path):
    path = write_content_file(
        tmp_path,
        "insert.md",
        {"title": "Insertion"},
        "Corps.\n",
    )
    window = QtEditorWindow(path)
    _set_cursor(window, 5)

    window.insert_footnote("Nouvelle note")
    assert window.save_document()

    reopened = QtEditorWindow(path)
    assert _targets(reopened)[0].note_id == "1"
    assert reopened.footnote_definitions == {
        "1": [InlineRun(text="Nouvelle note")]
    }


def test_store_only_change_sets_global_dirty_and_unsaved_prompt(monkeypatch):
    window = QtEditorWindow()
    _load_model(
        window,
        [Block(kind=PARAGRAPH, runs=[InlineRun(footnote_ref="1")])],
        {"1": [InlineRun(text="Initiale")]},
    )
    answers = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda *args: answers.append(args) or QMessageBox.StandardButton.Cancel,
    )

    assert window.edit_footnote_definition("1", "Modifiée")

    assert not window.editor.document().isModified()
    assert window.footnote_store.modified
    assert window.document_has_unsaved_changes
    assert window.windowTitle().endswith("*")
    assert not window._confirm_unsaved_changes()
    assert answers


def test_store_dirty_can_cancel_opening_another_file(tmp_path, monkeypatch):
    first = write_content_file(
        tmp_path,
        "first-dirty.md",
        {"title": "Premier"},
        "Premier[^1].\n\n[^1]: Une.\n",
    )
    second = write_content_file(
        tmp_path,
        "second-clean.md",
        {"title": "Second"},
        "Second.\n",
    )
    window = QtEditorWindow(first)
    window.edit_footnote_definition("1", "Modifiée")
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda *args: QMessageBox.StandardButton.Cancel,
    )

    assert not window.open_document(second)
    assert window.current_path == first
    assert window.footnote_definitions == {
        "1": [InlineRun(text="Modifiée")]
    }


def test_simple_definition_edit_cancel_and_rich_definition_refusal(monkeypatch):
    window = QtEditorWindow()
    _load_model(
        window,
        [Block(kind=PARAGRAPH, runs=[InlineRun(footnote_ref="1")])],
        {"1": [InlineRun(text="Simple")]},
    )
    monkeypatch.setattr(
        QInputDialog,
        "getText",
        lambda *args: ("Ignorée", False),
    )
    assert not window._edit_selected_footnote()
    assert window.footnote_definitions["1"] == [InlineRun(text="Simple")]

    window.footnote_store.load(
        {"1": [InlineRun(text="Riche", bold=True)]}
    )
    assert not window.edit_footnote_button.isEnabled()
    with pytest.raises(ValueError, match="mise en forme riche"):
        window.edit_footnote_definition("1", "Perdue")
    assert window.footnote_definitions["1"] == [
        InlineRun(text="Riche", bold=True)
    ]


@pytest.mark.parametrize("reference_count", [0, 1, 2])
def test_delete_definition_keeps_zero_one_or_multiple_body_references(
    reference_count,
    monkeypatch,
):
    window = QtEditorWindow()
    runs = []
    for index in range(reference_count):
        if index:
            runs.append(InlineRun(text=" "))
        runs.append(InlineRun(footnote_ref="1"))
    _load_model(
        window,
        [Block(kind=PARAGRAPH, runs=runs or [InlineRun(text="Sans appel")])],
        {"1": [InlineRun(text="À supprimer")]},
    )
    messages = []
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args: messages.append(args[2]) or QMessageBox.StandardButton.Yes,
    )

    assert window._delete_selected_footnote()

    assert window.footnote_definitions == {}
    assert len(_targets(window)) == reference_count
    assert str(reference_count) in messages[0] if reference_count else "orpheline" in messages[0]
    assert window.footnote_store.modified


def test_save_and_reopen_simple_edit_and_reference_without_definition(tmp_path):
    body = "Corps[^1].\n\n[^1]: Initiale.\n"
    path = write_content_file(tmp_path, "notes.md", {"title": "Notes"}, body)
    window = QtEditorWindow(path)
    assert window.edit_footnote_definition("1", "Modifiée.")
    assert window.save_document()

    assert not window.document_has_unsaved_changes
    reopened = QtEditorWindow(path)
    assert reopened.footnote_definitions == {
        "1": [InlineRun(text="Modifiée.")]
    }

    reopened.delete_footnote_definition("1")
    assert reopened.save_document()
    final = QtEditorWindow(path)
    assert final.footnote_definitions == {}
    assert _targets(final)[0].note_id == "1"


def test_opening_another_file_reloads_store_cleanly(tmp_path):
    first = write_content_file(
        tmp_path,
        "first.md",
        {"title": "Premier"},
        "Premier[^1].\n\n[^1]: Une.\n",
    )
    second = write_content_file(
        tmp_path,
        "second.md",
        {"title": "Second"},
        "Second[^2].\n\n[^2]: Deux.\n",
    )
    window = QtEditorWindow(first)
    window.edit_footnote_definition("1", "Sale")

    window.load_markdown(second)

    assert window.footnote_definitions == {"2": [InlineRun(text="Deux.")]}
    assert not window.footnote_store.modified
    assert not window.document_has_unsaved_changes


def test_save_renumbers_duplicates_missing_definition_and_orphan(tmp_path):
    blocks = [
        Block(
            kind=PARAGRAPH,
            runs=[
                InlineRun(footnote_ref="3"),
                InlineRun(text=" "),
                InlineRun(footnote_ref="8"),
                InlineRun(text=" "),
                InlineRun(footnote_ref="3"),
                InlineRun(text=" "),
                InlineRun(footnote_ref="12"),
            ],
        ),
        Block(
            kind=FOOTNOTE_DEFINITION,
            footnote_id="3",
            runs=[InlineRun(text="Trois")],
        ),
        Block(
            kind=FOOTNOTE_DEFINITION,
            footnote_id="8",
            runs=[InlineRun(text="Huit")],
        ),
        Block(
            kind=FOOTNOTE_DEFINITION,
            footnote_id="20",
            runs=[InlineRun(text="Orpheline")],
        ),
    ]
    path = write_content_file(
        tmp_path,
        "renumber.md",
        {"title": "Renumérotation", "slug": "renumber"},
        blocks_to_markdown(blocks),
    )
    window = QtEditorWindow(path)

    assert window.save_document()

    metadata, saved_body = read_content_file(path)
    saved = markdown_to_blocks(saved_body)
    body_blocks, definitions = separate_footnote_definitions(saved)
    assert metadata == {"title": "Renumérotation", "slug": "renumber"}
    assert [run.footnote_ref for run in body_blocks[0].runs if run.footnote_ref] == [
        "1",
        "2",
        "1",
        "3",
    ]
    assert definitions == {
        "1": [InlineRun(text="Trois")],
        "2": [InlineRun(text="Huit")],
        "4": [InlineRun(text="Orpheline")],
    }
    assert not window.document_has_unsaved_changes


@pytest.mark.parametrize("prior_dirty", [False, True])
def test_failed_save_restores_body_store_and_prior_modified_states(
    tmp_path,
    monkeypatch,
    prior_dirty,
):
    path = write_content_file(
        tmp_path,
        "failure.md",
        {"title": "Échec"},
        "Corps[^3].\n\n[^3]: Note.\n",
    )
    window = QtEditorWindow(path)
    if prior_dirty:
        cursor = QTextCursor(window.editor.document())
        cursor.setPosition(0)
        cursor.insertText("X")
        window.edit_footnote_definition("3", "Note modifiée.")
    before_body = extract_blocks(window.editor.document())
    before_store = window.footnote_definitions
    monkeypatch.setattr(
        window_module,
        "save_content_document",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("échec simulé")),
    )
    monkeypatch.setattr(QMessageBox, "critical", lambda *args: None)

    assert not window.save_document()

    assert extract_blocks(window.editor.document()) == before_body
    assert window.footnote_definitions == before_store
    assert window.editor.document().isModified() is prior_dirty
    assert window.footnote_store.modified is prior_dirty
    assert window.document_has_unsaved_changes is prior_dirty


def test_reference_renumbering_is_one_native_body_undo_operation():
    window = QtEditorWindow()
    original = [
        Block(
            kind=PARAGRAPH,
            runs=[
                InlineRun(footnote_ref="12"),
                InlineRun(text=" "),
                InlineRun(footnote_ref="3"),
            ],
        )
    ]
    _load_model(window, original)

    assert renumber_footnote_references(
        window.editor.document(),
        {"12": "1", "3": "2"},
    )
    assert [target.note_id for target in _targets(window)] == ["1", "2"]

    window.editor.undo()
    assert extract_blocks(window.editor.document()) == original
    window.editor.redo()
    assert [target.note_id for target in _targets(window)] == ["1", "2"]


def test_successful_renumber_save_clears_undo_to_prevent_store_divergence(tmp_path):
    path = write_content_file(
        tmp_path,
        "undo.md",
        {"title": "Undo"},
        "Corps[^3].\n\n[^3]: Note.\n",
    )
    window = QtEditorWindow(path)
    cursor = QTextCursor(window.editor.document())
    cursor.setPosition(0)
    cursor.insertText("X")
    assert window.editor.document().isUndoAvailable()

    assert window.save_document()

    assert not window.editor.document().isUndoAvailable()
    window.editor.undo()
    assert _targets(window)[0].note_id == "1"
    assert set(window.footnote_definitions) == {"1"}
