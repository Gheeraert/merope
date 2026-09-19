from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCharFormat, QTextCursor, QTextFormat, QTextTable
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from bloggen.markdown.rich_text_export import blocks_to_markdown
from bloggen.markdown.rich_text_model import (
    BLOCKQUOTE,
    BULLET_LIST,
    HEADING,
    LIST_ITEM,
    PARAGRAPH,
    TABLE,
    TABLE_CELL,
    TABLE_ROW,
    VERBATIM,
    Block,
    InlineRun,
)
from bloggen.ui.qt_editor.document_adapter import (
    extract_blocks,
    is_caption_block,
    populate_document,
)
import bloggen.ui.qt_editor.spellcheck as spellcheck_module
from bloggen.ui.qt_editor.spellcheck import (
    FrenchSpellChecker,
    SpellingIssue,
    match_case,
    spellcheck_available,
)
from bloggen.ui.qt_editor.text_edit import MeropeTextEdit


_EDITORS: list[MeropeTextEdit] = []


@pytest.fixture(scope="module", autouse=True)
def qapplication():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(autouse=True)
def close_editors(qapplication):
    yield
    for editor in _EDITORS:
        editor.hide()
        editor.deleteLater()
    _EDITORS.clear()
    qapplication.processEvents()


def _editor(blocks: list[Block]) -> MeropeTextEdit:
    editor = MeropeTextEdit()
    _EDITORS.append(editor)
    populate_document(editor.document(), blocks)
    editor._spell_highlighter.rehighlight()
    QApplication.processEvents()
    return editor


def _spell_ranges(block) -> list[tuple[int, int]]:
    return [
        (item.start, item.length)
        for item in block.layout().formats()
        if item.format.underlineStyle()
        == QTextCharFormat.UnderlineStyle.SpellCheckUnderline
    ]


def _misspelled_text(block) -> list[str]:
    return [
        block.text()[start : start + length]
        for start, length in _spell_ranges(block)
    ]


def _table(*rows: tuple[InlineRun | str, ...]) -> Block:
    return Block(
        kind=TABLE,
        children=[
            Block(
                kind=TABLE_ROW,
                children=[
                    Block(
                        kind=TABLE_CELL,
                        runs=[
                            cell if isinstance(cell, InlineRun) else InlineRun(text=cell)
                        ],
                    )
                    for cell in row
                ],
            )
            for row in rows
        ],
    )


@pytest.mark.parametrize(
    "word",
    [
        "bonjour",
        "maison",
        "littérature",
        "français",
        "école",
        "élève",
        "œuvre",
    ],
)
def test_french_backend_recognizes_common_words(word):
    checker = FrenchSpellChecker()

    assert checker.available
    assert checker.issues(word) == []
    assert checker._spellchecker.distance == 1


def test_french_backend_returns_exact_source_ranges():
    checker = FrenchSpellChecker()
    text = "bonjour, bonjor et maisonnn."

    assert checker.issues(text) == [
        SpellingIssue(start=9, length=6, word="bonjor"),
        SpellingIssue(start=19, length=8, word="maisonnn"),
    ]


def test_backend_cache_normalizes_case_and_reuses_the_session_dictionary():
    checker = FrenchSpellChecker()
    other = FrenchSpellChecker()

    assert spellcheck_available()
    assert checker._spellchecker is other._spellchecker
    assert checker.is_known("Maison")
    assert len(checker._known_cache) == 1
    assert checker.is_known("maison")
    assert len(checker._known_cache) == 1
    assert checker.issues("Bonjor") == [
        SpellingIssue(start=0, length=6, word="Bonjor")
    ]


@pytest.mark.parametrize(
    "text",
    [
        "l’homme",
        "l'homme",
        "d’abord",
        "j’aime",
        "c’est",
        "qu’il",
        "lorsqu’il",
        "puisqu’il",
        "jusqu’ici",
        "aujourd’hui",
        "porte-monnaie",
        "dix-sept",
        "peut-être",
    ],
)
def test_french_backend_handles_elisions_and_compounds(text):
    assert FrenchSpellChecker().issues(text) == []


