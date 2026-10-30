"""Read one simple rectangular table from an Excel or tabulated clipboard.

The structure comes from Excel's HTML, the only representation that shows
merged cells; the values come from its tabulated text, which keeps what the
sheet displays without HTML's line wrapping.  Whatever cannot be converted
faithfully is refused before the document is touched.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from html.parser import HTMLParser

from PySide6.QtCore import QMimeData

from bloggen.markdown.rich_text_model import (
    TABLE,
    TABLE_CELL,
    TABLE_ROW,
    Block,
    InlineRun,
)
from bloggen.ui.qt_editor.clipboard_fragment import MEROPE_FRAGMENT_MIME


# Au-delà, QTextTable fige l'interface : mieux vaut refuser que bloquer.
MAX_TABLE_CELLS = 20_000

_EXCEL_MIME_MARKERS = ("Biff5", "Biff8", "Biff12", "XML Spreadsheet")
_EXCEL_HTML_RE = re.compile(
    r"<meta\b[^>]*\bcontent\s*=\s*[\"']?(?:Excel\.Sheet|Microsoft\s+Excel)",
    re.IGNORECASE,
)
# Excel note ainsi un texte débordant ou « centré sur plusieurs colonnes » :
# la cellule n'est pas fusionnée et ses voisines sont réellement vides.
_IGNORED_COLSPAN_RE = re.compile(r"mso-ignore\s*:\s*colspan", re.IGNORECASE)
_HTML_WHITESPACE_RE = re.compile(r"[ \t\r\n]+")
_LINE_BREAKS = "\v\f\x85\u2028\u2029"
_BLOCK_BREAK = "\x00"
_SKIPPED_TAGS = frozenset({"head", "rp", "rt", "script", "style", "title"})
_BLOCK_TAGS = frozenset(
    {
        "blockquote",
        "br",
        "div",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "hr",
        "li",
        "ol",
        "p",
        "pre",
        "ul",
    }
)
_OBJECT_TAGS = frozenset({"embed", "iframe", "img", "object", "svg"})
# L'exportateur Markdown échappe la syntaxe des tableaux et l'emphase, mais ces
# formes-ci restent interprétées à la publication, comme du texte saisi : la
# valeur serait altérée, voire perdue (code, HTML brut, entité, note, indice,
# barré, mathématiques).
_INTERPRETED_SYNTAX_RE = re.compile(
    r"`[^`]*`"
    r"|<(?:!--|[/!?]?[A-Za-z])[^<>]*>"
    r"|&(?:#\d+|#[xX][0-9a-fA-F]+|[A-Za-z][A-Za-z0-9]*);"
    r"|\(\(.+?\)\)"
    r"|~~.+?~~|~[^\s~]+~"
    r"|\$[^\s$](?:[^$]*[^\s$])?\$(?!\d)"
)
_PREVIEW_MAX_CHARACTERS = 60

_MERGED_MESSAGE = (
    "Ce tableau contient des cellules fusionnées, qu’un tableau Markdown ne "
    "peut pas représenter. Défusionnez-les dans Excel, puis copiez à nouveau "
    "la plage."
)
_NESTED_MESSAGE = (
    "Ce contenu contient un tableau imbriqué, qu’un tableau Markdown ne peut "
    "pas représenter."
)
_MULTILINE_MESSAGE = (
    "Une cellule contient plusieurs lignes ou paragraphes, qu’un tableau "
    "Markdown ne peut pas représenter. Supprimez ces retours à la ligne dans "
    "Excel, puis copiez à nouveau la plage."
)
_OBJECT_MESSAGE = (
    "Cette plage contient une image ou un objet, qu’un tableau Markdown ne "
    "peut pas représenter."
)
_IRREGULAR_MESSAGE = (
    "Les lignes de ce tableau n’ont pas toutes le même nombre de cellules. "
    "Pour coller ce contenu tel quel, utilisez « Coller en texte brut »."
)
_AMBIGUOUS_MESSAGE = (
    "La structure de ce tableau est ambiguë : le HTML et le texte fournis par "
    "Excel ne concordent pas (une cellule contient peut-être une tabulation). "
    "Pour coller ce contenu tel quel, utilisez « Coller en texte brut »."
)


class TablePasteRefused(ValueError):
    """The clipboard holds a table that cannot be converted faithfully."""


@dataclass(frozen=True, slots=True)
class ClipboardTable:
    rows: tuple[tuple[str, ...], ...]

    @property
    def row_count(self) -> int:
        return len(self.rows)

    @property
    def column_count(self) -> int:
        return len(self.rows[0])

    @property
    def is_single_cell(self) -> bool:
        return self.row_count == 1 and self.column_count == 1


def read_clipboard_table(source: QMimeData) -> ClipboardTable | None:
    """Return the clipboard's table, or ``None`` for ordinary content.

    Raises ``TablePasteRefused`` when it is a table Merope must not convert.
    Tabulated text is only trusted without a richer representation: it then
    needs several rows and columns to be told apart from ordinary text.
    """

    if source.hasFormat(MEROPE_FRAGMENT_MIME):
        return None
    html = source.html() if source.hasHtml() else ""
    text = source.text() if source.hasText() else ""
    if _comes_from_excel(source, html):
        table = _read_excel(html, text)
    elif html.strip() or source.hasImage() or source.hasUrls():
        return None
    else:
        table = _read_tabulated_text(text)
    if table is not None and table.row_count * table.column_count > MAX_TABLE_CELLS:
        raise TablePasteRefused(
            f"Ce tableau dépasse {MAX_TABLE_CELLS} cellules : Mérope ne peut "
            "pas l’éditer confortablement."
        )
    return table


def table_block(table: ClipboardTable, *, first_row_is_header: bool) -> Block:
    """Build the canonical table; Markdown always needs a header row."""

    rows = table.rows
    if not first_row_is_header:
        rows = (("",) * table.column_count, *rows)
    return Block(
        kind=TABLE,
        children=[
            Block(
                kind=TABLE_ROW,
                children=[
                    Block(kind=TABLE_CELL, runs=[InlineRun(text=value)])
                    for value in row
                ],
            )
            for row in rows
        ],
    )


def _comes_from_excel(source: QMimeData, html: str) -> bool:
    return bool(_EXCEL_HTML_RE.search(html)) or any(
        marker in mime_format
        for mime_format in source.formats()
        for marker in _EXCEL_MIME_MARKERS
    )


def _read_excel(html: str, text: str) -> ClipboardTable | None:
    html_rows = _scan_html_table(html)
    text_rows = _split_tabulated_text(text)
    if html_rows is None:
        if not text_rows:
            return None
        _refuse_quoted_multiline_cell(text_rows)
        return _rectangular(text_rows)
    table = _rectangular(html_rows)
    if not text_rows:
        return table
    return _rectangular(_values_from_text(table.rows, text_rows))


def _read_tabulated_text(text: str) -> ClipboardTable | None:
    rows = _split_tabulated_text(text.rstrip("\r\n"))
    if len(rows) < 2 or any(len(row) < 2 for row in rows):
        return None
    # Des lignes qui commencent toutes par une tabulation sont du texte indenté.
    if not any(row[0].strip() for row in rows):
        return None
    _refuse_quoted_multiline_cell(rows)
    return _rectangular(rows)


def _split_tabulated_text(text: str) -> list[list[str]]:
    """Split rows and cells; the final line ending does not start a row."""

    normalized = text.replace("\x00", "").replace("\r\n", "\n").replace("\r", "\n")
    if normalized.endswith("\n"):
        normalized = normalized[:-1]
    elif not normalized:
        return []
    return [line.split("\t") for line in normalized.split("\n")]


def _refuse_quoted_multiline_cell(rows: list[list[str]]) -> None:
    """Excel quotes a multiline cell, whose lines then look like rows."""

    if any(
        cell.startswith('"') and cell.count('"') % 2 == 1
        for row in rows
        for cell in row
    ):
        raise TablePasteRefused(_MULTILINE_MESSAGE)


def _rectangular(rows: list[list[str]] | tuple[tuple[str, ...], ...]) -> ClipboardTable:
    if any(len(row) != len(rows[0]) for row in rows) or not rows[0]:
        raise TablePasteRefused(_IRREGULAR_MESSAGE)
    if any(character in cell for row in rows for cell in row for character in _LINE_BREAKS):
        raise TablePasteRefused(_MULTILINE_MESSAGE)
    for row in rows:
        for cell in row:
            if _INTERPRETED_SYNTAX_RE.search(cell):
                raise TablePasteRefused(
                    f"La cellule « {cell.strip()[:_PREVIEW_MAX_CHARACTERS]} » contient "
                    "une syntaxe (code, balise, entité, note, indice…) que la "
                    "publication interpréterait au lieu d’afficher cette valeur. "
                    "Modifiez-la dans Excel, ou utilisez « Coller en texte brut »."
                )
    return ClipboardTable(tuple(tuple(cell.strip() for cell in row) for row in rows))


def _values_from_text(
    html_rows: tuple[tuple[str, ...], ...],
    text_rows: list[list[str]],
) -> list[list[str]]:
    """Fill the HTML structure with Excel's text, clipped to the used range."""

    width = len(html_rows[0])
    if len(text_rows) > len(html_rows) or any(len(row) > width for row in text_rows):
        raise TablePasteRefused(_AMBIGUOUS_MESSAGE)
    values = []
    for row_index, html_row in enumerate(html_rows):
        text_row = text_rows[row_index] if row_index < len(text_rows) else []
        padded = text_row + [""] * (width - len(text_row))
        if not all(map(_same_value, html_row, padded)):
            raise TablePasteRefused(_AMBIGUOUS_MESSAGE)
        values.append(padded)
    return values


