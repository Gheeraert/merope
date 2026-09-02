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
    return "".join(_run_to_md(run) for run in _merge_adjacent_runs(runs))


def _merge_adjacent_runs(runs: list[InlineRun]) -> list[InlineRun]:
    """Coalesce consecutive plain-text runs that share the same formatting.

    The editor widget can split what the user perceives as a single
    formatted span into several adjacent runs with identical formatting
    (e.g. around an input-method/language change mid-word). Serializing
    each such run with its own ``**``/``*`` pair produces markers stacked
    back to back (``** ****mot**``) that Markdown treats as literal
    asterisks rather than emphasis, since a delimiter run can't be
    "flanked" from inside an adjacent identical run. Merging first avoids
    emitting a marker pair per fragment.
    """
    merged: list[InlineRun] = []
    for run in runs:
        is_plain_text = run.image_src is None and run.footnote_ref is None
        if is_plain_text and merged:
            previous = merged[-1]
            previous_is_plain_text = previous.image_src is None and previous.footnote_ref is None
            if previous_is_plain_text and (
                previous.bold,
                previous.italic,
                previous.strikethrough,
                previous.superscript,
                previous.link_href,
            ) == (run.bold, run.italic, run.strikethrough, run.superscript, run.link_href):
                merged[-1] = InlineRun(
                    text=previous.text + run.text,
                    bold=previous.bold,
                    italic=previous.italic,
                    strikethrough=previous.strikethrough,
                    superscript=previous.superscript,
                    link_href=previous.link_href,
                )
                continue
        merged.append(run)
    return merged


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

    leading = ""
    trailing = ""
    core = run.text
    has_marked_formatting = run.bold or run.italic or run.strikethrough or run.superscript
    if has_marked_formatting and core:
        stripped = core.strip()
        if stripped:
            lead_len = len(core) - len(core.lstrip())
            leading, core, trailing = core[:lead_len], stripped, core[lead_len + len(stripped):]
        else:
            # Whitespace-only run: markers can't legally wrap it, so leave
            # the whitespace bare rather than emit stray ``**``/``*``.
            leading, core = core, ""

    text = _escape_text(core)
    if core:
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
    text = f"{leading}{text}{trailing}"
    if run.link_href:
        text = f"[{text}]({run.link_href})"
    return text


def _escape_text(text: str) -> str:
    return _ESCAPE_RE.sub(r"\\\1", text)
