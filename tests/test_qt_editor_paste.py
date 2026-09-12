from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QMimeData
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QApplication

from bloggen.markdown.rich_text_export import blocks_to_markdown
from bloggen.markdown.rich_text_model import (
    BLOCKQUOTE,
    BULLET_LIST,
    HEADING,
    LIST_ITEM,
    ORDERED_LIST,
    PARAGRAPH,
    VERBATIM,
    Block,
    InlineRun,
)
from bloggen.markdown.typography import NBSP
from bloggen.ui.qt_editor import text_edit as text_edit_module
from bloggen.ui.qt_editor.document_adapter import extract_blocks, populate_document
from bloggen.ui.qt_editor.text_edit import MeropeTextEdit


@pytest.fixture(scope="module", autouse=True)
def qapplication():
    app = QApplication.instance() or QApplication([])
    yield app
    app.clipboard().clear()


def _editor(blocks: list[Block] | None = None) -> MeropeTextEdit:
    editor = MeropeTextEdit()
    populate_document(editor.document(), blocks or [])
    return editor


def _paste_html(editor: MeropeTextEdit, html: str, *, text: str = "fallback") -> None:
    mime = QMimeData()
    mime.setHtml(html)
    mime.setText(text)
    editor.insertFromMimeData(mime)


def _paste_text(editor: MeropeTextEdit, text: str) -> None:
    mime = QMimeData()
    mime.setText(text)
    editor.insertFromMimeData(mime)


def _set_cursor(editor: MeropeTextEdit, position: int, end: int | None = None) -> None:
    cursor = editor.textCursor()
    cursor.setPosition(position)
    if end is not None:
        cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
    editor.setTextCursor(cursor)


def _text(block: Block) -> str:
    return "".join(run.text for run in block.runs)


def _paste_from_qt_clipboard(editor: MeropeTextEdit, mime: QMimeData) -> None:
    clipboard = QApplication.clipboard()
    clipboard.setMimeData(mime)
    editor.paste()


def test_qt_paste_prefers_html_over_plain_text_and_uses_merope_importer(monkeypatch):
    editor = _editor()
    calls = []
    original_importer = text_edit_module.html_to_blocks

    def recording_importer(html, **kwargs):
        calls.append((html, kwargs))
        return original_importer(html, **kwargs)

    monkeypatch.setattr(text_edit_module, "html_to_blocks", recording_importer)
    mime = QMimeData()
    mime.setHtml("<p><b>Riche</b></p>")
    mime.setText("fallback brut")

    assert editor.canInsertFromMimeData(mime) is True
    _paste_from_qt_clipboard(editor, mime)

    assert len(calls) == 1
    assert calls[0][0] == "<p><b>Riche</b></p>"
    assert extract_blocks(editor.document()) == [
        Block(kind=PARAGRAPH, runs=[InlineRun(text="Riche", bold=True)])
    ]


def test_qt_paste_accepts_html_without_plain_text():
    editor = _editor()
    mime = QMimeData()
    mime.setHtml("<h2>Titre HTML</h2>")

    assert editor.canInsertFromMimeData(mime) is True
    _paste_from_qt_clipboard(editor, mime)

    assert extract_blocks(editor.document()) == [
        Block(kind=HEADING, level=2, runs=[InlineRun(text="Titre HTML")])
    ]


def test_qt_paste_accepts_plain_text_without_html():
    editor = _editor()
    mime = QMimeData()
    mime.setText("Texte brut")

    assert editor.canInsertFromMimeData(mime) is True
    _paste_from_qt_clipboard(editor, mime)

    assert extract_blocks(editor.document()) == [
        Block(kind=PARAGRAPH, runs=[InlineRun(text="Texte brut")])
    ]


def test_qt_paste_rejects_unsupported_mime_only():
    original = [Block(kind=PARAGRAPH, runs=[InlineRun(text="Intact")])]
    editor = _editor(original)
    mime = QMimeData()
    mime.setData("application/x-merope-unsupported", b"opaque")

    assert editor.canInsertFromMimeData(mime) is False
    _paste_from_qt_clipboard(editor, mime)

    assert extract_blocks(editor.document()) == original
    assert editor.document().isUndoAvailable() is False


