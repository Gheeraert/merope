from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent, QTextCursor
from PySide6.QtWidgets import QApplication

from bloggen.markdown.rich_text_export import blocks_to_markdown
from bloggen.markdown.rich_text_model import (
    BLOCKQUOTE,
    BULLET_LIST,
    HEADING,
    LIST_ITEM,
    PARAGRAPH,
    Block,
    InlineRun,
)
from bloggen.markdown.typography import NBSP, apply_french_typography
from bloggen.ui.content_editor.typography import TypographyMixin
from bloggen.ui.qt_editor.document_adapter import extract_blocks, populate_document
from bloggen.ui.qt_editor.text_edit import MeropeTextEdit


@pytest.fixture(scope="module", autouse=True)
def qapplication():
    app = QApplication.instance() or QApplication([])
    yield app


def _editor(blocks: list[Block] | None = None) -> MeropeTextEdit:
    editor = MeropeTextEdit()
    populate_document(editor.document(), blocks or [])
    cursor = editor.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.End)
    editor.setTextCursor(cursor)
    editor.show()
    editor.setFocus()
    return editor


def _type(editor: MeropeTextEdit, text: str) -> None:
    for char in text:
        event = QKeyEvent(
            QEvent.Type.KeyPress,
            Qt.Key.Key_unknown,
            Qt.KeyboardModifier.NoModifier,
            char,
        )
        QApplication.sendEvent(editor, event)
    QApplication.processEvents()


def _leaf_text(block: Block) -> str:
    return "".join(run.text for run in block.runs)


def _document_text(editor: MeropeTextEdit) -> str:
    blocks = extract_blocks(editor.document())
    return "\n".join(_leaf_text(block) for block in blocks)


def test_straight_quote_opens_then_closes_with_internal_nbsp():
    editor = _editor()

    _type(editor, '"Bossuet"')

    assert _document_text(editor) == f"«{NBSP}Bossuet{NBSP}»"


def test_opening_and_closing_guillemets_typed_directly_get_internal_nbsp():
    editor = _editor()

    _type(editor, "«Bossuet »")

    assert _document_text(editor) == f"«{NBSP}Bossuet{NBSP}»"


@pytest.mark.parametrize("punctuation", list(";:!?"))
@pytest.mark.parametrize("existing_space", [False, True])
def test_double_punctuation_gets_exactly_one_nbsp(punctuation, existing_space):
    editor = _editor()
    _type(editor, "Texte" + (" " if existing_space else "") + punctuation)

    assert _document_text(editor) == f"Texte{NBSP}{punctuation}"


@pytest.mark.parametrize(
    ("typed", "expected"),
    [("Voir p. 12", f"Voir p.{NBSP}12"), ("Voir pp. 123", f"Voir pp.{NBSP}123")],
)
def test_page_number_space_becomes_nbsp(typed, expected):
    editor = _editor()

    _type(editor, typed)

    assert _document_text(editor) == expected


def test_space_before_period_is_removed():
    editor = _editor()

    _type(editor, f"Texte {NBSP} .")

    assert _document_text(editor) == "Texte."


@pytest.mark.parametrize(
    ("typed", "expected"),
    [("oeuvre", "œuvre"), ("soeur", "sœur"), ("Oeuvre", "Œuvre")],
)
def test_supported_oe_word_is_ligatured_while_typing(typed, expected):
    editor = _editor()

    _type(editor, typed)

    assert _document_text(editor) == expected


@pytest.mark.parametrize("ordinal", ["XVe", "XVIe", "XVIIe", "XXIe"])
def test_common_century_suffix_is_semantic_superscript_immediately(ordinal):
    editor = _editor()

    _type(editor, ordinal)

    runs = extract_blocks(editor.document())[0].runs
    assert "".join(run.text for run in runs) == ordinal
    assert runs[-1] == InlineRun(text="e", superscript=True)


def test_century_superscript_does_not_leak_into_following_text():
    editor = _editor()

    _type(editor, "XVIIe siècle")

    assert extract_blocks(editor.document())[0].runs == [
        InlineRun(text="XVII"),
        InlineRun(text="e", superscript=True),
        InlineRun(text=" siècle"),
    ]


