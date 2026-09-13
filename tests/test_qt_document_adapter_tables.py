from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtGui import (
    QTextBlockFormat,
    QTextCursor,
    QTextDocument,
    QTextFrameFormat,
    QTextListFormat,
    QTextTable,
)
from PySide6.QtWidgets import QApplication

from bloggen.content.footnotes import footnote_reference_order
from bloggen.markdown.rich_text_export import blocks_to_markdown
from bloggen.markdown.rich_text_import import markdown_to_blocks
from bloggen.markdown.rich_text_model import (
    HEADING,
    PARAGRAPH,
    TABLE,
    TABLE_CELL,
    TABLE_ROW,
    Block,
    InlineRun,
)
from bloggen.ui.qt_editor.constants import (
    BLOCK_KIND_PROPERTY,
    FOOTNOTE_MARKER_PROPERTY,
    MEROPE_TABLE_PROPERTY,
    RAW_BLOCK_KIND_PROPERTY,
)
from bloggen.ui.qt_editor.document_adapter import (
    UnsupportedBlockError,
    extract_blocks,
    make_image_format,
    populate_document,
    renumber_footnote_references,
    table_is_qt_editable,
)


@pytest.fixture(scope="module", autouse=True)
def qapplication():
    app = QApplication.instance() or QApplication([])
    yield app


def _cell(*runs: InlineRun) -> Block:
    return Block(kind=TABLE_CELL, runs=list(runs) or [InlineRun(text="")])


def _table(rows: list[list[Block]]) -> Block:
    return Block(
        kind=TABLE,
        children=[Block(kind=TABLE_ROW, children=row) for row in rows],
    )


def _simple_table(text: str = "Cellule") -> Block:
    return _table([[_cell(InlineRun(text=text))]])


def _qtext_tables(document: QTextDocument) -> list[QTextTable]:
    return [
        frame
        for frame in document.rootFrame().childFrames()
        if isinstance(frame, QTextTable)
    ]


def _only_qtext_table(document: QTextDocument) -> QTextTable:
    tables = _qtext_tables(document)
    assert len(tables) == 1
    return tables[0]


def _replace_cell_with_image(table: QTextTable) -> None:
    block = table.cellAt(0, 0).firstCursorPosition().block()
    cursor = QTextCursor(block)
    cursor.movePosition(
        QTextCursor.MoveOperation.EndOfBlock,
        QTextCursor.MoveMode.KeepAnchor,
    )
    cursor.removeSelectedText()
    cursor.insertImage(make_image_format(InlineRun(image_src="image.png")))


def test_table_is_qt_editable_separates_validity_from_graphical_subset():
    assert table_is_qt_editable(_simple_table()) is True
    assert table_is_qt_editable(
        _table([[_cell(InlineRun(footnote_ref="1"))]])
    ) is True
    assert table_is_qt_editable(
        _table([[_cell(InlineRun(image_src="image.png"))]])
    ) is False
    assert table_is_qt_editable(
        _table([[_cell(InlineRun(text="A"))], [_cell(), _cell()]])
    ) is False
    assert table_is_qt_editable(Block(kind=PARAGRAPH)) is False


@pytest.mark.parametrize(
    "model",
    [
        _simple_table(),
        _table(
            [[_cell(InlineRun(text="A")), _cell(), _cell(InlineRun(text="C"))]]
        ),
        _table(
            [
                [
                    _cell(InlineRun(text="Élément\u00a0accentué")),
                    _cell(InlineRun(text="gras", bold=True)),
                    _cell(InlineRun(text="italique", italic=True)),
                ],
                [
                    _cell(InlineRun(text="barré", strikethrough=True)),
                    _cell(InlineRun(text="souligné", underline=True)),
                    _cell(InlineRun(text="exposant", superscript=True)),
                ],
                [
                    _cell(
                        InlineRun(
                            text="lien",
                            link_href="https://example.org/a_(b)",
                        )
                    ),
                    _cell(InlineRun(footnote_ref="7")),
                    _cell(
                        InlineRun(text="avant "),
                        InlineRun(text="mixte", bold=True, italic=True),
                    ),
                ],
            ]
        ),
    ],
)
def test_graphical_table_populates_and_extracts_exactly(model):
    document = QTextDocument()

    populate_document(document, [model])

    table = _only_qtext_table(document)
    assert table.format().property(MEROPE_TABLE_PROPERTY) is True
    assert table.format().headerRowCount() == 1
    assert extract_blocks(document) == [model]
    assert document.isModified() is False
    assert document.isUndoAvailable() is False


