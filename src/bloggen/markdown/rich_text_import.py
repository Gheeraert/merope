"""Convert Markdown body text into the rich-text ``Block``/``InlineRun`` model.

This is a deliberately constrained importer: it only understands the subset
of Markdown produced by :mod:`bloggen.markdown.rich_text_export` (ATX
headings, bold/italic/strikethrough, links, images, footnote references,
bullet/ordered lists, blockquotes, pipe tables, footnote definitions). Any
chunk of text it cannot confidently classify is preserved as a ``VERBATIM``
block and reproduced byte-for-byte on the next export, instead of being
guessed at or dropped.

This is *not* a general-purpose Markdown parser: it exists solely to let the
WYSIWYG editor reopen files it (or a human writing in the same limited
style) has produced. The actual Markdown -> TEI -> HTML build pipeline is
untouched and still goes exclusively through Pandoc.
"""

from __future__ import annotations

import re

from bloggen.markdown.image_attributes import parse_image_attributes
from bloggen.markdown.rich_text_model import (
    BLOCKQUOTE,
    BULLET_LIST,
    FOOTNOTE_DEFINITION,
    HEADING,
    LIST_ITEM,
    ORDERED_LIST,
    PARAGRAPH,
    TABLE,
    TABLE_CELL,
    TABLE_ROW,
    VERBATIM,
    Block,
    InlineRun,
)

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_FOOTNOTE_DEF_RE = re.compile(r"^\[\^([^\]]+)\]:\s*(.*)$")
_BLOCKQUOTE_LINE_RE = re.compile(r"^>\s?(.*)$")
_BULLET_ITEM_RE = re.compile(r"^[-*]\s+(.*)$")
_ORDERED_ITEM_RE = re.compile(r"^\d+\.\s+(.*)$")
_TABLE_SEPARATOR_RE = re.compile(r"^\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)*\|?$")
_STRUCTURAL_LINE_RE = re.compile(r"^(#{1,6}\s|>\s?|[-*]\s|\d+\.\s|\||<)")

_ATOM_RE = re.compile(
    r"!\[(?P<image_alt>[^\]]*)\]\((?P<image_src>[^)]+)\)(\{(?P<image_attrs>[^}]*)\})?"
    r"|\[\^(?P<footnote_ref>[^\]]+)\]"
    r"|\[(?P<link_text>[^\]]*)\]\((?P<link_href>[^)]+)\)"
    r"|(?P<emphasis>\*\*\*.+?\*\*\*|\*\*.+?\*\*|~~.+?~~|\*[^*]+?\*)"
)
_UNESCAPE_RE = re.compile(r"\\([\\*_\[\]])")


def markdown_to_blocks(body: str) -> list[Block]:
    normalized = body.replace("\r\n", "\n").replace("\r", "\n")
    return [_chunk_to_block(chunk) for chunk in _split_into_chunks(normalized)]


def _split_into_chunks(text: str) -> list[list[str]]:
    chunks: list[list[str]] = []
    current: list[str] = []
    for line in text.split("\n"):
        if line.strip() == "":
            if current:
                chunks.append(current)
                current = []
        else:
            current.append(line)
    if current:
        chunks.append(current)
    return chunks


def _chunk_to_block(lines: list[str]) -> Block:
    if len(lines) == 1:
        heading_match = _HEADING_RE.match(lines[0])
        if heading_match:
            level = len(heading_match.group(1))
            return Block(kind=HEADING, level=level, runs=_parse_inline(heading_match.group(2)))

        footnote_match = _FOOTNOTE_DEF_RE.match(lines[0])
        if footnote_match:
            return Block(
                kind=FOOTNOTE_DEFINITION,
                footnote_id=footnote_match.group(1),
                runs=_parse_inline(footnote_match.group(2)),
            )

    table = parse_table_lines(lines)
    if table is not None:
        return table

    if all(_BLOCKQUOTE_LINE_RE.match(line) for line in lines):
        content = " ".join(_BLOCKQUOTE_LINE_RE.match(line).group(1) for line in lines)
        return Block(kind=BLOCKQUOTE, runs=_parse_inline(content))

    bullet_list = _try_list(lines, _BULLET_ITEM_RE, BULLET_LIST)
    if bullet_list is not None:
        return bullet_list

    ordered_list = _try_list(lines, _ORDERED_ITEM_RE, ORDERED_LIST)
    if ordered_list is not None:
        return ordered_list

    if not any(_STRUCTURAL_LINE_RE.match(line) for line in lines):
        text = " ".join(line.strip() for line in lines)
        return Block(kind=PARAGRAPH, runs=_parse_inline(text))

    return Block(kind=VERBATIM, raw_text="\n".join(lines))


