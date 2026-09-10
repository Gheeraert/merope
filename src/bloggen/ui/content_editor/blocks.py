"""Bridges the Tk Text widget's tags to the Block/InlineRun rich-text
model: extract_blocks() on save, _populate_from_blocks() on load."""

from __future__ import annotations

from bloggen.markdown.rich_text_export import blocks_to_markdown
from bloggen.markdown.rich_text_import import parse_table_lines
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
from bloggen.ui.image_widget import ImageWidget
from .constants import _BLOCK_LINE_TAGS

class BlocksMixin:
    """Bridges the Tk Text widget's tags to the Block/InlineRun rich-text
    model: extract_blocks() on save, _populate_from_blocks() on load."""

    def _line_block_type(self, line: int) -> str:
        """The recognized block-level tag for ``line``, or ``"plain"`` if none.

        ``"plain"`` (rather than ``None``) is returned so a plain paragraph
        group is never confused with "no group started yet" in
        :meth:`extract_blocks`.
        """
        tags = set(self.text.tag_names(f"{line}.0"))
        for candidate in _BLOCK_LINE_TAGS:
            if candidate in tags:
                return candidate
        return "plain"

    def _line_has_window(self, line: int) -> bool:
        """True if ``line`` contains an embedded window (e.g. an image).

        ``Text.get()`` silently omits embedded windows from its returned
        text, so a line holding only an image looks empty to a naive
        blank-line check and would otherwise be skipped as a paragraph
        separator, silently dropping the image on extraction.
        """
        dump = self.text.dump(f"{line}.0", f"{line}.end", window=True)
        return any(key == "window" for key, _value, _index in dump)

    def _extract_runs(self, start: str, end: str) -> list[InlineRun]:
        runs: list[InlineRun] = []
        active: set[str] = set()
        buffer = ""

        def flush() -> None:
            nonlocal buffer
            if not buffer:
                return
            fnref_tag = next((t for t in active if t in self.footnote_ref_data), None)
            link_tag = next((t for t in active if t in self.link_data), None)
            if fnref_tag:
                runs.append(InlineRun(footnote_ref=self.footnote_ref_data[fnref_tag]))
            else:
                runs.append(
                    InlineRun(
                        text=buffer,
                        bold="bold" in active,
                        italic="italic" in active,
                        strikethrough="strike" in active,
                        superscript="superscript" in active,
                        link_href=self.link_data.get(link_tag) if link_tag else None,
                    )
                )
            buffer = ""

        for key, value, _index in self.text.dump(start, end, tag=True, text=True, window=True):
            if key == "tagon":
                flush()
                active.add(value)
            elif key == "tagoff":
                flush()
                active.discard(value)
            elif key == "text":
                if "list_marker" in active:
                    continue
                buffer += value
            elif key == "window":
                flush()
                widget = self.text.nametowidget(value)
                if isinstance(widget, ImageWidget):
                    runs.append(
                        InlineRun(
                            image_src=widget.src,
                            image_alt=widget.alt,
                            image_width=str(widget.width),
                            image_height=str(widget.height),
                            image_align=widget.align,
                        )
                    )
        flush()
        return runs or [InlineRun(text="")]

    def extract_blocks(self) -> list[Block]:
        line_count = int(self.text.index("end-1c").split(".")[0])
        blocks: list[Block] = []
        group_type: str | None = None
        group_start = 1

        def flush_group(end_line: int) -> None:
            nonlocal group_type
            if group_type is None:
                return
            blocks.append(self._build_group_block(group_type, group_start, end_line))
            group_type = None

        line = 1
        while line <= line_count:
            line_text = self.text.get(f"{line}.0", f"{line}.end")
            if line_text.strip() == "" and not self._line_has_window(line):
                flush_group(line - 1)
                line += 1
                continue
            block_type = self._line_block_type(line)
            if group_type is None:
                group_type = block_type
                group_start = line
            elif block_type != group_type or block_type in ("h1", "h2", "h3", "h4"):
                flush_group(line - 1)
                group_type = block_type
                group_start = line
            line += 1
        flush_group(line_count)

        self._sync_footnote_widgets_to_model()
        for note_id in sorted(self.footnote_definitions, key=int):
            blocks.append(
                Block(
                    kind=FOOTNOTE_DEFINITION,
                    footnote_id=note_id,
                    runs=self.footnote_definitions[note_id],
                )
            )
        return blocks

    def _build_group_block(self, group_type: str | None, start_line: int, end_line: int) -> Block:
        if group_type in ("h1", "h2", "h3", "h4"):
            return Block(kind=HEADING, level=int(group_type[1]), runs=self._extract_runs(f"{start_line}.0", f"{start_line}.end"))

        if group_type == "blockquote":
            runs = self._merge_lines_runs(start_line, end_line)
            return Block(kind=BLOCKQUOTE, runs=runs, alignment=self._line_alignment(start_line))

        if group_type in ("bullet_item", "ordered_item"):
            items = [
                Block(kind=LIST_ITEM, runs=self._extract_runs(f"{ln}.0", f"{ln}.end"))
                for ln in range(start_line, end_line + 1)
            ]
            kind = BULLET_LIST if group_type == "bullet_item" else ORDERED_LIST
            return Block(kind=kind, children=items)

        if group_type == "table_source":
            lines = [self.text.get(f"{ln}.0", f"{ln}.end") for ln in range(start_line, end_line + 1)]
            table = parse_table_lines(lines)
            if table is not None:
                return table
            return Block(kind=VERBATIM, raw_text="\n".join(lines))

        if group_type == "verbatim":
            lines = [self.text.get(f"{ln}.0", f"{ln}.end") for ln in range(start_line, end_line + 1)]
            return Block(kind=VERBATIM, raw_text="\n".join(lines))

        # plain paragraph
        runs = self._merge_lines_runs(start_line, end_line)
        return Block(kind=PARAGRAPH, runs=runs, alignment=self._line_alignment(start_line))

    def _merge_lines_runs(self, start_line: int, end_line: int) -> list[InlineRun]:
        runs: list[InlineRun] = []
        for i, line in enumerate(range(start_line, end_line + 1)):
            if i > 0:
                runs.append(InlineRun(text=" "))
            runs.extend(self._extract_runs(f"{line}.0", f"{line}.end"))
        return runs

    # -- population (Block model -> Text widget) ---------------------------

    def _populate_from_blocks(self, blocks: list[Block]) -> None:
        self._suppress_undo_tracking = True
        self._destroy_embedded_images()
        self.text.delete("1.0", "end")
        self.footnote_definitions.clear()
        self.link_data.clear()
        self.footnote_ref_data.clear()
        self._note_link_data.clear()
        self._footnote_text_widgets.clear()

        body_blocks = [b for b in blocks if b.kind != FOOTNOTE_DEFINITION]
        for block in blocks:
            if block.kind == FOOTNOTE_DEFINITION and block.footnote_id:
                self.footnote_definitions[block.footnote_id] = list(block.runs) or [InlineRun(text="")]

        for index, block in enumerate(body_blocks):
            if index > 0:
                self.text.insert("end", "\n\n")
            self._insert_block(block)

        self._refresh_combined_fonts()
        self._quote_parity_opening = True
        self._refresh_notes_panel()
        self.text.edit_reset()
        self._undo_stack.clear()
        self._redo_stack.clear()
        self._current_edit_kind = None
        self._last_char_count = self._char_count()
        self._suppress_undo_tracking = False
        self._dirty = False

    def _insert_block(self, block: Block) -> None:
        if block.kind == PARAGRAPH:
            start = self.text.index("end-1c")
            self._insert_runs(block.runs)
            self.text.tag_add("plain", start, self.text.index("end-1c"))
            self._tag_alignment(block.alignment, start, self.text.index("end-1c"))
        elif block.kind == HEADING:
            start = self.text.index("end-1c")
            self._insert_runs(block.runs)
            self.text.tag_add(f"h{block.level or 1}", start, self.text.index("end-1c"))
        elif block.kind == BLOCKQUOTE:
            start = self.text.index("end-1c")
            self._insert_runs(block.runs)
            self.text.tag_add("blockquote", start, self.text.index("end-1c"))
            self._tag_alignment(block.alignment, start, self.text.index("end-1c"))
        elif block.kind in (BULLET_LIST, ORDERED_LIST):
            tag = "bullet_item" if block.kind == BULLET_LIST else "ordered_item"
            for i, item in enumerate(block.children):
                if i > 0:
                    self.text.insert("end", "\n")
                start = self.text.index("end-1c")
                self.text.insert("end", self._list_marker_text(tag, i + 1))
                self.text.tag_add("list_marker", start, self.text.index("end-1c"))
                self._insert_runs(item.runs)
                self.text.tag_add(tag, start, self.text.index("end-1c"))
        elif block.kind == TABLE:
            table_text = blocks_to_markdown([block]).rstrip("\n")
            start_line = int(self.text.index("end-1c").split(".")[0])
            self.text.insert("end", table_text)
            end_line = int(self.text.index("end-1c").split(".")[0])
            for line in range(start_line, end_line + 1):
                self.text.tag_add("table_source", f"{line}.0", f"{line}.end")
        elif block.kind == VERBATIM:
            start_line = int(self.text.index("end-1c").split(".")[0])
            self.text.insert("end", block.raw_text or "")
            end_line = int(self.text.index("end-1c").split(".")[0])
            for line in range(start_line, end_line + 1):
                self.text.tag_add("verbatim", f"{line}.0", f"{line}.end")

    def _insert_runs(self, runs: list[InlineRun]) -> None:
        for run in runs:
            if run.image_src is not None:
                width = int(run.image_width) if run.image_width else None
                height = int(run.image_height) if run.image_height else None
                self._insert_image_widget(
                    "end",
                    run.image_src,
                    run.image_alt or "",
                    width=width,
                    height=height,
                    align=run.image_align,
                )
                continue
            if run.footnote_ref is not None:
                self._insert_footnote_marker(self.text.index("end-1c"), run.footnote_ref)
                continue

            start = self.text.index("end-1c")
            self.text.insert("end", run.text)
            end = self.text.index("end-1c")
            if run.bold:
                self.text.tag_add("bold", start, end)
            if run.italic:
                self.text.tag_add("italic", start, end)
            if run.strikethrough:
                self.text.tag_add("strike", start, end)
            if run.superscript:
                self.text.tag_add("superscript", start, end)
            if run.link_href:
                tag = self._new_tag("link")
                self.link_data[tag] = run.link_href
                self.text.tag_add(tag, start, end)
                self.text.tag_add("link_style", start, end)

    # -- save ---------------------------------------------------------------
