"""Graphical tables stay legible in both themes and across a live switch.

Offscreen Qt has no system colour scheme, so these tests switch the application
palette, which is what Qt itself does when Windows changes theme.
"""

from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtGui import (
    QColor,
    QImage,
    QPalette,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
    QTextTable,
)
from PySide6.QtWidgets import QApplication

from bloggen.markdown.rich_text_model import (
    PARAGRAPH,
    TABLE,
    TABLE_CELL,
    TABLE_ROW,
    VERBATIM,
    Block,
    InlineRun,
)
from bloggen.ui.qt_editor.constants import (
    RAW_BLOCK_BACKGROUND,
    RAW_TABLE_BACKGROUND,
    TABLE_HEADER_BACKGROUND,
)
from bloggen.ui.qt_editor.document_adapter import (
    extract_blocks,
    make_raw_block_format,
    populate_document,
)
from bloggen.ui.qt_editor.formatting import set_link
from bloggen.ui.qt_editor.spellcheck import FrenchSpellHighlighter
from bloggen.ui.qt_editor.table_dialog import TableInsertDialog
from bloggen.ui.qt_editor.text_edit import MeropeTextEdit
from bloggen.ui.qt_editor.toolbar_icons import toolbar_icon
from bloggen.ui.qt_editor.window import QtEditorWindow


MINIMUM_CONTRAST = 4.5
LINK_LIGHT = "#1a5fb4"


def _palette(
    *,
    base: str,
    text: str,
    window: str,
    link: str,
    highlight: str,
) -> QPalette:
    palette = QPalette()
    for role, value in (
        (QPalette.ColorRole.Base, base),
        (QPalette.ColorRole.Text, text),
        (QPalette.ColorRole.Window, window),
        (QPalette.ColorRole.WindowText, text),
        (QPalette.ColorRole.Button, window),
        (QPalette.ColorRole.ButtonText, text),
        (QPalette.ColorRole.Link, link),
        (QPalette.ColorRole.Highlight, highlight),
        (QPalette.ColorRole.HighlightedText, "#ffffff"),
    ):
        palette.setColor(role, QColor(value))
    return palette


# Valeurs relevées sur la palette Qt de Windows 11.
LIGHT = _palette(
    base="#ffffff",
    text="#000000",
    window="#f3f3f3",
    link="#003e92",
    highlight="#0067c0",
)
DARK = _palette(
    base="#2d2d2d",
    text="#ffffff",
    window="#202020",
    link="#99ebff",
    highlight="#0078d4",
)
THEMES = {"clair": LIGHT, "sombre": DARK}


@pytest.fixture(scope="module", autouse=True)
def qapplication():
    app = QApplication.instance() or QApplication([])
    original = QPalette(app.palette())
    yield app
    app.setPalette(original)


@pytest.fixture(autouse=True)
def restore_palette(qapplication):
    original = QPalette(qapplication.palette())
    yield
    qapplication.setPalette(original)
    qapplication.processEvents()


def _switch(app: QApplication, palette: QPalette) -> None:
    app.setPalette(palette)
    app.processEvents()


def _cell(*runs: InlineRun) -> Block:
    return Block(kind=TABLE_CELL, runs=list(runs) or [InlineRun(text="")])


def _table() -> Block:
    return Block(
        kind=TABLE,
        children=[
            Block(
                kind=TABLE_ROW,
                children=[_cell(InlineRun(text="En-tête")), _cell(InlineRun(text="Titre"))],
            ),
            Block(
                kind=TABLE_ROW,
                children=[
                    _cell(InlineRun(text="Donnée")),
                    _cell(InlineRun(text="Lien", link_href="https://example.org")),
                ],
            ),
        ],
    )


def _editor(blocks: list[Block]) -> MeropeTextEdit:
    editor = MeropeTextEdit()
    editor.resize(600, 300)
    populate_document(editor.document(), blocks)
    editor.document().clearUndoRedoStacks()
    editor.document().setModified(False)
    editor.show()
    QApplication.processEvents()
    return editor