@pytest.mark.parametrize(
    "run",
    [
        InlineRun(text="mot", bold=True),
        InlineRun(text="mot", italic=True),
        InlineRun(text="mot", strikethrough=True),
        InlineRun(text="mot", superscript=True),
        InlineRun(text="mot", link_href="https://example.org"),
    ],
)
def test_typing_autocorrection_preserves_existing_inline_format(run):
    editor = _editor([Block(kind=PARAGRAPH, runs=[run])])

    _type(editor, ":")

    extracted = extract_blocks(editor.document())[0].runs
    assert extracted[0].text.startswith("mot")
    assert extracted[0].bold == run.bold
    assert extracted[0].italic == run.italic
    assert extracted[0].strikethrough == run.strikethrough
    assert extracted[0].superscript == run.superscript
    assert extracted[0].link_href == run.link_href


@pytest.mark.parametrize(
    ("block", "expected_kind"),
    [
        (
            Block(kind=HEADING, level=2, runs=[InlineRun(text="Titre", italic=True)]),
            HEADING,
        ),
        (
            Block(kind=BLOCKQUOTE, runs=[InlineRun(text="Citation", bold=True)]),
            BLOCKQUOTE,
        ),
    ],
)
def test_autocorrection_preserves_heading_and_blockquote(block, expected_kind):
    editor = _editor([block])

    _type(editor, "!")

    extracted = extract_blocks(editor.document())[0]
    assert extracted.kind == expected_kind
    assert _leaf_text(extracted).endswith(f"{NBSP}!")
    assert extracted.runs[0].bold == block.runs[0].bold
    assert extracted.runs[0].italic == block.runs[0].italic


def test_autocorrection_preserves_list_structure():
    editor = _editor(
        [
            Block(
                kind=BULLET_LIST,
                children=[Block(kind=LIST_ITEM, runs=[InlineRun(text="Élément")])],
            )
        ]
    )

    _type(editor, "?")

    extracted = extract_blocks(editor.document())[0]
    assert extracted.kind == BULLET_LIST
    assert _leaf_text(extracted.children[0]) == f"Élément{NBSP}?"


def test_autocorrection_preserves_paragraph_alignment():
    editor = _editor(
        [Block(kind=PARAGRAPH, runs=[InlineRun(text="Aligné")], alignment="right")]
    )

    _type(editor, ";")

    extracted = extract_blocks(editor.document())[0]
    assert extracted.alignment == "right"
    assert _leaf_text(extracted) == f"Aligné{NBSP};"


def test_non_bmp_character_before_correction_does_not_shift_the_edit():
    editor = _editor()

    _type(editor, "📚Texte:")

    assert _document_text(editor) == f"📚Texte{NBSP}:"


def test_century_superscript_preserves_bold_italic_and_link():
    editor = _editor(
        [
            Block(
                kind=PARAGRAPH,
                runs=[
                    InlineRun(
                        text="XVII",
                        bold=True,
                        italic=True,
                        link_href="https://example.org",
                    )
                ],
            )
        ]
    )

    _type(editor, "e")

    runs = extract_blocks(editor.document())[0].runs
    assert runs[-1] == InlineRun(
        text="e",
        bold=True,
        italic=True,
        superscript=True,
        link_href="https://example.org",
    )


@pytest.mark.parametrize(
    ("initial", "typed", "corrected"),
    [
        ("Mérope ", ":", f"Mérope{NBSP}:"),
        ("", '"', f"«{NBSP}"),
        ("oeuvr", "e", "œuvre"),
        ("Voir p. ", "1", f"Voir p.{NBSP}1"),
        ("XVII", "e", "XVIIe"),
    ],
)
def test_typing_and_autocorrection_are_one_native_undo_step(initial, typed, corrected):
    blocks = [Block(kind=PARAGRAPH, runs=[InlineRun(text=initial)])] if initial else []
    editor = _editor(blocks)

    _type(editor, typed)
    assert _document_text(editor) == corrected

    editor.undo()
    assert _document_text(editor) == initial
    editor.redo()
    assert _document_text(editor) == corrected


