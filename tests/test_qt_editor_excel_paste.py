"""Excel clipboard import.

``tests/fixtures/excel_clipboard`` holds real captures: what Qt read from the
Windows clipboard after copying ranges in Excel 16 (only user paths and base64
shape data were scrubbed).  ``docs/QT_MANUAL_TEST_EXCEL_PASTE.md`` covers what
remains manual.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QMimeData, Qt
from PySide6.QtGui import QImage, QTextCursor, QTextTable
from PySide6.QtWidgets import QApplication, QDialog

from bloggen.markdown.rich_text_export import blocks_to_markdown
from bloggen.markdown.rich_text_import import markdown_to_blocks
from bloggen.markdown.rich_text_model import (
    PARAGRAPH,
    TABLE,
    VERBATIM,
    Block,
    InlineRun,
)
from bloggen.render.xslt_runner import render_tei_file_to_html_fragment
from bloggen.tei.pandoc_converter import convert_markdown_file_to_tei
from bloggen.ui.qt_editor import text_edit as text_edit_module
from bloggen.ui.qt_editor.clipboard_fragment import (
    MEROPE_FRAGMENT_MIME,
    encode_blocks_as_markdown,
)
from bloggen.ui.qt_editor.document_adapter import extract_blocks, populate_document
from bloggen.ui.qt_editor.footnote_editor import FootnoteTextEdit
from bloggen.ui.qt_editor.table_clipboard import (
    MAX_TABLE_CELLS,
    ClipboardTable,
    TablePasteRefused,
    read_clipboard_table,
    table_block,
)
from bloggen.ui.qt_editor.table_dialog import TablePasteChoice, TablePasteDialog
from bloggen.ui.qt_editor.text_edit import MeropeTextEdit


FIXTURES = Path(__file__).parent / "fixtures" / "excel_clipboard"
BIFF12 = 'application/x-qt-windows-mime;value="Biff12"'
EXCEL_HEAD = (
    "<html><head><meta name=ProgId content=Excel.Sheet>"
    '<meta name=Generator content="Microsoft Excel 15">'
    "<style><!--td {color:black}--></style></head><body>"
)
SPEC_MARKDOWN = (
    "| Auteur | Œuvre | Date |\n"
    "| --- | --- | --- |\n"
    "| Corneille | Le Cid | 1637 |\n"
    "| Racine | Phèdre | 1677 |"
)


@pytest.fixture(scope="module", autouse=True)
def qapplication():
    return QApplication.instance() or QApplication([])


def _excel(name: str) -> QMimeData:
    """Rebuild a captured clipboard, including the bitmap Excel always offers."""

    capture = json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
    mime = QMimeData()
    for mime_format in capture["formats"]:
        if mime_format.startswith("application/x-qt-windows-mime"):
            mime.setData(mime_format, b"")
    if capture["html"]:
        mime.setHtml(capture["html"])
    if capture["text"]:
        mime.setText(capture["text"])
    if capture["hasImage"]:
        mime.setImageData(QImage(1, 1, QImage.Format.Format_RGB32))
    return mime


def _excel_html(body: str, text: str | None = None) -> QMimeData:
    mime = QMimeData()
    mime.setHtml(f"{EXCEL_HEAD}{body}</body></html>")
    if text is not None:
        mime.setText(text)
    return mime


def _plain(text: str) -> QMimeData:
    mime = QMimeData()
    mime.setText(text)
    return mime


def _paragraph(text: str) -> Block:
    return Block(kind=PARAGRAPH, runs=[InlineRun(text=text)])


def _table_model(*rows: tuple[str, ...]) -> Block:
    return table_block(ClipboardTable(tuple(rows)), first_row_is_header=True)


class _Prompt:
    """Replace the modal dialog and remember whether it was shown."""

    def __init__(self, choice: TablePasteChoice) -> None:
        self.choice = choice
        self.tables: list[ClipboardTable] = []
        self.can_paste_as_text: list[bool] = []

    def __call__(self, _parent, table, *, can_paste_as_text):
        self.tables.append(table)
        self.can_paste_as_text.append(can_paste_as_text)
        return self.choice


@pytest.fixture
def prompt(monkeypatch):
    answer = _Prompt(TablePasteChoice.TABLE_WITH_HEADER)
    monkeypatch.setattr(text_edit_module, "ask_table_paste_choice", answer)
    return answer


def _editor(blocks: list[Block] | None = None) -> MeropeTextEdit:
    editor = MeropeTextEdit()
    editor.refusals = []
    editor.pasteRefused.connect(editor.refusals.append)
    populate_document(editor.document(), blocks if blocks is not None else [_paragraph("")])
    editor.document().clearUndoRedoStacks()
    editor.document().setModified(False)
    return editor


def _markdown(editor: MeropeTextEdit) -> str:
    return blocks_to_markdown(extract_blocks(editor.document())).rstrip("\n")


def _only_table(editor: MeropeTextEdit) -> QTextTable:
    tables = [
        frame
        for frame in editor.document().rootFrame().childFrames()
        if isinstance(frame, QTextTable)
    ]
    assert len(tables) == 1
    return tables[0]


# --- Lecture : valeurs issues d'un vrai presse-papiers Excel ----------------


def test_simple_excel_range_is_read_with_its_three_columns():
    assert read_clipboard_table(_excel("simple")).rows == (
        ("Auteur", "Œuvre", "Date"),
        ("Corneille", "Le Cid", "1637"),
        ("Racine", "Phèdre", "1677"),
    )


def test_displayed_values_are_preserved_without_conversion():
    rows = read_clipboard_table(_excel("values")).rows

    assert rows[1] == ("007", "1 234,50", "15/03/2023", "246900,0%", "")
    assert rows[2][0] == "a|b *c* _d_ [e] \\f ^g & é œ — € 中"
    assert rows[2][1] == "espaces  internes"
    assert rows[3][:3] == ('"guillemets"', "#DIV/0!", "50%")


def test_narrow_column_uses_the_value_not_the_hash_marks():
    rows = read_clipboard_table(_excel("formats")).rows

    assert rows[1][0] == "1 234,50 €"
    assert rows[1][1] == "123456789"
    assert rows[1][2:] == ("mercredi 15 mars 2023", "VRAI", "(12,50)")


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("center_across", (("Centré", "", "c"), ("1", "2", "3"))),
        (
            "overflow",
            (
                (
                    "Un texte long qui deborde sur les cellules voisines vides de la feuille",
                    "",
                    "",
                    "d",
                ),
                ("1", "2", "3", "4"),
            ),
        ),
    ],
)
def test_excel_ignored_colspan_is_not_a_merged_cell(name, expected):
    assert read_clipboard_table(_excel(name)).rows == expected


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("one_row", (("c1", "", ""),)),
        ("trailing_empty", (("a", "b"), ("", ""))),
        ("one_column", (("c1",), ("c2",), ("c3",))),
        ("hidden", (("a", "c"), ("4", "6"))),
    ],
)
def test_html_gives_the_shape_when_excel_clips_its_text(name, expected):
    assert read_clipboard_table(_excel(name)).rows == expected


def test_wrapped_html_source_lines_do_not_alter_the_value():
    rows = read_clipboard_table(_excel("wrap_link")).rows

    assert rows[0][0] == (
        "Texte long renvoyé à la ligne automatiquement "
        "dans une colonne étroite, sans retour manuel"
    )
    assert rows[0][1] == "b"


def test_single_excel_cell_is_flagged_as_a_value():
    table = read_clipboard_table(_excel("single"))
    assert table.is_single_cell
    assert table.rows == (("Corneille",),)


def test_html_without_text_gives_normalized_values():
    table = read_clipboard_table(
        _excel_html(
            "<table><tr><th>A\n  B</th><td>1&nbsp;000</td></tr>"
            "<tr><td>&nbsp;</td><td><p>x</p></td></tr></table>"
        )
    )
    assert table.rows == (("A B", "1\xa0000"), ("", "x"))


# --- Lecture : refus explicites ---------------------------------------------


@pytest.mark.parametrize(
    ("name", "message"),
    [
        ("merged_h", "fusionnées"),
        ("merged_v", "fusionnées"),
        ("multiline", "plusieurs lignes"),
        ("multiline_quote", "plusieurs lignes"),
        ("shape", "image ou un objet"),
        ("tab_in_cell", "ambiguë"),
    ],
)
def test_captured_complex_ranges_are_refused(name, message):
    with pytest.raises(TablePasteRefused, match=message):
        read_clipboard_table(_excel(name))


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ("<table><tr><td colspan=2>a</td></tr><tr><td>1</td><td>2</td></tr></table>", "fusionnées"),
        ("<table><tr><td rowspan=2>a</td><td>b</td></tr><tr><td>2</td></tr></table>", "fusionnées"),
        ("<table><tr><td><table><tr><td>a</td></tr></table></td></tr></table>", "imbriqué"),
        ("<table><tr><td>a<br>b</td><td>c</td></tr></table>", "plusieurs lignes"),
        ("<table><tr><td><p>a</p><p>b</p></td><td>c</td></tr></table>", "plusieurs lignes"),
        ("<table><tr><td>a b</td><td>c</td></tr></table>", "plusieurs lignes"),
        ("<table><tr><td>a</td><td>b</td></tr><tr><td>c</td></tr></table>", "même nombre"),
        ("<table><tr><td>a</td></tr></table><table><tr><td>b</td></tr></table>", "même nombre"),
        ("avant<table><tr><td>a</td><td>b</td></tr></table>", "même nombre"),
        ("<table><caption>t</caption><tr><td>a</td><td>b</td></tr></table>", "même nombre"),
        ("<table><tr><td><img src='x.png'></td><td>b</td></tr></table>", "image ou un objet"),
    ],
)
def test_synthetic_complex_structures_are_refused(body, message):
    with pytest.raises(TablePasteRefused, match=message):
        read_clipboard_table(_excel_html(body))


def test_text_disagreeing_with_html_is_refused_as_ambiguous():
    body = "<table><tr><td>a</td><td>b</td></tr></table>"
    with pytest.raises(TablePasteRefused, match="ambiguë"):
        read_clipboard_table(_excel_html(body, "a\tautre\n"))
    with pytest.raises(TablePasteRefused, match="ambiguë"):
        read_clipboard_table(_excel_html(body, "a\tb\tc\n"))


@pytest.mark.parametrize(
    "value",
    [
        "`code`",
        "<b>x</b>",
        "x<y>z",
        "<!-- c -->",
        "&eacute;",
        "&#233;",
        "((note))",
        "H~2~O",
        "~~barré~~",
        "$a+b$",
    ],
)
def test_values_the_publication_would_interpret_are_refused(value):
    mime = _plain(f"Titre\tAutre\n{value}\tx\n")
    with pytest.raises(TablePasteRefused, match="interpréterait") as error:
        read_clipboard_table(mime)
    assert value in str(error.value)


@pytest.mark.parametrize(
    "value",
    ["R&D", "<5", "a < b > c", "$1 et $2", "5 $ et 6 $", "`seul", "~1", "x^2", "(1)", "=A1"],
)
def test_ordinary_punctuation_is_not_mistaken_for_syntax(value):
    assert read_clipboard_table(_plain(f"Titre\tAutre\n{value}\tx\n")).rows[1][0] == value


def test_oversized_table_is_refused():
    row = "\t".join("x" for _column in range(101))
    text = "\n".join(row for _row in range(MAX_TABLE_CELLS // 101 + 1))
    with pytest.raises(TablePasteRefused, match="dépasse"):
        read_clipboard_table(_plain(text))


# --- Lecture : repli sur le texte tabulé et contenus ordinaires -------------


def test_tabulated_text_is_a_fallback_when_html_is_absent():
    assert read_clipboard_table(_plain("a\tb\r\n1\t\r\n")).rows == (("a", "b"), ("1", ""))


def test_excel_formats_without_html_use_strict_tabulated_text():
    mime = _plain("seule\tligne\n")
    mime.setData(BIFF12, b"")
    assert read_clipboard_table(mime).rows == (("seule", "ligne"),)

    irregular = _plain("a\tb\nc\n")
    irregular.setData(BIFF12, b"")
    with pytest.raises(TablePasteRefused, match="même nombre"):
        read_clipboard_table(irregular)


@pytest.mark.parametrize(
    "text",
    [
        "un paragraphe",
        "deux\nlignes",
        "une\ttabulation",
        "a\tb\n\nc\td",
        "\tcode\n\tindenté",
    ],
)
def test_ordinary_text_is_not_a_table(text):
    assert read_clipboard_table(_plain(text)) is None


def test_tabulated_text_alone_refuses_irregular_rows():
    with pytest.raises(TablePasteRefused, match="même nombre"):
        read_clipboard_table(_plain("a\tb\nc\td\te"))


def test_tabulated_text_alone_refuses_excel_quoted_multiline_cell():
    with pytest.raises(TablePasteRefused, match="plusieurs lignes"):
        read_clipboard_table(_plain('a\t"b\nc"\td'))


def test_non_excel_html_keeps_its_own_paste_rules():
    mime = QMimeData()
    mime.setHtml("<table><tr><td colspan=2>Word</td></tr></table>")
    mime.setText("Word\t\n")
    assert read_clipboard_table(mime) is None


def test_tabulated_text_next_to_an_image_or_files_is_left_alone():
    mime = _plain("a\tb\nc\td")
    mime.setImageData(QImage(1, 1, QImage.Format.Format_RGB32))
    assert read_clipboard_table(mime) is None


def test_excel_shape_without_cells_is_left_alone():
    assert read_clipboard_table(_excel("shape_only")) is None


def test_merope_fragment_wins_over_any_other_format():
    mime = _excel("simple")
    mime.setData(MEROPE_FRAGMENT_MIME, encode_blocks_as_markdown([_paragraph("x")]))
    assert read_clipboard_table(mime) is None


# --- Boîte de dialogue ------------------------------------------------------


def test_paste_dialog_defaults_to_first_row_as_headers():
    table = ClipboardTable((("Auteur", "Date"), ("Racine", "1677")))
    dialog = TablePasteDialog(table, can_paste_as_text=True)

    assert dialog.first_row_check.isChecked()
    assert dialog.first_row_check.text() == "Première ligne = en-têtes"
    assert dialog.preview_label.text() == "Auteur | Date"
    dialog.accept()
    assert dialog.choice() == TablePasteChoice.TABLE_WITH_HEADER


def test_paste_dialog_unchecked_means_no_header_and_cancel_means_nothing():
    table = ClipboardTable((("1", "2"),))
    dialog = TablePasteDialog(table, can_paste_as_text=True)
    dialog.first_row_check.setChecked(False)
    dialog.accept()
    assert dialog.choice() == TablePasteChoice.TABLE_WITHOUT_HEADER

    cancelled = TablePasteDialog(table, can_paste_as_text=True)
    cancelled.reject()
    assert cancelled.result() == QDialog.DialogCode.Rejected
    assert cancelled.choice() == TablePasteChoice.CANCEL


def test_paste_dialog_plain_text_button():
    table = ClipboardTable((("1", "2"),))
    dialog = TablePasteDialog(table, can_paste_as_text=True)
    dialog.plain_text_button.click()
    assert dialog.choice() == TablePasteChoice.PLAIN_TEXT
    assert not TablePasteDialog(table, can_paste_as_text=False).plain_text_button.isEnabled()


def test_paste_dialog_shows_cell_text_literally():
    dialog = TablePasteDialog(ClipboardTable((("<b>x</b>", "y"),)), can_paste_as_text=True)
    assert dialog.preview_label.textFormat() == Qt.TextFormat.PlainText


# --- Collage dans l'éditeur -------------------------------------------------


def test_paste_produces_the_expected_markdown_table(prompt):
    editor = _editor()

    editor.insertFromMimeData(_excel("simple"))

    assert _markdown(editor) == SPEC_MARKDOWN
    assert isinstance(_only_table(editor), QTextTable)
    assert prompt.tables[0].column_count == 3
    assert prompt.can_paste_as_text == [True]
    assert editor.refusals == []


def test_paste_without_headers_produces_an_empty_header_row(prompt):
    prompt.choice = TablePasteChoice.TABLE_WITHOUT_HEADER
    editor = _editor()

    editor.insertFromMimeData(_excel("simple"))

    assert _markdown(editor) == (
        "|  |  |  |\n"
        "| --- | --- | --- |\n"
        "| Auteur | Œuvre | Date |\n"
        "| Corneille | Le Cid | 1637 |\n"
        "| Racine | Phèdre | 1677 |"
    )


def test_empty_cells_and_markdown_characters_are_escaped(prompt):
    editor = _editor()

    editor.insertFromMimeData(_plain("a|b\t*c*\n\t_d_ [e] \\f ^g\n"))

    assert _markdown(editor) == (
        "| a\\|b | \\*c\\* |\n"
        "| --- | --- |\n"
        "|  | \\_d\\_ \\[e\\] \\\\f \\^g |"
    )


def test_pasted_table_survives_saving_and_reopening(prompt):
    editor = _editor()
    editor.insertFromMimeData(_plain("a|b\t*c*\n\t007\n1\xa0234,50\tŒ — 中\n"))
    markdown = _markdown(editor)

    reopened = markdown_to_blocks(markdown)

    assert [block.kind for block in reopened] == [TABLE]
    assert blocks_to_markdown(reopened).rstrip("\n") == markdown
    assert reopened[0].children[0].children[0].runs[0].text == "a|b"
    assert reopened[0].children[1].children[1].runs[0].text == "007"


def test_paste_is_one_undo_step_with_redo(prompt):
    editor = _editor([_paragraph("Avant"), _paragraph("Après")])
    before = extract_blocks(editor.document())
    cursor = editor.textCursor()
    cursor.setPosition(5)
    editor.setTextCursor(cursor)

    editor.insertFromMimeData(_excel("simple"))
    after = extract_blocks(editor.document())
    assert any(block.kind == TABLE for block in after)

    editor.undo()
    assert extract_blocks(editor.document()) == before
    assert not editor.document().isUndoAvailable()
    editor.redo()
    assert extract_blocks(editor.document()) == after


def test_paste_replaces_the_selection_in_the_same_undo_step(prompt):
    editor = _editor([_paragraph("remplacer")])
    before = extract_blocks(editor.document())
    editor.selectAll()

    editor.insertFromMimeData(_excel("simple"))
    assert "remplacer" not in _markdown(editor)
    assert "Corneille" in _markdown(editor)

    editor.undo()
    assert extract_blocks(editor.document()) == before


@pytest.mark.parametrize(
    ("name", "message"),
    [("merged_h", "fusionnées"), ("merged_v", "fusionnées"), ("multiline", "plusieurs lignes")],
)
def test_refused_paste_leaves_the_document_untouched(prompt, name, message):
    editor = _editor([_paragraph("Intact")])
    before = extract_blocks(editor.document())
    editor.selectAll()

    editor.insertFromMimeData(_excel(name))

    assert extract_blocks(editor.document()) == before
    assert editor.textCursor().hasSelection()
    assert not editor.document().isModified()
    assert not editor.document().isUndoAvailable()
    assert prompt.tables == []
    assert len(editor.refusals) == 1
    assert message in editor.refusals[0]


def test_cancelled_paste_leaves_the_document_untouched(prompt):
    prompt.choice = TablePasteChoice.CANCEL
    editor = _editor([_paragraph("Intact")])
    before = extract_blocks(editor.document())
    editor.selectAll()

    editor.insertFromMimeData(_excel("simple"))

    assert extract_blocks(editor.document()) == before
    assert not editor.document().isModified()
    assert not editor.document().isUndoAvailable()
    assert editor.refusals == []


def test_plain_text_choice_keeps_the_tabulated_text(prompt):
    prompt.choice = TablePasteChoice.PLAIN_TEXT
    editor = _editor()

    editor.insertFromMimeData(_plain("a\tb\nc\td"))

    assert all(block.kind != TABLE for block in extract_blocks(editor.document()))
    assert "a\tb" in editor.toPlainText()


def test_single_excel_cell_pastes_as_text_without_prompt(prompt):
    editor = _editor([_paragraph("Nom : ")])
    cursor = editor.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.End)
    editor.setTextCursor(cursor)

    editor.insertFromMimeData(_excel("single"))

    assert _markdown(editor) == "Nom : Corneille"
    assert prompt.tables == []
    assert editor.refusals == []


def test_empty_excel_cell_pastes_nothing(prompt):
    editor = _editor([_paragraph("Intact")])
    editor.selectAll()

    editor.insertFromMimeData(_excel("empty_single"))

    assert _markdown(editor) == "Intact"
    assert not editor.document().isModified()
    assert prompt.tables == []


def test_single_excel_cell_pastes_into_a_table_cell(prompt):
    editor = _editor([_table_model(("x", "y"), ("1", "2"))])
    editor.setTextCursor(_only_table(editor).cellAt(1, 1).lastCursorPosition())

    editor.insertFromMimeData(_excel("single"))

    assert "| 1 | 2Corneille |" in _markdown(editor)
    assert editor.refusals == []


def test_range_is_refused_inside_a_table_cell_without_prompt(prompt):
    editor = _editor([_table_model(("x", "y"), ("1", "2"))])
    before = extract_blocks(editor.document())
    editor.setTextCursor(_only_table(editor).cellAt(1, 1).firstCursorPosition())

    editor.insertFromMimeData(_excel("simple"))

    assert extract_blocks(editor.document()) == before
    assert prompt.tables == []
    assert "cellule de tableau" in editor.refusals[0]


def test_range_in_a_raw_block_keeps_receiving_its_text(prompt):
    raw = Block(kind=VERBATIM, raw_text="brut")
    editor = _editor([raw])
    cursor = editor.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.End)
    editor.setTextCursor(cursor)

    editor.insertFromMimeData(_excel("simple"))

    assert prompt.tables == []
    assert "Auteur\tŒuvre\tDate" in editor.toPlainText()
    assert all(block.kind != TABLE for block in extract_blocks(editor.document()))


# --- Collage normal préservé ------------------------------------------------


def test_footnote_editor_never_receives_a_table(prompt):
    editor = FootnoteTextEdit()
    mime = _plain("a\tb")
    mime.setData(BIFF12, b"")

    editor.insertFromMimeData(mime)

    assert prompt.tables == []
    assert "a\tb" in editor.toPlainText()


def test_normal_plain_text_paste_is_unchanged(prompt):
    editor = _editor()

    editor.insertFromMimeData(_plain("Du texte\nsur deux lignes"))

    assert prompt.tables == []
    assert editor.toPlainText() == "Du texte\nsur deux lignes"


def test_normal_html_paste_is_unchanged(prompt):
    editor = _editor()
    mime = QMimeData()
    mime.setHtml("<p>Un <b>paragraphe</b></p>")
    mime.setText("Un paragraphe")

    editor.insertFromMimeData(mime)

    assert prompt.tables == []
    assert _markdown(editor) == "Un **paragraphe**"


def test_web_table_keeps_its_existing_refusal(prompt):
    editor = _editor([_paragraph("Intact")])
    mime = QMimeData()
    mime.setHtml("<table><tr><td>a</td><td>b</td></tr></table>")
    mime.setText("a\tb")

    editor.insertFromMimeData(mime)

    assert prompt.tables == []
    assert _markdown(editor) == "Intact"
    assert len(editor.refusals) == 1


def test_internal_table_fragment_paste_is_unchanged(prompt):
    editor = _editor()
    model = _table_model(("a", "b"), ("1", "2"))
    mime = QMimeData()
    mime.setData(MEROPE_FRAGMENT_MIME, encode_blocks_as_markdown([model]))
    mime.setText("a\tb\n1\t2")

    editor.insertFromMimeData(mime)

    assert prompt.tables == []
    tables = [block for block in extract_blocks(editor.document()) if block.kind == TABLE]
    assert tables == [model]


def test_paste_plain_text_command_never_builds_a_table(prompt):
    editor = _editor()

    assert editor.paste_plain_text("a\tb\nc\td")

    assert prompt.tables == []
    assert all(block.kind != TABLE for block in extract_blocks(editor.document()))


# --- Rendu HTML par le moteur existant --------------------------------------


@pytest.mark.skipif(shutil.which("pandoc") is None, reason="Pandoc requis")
@pytest.mark.parametrize(
    "choice",
    [TablePasteChoice.TABLE_WITH_HEADER, TablePasteChoice.TABLE_WITHOUT_HEADER],
)
def test_pasted_table_renders_through_the_real_pipeline(prompt, tmp_path, choice):
    prompt.choice = choice
    editor = _editor()
    editor.insertFromMimeData(
        _plain(
            "Auteur\tŒuvre\tDate\n"
            "Corneille\ta|b *c*\t007\n"
            "Racine\t\t1\xa0234,50\n"
            "Molière\tR&D <5\t12/03/1673\n"
        )
    )
    source = tmp_path / "article.md"
    source.write_text(f"---\ntitle: T\n---\n\n{_markdown(editor)}\n", encoding="utf-8")
    tei = tmp_path / "article.xml"

    assert convert_markdown_file_to_tei(source, tei).success
    html = render_tei_file_to_html_fragment(tei)

    assert '<table class="tei-table">' in html
    for value in (
        "Auteur",
        "Œuvre",
        "Corneille",
        "a|b *c*",
        "007",
        "234,50",
        "R&amp;D &lt;5",
        "12/03/1673",
    ):
        assert value in html
    # An empty header row disappears at rendering instead of showing up empty.
    assert html.count("<tr") == 4
    assert html.count("<td></td>") == 1