def _only_table(editor: MeropeTextEdit) -> QTextTable:
    return next(
        frame
        for frame in editor.document().rootFrame().childFrames()
        if isinstance(frame, QTextTable)
    )


def _relative_luminance(color: QColor) -> float:
    def channel(value: float) -> float:
        return value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4

    return (
        0.2126 * channel(color.redF())
        + 0.7152 * channel(color.greenF())
        + 0.0722 * channel(color.blueF())
    )


def _contrast(first: QColor, second: QColor) -> float:
    lighter, darker = sorted(
        (_relative_luminance(first), _relative_luminance(second)),
        reverse=True,
    )
    return (lighter + 0.05) / (darker + 0.05)


def _pixel_colors(image: QImage, x_range: range, y_range: range) -> dict[str, int]:
    counts: dict[str, int] = {}
    for y in y_range:
        for x in x_range:
            name = image.pixelColor(x, y).name()
            counts[name] = counts.get(name, 0) + 1
    return counts


def _cell_rendering(editor: MeropeTextEdit, row: int, column: int) -> tuple[QColor, QColor]:
    """Return ``(fill, strongest ink)`` painted inside one table cell."""

    table = _only_table(editor)
    cell = table.cellAt(row, column)
    start = editor.cursorRect(cell.firstCursorPosition())
    end = editor.cursorRect(cell.lastCursorPosition())
    scale = editor.viewport().devicePixelRatioF()
    image = editor.viewport().grab().toImage()
    pixels = _pixel_colors(
        image,
        range(int(start.left() * scale), int((end.right() + 1) * scale)),
        range(int(start.top() * scale), int((end.bottom() + 1) * scale)),
    )
    fill = QColor(max(pixels, key=pixels.get))
    ink = max((QColor(name) for name in pixels), key=lambda color: _contrast(color, fill))
    return fill, ink


# --- Lisibilité dans chaque thème -------------------------------------------


@pytest.mark.parametrize("theme", THEMES)
def test_header_text_is_legible(qapplication, theme):
    _switch(qapplication, THEMES[theme])
    editor = _editor([_table()])

    fill, ink = _cell_rendering(editor, 0, 0)

    assert _contrast(fill, ink) >= MINIMUM_CONTRAST
    editor.deleteLater()


@pytest.mark.parametrize("theme", THEMES)
def test_body_and_link_text_are_legible(qapplication, theme):
    _switch(qapplication, THEMES[theme])
    editor = _editor([_table()])

    for column in (0, 1):
        fill, ink = _cell_rendering(editor, 1, column)
        assert _contrast(fill, ink) >= MINIMUM_CONTRAST
    editor.deleteLater()


def test_header_tint_keeps_the_historic_light_colour_and_darkens_on_dark(qapplication):
    _switch(qapplication, LIGHT)
    editor = _editor([_table()])
    light_fill, _ink = _cell_rendering(editor, 0, 0)
    assert light_fill.name() == "#e8edf3"

    _switch(qapplication, DARK)
    dark_fill, _ink = _cell_rendering(editor, 0, 0)
    assert dark_fill.lightness() < 110
    assert dark_fill != QColor("#2d2d2d")
    editor.deleteLater()


@pytest.mark.parametrize("theme", THEMES)
def test_selected_header_text_is_legible(qapplication, theme):
    _switch(qapplication, THEMES[theme])
    editor = _editor([_table()])
    cell = _only_table(editor).cellAt(0, 0)
    cursor = cell.firstCursorPosition()
    cursor.setPosition(cell.lastCursorPosition().position(), QTextCursor.MoveMode.KeepAnchor)
    editor.setTextCursor(cursor)
    QApplication.processEvents()

    fill, ink = _cell_rendering(editor, 0, 0)

    assert fill == THEMES[theme].color(QPalette.ColorRole.Highlight)
    assert _contrast(fill, ink) >= 3.0
    editor.deleteLater()


