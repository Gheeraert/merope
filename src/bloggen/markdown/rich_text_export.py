"""Convert the rich-text ``Block``/``InlineRun`` model into Pandoc Markdown.

This is the "write" half of the WYSIWYG editor's round trip; the "read" half
lives in :mod:`bloggen.markdown.rich_text_import`. Output is plain Markdown
text (no front matter) meant to be combined with
:func:`bloggen.markdown.front_matter.format_front_matter`.
"""

from __future__ import annotations

import re

from bloggen.markdown.image_attributes import format_image_attributes
from bloggen.markdown.paragraph_alignment import format_alignment_marker
from bloggen.markdown.rich_text_model import (
    BLOCKQUOTE,
    BULLET_LIST,
    FOOTNOTE_DEFINITION,
    HEADING,
    LIST_ITEM,
    ORDERED_LIST,
    PARAGRAPH,
    TABLE,
    VERBATIM,
    Block,
    InlineRun,
)

_ESCAPE_RE = re.compile(r"([\\*_\[\]^])")


def blocks_to_markdown(blocks: list[Block]) -> str:
    parts = [_block_to_md(block) for block in blocks]
    text = "\n\n".join(part for part in parts if part)
    return text.rstrip("\n") + "\n"


def _block_to_md(block: Block) -> str:
    if block.kind == PARAGRAPH:
        return format_alignment_marker(block.alignment) + _runs_to_md(block.runs)
    if block.kind == HEADING:
        level = block.level or 1
        return f"{'#' * level} {_runs_to_md(block.runs)}"
    if block.kind == BLOCKQUOTE:
        inner = _runs_to_md(block.runs) if block.runs else "\n\n".join(
            _block_to_md(child) for child in block.children
        )
        inner = format_alignment_marker(block.alignment) + inner
        return "\n".join(f"> {line}" if line else ">" for line in inner.split("\n"))
    if block.kind == BULLET_LIST:
        return "\n".join(_list_item_to_md(item, marker="-") for item in block.children)
    if block.kind == ORDERED_LIST:
        return "\n".join(
            _list_item_to_md(item, marker=f"{index}.")
            for index, item in enumerate(block.children, start=1)
        )
    if block.kind == TABLE:
        return _table_to_md(block)
    if block.kind == FOOTNOTE_DEFINITION:
        return f"[^{block.footnote_id}]: {_runs_to_md(block.runs)}"
    if block.kind == VERBATIM:
        return block.raw_text or ""
    raise ValueError(f"Type de bloc inconnu: {block.kind}")


def _list_item_to_md(item: Block, *, marker: str) -> str:
    if item.children:
        content = "\n\n".join(_block_to_md(child) for child in item.children)
    else:
        content = _runs_to_md(item.runs)
    lines = content.split("\n")
    indent = " " * (len(marker) + 1)
    prefixed = [f"{marker} {lines[0]}" if lines else f"{marker} "]
    prefixed.extend(f"{indent}{line}" for line in lines[1:])
    return "\n".join(prefixed)


def _table_to_md(table: Block) -> str:
    rows = [[_runs_to_md(cell.runs) for cell in row.children] for row in table.children]
    if not rows:
        return ""
    column_count = max(len(row) for row in rows)
    rows = [row + [""] * (column_count - len(row)) for row in rows]

    lines = [_table_row_line(rows[0])]
    lines.append(_table_row_line(["---"] * column_count))
    for row in rows[1:]:
        lines.append(_table_row_line(row))
    return "\n".join(lines)


def _table_row_line(cells: list[str]) -> str:
    escaped = [cell.replace("|", "\\|") for cell in cells]
    return "| " + " | ".join(escaped) + " |"


def _runs_to_md(runs: list[InlineRun]) -> str:
    return "".join(_run_to_md(run) for run in runs)


def _run_to_md(run: InlineRun) -> str:
    if run.image_src is not None:
        alt = _escape_text(run.image_alt or "")
        attrs = format_image_attributes(
            {
                "width": run.image_width or "",
                "height": run.image_height or "",
                "align": run.image_align or "",
            }
        )
        return f"![{alt}]({run.image_src}){attrs}"
    if run.footnote_ref is not None:
        return f"[^{run.footnote_ref}]"

    text = _escape_text(run.text)
    if run.strikethrough:
        text = f"~~{text}~~"
    if run.superscript:
        text = f"^{text}^"
    if run.bold and run.italic:
        text = f"***{text}***"
    elif run.bold:
        text = f"**{text}**"
    elif run.italic:
        text = f"*{text}*"
    if run.link_href:
        text = f"[{text}]({run.link_href})"
    return text


def _escape_text(text: str) -> str:
    return _ESCAPE_RE.sub(r"\\\1", text)