def test_single_rich_paragraph_is_inserted_inline_at_cursor():
    editor = _editor(
        [Block(kind=PARAGRAPH, runs=[InlineRun(text="Avant après")])]
    )
    _set_cursor(editor, len("Avant "))

    _paste_html(editor, "<p><b>texte riche</b></p>")

    blocks = extract_blocks(editor.document())
    assert len(blocks) == 1
    assert _text(blocks[0]) == "Avant texte richeaprès"
    assert any(run.text == "texte riche" and run.bold for run in blocks[0].runs)


def test_two_paragraphs_are_real_blocks_and_preserve_surrounding_text():
    editor = _editor(
        [Block(kind=PARAGRAPH, runs=[InlineRun(text="Avant après")])]
    )
    _set_cursor(editor, len("Avant "))

    _paste_html(editor, "<p>Paragraphe A</p><p>Paragraphe B</p>")

    blocks = extract_blocks(editor.document())
    assert [block.kind for block in blocks] == [PARAGRAPH] * 4
    assert [_text(block) for block in blocks] == [
        "Avant ",
        "Paragraphe A",
        "Paragraphe B",
        "après",
    ]


def test_rich_paste_replaces_existing_selection():
    editor = _editor(
        [Block(kind=PARAGRAPH, runs=[InlineRun(text="Avant supprimer après")])]
    )
    start = len("Avant ")
    _set_cursor(editor, start, start + len("supprimer "))

    _paste_html(editor, "<p><i>remplacement</i></p>")

    block = extract_blocks(editor.document())[0]
    assert _text(block) == "Avant remplacementaprès"
    assert any(run.text == "remplacement" and run.italic for run in block.runs)

    editor.undo()
    assert extract_blocks(editor.document()) == [
        Block(kind=PARAGRAPH, runs=[InlineRun(text="Avant supprimer après")])
    ]
    editor.redo()
    assert _text(extract_blocks(editor.document())[0]) == "Avant remplacementaprès"


def test_paste_between_blocks_keeps_both_existing_blocks():
    editor = _editor(
        [
            Block(kind=PARAGRAPH, runs=[InlineRun(text="Avant")]),
            Block(kind=PARAGRAPH, runs=[InlineRun(text="Après")]),
        ]
    )
    second = editor.document().begin().next()
    _set_cursor(editor, second.position())

    _paste_html(editor, "<p>A</p><p>B</p>")

    assert [_text(block) for block in extract_blocks(editor.document())] == [
        "Avant",
        "A",
        "B",
        "Après",
    ]


def test_inline_formats_and_combinations_roundtrip_to_markdown():
    editor = _editor()
    html = (
        "<p><b>gras</b> <i>italique</i> <b><i>mixte</i></b> "
        "<s>barré</s> <sup>2</sup> "
        '<a href="https://example.org"><b>lien gras</b></a> '
        '<a href="https://example.net"><i>lien italique</i></a></p>'
    )

    _paste_html(editor, html)

    assert blocks_to_markdown(extract_blocks(editor.document())) == (
        "**gras** *italique* ***mixte*** ~~barré~~ ^2^ "
        "[**lien gras**](https://example.org) "
        "[*lien italique*](https://example.net)\n"
    )


def test_heading_and_blockquote_keep_native_block_semantics():
    editor = _editor()

    _paste_html(editor, "<h2><i>Titre</i></h2><blockquote>Citation</blockquote>")

    blocks = extract_blocks(editor.document())
    assert blocks == [
        Block(kind=HEADING, level=2, runs=[InlineRun(text="Titre", italic=True)]),
        Block(kind=BLOCKQUOTE, runs=[InlineRun(text="Citation")]),
    ]