def _try_list(lines: list[str], item_re: re.Pattern[str], kind: str) -> Block | None:
    matches = [item_re.match(line) for line in lines]
    if not all(matches):
        return None
    items = [Block(kind=LIST_ITEM, runs=_parse_inline(match.group(1))) for match in matches]
    return Block(kind=kind, children=items)


def parse_table_lines(lines: list[str]) -> Block | None:
    """Parse a pipe-table (header + separator + rows). ``None`` if ``lines``
    is not a well-formed table, so the caller can fall back to another
    representation instead of guessing. Exposed publicly so the content
    editor's UI can reuse it for the raw "table_source" region of the
    Tk ``Text`` widget, where tables are edited as structured pipe text.
    """
    if len(lines) < 2 or not lines[0].strip().startswith("|"):
        return None
    if not _TABLE_SEPARATOR_RE.match(lines[1].strip()):
        return None

    rows = [lines[0], *lines[2:]]
    row_blocks = []
    for row_line in rows:
        cells = _split_table_row(row_line)
        cell_blocks = [Block(kind=TABLE_CELL, runs=_parse_inline(cell)) for cell in cells]
        row_blocks.append(Block(kind=TABLE_ROW, children=cell_blocks))
    return Block(kind=TABLE, children=row_blocks)


def _split_table_row(line: str) -> list[str]:
    stripped = line.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|"):
        stripped = stripped[:-1]

    cells: list[str] = []
    current = []
    i = 0
    while i < len(stripped):
        char = stripped[i]
        if char == "\\" and i + 1 < len(stripped) and stripped[i + 1] == "|":
            current.append("|")
            i += 2
            continue
        if char == "|":
            cells.append("".join(current).strip())
            current = []
            i += 1
            continue
        current.append(char)
        i += 1
    cells.append("".join(current).strip())
    return cells


def _parse_inline(text: str) -> list[InlineRun]:
    runs: list[InlineRun] = []
    pos = 0
    for match in _ATOM_RE.finditer(text):
        if match.start() > pos:
            runs.append(InlineRun(text=_unescape(text[pos : match.start()])))
        runs.append(_atom_to_run(match))
        pos = match.end()
    if pos < len(text):
        runs.append(InlineRun(text=_unescape(text[pos:])))
    if not runs:
        runs.append(InlineRun(text=""))
    return runs


def _atom_to_run(match: re.Match[str]) -> InlineRun:
    if match.group("image_src") is not None:
        attrs = parse_image_attributes(match.group("image_attrs") or "")
        return InlineRun(
            image_src=match.group("image_src"),
            image_alt=_unescape(match.group("image_alt") or ""),
            image_width=attrs.get("width"),
            image_height=attrs.get("height"),
            image_align=attrs.get("align"),
        )
    if match.group("footnote_ref") is not None:
        return InlineRun(footnote_ref=match.group("footnote_ref"))
    if match.group("link_href") is not None:
        run = _peel_emphasis(match.group("link_text") or "")
        run.link_href = match.group("link_href")
        return run
    return _peel_emphasis(match.group("emphasis"))


def _peel_emphasis(span: str) -> InlineRun:
    bold = italic = strikethrough = False
    changed = True
    while changed:
        changed = False
        if len(span) >= 6 and span.startswith("***") and span.endswith("***"):
            span = span[3:-3]
            bold = italic = True
            changed = True
        elif len(span) >= 4 and span.startswith("**") and span.endswith("**"):
            span = span[2:-2]
            bold = True
            changed = True
        elif len(span) >= 4 and span.startswith("~~") and span.endswith("~~"):
            span = span[2:-2]
            strikethrough = True
            changed = True
        elif (
            len(span) >= 2
            and span.startswith("*")
            and span.endswith("*")
            and not span.startswith("**")
        ):
            span = span[1:-1]
            italic = True
            changed = True
    return InlineRun(text=_unescape(span), bold=bold, italic=italic, strikethrough=strikethrough)


def _unescape(text: str) -> str:
    return _UNESCAPE_RE.sub(r"\1", text)