@pytest.mark.parametrize(
    "models",
    [
        [
            Block(kind=PARAGRAPH, runs=[InlineRun(text="Avant")]),
            _simple_table(),
            Block(kind=PARAGRAPH, runs=[InlineRun(text="Après")]),
        ],
        [_simple_table(), Block(kind=PARAGRAPH, runs=[InlineRun(text="Après")])],
        [Block(kind=PARAGRAPH, runs=[InlineRun(text="Avant")]), _simple_table()],
        [_simple_table("A"), _simple_table("B")],
        [
            Block(kind=PARAGRAPH, runs=[InlineRun(text="A")]),
            _simple_table("B"),
            Block(kind=PARAGRAPH, runs=[InlineRun(text="C")]),
            _simple_table("D"),
            Block(kind=PARAGRAPH, runs=[InlineRun(text="E")]),
        ],
    ],
)
def test_top_level_table_order_has_no_phantom_paragraphs(models):
    document = QTextDocument()

    populate_document(document, models)

    assert extract_blocks(document) == models
    assert len(_qtext_tables(document)) == sum(
        block.kind == TABLE for block in models
    )


def test_markdown_qtexttable_markdown_roundtrip_is_semantically_stable():
    source = (
        "| **Nom** | *Valeur* |\n"
        "| --- | --- |\n"
        "| [lien](https://example.org/a_(b)) | note[^7] |\n"
    )
    expected = markdown_to_blocks(source)
    document = QTextDocument()

    populate_document(document, expected)
    extracted = extract_blocks(document)
    markdown = blocks_to_markdown(extracted)

    assert _qtext_tables(document)
    assert extracted == expected
    assert markdown_to_blocks(markdown) == expected


def test_table_with_image_remains_a_raw_table_fallback():
    model = _table(
        [[_cell(InlineRun(image_src="image.png", image_alt="Illustration"))]]
    )
    document = QTextDocument()

    populate_document(document, [model])

    assert _qtext_tables(document) == []
    assert document.begin().blockFormat().property(RAW_BLOCK_KIND_PROPERTY) == TABLE
    assert extract_blocks(document) == [model]


def test_graphical_table_footnotes_are_atomic_and_renumbered_in_reading_order():
    model = _table(
        [
            [_cell(InlineRun(text="A"), InlineRun(footnote_ref="7")), _cell()],
            [_cell(InlineRun(footnote_ref="2")), _cell(InlineRun(text="D"))],
        ]
    )
    document = QTextDocument()
    populate_document(document, [model])
    table = _only_qtext_table(document)
    marker_formats = []
    for row in range(table.rows()):
        for column in range(table.columns()):
            iterator = table.cellAt(row, column).firstCursorPosition().block().begin()
            while not iterator.atEnd():
                fragment = iterator.fragment()
                if fragment.isValid() and fragment.charFormat().hasProperty(
                    FOOTNOTE_MARKER_PROPERTY
                ):
                    marker_formats.append(fragment.charFormat())
                iterator += 1

    assert len(marker_formats) == 2
    assert all(bool(fmt.property(FOOTNOTE_MARKER_PROPERTY)) for fmt in marker_formats)
    assert footnote_reference_order(extract_blocks(document)) == ["7", "2"]

    assert renumber_footnote_references(document, {"7": "1", "2": "2"}) is True
    assert footnote_reference_order(extract_blocks(document)) == ["1", "2"]