@pytest.mark.parametrize(
    ("html", "kind"),
    [
        ("<ul><li>Un</li><li>Deux</li></ul>", BULLET_LIST),
        ("<ol><li>Un</li><li>Deux</li></ol>", ORDERED_LIST),
    ],
)
def test_html_lists_become_real_qtextlists(html, kind):
    editor = _editor()

    _paste_html(editor, html)

    block = extract_blocks(editor.document())[0]
    assert block == Block(
        kind=kind,
        children=[
            Block(kind=LIST_ITEM, runs=[InlineRun(text="Un")]),
            Block(kind=LIST_ITEM, runs=[InlineRun(text="Deux")]),
        ],
    )
    assert editor.document().begin().textList() is not None


def test_word_like_html_uses_the_existing_importer():
    editor = _editor()
    html = (
        "<!--[if gte mso 9]><xml></xml><![endif]-->"
        "<h1 class=MsoTitle><b>Titre Word</b></h1>"
        "<p class=MsoNormal style='mso-margin-top-alt:auto'>"
        "Texte <i>italique</i> et "
        '<a href="https://example.org">lien</a>.<o:p></o:p></p>'
        "<ul><li>Premier</li><li>Deuxième</li></ul>"
    )

    _paste_html(editor, html)

    assert blocks_to_markdown(extract_blocks(editor.document())) == (
        "# **Titre Word**\n\n"
        "Texte *italique* et [lien](https://example.org).\n\n"
        "- Premier\n- Deuxième\n"
    )


def test_google_docs_like_html_preserves_styles_without_wrapper_bold():
    editor = _editor()
    html = (
        '<b id="docs-internal-guid-x" style="font-weight:normal">'
        '<p><span style="font-weight:700">Gras</span> et '
        '<span style="font-style:italic">italique</span>.</p>'
        "<ol><li><p>Premier</p></li><li><p>Deuxième</p></li></ol>"
        "</b>"
    )

    _paste_html(editor, html)

    assert blocks_to_markdown(extract_blocks(editor.document())) == (
        "**Gras** et *italique*.\n\n1. Premier\n2. Deuxième\n"
    )


def test_pasted_typography_and_century_superscript_are_preserved_exactly():
    editor = _editor()

    _paste_html(editor, '<p>"Bossuet", p. 12 : le XVIIe siecle!</p>')

    blocks = extract_blocks(editor.document())
    assert _text(blocks[0]) == (
        f"«{NBSP}Bossuet{NBSP}», p.{NBSP}12{NBSP}: le XVIIe siecle{NBSP}!"
    )
    assert blocks_to_markdown(blocks) == (
        f"«{NBSP}Bossuet{NBSP}», p.{NBSP}12{NBSP}: le XVII^e^ siecle{NBSP}!\n"
    )


def test_structural_rich_paste_is_one_native_undo_redo_step():
    original = [Block(kind=PARAGRAPH, runs=[InlineRun(text="Avant après")])]
    editor = _editor(original)
    _set_cursor(editor, len("Avant "))

    _paste_html(editor, "<h2>Titre</h2><ul><li>Un</li><li>Deux</li></ul>")
    pasted = extract_blocks(editor.document())
    assert [block.kind for block in pasted] == [PARAGRAPH, HEADING, BULLET_LIST, PARAGRAPH]

    editor.undo()
    assert extract_blocks(editor.document()) == original
    editor.redo()
    assert extract_blocks(editor.document()) == pasted


def test_structural_paste_in_middle_of_list_item_preserves_both_sides_and_list():
    original = [
        Block(
            kind=BULLET_LIST,
            children=[
                Block(kind=LIST_ITEM, runs=[InlineRun(text="Avant après")]),
                Block(kind=LIST_ITEM, runs=[InlineRun(text="Deux")]),
            ],
        )
    ]
    editor = _editor(original)
    _set_cursor(editor, len("Avant "))

    _paste_html(editor, "<h2>Titre</h2><blockquote>Citation</blockquote>")

    pasted = extract_blocks(editor.document())
    assert pasted == [
        Block(
            kind=BULLET_LIST,
            children=[Block(kind=LIST_ITEM, runs=[InlineRun(text="Avant ")])],
        ),
        Block(kind=HEADING, level=2, runs=[InlineRun(text="Titre")]),
        Block(kind=BLOCKQUOTE, runs=[InlineRun(text="Citation")]),
        Block(
            kind=BULLET_LIST,
            children=[
                Block(kind=LIST_ITEM, runs=[InlineRun(text="après")]),
                Block(kind=LIST_ITEM, runs=[InlineRun(text="Deux")]),
            ],
        ),
    ]

    editor.undo()
    assert extract_blocks(editor.document()) == original
    editor.redo()
    assert extract_blocks(editor.document()) == pasted


