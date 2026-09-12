"""Convert Markdown body text into the rich-text ``Block``/``InlineRun`` model.

This is a deliberately constrained importer: it only understands the subset
of Markdown produced by :mod:`bloggen.markdown.rich_text_export` (ATX
headings, bold/italic/underline/strikethrough, links, images, footnote references,
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
from bloggen.markdown.paragraph_alignment import strip_alignment_marker
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
_ORDERED_ITEM_RE = re.compile(r"^(\d+)\.\s+(.*)$")
_TABLE_SEPARATOR_RE = re.compile(r"^\|?\s*-{3,}\s*(\|\s*-{3,}\s*)*\|?$")
_STRUCTURAL_LINE_RE = re.compile(
    r"^ {0,3}(?:#{1,6}\s|>\s?|[-*+]\s|\d+[.)]\s|\||<)"
)
_FENCE_OPEN_RE = re.compile(r"^ {0,3}(?P<fence>`{3,}|~{3,}).*$")
_SETEXT_UNDERLINE_RE = re.compile(r"^ {0,3}(?:=+|-+)\s*$")
_DEFINITION_CONTINUATION_RE = re.compile(r"^ {0,3}:\s+")
_LINK_DEFINITION_RE = re.compile(r"^ {0,3}\[[^]]+\]:\s*\S")
_THEMATIC_BREAK_RE = re.compile(
    r"^ {0,3}(?:\*(?:\s*\*){2,}|-(?:\s*-){2,}|_(?:\s*_){2,})\s*$"
)
_EMPHASIS_RE = re.compile(
    r"\*\*\*.+?\*\*\*|\*\*.+?\*\*|~~.+?~~|\^[^\^]+?\^|\*[^*]+?\*"
)
_UNESCAPE_RE = re.compile(r"\\([\\*_\[\]^])")


def markdown_to_blocks(body: str) -> list[Block]:
    normalized = body.replace("\r\n", "\n").replace("\r", "\n")
    return [_chunk_to_block(chunk) for chunk in _split_into_chunks(normalized)]


def _split_into_chunks(text: str) -> list[list[str]]:
    lines = text.split("\n")
    if lines and lines[-1] == "":
        # ``blocks_to_markdown`` owns the one canonical trailing newline.
        lines.pop()
    chunks: list[list[str]] = []
    current: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        fence = _opening_fence(line)
        if fence is not None:
            if current:
                chunks.append(current)
                current = []
            fenced = [line]
            index += 1
            while index < len(lines):
                fenced.append(lines[index])
                if _is_closing_fence(lines[index], fence):
                    index += 1
                    break
                index += 1
            chunks.append(fenced)
            continue
        if line.strip() == "":
            if current:
                if _blank_continues_footnote(lines, index, current):
                    current.append(line)
                else:
                    chunks.append(current)
                    current = []
        else:
            current.append(line)
        index += 1
    if current:
        chunks.append(current)
    return chunks


def _opening_fence(line: str) -> str | None:
    match = _FENCE_OPEN_RE.match(line)
    return match.group("fence") if match is not None else None


def _is_closing_fence(line: str, opening: str) -> bool:
    stripped = line.lstrip(" ")
    indentation = len(line) - len(stripped)
    if indentation > 3:
        return False
    marker = re.escape(opening[0])
    return bool(re.fullmatch(rf"{marker}{{{len(opening)},}}[ \t]*", stripped))


def _blank_continues_footnote(
    lines: list[str],
    index: int,
    current: list[str],
) -> bool:
    if not current or _FOOTNOTE_DEF_RE.match(current[0]) is None:
        return False
    following = index + 1
    while following < len(lines) and not lines[following].strip():
        following += 1
    return following < len(lines) and _is_indented_code_line(lines[following])


def _chunk_to_block(lines: list[str]) -> Block:
    if _chunk_starts_with_fence(lines):
        return Block(kind=VERBATIM, raw_text="\n".join(lines))
    if len(lines) == 1 and _THEMATIC_BREAK_RE.match(lines[0]):
        return Block(kind=VERBATIM, raw_text=lines[0])

    if len(lines) == 1:
        heading_match = _HEADING_RE.match(lines[0])
        if heading_match and _inline_is_losslessly_representable(
            heading_match.group(2)
        ):
            level = len(heading_match.group(1))
            return Block(kind=HEADING, level=level, runs=_parse_inline(heading_match.group(2)))

        footnote_match = _FOOTNOTE_DEF_RE.match(lines[0])
        if footnote_match and _inline_is_losslessly_representable(
            footnote_match.group(2)
        ):
            return Block(
                kind=FOOTNOTE_DEFINITION,
                footnote_id=footnote_match.group(1),
                runs=_parse_inline(footnote_match.group(2)),
            )

    table = parse_table_lines(lines)
    if table is not None:
        return table

    blockquote_matches = [_BLOCKQUOTE_LINE_RE.match(line) for line in lines]
    if all(blockquote_matches):
        content_lines = [match.group(1) for match in blockquote_matches]
        if _is_safe_paragraph_chunk(content_lines):
            content = " ".join(content_lines)
            content, alignment = strip_alignment_marker(content)
            return Block(
                kind=BLOCKQUOTE,
                runs=_parse_inline(content),
                alignment=alignment,
            )

    bullet_list = _try_list(lines, _BULLET_ITEM_RE, BULLET_LIST)
    if bullet_list is not None:
        return bullet_list

    ordered_list = _try_ordered_list(lines)
    if ordered_list is not None:
        return ordered_list

    if _is_safe_paragraph_chunk(lines):
        text = " ".join(line.strip() for line in lines)
        text, alignment = strip_alignment_marker(text)
        return Block(kind=PARAGRAPH, runs=_parse_inline(text), alignment=alignment)

    return Block(kind=VERBATIM, raw_text="\n".join(lines))


def _chunk_starts_with_fence(lines: list[str]) -> bool:
    return bool(lines and _opening_fence(lines[0]) is not None)


def _is_safe_paragraph_chunk(lines: list[str]) -> bool:
    if not lines or any(not line.strip() for line in lines):
        return False
    if len(lines) > 1 and _FOOTNOTE_DEF_RE.match(lines[0]):
        return False
    for line in lines:
        if (
            _opening_fence(line) is not None
            or _is_indented_code_line(line)
            or line.endswith("  ")
            or _has_markdown_backslash_break(line)
            or _SETEXT_UNDERLINE_RE.match(line)
            or _THEMATIC_BREAK_RE.match(line)
            or _DEFINITION_CONTINUATION_RE.match(line)
            or _LINK_DEFINITION_RE.match(line)
            or _STRUCTURAL_LINE_RE.match(line)
            or not _inline_is_losslessly_representable(line)
        ):
            return False
    return True


def _is_indented_code_line(line: str) -> bool:
    return line.startswith("\t") or line.startswith("    ")


def _has_markdown_backslash_break(line: str) -> bool:
    trailing = len(line) - len(line.rstrip("\\"))
    return trailing % 2 == 1


def _inline_is_losslessly_representable(text: str) -> bool:
    position = 0
    while position < len(text):
        if text[position] == "\\" and position + 1 < len(text):
            position += 2
            continue
        supported = _scan_inline_atom(text, position)
        if supported is not None:
            position = supported[1]
            continue
        if text[position] != "[":
            position += 1
            continue
        bracketed = _read_bracketed(text, position)
        if bracketed is None:
            position += 1
            continue
        _content, end = bracketed
        if end < len(text) and text[end] == "[":
            return False
        if text.startswith("{", end) and not text.startswith("{.underline}", end):
            return False
        position = end
    return True


def _try_list(lines: list[str], item_re: re.Pattern[str], kind: str) -> Block | None:
    matches = [item_re.match(line) for line in lines]
    if not all(matches):
        return None
    if not all(
        _inline_is_losslessly_representable(match.group(1)) for match in matches
    ):
        return None
    items = [Block(kind=LIST_ITEM, runs=_parse_inline(match.group(1))) for match in matches]
    return Block(kind=kind, children=items)


def _try_ordered_list(lines: list[str]) -> Block | None:
    matches = [_ORDERED_ITEM_RE.match(line) for line in lines]
    if not all(matches):
        return None
    numbers = [int(match.group(1)) for match in matches]
    if numbers != list(range(1, len(matches) + 1)):
        return None
    if not all(
        _inline_is_losslessly_representable(match.group(2)) for match in matches
    ):
        return None
    items = [
        Block(kind=LIST_ITEM, runs=_parse_inline(match.group(2)))
        for match in matches
    ]
    return Block(kind=ORDERED_LIST, children=items)


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
        if not all(_inline_is_losslessly_representable(cell) for cell in cells):
            return None
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
    plain_start = 0
    pos = 0
    while pos < len(text):
        if text[pos] == "\\" and pos + 1 < len(text):
            pos += 2
            continue
        atom = _scan_inline_atom(text, pos)
        if atom is None:
            pos += 1
            continue
        run, end = atom
        if plain_start < pos:
            runs.append(InlineRun(text=_unescape(text[plain_start:pos])))
        runs.append(run)
        pos = end
        plain_start = end
    if plain_start < len(text):
        runs.append(InlineRun(text=_unescape(text[plain_start:])))
    if not runs:
        runs.append(InlineRun(text=""))
    return runs


def _scan_inline_atom(text: str, start: int) -> tuple[InlineRun, int] | None:
    if text.startswith("![", start):
        return _scan_image(text, start)
    if text.startswith("[^", start):
        return _scan_footnote_reference(text, start)
    if text[start] == "[":
        return _scan_bracket_atom(text, start)
    emphasis = _EMPHASIS_RE.match(text, start)
    if emphasis is not None:
        return _peel_emphasis(emphasis.group(0)), emphasis.end()
    return None


def _scan_image(text: str, start: int) -> tuple[InlineRun, int] | None:
    bracketed = _read_bracketed(text, start + 1)
    if bracketed is None:
        return None
    alt, end = bracketed
    parenthesized = _read_parenthesized(text, end)
    if parenthesized is None:
        return None
    source, end = parenthesized
    attrs_text = ""
    if end < len(text) and text[end] == "{":
        attrs_end = text.find("}", end + 1)
        if attrs_end != -1:
            candidate = text[end + 1 : attrs_end]
            if _image_attributes_are_supported(candidate):
                attrs_text = candidate
                end = attrs_end + 1
    attrs = parse_image_attributes(attrs_text)
    return (
        InlineRun(
            image_src=source,
            image_alt=_unescape(alt),
            image_width=attrs.get("width"),
            image_height=attrs.get("height"),
            image_align=attrs.get("align"),
        ),
        end,
    )


def _image_attributes_are_supported(attr_text: str) -> bool:
    tokens = attr_text.split()
    if not tokens:
        return False
    keys: set[str] = set()
    for token in tokens:
        key, separator, value = token.partition("=")
        if (
            separator != "="
            or key not in {"width", "height", "align"}
            or not value
            or key in keys
        ):
            return False
        keys.add(key)
    return True


def _scan_footnote_reference(
    text: str,
    start: int,
) -> tuple[InlineRun, int] | None:
    bracketed = _read_bracketed(text, start)
    if bracketed is None:
        return None
    content, end = bracketed
    if not content.startswith("^") or len(content) == 1:
        return None
    return InlineRun(footnote_ref=content[1:]), end


def _scan_bracket_atom(text: str, start: int) -> tuple[InlineRun, int] | None:
    bracketed = _read_bracketed(text, start)
    if bracketed is None:
        return None
    content, end = bracketed
    if text.startswith("{.underline}", end):
        run = _scan_complete_link(content)
        if run is None:
            run = _peel_emphasis(content)
        run.underline = True
        return run, end + len("{.underline}")
    parenthesized = _read_parenthesized(text, end)
    if parenthesized is None:
        return None
    href, end = parenthesized
    run = _peel_emphasis(content)
    run.link_href = href
    return run, end


def _scan_complete_link(text: str) -> InlineRun | None:
    atom = _scan_bracket_atom(text, 0) if text.startswith("[") else None
    if atom is None or atom[1] != len(text):
        return None
    run = atom[0]
    if run.link_href is None or run.underline:
        return None
    return run


def _read_bracketed(text: str, start: int) -> tuple[str, int] | None:
    if start >= len(text) or text[start] != "[":
        return None
    depth = 1
    position = start + 1
    while position < len(text):
        char = text[position]
        if char == "\\" and position + 1 < len(text):
            position += 2
            continue
        if char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
            if depth == 0:
                return text[start + 1 : position], position + 1
        position += 1
    return None


def _read_parenthesized(text: str, start: int) -> tuple[str, int] | None:
    if start >= len(text) or text[start] != "(":
        return None
    depth = 1
    position = start + 1
    while position < len(text):
        char = text[position]
        if char == "\\" and position + 1 < len(text):
            position += 2
            continue
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return text[start + 1 : position], position + 1
        position += 1
    return None


def _peel_emphasis(span: str) -> InlineRun:
    bold = italic = strikethrough = superscript = False
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
        elif len(span) >= 2 and span.startswith("^") and span.endswith("^"):
            span = span[1:-1]
            superscript = True
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
    return InlineRun(
        text=_unescape(span),
        bold=bold,
        italic=italic,
        strikethrough=strikethrough,
        superscript=superscript,
    )


def _unescape(text: str) -> str:
    return _UNESCAPE_RE.sub(r"\1", text)