def test_quote_undo_redo_needs_no_external_parity_state():
    editor = _editor()
    _type(editor, '"mot"')
    closed = _document_text(editor)

    editor.undo()
    assert _document_text(editor) == f"«{NBSP}mot"
    editor.redo()
    assert _document_text(editor) == closed

    editor.undo()
    _type(editor, '"')
    assert _document_text(editor) == closed


def test_quote_choice_follows_document_at_moved_cursor():
    editor = _editor()
    _type(editor, '"un"')

    cursor = editor.textCursor()
    cursor.setPosition(0)
    editor.setTextCursor(cursor)
    _type(editor, '"')
    assert _document_text(editor).startswith(f"«{NBSP}«{NBSP}un")

    cursor = editor.textCursor()
    cursor.setPosition(4)
    editor.setTextCursor(cursor)
    _type(editor, '"')
    assert _document_text(editor)[4:6] == f"{NBSP}»"


def test_quote_key_wraps_a_mixed_format_selection_without_flattening_it():
    editor = _editor(
        [
            Block(
                kind=PARAGRAPH,
                runs=[InlineRun(text="mot "), InlineRun(text="fort", bold=True)],
            )
        ]
    )
    cursor = editor.textCursor()
    cursor.select(QTextCursor.SelectionType.Document)
    editor.setTextCursor(cursor)

    _type(editor, '"')

    block = extract_blocks(editor.document())[0]
    assert _leaf_text(block) == f"«{NBSP}mot fort{NBSP}»"
    assert any("fort" in run.text and run.bold for run in block.runs)

    editor.undo()
    assert extract_blocks(editor.document())[0].runs == [
        InlineRun(text="mot "),
        InlineRun(text="fort", bold=True),
    ]


def test_apply_typography_to_selection_crosses_fragments_and_is_one_undo_step():
    original = [
        InlineRun(text='"mot '),
        InlineRun(text="fort", bold=True),
        InlineRun(text='?"'),
    ]
    editor = _editor([Block(kind=PARAGRAPH, runs=original)])
    cursor = editor.textCursor()
    cursor.select(QTextCursor.SelectionType.Document)
    editor.setTextCursor(cursor)

    assert editor.apply_typography_to_selection() is True

    block = extract_blocks(editor.document())[0]
    assert _leaf_text(block) == f"«{NBSP}mot fort{NBSP}?{NBSP}»"
    assert any(run.text == "fort" and run.bold for run in block.runs)
    editor.undo()
    assert extract_blocks(editor.document())[0].runs == original
    editor.redo()
    assert _leaf_text(extract_blocks(editor.document())[0]) == (
        f"«{NBSP}mot fort{NBSP}?{NBSP}»"
    )


def test_full_typographic_example_roundtrips_to_semantic_markdown():
    editor = _editor()

    _type(editor, '"Bossuet", p. 12 : l\'oeuvre du XVIIe siècle !')

    blocks = extract_blocks(editor.document())
    assert _leaf_text(blocks[0]) == (
        f"«{NBSP}Bossuet{NBSP}», p.{NBSP}12{NBSP}: "
        f"l'œuvre du XVIIe siècle{NBSP}!"
    )
    assert any(run.text == "e" and run.superscript for run in blocks[0].runs)
    assert blocks_to_markdown(blocks) == (
        f"«{NBSP}Bossuet{NBSP}», p.{NBSP}12{NBSP}: "
        f"l'œuvre du XVII^e^ siècle{NBSP}!\n"
    )


@pytest.mark.parametrize(
    "typed",
    ['"Bossuet"', "Voir p. 12 :", "l'oeuvre ."],
)
def test_qt_and_tk_typing_rules_produce_the_same_unicode_text(typed, tk_root):
    tk_widget = __import__("tkinter").Text(tk_root)
    tk_widget.tag_configure("superscript", offset=4)
    harness = TypographyMixin()
    opening_next = True
    for char in typed:
        tk_widget.insert("insert", char)
        opening_next = harness._apply_typing_autoformat(
            tk_widget,
            char,
            opening_next=opening_next,
        )

    editor = _editor()
    _type(editor, typed)

    assert _document_text(editor) == tk_widget.get("1.0", "end-1c")
    assert _document_text(editor) == apply_french_typography(
        tk_widget.get("1.0", "end-1c")
    )
    tk_widget.destroy()