def test_structural_paste_replacing_multi_block_selection_preserves_edges():
    original = [
        Block(kind=PARAGRAPH, runs=[InlineRun(text="Avant supprimer")]),
        Block(kind=HEADING, level=3, runs=[InlineRun(text="Titre supprimé")]),
        Block(kind=PARAGRAPH, runs=[InlineRun(text="retirer après")]),
    ]
    editor = _editor(original)
    first = editor.document().begin()
    third = first.next().next()
    start = first.position() + len("Avant ")
    end = third.position() + len("retirer ")
    _set_cursor(editor, start, end)

    _paste_html(editor, "<blockquote>Citation</blockquote><ol><li>Un</li><li>Deux</li></ol>")

    pasted = extract_blocks(editor.document())
    assert pasted == [
        Block(kind=PARAGRAPH, runs=[InlineRun(text="Avant ")]),
        Block(kind=BLOCKQUOTE, runs=[InlineRun(text="Citation")]),
        Block(
            kind=ORDERED_LIST,
            children=[
                Block(kind=LIST_ITEM, runs=[InlineRun(text="Un")]),
                Block(kind=LIST_ITEM, runs=[InlineRun(text="Deux")]),
            ],
        ),
        Block(kind=PARAGRAPH, runs=[InlineRun(text="après")]),
    ]

    editor.undo()
    assert extract_blocks(editor.document()) == original
    editor.redo()
    assert extract_blocks(editor.document()) == pasted


def test_plain_text_fallback_matches_tk_policy_without_typographic_normalization():
    editor = _editor()
    plain = '"Bossuet" : p. 12 ((note))'

    _paste_text(editor, plain)

    assert extract_blocks(editor.document()) == [
        Block(kind=PARAGRAPH, runs=[InlineRun(text=plain)])
    ]


def test_empty_html_uses_available_plain_text_fallback():
    editor = _editor()

    _paste_html(editor, "   ", text="Texte brut")

    assert _text(extract_blocks(editor.document())[0]) == "Texte brut"


@pytest.mark.parametrize(
    ("html", "tag"),
    [
        ("<p>Avant</p><table><tr><td>Cellule</td></tr></table>", "table"),
        ("<p>Avant</p><pre>code</pre>", "pre"),
    ],
)
def test_unsupported_html_refuses_the_entire_paste(html, tag):
    original = [Block(kind=PARAGRAPH, runs=[InlineRun(text="Document intact")])]
    editor = _editor(original)
    refused = []
    editor.pasteRefused.connect(refused.append)

    _paste_html(editor, html, text="fallback qui perdrait la structure")

    assert extract_blocks(editor.document()) == original
    assert len(refused) == 1
    assert f"<{tag}>" in refused[0]
    assert editor.document().isUndoAvailable() is False


def test_adapter_validation_failure_cannot_partially_replace_selection(monkeypatch):
    original = [Block(kind=PARAGRAPH, runs=[InlineRun(text="Document intact")])]
    editor = _editor(original)
    _set_cursor(editor, 0, len("Document"))
    refused = []
    editor.pasteRefused.connect(refused.append)
    monkeypatch.setattr(
        text_edit_module,
        "html_to_blocks",
        lambda *args, **kwargs: [Block(kind="structure_inconnue")],
    )

    _paste_html(editor, "<p>contenu</p>")

    assert extract_blocks(editor.document()) == original
    assert refused and "structure_inconnue" in refused[0]
