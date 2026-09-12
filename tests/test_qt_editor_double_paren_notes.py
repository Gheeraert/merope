"""Contract tests for the deliberately deferred ``((note))`` shorthand.

Unlike structured footnotes, double-parenthesis notes stay ordinary rich text
inside both Merope editors. Only Markdown normalization in the real
build/preview pipeline turns them into Pandoc inline notes.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QEvent, QMimeData, Qt
from PySide6.QtGui import QKeyEvent, QTextCursor
from PySide6.QtWidgets import QApplication

from bloggen.content.footnotes import separate_footnote_definitions
from bloggen.content.writer import read_content_file, write_content_file
from bloggen.markdown.normalizer import normalize_markdown_text
from bloggen.markdown.rich_text_export import blocks_to_markdown
from bloggen.markdown.rich_text_import import markdown_to_blocks
from bloggen.markdown.rich_text_model import (
    FOOTNOTE_DEFINITION,
    PARAGRAPH,
    Block,
    InlineRun,
)
from bloggen.markdown.typography import NBSP
from bloggen.ui.qt_editor.document_adapter import extract_blocks, populate_document
from bloggen.ui.qt_editor.footnote_editor import FootnoteTextEdit
from bloggen.ui.qt_editor.formatting import set_link, toggle_bold, toggle_italic
from bloggen.ui.qt_editor.text_edit import MeropeTextEdit
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


def _editor(
    blocks: list[Block] | None = None,
    *,
    cls: type[MeropeTextEdit] = MeropeTextEdit,
) -> MeropeTextEdit:
    editor = cls()
    populate_document(editor.document(), blocks or [])
    cursor = editor.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.End)
    editor.setTextCursor(cursor)
    editor.document().setModified(False)
    return editor


def _type(editor: MeropeTextEdit, text: str) -> None:
    for character in text:
        event = QKeyEvent(
            QEvent.Type.KeyPress,
            Qt.Key.Key_unknown,
            Qt.KeyboardModifier.NoModifier,
            character,
        )
        QApplication.sendEvent(editor, event)
    QApplication.processEvents()


def _select_all(editor: MeropeTextEdit) -> None:
    cursor = QTextCursor(editor.document())
    cursor.setPosition(0)
    cursor.setPosition(
        editor.document().characterCount() - 1,
        QTextCursor.MoveMode.KeepAnchor,
    )
    editor.setTextCursor(cursor)


def _select(editor: MeropeTextEdit, start: int, end: int) -> None:
    cursor = QTextCursor(editor.document())
    cursor.setPosition(start)
    cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
    editor.setTextCursor(cursor)


def _text(runs: list[InlineRun]) -> str:
    return "".join(run.text for run in runs)


def _assert_only_literal_text(blocks: list[Block], expected: str) -> None:
    assert len(blocks) == 1
    assert blocks[0].kind == PARAGRAPH
    assert _text(blocks[0].runs) == expected
    assert all(run.footnote_ref is None for run in blocks[0].runs)


@pytest.mark.parametrize(
    "typed",
    [
        "Une phrase((voici la note)).",
        "((note)).",
        "Mot((note)), suite",
        "A((une)) et B((deux)).",
    ],
)
def test_typing_double_parentheses_keeps_literal_text_without_reference(typed):
    editor = _editor()

    _type(editor, typed)

    _assert_only_literal_text(extract_blocks(editor.document()), typed)


def test_rich_content_inside_shortcut_roundtrips_as_ordinary_runs():
    runs = [
        InlineRun(text="Bossuet((voir "),
        InlineRun(text="Le Titre", italic=True),
        InlineRun(text=" et "),
        InlineRun(
            text="ce lien",
            bold=True,
            link_href="https://example.org",
        ),
        InlineRun(text=" pour plus))."),
    ]
    editor = _editor([Block(kind=PARAGRAPH, runs=runs)])

    extracted = extract_blocks(editor.document())

    assert extracted == [Block(kind=PARAGRAPH, runs=runs)]
    assert all(run.footnote_ref is None for run in extracted[0].runs)
    markdown = blocks_to_markdown(extracted)
    assert markdown == (
        "Bossuet((voir *Le Titre* et "
        "[**ce lien**](https://example.org) pour plus)).\n"
    )
    assert markdown_to_blocks(markdown) == extracted


def test_user_can_apply_rich_formats_inside_literal_shortcut():
    editor = _editor(
        [
            Block(
                kind=PARAGRAPH,
                runs=[InlineRun(text="((voir Le Titre et lien))")],
            )
        ]
    )

    _select(editor, 2, 6)
    toggle_bold(editor)
    _select(editor, 7, 15)
    toggle_italic(editor)
    _select(editor, 19, 23)
    set_link(editor, "https://example.org")

    runs = extract_blocks(editor.document())[0].runs
    assert _text(runs) == "((voir Le Titre et lien))"
    assert any(run.text == "voir" and run.bold for run in runs)
    assert any(run.text == "Le Titre" and run.italic for run in runs)
    assert any(
        run.text == "lien" and run.link_href == "https://example.org"
        for run in runs
    )
    assert all(run.footnote_ref is None for run in runs)


def test_internal_merope_clipboard_preserves_rich_literal_shortcut():
    runs = [
        InlineRun(text="((une "),
        InlineRun(text="note", bold=True, italic=True),
        InlineRun(text=" liée", link_href="https://example.org"),
        InlineRun(text="))"),
    ]
    source = _editor([Block(kind=PARAGRAPH, runs=runs)])
    destination = _editor()
    _select_all(source)

    source.copy()
    destination.paste()

    assert extract_blocks(destination.document()) == [
        Block(kind=PARAGRAPH, runs=runs, alignment="justify")
    ]
    assert all(
        run.footnote_ref is None
        for run in extract_blocks(destination.document())[0].runs
    )


def test_internal_merope_cut_and_paste_moves_literal_shortcut_as_rich_text():
    runs = [
        InlineRun(text="Avant "),
        InlineRun(text="((note", bold=True),
        InlineRun(text=" riche))", italic=True),
        InlineRun(text=" après"),
    ]
    editor = _editor([Block(kind=PARAGRAPH, runs=runs)])
    _select(editor, 6, 20)

    editor.cut()
    cut_blocks = extract_blocks(editor.document())
    assert _text(cut_blocks[0].runs) == "Avant  après"
    cursor = editor.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.End)
    editor.setTextCursor(cursor)
    editor.paste()

    pasted = extract_blocks(editor.document())[0].runs
    assert _text(pasted) == "Avant  après((note riche))"
    assert any(run.text == "((note" and run.bold for run in pasted)
    assert any(run.text == "riche))" and run.italic for run in pasted)
    assert all(run.footnote_ref is None for run in pasted)


def test_literal_shortcut_copied_from_modal_note_stays_literal_in_body():
    runs = [
        InlineRun(text="((quelque "),
        InlineRun(text="chose", italic=True),
        InlineRun(text="))"),
    ]
    note = _editor([Block(kind=PARAGRAPH, runs=runs)], cls=FootnoteTextEdit)
    body = _editor()
    _select_all(note)

    note.copy()
    body.paste()

    assert extract_blocks(body.document()) == [
        Block(kind=PARAGRAPH, runs=runs, alignment="justify")
    ]


def test_html_paste_keeps_double_parentheses_as_normal_rich_text():
    editor = _editor()
    mime = QMimeData()
    mime.setHtml(
        '<p>Bossuet((une <strong>note</strong> avec '
        '<a href="https://example.org">lien</a>)).</p>'
    )
    mime.setText("fallback interdit")

    editor.insertFromMimeData(mime)

    blocks = extract_blocks(editor.document())
    _assert_only_literal_text(blocks, "Bossuet((une note avec lien)).")
    assert any(run.text == "note" and run.bold for run in blocks[0].runs)
    assert any(
        run.text == "lien" and run.link_href == "https://example.org"
        for run in blocks[0].runs
    )


def test_typography_does_not_touch_double_parenthesis_delimiters():
    editor = _editor(
        [Block(kind=PARAGRAPH, runs=[InlineRun(text="Mot((note)) : suite")])]
    )
    _select_all(editor)

    assert editor.apply_typography_to_selection()

    _assert_only_literal_text(
        extract_blocks(editor.document()),
        f"Mot((note)){NBSP}: suite",
    )


def test_save_and_reopen_preserve_rich_shortcut_without_footnote_store(tmp_path):
    runs = [
        InlineRun(text="Bossuet parle((Une remarque sur "),
        InlineRun(text="Meaux", bold=True),
        InlineRun(text="))."),
    ]
    markdown = blocks_to_markdown([Block(kind=PARAGRAPH, runs=runs)])
    path = write_content_file(
        tmp_path,
        "shortcut.md",
        {"title": "Raccourci", "slug": "shortcut"},
        markdown,
    )
    window = QtEditorWindow(path)
    _metadata, original_body = read_content_file(path)

    assert window.footnote_definitions == {}
    assert window.save_document()

    metadata, saved_body = read_content_file(path)
    assert metadata == {"title": "Raccourci", "slug": "shortcut"}
    assert saved_body == original_body
    assert "[^" not in saved_body
    reopened = QtEditorWindow(path)
    assert reopened.footnote_definitions == {}
    assert extract_blocks(reopened.editor.document()) == [
        Block(kind=PARAGRAPH, runs=runs)
    ]


def test_structured_and_deferred_notes_coexist_and_only_real_note_renumbers(tmp_path):
    blocks = [
        Block(
            kind=PARAGRAPH,
            runs=[
                InlineRun(text="Vraie note"),
                InlineRun(footnote_ref="3"),
                InlineRun(text=" et raccourci((note différée))."),
            ],
        ),
        Block(
            kind=FOOTNOTE_DEFINITION,
            footnote_id="3",
            runs=[InlineRun(text="Définition structurée.")],
        ),
    ]
    path = write_content_file(
        tmp_path,
        "coexistence.md",
        {"title": "Coexistence"},
        blocks_to_markdown(blocks),
    )
    window = QtEditorWindow(path)

    assert window.save_document()

    _metadata, saved_body = read_content_file(path)
    body, definitions = separate_footnote_definitions(markdown_to_blocks(saved_body))
    assert [run.footnote_ref for run in body[0].runs if run.footnote_ref] == ["1"]
    assert _text(body[0].runs) == "Vraie note et raccourci((note différée))."
    assert definitions == {"1": [InlineRun(text="Définition structurée.")]}
    assert "((note différée))" in saved_body
    assert normalize_markdown_text(saved_body, google_docs_mode=False) == (
        "\nVraie note[^1] et raccourci^[note différée].\n\n"
        "[^1]: Définition structurée.\n"
    )


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("Bossuet((une note)).", "Bossuet^[une note].\n"),
        ("Bossuet((une note)), suite", "Bossuet^[une note], suite\n"),
        (
            "A((première)) et B((seconde)).",
            "A^[première] et B^[seconde].\n",
        ),
        (
            "Bossuet((voir [Meaux](https://example.org))).",
            "Bossuet^[voir [Meaux](https://example.org)].\n",
        ),
    ],
)
def test_real_normalizer_converts_saved_shortcuts_only_at_build_time(
    source,
    expected,
):
    assert normalize_markdown_text(source, google_docs_mode=False) == expected


def test_real_normalizer_keeps_inline_and_fenced_code_protected():
    source = (
        "Texte `((code inline))` et ((note réelle)).\n\n"
        "```text\n((code bloc))\n```\n"
    )

    normalized = normalize_markdown_text(source, google_docs_mode=False)

    assert "`((code inline))`" in normalized
    assert "^[note réelle]" in normalized
    assert "((code bloc))" in normalized
    assert "^[code inline]" not in normalized
    assert "^[code bloc]" not in normalized