def test_unmarked_qtexttable_is_rejected():
    document = QTextDocument()
    QTextCursor(document).insertTable(1, 1)

    with pytest.raises(UnsupportedBlockError, match="étrangers"):
        extract_blocks(document)


def test_wrong_header_row_count_is_rejected():
    document = QTextDocument()
    populate_document(document, [_simple_table()])
    table = _only_qtext_table(document)
    table_format = table.format()
    table_format.setHeaderRowCount(0)
    table.setFormat(table_format)

    with pytest.raises(UnsupportedBlockError, match="ligne d’en-tête"):
        extract_blocks(document)


def test_multiblock_cell_is_rejected():
    document = QTextDocument()
    populate_document(document, [_simple_table()])
    table = _only_qtext_table(document)
    table.cellAt(0, 0).lastCursorPosition().insertBlock()

    with pytest.raises(UnsupportedBlockError, match="un seul paragraphe"):
        extract_blocks(document)


def test_list_in_cell_is_rejected():
    document = QTextDocument()
    populate_document(document, [_simple_table()])
    table = _only_qtext_table(document)
    table.cellAt(0, 0).firstCursorPosition().createList(QTextListFormat())

    with pytest.raises(UnsupportedBlockError, match="listes"):
        extract_blocks(document)


def test_image_inserted_in_graphical_cell_is_rejected():
    document = QTextDocument()
    populate_document(document, [_simple_table()])
    table = _only_qtext_table(document)
    _replace_cell_with_image(table)

    with pytest.raises(UnsupportedBlockError, match="images"):
        extract_blocks(document)


def test_nested_table_is_rejected():
    document = QTextDocument()
    populate_document(document, [_simple_table()])
    table = _only_qtext_table(document)
    table.cellAt(0, 0).firstCursorPosition().insertTable(1, 1)

    with pytest.raises(UnsupportedBlockError, match="imbriqués"):
        extract_blocks(document)


def test_merged_cells_are_rejected():
    document = QTextDocument()
    populate_document(
        document,
        [_table([[_cell(InlineRun(text="A")), _cell(InlineRun(text="B"))]])],
    )
    table = _only_qtext_table(document)
    table.mergeCells(0, 0, 1, 2)

    with pytest.raises(UnsupportedBlockError, match="fusionnées"):
        extract_blocks(document)


def test_unknown_cell_block_semantics_are_rejected():
    document = QTextDocument()
    populate_document(document, [_simple_table()])
    table = _only_qtext_table(document)
    cursor = table.cellAt(0, 0).firstCursorPosition()
    block_format = QTextBlockFormat(cursor.blockFormat())
    block_format.setProperty(BLOCK_KIND_PROPERTY, HEADING)
    cursor.setBlockFormat(block_format)

    with pytest.raises(UnsupportedBlockError, match="structure de bloc"):
        extract_blocks(document)


def test_unknown_cell_inline_semantics_are_rejected():
    document = QTextDocument()
    populate_document(document, [_simple_table()])
    table = _only_qtext_table(document)
    cursor = table.cellAt(0, 0).firstCursorPosition()
    cursor.movePosition(
        QTextCursor.MoveOperation.EndOfBlock,
        QTextCursor.MoveMode.KeepAnchor,
    )
    char_format = cursor.charFormat()
    char_format.setProperty(MEROPE_TABLE_PROPERTY + 100, True)
    cursor.setCharFormat(char_format)

    with pytest.raises(UnsupportedBlockError, match="sémantique Qt inconnue"):
        extract_blocks(document)


def test_foreign_top_level_frame_is_rejected():
    document = QTextDocument()
    QTextCursor(document).insertFrame(QTextFrameFormat())

    with pytest.raises(UnsupportedBlockError, match="Cadre QTextDocument étranger"):
        extract_blocks(document)