@pytest.mark.parametrize("text", ["l’hommee", "l'hommee"])
def test_french_backend_marks_only_the_bad_elided_component(text):
    assert FrenchSpellChecker().issues(text) == [
        SpellingIssue(start=2, length=6, word="hommee")
    ]


def test_french_backend_ignores_urls_email_acronyms_numbers_and_path():
    text = (
        "https://example.org/bonjor www.example.org/maisonnn "
        "test@example.org CNRS TEI XML 1685 12e C:\\Users\\Tony\\document.md"
    )

    assert FrenchSpellChecker().issues(text) == []


def test_backend_disables_cleanly_without_optional_dependency(monkeypatch):
    monkeypatch.setattr(spellcheck_module, "_load_spellchecker", lambda: None)

    checker = FrenchSpellChecker()

    assert not checker.available
    assert checker.issues("bonjor") == []


def test_highlighter_marks_only_the_unknown_word_in_a_paragraph():
    editor = _editor(
        [Block(kind=PARAGRAPH, runs=[InlineRun(text="bonjour bonjor")])]
    )

    assert _spell_ranges(editor.document().begin()) == [(8, 6)]
    assert _misspelled_text(editor.document().begin()) == ["bonjor"]
    issue_format = editor._spell_highlighter.issue_format
    assert (
        issue_format.underlineStyle()
        == QTextCharFormat.UnderlineStyle.SpellCheckUnderline
    )
    assert issue_format.underlineColor().isValid()
    for property_id in (
        QTextFormat.Property.ForegroundBrush,
        QTextFormat.Property.BackgroundBrush,
        QTextFormat.Property.FontWeight,
        QTextFormat.Property.FontItalic,
        QTextFormat.Property.FontPointSize,
    ):
        assert not issue_format.hasProperty(property_id)


def test_highlighting_preserves_rich_canonical_runs_and_markdown():
    original = [
        Block(
            kind=PARAGRAPH,
            runs=[
                InlineRun(text="bonjor", bold=True),
                InlineRun(text=" et "),
                InlineRun(
                    text="maisonnn",
                    italic=True,
                    underline=True,
                    link_href="https://example.org",
                ),
                InlineRun(text=" puis maison", italic=True),
                InlineRun(footnote_ref="1"),
            ],
        )
    ]
    expected_markdown = blocks_to_markdown(original)
    editor = _editor(original)
    document = editor.document()

    assert _misspelled_text(document.begin()) == ["bonjor", "maisonnn"]
    assert extract_blocks(document) == original
    assert blocks_to_markdown(extract_blocks(document)) == expected_markdown
    assert not document.isModified()
    assert not document.isUndoAvailable()


@pytest.mark.parametrize(
    "block",
    [
        Block(kind=PARAGRAPH, runs=[InlineRun(text="bonjor")]),
        Block(kind=HEADING, level=2, runs=[InlineRun(text="bonjor")]),
        Block(kind=BLOCKQUOTE, runs=[InlineRun(text="bonjor")]),
    ],
)
def test_highlighter_checks_editorial_leaf_blocks(block):
    editor = _editor([block])

    assert _misspelled_text(editor.document().begin()) == ["bonjor"]


def test_highlighter_checks_list_items():
    editor = _editor(
        [
            Block(
                kind=BULLET_LIST,
                children=[Block(kind=LIST_ITEM, runs=[InlineRun(text="bonjor")])],
            )
        ]
    )

    assert _misspelled_text(editor.document().begin()) == ["bonjor"]


def test_highlighter_checks_graphical_table_cells():
    editor = _editor([_table(("bonjour", "bonjor"), ("maison", "maisonnn"))])
    table = next(
        frame
        for frame in editor.document().rootFrame().childFrames()
        if isinstance(frame, QTextTable)
    )

    assert _misspelled_text(table.cellAt(0, 0).firstCursorPosition().block()) == []
    assert _misspelled_text(table.cellAt(0, 1).firstCursorPosition().block()) == [
        "bonjor"
    ]
    assert _misspelled_text(table.cellAt(1, 1).firstCursorPosition().block()) == [
        "maisonnn"
    ]
    assert extract_blocks(editor.document()) == [
        _table(("bonjour", "bonjor"), ("maison", "maisonnn"))
    ]