def _same_value(html_value: str, text_value: str) -> bool:
    # « ### » : une colonne trop étroite n'affecte que l'affichage HTML.
    if html_value and not html_value.strip("#"):
        return True
    return html_value.split() == text_value.split()


def _scan_html_table(html: str) -> list[list[str]] | None:
    """Return the HTML table's cells, or ``None`` when it holds no table."""

    if not html.strip():
        return None
    scanner = _HtmlTableScanner()
    scanner.feed(html)
    scanner.close()
    if scanner.has_object:
        raise TablePasteRefused(_OBJECT_MESSAGE)
    if scanner.is_nested:
        raise TablePasteRefused(_NESTED_MESSAGE)
    if scanner.is_merged:
        raise TablePasteRefused(_MERGED_MESSAGE)
    if scanner.is_multiline:
        raise TablePasteRefused(_MULTILINE_MESSAGE)
    if scanner.table_count == 0:
        return None
    if scanner.table_count > 1 or scanner.has_stray_content or not scanner.rows:
        raise TablePasteRefused(_IRREGULAR_MESSAGE)
    return scanner.rows


class _HtmlTableScanner(HTMLParser):
    """Collect one table's cells and every feature Markdown cannot express."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[str]] = []
        self.table_count = 0
        self.is_merged = False
        self.is_nested = False
        self.is_multiline = False
        self.has_object = False
        self.has_stray_content = False
        self._table_depth = 0
        self._skip_depth = 0
        self._row: list[str] | None = None
        self._cell: list[str] | None = None
        self._ignored_columns = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = tag.lower()
        if tag in _SKIPPED_TAGS:
            self._skip_depth += 1
        elif self._skip_depth:
            return
        elif tag in _OBJECT_TAGS or tag.startswith("v:"):
            self.has_object = True
        elif tag == "table":
            if self._table_depth:
                self.is_nested = True
            else:
                self.table_count += 1
            self._table_depth += 1
        elif tag == "tr" and self._table_depth == 1:
            self._close_row()
            self._row = []
        elif tag in {"td", "th"} and self._table_depth == 1:
            self._close_cell()
            if self._row is None:
                self._row = []
            self._open_cell({name.lower(): value or "" for name, value in attrs})
        elif tag in _BLOCK_TAGS and self._cell is not None:
            self._cell.append(_BLOCK_BREAK)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in _SKIPPED_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
        elif self._skip_depth:
            return
        elif tag == "table":
            if self._table_depth == 1:
                self._close_row()
            self._table_depth = max(0, self._table_depth - 1)
        elif tag == "tr" and self._table_depth == 1:
            self._close_row()
        elif tag in {"td", "th"} and self._table_depth == 1:
            self._close_cell()
        elif tag in _BLOCK_TAGS and self._cell is not None:
            self._cell.append(_BLOCK_BREAK)

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        if self._cell is not None:
            self._cell.append(data)
        elif data.strip():
            self.has_stray_content = True

    def close(self) -> None:
        super().close()
        self._close_row()

    def _open_cell(self, attributes: dict[str, str]) -> None:
        self._cell = []
        self._ignored_columns = 0
        columns = _span(attributes.get("colspan"))
        if _span(attributes.get("rowspan")) > 1:
            self.is_merged = True
        elif columns > 1:
            if _IGNORED_COLSPAN_RE.search(attributes.get("style", "")):
                self._ignored_columns = columns - 1
            else:
                self.is_merged = True

    def _close_cell(self) -> None:
        if self._cell is None or self._row is None:
            return
        value = "".join(self._cell)
        self._cell = None
        value = value.strip(_BLOCK_BREAK + " \t\r\n\xa0")
        if _BLOCK_BREAK in value:
            self.is_multiline = True
        self._row.append(_HTML_WHITESPACE_RE.sub(" ", value))
        self._row.extend([""] * self._ignored_columns)

    def _close_row(self) -> None:
        self._close_cell()
        if self._row is not None:
            self.rows.append(self._row)
            self._row = None


def _span(value: str | None) -> int:
    try:
        return max(1, int(value or 1))
    except ValueError:
        return 1