@pytest.mark.parametrize("theme", THEMES)
def test_multi_cell_selection_is_legible(qapplication, theme):
    _switch(qapplication, THEMES[theme])
    editor = _editor([_table()])
    table = _only_table(editor)
    cursor = table.cellAt(0, 0).firstCursorPosition()
    cursor.setPosition(
        table.cellAt(1, 0).lastCursorPosition().position(),
        QTextCursor.MoveMode.KeepAnchor,
    )
    editor.setTextCursor(cursor)
    QApplication.processEvents()

    for row in (0, 1):
        fill, ink = _cell_rendering(editor, row, 0)
        assert _contrast(fill, ink) >= 3.0
    editor.deleteLater()


@pytest.mark.parametrize(
    "background",
    [TABLE_HEADER_BACKGROUND, RAW_TABLE_BACKGROUND, RAW_BLOCK_BACKGROUND],
)
@pytest.mark.parametrize("theme", THEMES)
def test_every_tint_is_translucent_and_legible(theme, background):
    tint = QColor(background)
    palette = THEMES[theme]
    base = palette.color(QPalette.ColorRole.Base)
    alpha = tint.alphaF()
    composed = QColor.fromRgbF(
        tint.redF() * alpha + base.redF() * (1 - alpha),
        tint.greenF() * alpha + base.greenF() * (1 - alpha),
        tint.blueF() * alpha + base.blueF() * (1 - alpha),
    )

    assert alpha < 1
    assert _contrast(composed, palette.color(QPalette.ColorRole.Text)) >= MINIMUM_CONTRAST


@pytest.mark.parametrize("theme", THEMES)
def test_insert_dialog_follows_the_palette(qapplication, theme):
    _switch(qapplication, THEMES[theme])
    dialog = TableInsertDialog()

    assert dialog.palette().color(QPalette.ColorRole.Base) == THEMES[theme].color(
        QPalette.ColorRole.Base
    )
    assert not dialog.styleSheet()
    dialog.deleteLater()


# --- Basculement dynamique --------------------------------------------------


def test_switching_theme_repaints_tables_without_touching_the_document(qapplication):
    _switch(qapplication, LIGHT)
    editor = _editor([_table()])
    before = extract_blocks(editor.document())
    formats_before = _only_table(editor).cellAt(0, 0).format().background().color()

    for palette in (DARK, LIGHT, DARK):
        _switch(qapplication, palette)
        fill, ink = _cell_rendering(editor, 0, 0)
        assert _contrast(fill, ink) >= MINIMUM_CONTRAST
        assert ink == palette.color(QPalette.ColorRole.Text)

    assert extract_blocks(editor.document()) == before
    assert not editor.document().isModified()
    assert not editor.document().isUndoAvailable()
    assert _only_table(editor).cellAt(0, 0).format().background().color() == formats_before
    editor.deleteLater()


def test_link_colour_follows_the_theme_and_comes_back(qapplication):
    _switch(qapplication, LIGHT)
    editor = _editor([_table()])
    _fill, light_ink = _cell_rendering(editor, 1, 1)
    assert light_ink == QColor(LINK_LIGHT)

    _switch(qapplication, DARK)
    _fill, dark_ink = _cell_rendering(editor, 1, 1)
    assert dark_ink == DARK.color(QPalette.ColorRole.Link)

    _switch(qapplication, LIGHT)
    _fill, restored_ink = _cell_rendering(editor, 1, 1)
    assert restored_ink == QColor(LINK_LIGHT)
    assert not editor.document().isModified()
    editor.deleteLater()


def test_link_colour_overlay_survives_zoom(qapplication):
    _switch(qapplication, DARK)
    editor = _editor([_table()])
    assert editor.adjust_zoom(2)
    QApplication.processEvents()

    _fill, ink = _cell_rendering(editor, 1, 1)

    assert ink == DARK.color(QPalette.ColorRole.Link)
    editor.deleteLater()