def test_highlighter_checks_caption_without_changing_image_alt():
    original = [
        Block(
            kind=PARAGRAPH,
            runs=[InlineRun(image_src="image.png", image_alt="bonjor")],
        )
    ]
    editor = _editor(original)
    caption = editor.document().begin()
    while caption.isValid() and not is_caption_block(caption):
        caption = caption.next()

    assert caption.isValid()
    assert _misspelled_text(caption) == ["bonjor"]
    assert extract_blocks(editor.document()) == original


def test_highlighter_skips_verbatim_and_raw_table_fallback():
    raw_table = _table(
        (
            InlineRun(
                image_src="cell.png",
                image_alt="bonjor",
            ),
        )
    )
    original = [Block(kind=VERBATIM, raw_text="bonjor"), raw_table]
    editor = _editor(original)

    block = editor.document().begin()
    while block.isValid():
        assert _spell_ranges(block) == []
        block = block.next()
    assert extract_blocks(editor.document()) == original


def test_rehighlight_is_presentation_only_and_survives_repopulation():
    editor = _editor([Block(kind=PARAGRAPH, runs=[InlineRun(text="bonjor")])])
    document = editor.document()
    before = extract_blocks(document)

    editor._spell_highlighter.rehighlight()
    QApplication.processEvents()

    assert extract_blocks(document) == before
    assert not document.isModified()
    assert not document.isUndoAvailable()

    replacement = [Block(kind=PARAGRAPH, runs=[InlineRun(text="maisonnn")])]
    populate_document(document, replacement)
    editor._spell_highlighter.rehighlight()
    QApplication.processEvents()
    assert _misspelled_text(document.begin()) == ["maisonnn"]
    assert extract_blocks(document) == replacement
    assert not document.isModified()
    assert not document.isUndoAvailable()


def test_live_typing_updates_spelling_and_undo_only_reverts_the_typing():
    editor = _editor([Block(kind=PARAGRAPH, runs=[InlineRun(text="bonjour")])])
    editor.show()
    editor.activateWindow()
    editor.setFocus()
    cursor = QTextCursor(editor.document().begin())
    cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock)
    editor.setTextCursor(cursor)
    QApplication.processEvents()

    QTest.keyClicks(editor, "x")
    QApplication.processEvents()
    assert editor.document().begin().text() == "bonjourx"
    assert _misspelled_text(editor.document().begin()) == ["bonjourx"]

    editor.undo()
    QApplication.processEvents()
    assert editor.document().begin().text() == "bonjour"
    assert _spell_ranges(editor.document().begin()) == []
    assert not editor.document().isModified()


def test_live_correction_removes_the_spelling_underline():
    editor = _editor([Block(kind=PARAGRAPH, runs=[InlineRun(text="bonjor")])])
    editor.show()
    editor.activateWindow()
    editor.setFocus()
    cursor = QTextCursor(editor.document().begin())
    cursor.setPosition(editor.document().begin().position() + 5)
    editor.setTextCursor(cursor)
    QApplication.processEvents()
    assert _misspelled_text(editor.document().begin()) == ["bonjor"]

    QTest.keyClicks(editor, "u")
    QApplication.processEvents()

    assert editor.document().begin().text() == "bonjour"
    assert _spell_ranges(editor.document().begin()) == []


def test_suggestions_ranks_a_correction_first_for_a_typo():
    checker = FrenchSpellChecker()

    assert "bonjour" in checker.suggestions("bonjor")


def test_suggestions_is_empty_for_an_already_correct_word():
    checker = FrenchSpellChecker()

    assert checker.suggestions("bonjour") == []


def test_suggestions_is_capped_at_the_requested_limit():
    checker = FrenchSpellChecker()

    assert len(checker.suggestions("bonjor", limit=2)) <= 2


@pytest.mark.parametrize(
    ("original", "replacement", "expected"),
    [
        ("boujour", "bonjour", "bonjour"),
        ("Boujour", "bonjour", "Bonjour"),
        ("BOUJOUR", "bonjour", "BONJOUR"),
        ("B", "bonjour", "Bonjour"),
    ],
)
def test_match_case_carries_the_original_capitalization(original, replacement, expected):
    assert match_case(original, replacement) == expected