def test_misspelled_link_keeps_both_its_theme_colour_and_its_underline():
    document = QTextDocument()
    populate_document(
        document,
        [Block(kind=PARAGRAPH, runs=[InlineRun(text="Lien", link_href="https://example.org")])],
    )
    checker = SimpleNamespace(
        available=True,
        issues=lambda _text: [SimpleNamespace(start=0, length=4)],
    )
    highlighter = FrenchSpellHighlighter(document, checker=checker)

    highlighter.set_semantic_foreground(QColor("#99ebff"))

    formats = document.begin().layout().formats()
    assert sum(item.length for item in formats) == 4
    for item in formats:
        assert item.format.foreground().color() == QColor("#99ebff")
        assert item.format.underlineStyle() == QTextCharFormat.UnderlineStyle.SpellCheckUnderline
    zoom_ranges = highlighter.format_ranges(document.begin())
    assert {item.format.underlineStyle() for item in zoom_ranges} == {
        QTextCharFormat.UnderlineStyle.NoUnderline,
        QTextCharFormat.UnderlineStyle.SpellCheckUnderline,
    }


def test_undo_after_a_switch_restores_a_format_valid_in_the_active_theme(qapplication):
    _switch(qapplication, LIGHT)
    editor = _editor([_table()])
    editor.setTextCursor(_only_table(editor).cellAt(0, 0).firstCursorPosition())
    editor.insertPlainText("X")

    _switch(qapplication, DARK)
    editor.undo()
    QApplication.processEvents()

    fill, ink = _cell_rendering(editor, 0, 0)
    assert _contrast(fill, ink) >= MINIMUM_CONTRAST
    editor.deleteLater()


def test_removing_a_link_does_not_freeze_the_palette_colour(qapplication):
    """The stored colour used to turn white on white after a theme switch."""

    _switch(qapplication, DARK)
    editor = _editor(
        [Block(kind=PARAGRAPH, runs=[InlineRun(text="Lien", link_href="https://example.org")])]
    )
    editor.selectAll()
    set_link(editor, None)
    cursor = editor.textCursor()
    cursor.clearSelection()
    editor.setTextCursor(cursor)
    QApplication.processEvents()

    _switch(qapplication, LIGHT)

    image = editor.viewport().grab().toImage()
    pixels = _pixel_colors(image, range(image.width()), range(min(40, image.height())))
    fill = QColor("#ffffff")
    assert max(_contrast(QColor(name), fill) for name in pixels) >= MINIMUM_CONTRAST
    editor.deleteLater()


def test_raw_table_block_is_legible_in_both_themes(qapplication):
    raw = Block(kind=VERBATIM, raw_text="| a |\n| b |")
    _switch(qapplication, LIGHT)
    editor = _editor([raw])

    for palette in (LIGHT, DARK):
        _switch(qapplication, palette)
        image = editor.viewport().grab().toImage()
        pixels = _pixel_colors(image, range(image.width()), range(min(20, image.height())))
        fill = max(
            (QColor(name) for name in pixels if QColor(name) != palette.color(QPalette.ColorRole.Base)),
            key=lambda color: pixels[color.name()],
        )
        assert max(_contrast(QColor(name), fill) for name in pixels) >= MINIMUM_CONTRAST
    assert not editor.document().isModified()
    editor.deleteLater()


def test_raw_tints_are_the_shared_translucent_constants():
    def background(kind: str) -> str:
        brush = make_raw_block_format(kind, "groupe").background()
        return brush.color().name(QColor.NameFormat.HexArgb)

    assert background(TABLE) == RAW_TABLE_BACKGROUND
    assert background(VERBATIM) == RAW_BLOCK_BACKGROUND


def test_toolbar_glyph_icons_follow_a_live_switch(qapplication):
    _switch(qapplication, LIGHT)
    window = QtEditorWindow()
    action = window.insert_table_action
    light_key = action.icon().pixmap(30, 30).toImage()

    _switch(qapplication, DARK)
    dark_image = action.icon().pixmap(30, 30).toImage()

    assert dark_image != light_key
    assert dark_image == toolbar_icon(window, "table").pixmap(30, 30).toImage()
    window.editor.document().setModified(False)
    window.close()
    window.deleteLater()
