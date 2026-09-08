"""Toolbar formatting commands: character styles, headings/lists/
alignment, links/images/tables."""

from __future__ import annotations

from pathlib import Path
from tkinter import messagebox, filedialog, simpledialog
import tkinter as tk
from bloggen.markdown.rich_text_export import blocks_to_markdown
from bloggen.markdown.rich_text_model import TABLE, Block, InlineRun
from bloggen.markdown.typography import NBSP
from bloggen.ui.image_widget import ImageWidget, copy_into_images_dir
from .constants import _BLOCK_LINE_TAGS

_LIST_LINE_TAGS = {"bullet_item", "ordered_item"}
# Alignment is orthogonal to _BLOCK_LINE_TAGS (a paragraph or blockquote line
# can carry both its block-type tag and one of these). Only meaningful for
# PARAGRAPH/BLOCKQUOTE on export (see bloggen.markdown.paragraph_alignment).
_ALIGN_TAGS = ("align_left", "align_center", "align_right", "align_justify")


class FormattingMixin:
    """Toolbar formatting commands: character styles, headings/lists/
    alignment, links/images/tables."""

    def _selection_range(self) -> tuple[str, str] | None:
        ranges = self.text.tag_ranges("sel")
        if not ranges:
            return None
        return str(ranges[0]), str(ranges[1])

    def _activate_char_format(self, tag: str) -> None:
        """Toolbar checkbutton command: apply the toggle, then resync every
        checkbutton's pressed state to the real tags (the click already
        flipped this one's own ``BooleanVar`` optimistically, which may not
        match — e.g. a mixed-formatting selection resolves to "add", not
        "remove", in :meth:`_toggle_char_tag`).
        """
        self._toggle_char_tag(tag)
        self._update_toolbar_char_state()

    def _update_toolbar_char_state(self, _event: tk.Event | None = None) -> None:
        """Light up each character-formatting toolbar button (gras/italique/
        barré/exposant) that applies to the current selection, or — with no
        selection — to the character the cursor sits on, so the toolbar
        always reflects what's under the cursor instead of only ever
        showing "off".
        """
        if not self._char_format_vars:
            return
        selected = self._selection_range()
        if selected is not None:
            start, end = selected
            active = {
                tag
                for tag in self._char_format_vars
                if all(tag in self.text.tag_names(idx) for idx in self._char_indices(start, end))
            }
        else:
            active = set(self.text.tag_names("insert"))
        for tag, var in self._char_format_vars.items():
            var.set(tag in active)

    def _toggle_char_tag(self, tag: str) -> None:
        selected = self._selection_range()
        if selected is None:
            return
        start, end = selected
        fully_tagged = all(tag in self.text.tag_names(idx) for idx in self._char_indices(start, end))
        mark_start, mark_end = self._mark_range(start, end)
        if fully_tagged:
            self.text.tag_remove(tag, start, end)
            self._push_format_undo(
                lambda: self.text.tag_add(tag, mark_start, mark_end),
                lambda: self.text.tag_remove(tag, mark_start, mark_end),
            )
        else:
            self.text.tag_add(tag, start, end)
            self._push_format_undo(
                lambda: self.text.tag_remove(tag, mark_start, mark_end),
                lambda: self.text.tag_add(tag, mark_start, mark_end),
            )

    def _char_indices(self, start: str, end: str):
        count = int(self.text.count(start, end, "chars")[0])
        for i in range(count):
            yield f"{start}+{i}c"

    def _current_line(self) -> int:
        return int(self.text.index("insert").split(".")[0])

    def _selected_lines(self) -> tuple[int, int]:
        selected = self._selection_range()
        if selected is None:
            line = self._current_line()
            return line, line
        start, end = selected
        return int(start.split(".")[0]), int(end.split(".")[0])

    def _toggle_heading(self, level: int) -> None:
        tag = f"h{level}"
        self._toggle_line_tag(tag)

    def _activate_block_format(self, tag: str) -> None:
        """Toolbar checkbutton command for H1-H4/citation. ``_toggle_line_tag``
        already resyncs every such checkbutton's pressed state to the
        line's real tag afterwards (the click already flipped this one's
        own ``BooleanVar`` optimistically, which is wrong e.g. when the
        line was some other heading level and just switched to this one).
        """
        self._toggle_line_tag(tag)

    def _update_toolbar_block_state(self, _event: tk.Event | None = None) -> None:
        """Light up the H1-H4/citation toolbar button matching the block
        tag on the line the cursor sits on, mirroring
        :meth:`_update_toolbar_char_state` for character formatting.
        """
        if not self._block_format_vars:
            return
        tags = set(self.text.tag_names(f"{self._current_line()}.0"))
        for tag, var in self._block_format_vars.items():
            var.set(tag in tags)

    def _toggle_line_tag(self, tag: str) -> None:
        start_line, end_line = self._selected_lines()
        changes: list[tuple[str, str, set[str], set[str]]] = []
        ordinal = 0
        for line in range(start_line, end_line + 1):
            line_start = f"{line}.0"
            before = set(self.text.tag_names(line_start)) & _BLOCK_LINE_TAGS
            already = tag in before
            if before & _LIST_LINE_TAGS:
                self._strip_list_marker(line)
            line_end = f"{line}.end"
            for existing in _BLOCK_LINE_TAGS:
                self.text.tag_remove(existing, line_start, line_end)
            after: set[str] = set()
            if not already:
                if tag in _LIST_LINE_TAGS:
                    ordinal += 1
                    self._apply_list_marker(line, self._list_marker_text(tag, ordinal))
                    line_end = f"{line}.end"
                self.text.tag_add(tag, line_start, line_end)
                after = {tag}
            changes.append((line_start, line_end, before, after))
        self._push_line_tag_undo(_BLOCK_LINE_TAGS, changes)
        self._update_toolbar_block_state()

    def _list_marker_text(self, tag: str, ordinal: int) -> str:
        return "•  " if tag == "bullet_item" else f"{ordinal}.  "

    def _apply_list_marker(self, line: int, marker_text: str) -> None:
        """Insert a visible bullet/number at the start of ``line``, tagged
        "list_marker" so :meth:`_extract_runs` can recognize and skip it —
        it's a display affordance only, not part of the exported content
        (which already renders as a real ``<ul>``/``<ol>`` from the
        bullet_item/ordered_item line tag alone).
        """
        self._strip_list_marker(line)
        line_start = f"{line}.0"
        self.text.insert(line_start, marker_text)
        marker_end = self.text.index(f"{line_start}+{len(marker_text)}c")
        self.text.tag_add("list_marker", line_start, marker_end)

    def _strip_list_marker(self, line: int) -> None:
        line_start, line_end = f"{line}.0", f"{line}.end"
        marker_range = self.text.tag_nextrange("list_marker", line_start, line_end)
        if marker_range and self.text.compare(marker_range[0], "==", line_start):
            self.text.delete(*marker_range)

    def _set_paragraph_normal(self) -> None:
        """Clear the block-level formatting (heading/citation/liste) of the
        selected (or current) lines, back to a plain paragraph — the
        counterpart to the H1-H4/citation/liste buttons, none of which can
        otherwise be turned back off once applied.
        """
        start_line, end_line = self._selected_lines()
        changes: list[tuple[str, str, set[str], set[str]]] = []
        for line in range(start_line, end_line + 1):
            line_start = f"{line}.0"
            before = set(self.text.tag_names(line_start)) & _BLOCK_LINE_TAGS
            if not before:
                continue
            if before & _LIST_LINE_TAGS:
                self._strip_list_marker(line)
            line_end = f"{line}.end"
            for existing in _BLOCK_LINE_TAGS:
                self.text.tag_remove(existing, line_start, line_end)
            changes.append((line_start, line_end, before, set()))
        self._push_line_tag_undo(_BLOCK_LINE_TAGS, changes)
        self._update_toolbar_block_state()

    def _push_line_tag_undo(
        self, tag_universe: set[str] | tuple[str, ...], changes: list[tuple[str, str, set[str], set[str]]]
    ) -> None:
        """Record one combined undo/redo entry covering every line touched
        by a single toolbar action (e.g. a multi-line selection turned into
        a blockquote), so undoing it is a single Ctrl+Z rather than one per
        line.
        """
        marked = [
            (self._mark_range(line_start, line_end), before, after)
            for line_start, line_end, before, after in changes
            if before != after
        ]
        if not marked:
            return

        def apply(use_before: bool) -> None:
            for (mark_start, mark_end), before, after in marked:
                for existing in tag_universe:
                    self.text.tag_remove(existing, mark_start, mark_end)
                for t in before if use_before else after:
                    self.text.tag_add(t, mark_start, mark_end)

        self._push_format_undo(lambda: apply(True), lambda: apply(False))

    def _new_tag(self, prefix: str) -> str:
        self._tag_counter += 1
        return f"{prefix}_{self._tag_counter}"

    def _resolve_color(self, color_name: str, fallback: str) -> str:
        """Resolve a Tk color (including a symbolic one like
        "SystemButtonFace") to "#rrggbb". Widget options accept symbolic
        names directly, but ``PhotoImage.put()`` (used to draw toolbar
        icons) does not, so this is how those icons match the real active
        theme instead of a hard-coded guess.
        """
        try:
            r, g, b = self.winfo_rgb(color_name)
        except tk.TclError:
            return fallback
        return f"#{r >> 8:02x}{g >> 8:02x}{b >> 8:02x}"

    def _insert_nbsp(self) -> None:
        self.text.insert("insert", NBSP)

    def _set_alignment(self, alignment: str) -> None:
        """Set paragraph alignment for the selected (or current) lines.

        Unlike :meth:`_toggle_line_tag` (which toggles a tag on/off), each
        alignment button always sets that exact alignment: clicking "Gauche"
        on an already-left paragraph is a no-op, not a toggle, since "left"
        is simply the absence of any ``_ALIGN_TAGS`` member.
        """
        start_line, end_line = self._selected_lines()
        changes: list[tuple[str, str, set[str], set[str]]] = []
        for line in range(start_line, end_line + 1):
            line_start, line_end = f"{line}.0", f"{line}.end"
            before = set(self.text.tag_names(line_start)) & set(_ALIGN_TAGS)
            for existing in _ALIGN_TAGS:
                self.text.tag_remove(existing, line_start, line_end)
            after: set[str] = set()
            if alignment != "left":
                self.text.tag_add(f"align_{alignment}", line_start, line_end)
                after = {f"align_{alignment}"}
            changes.append((line_start, line_end, before, after))
        self._push_line_tag_undo(_ALIGN_TAGS, changes)

    def _line_alignment(self, line: int) -> str:
        tags = set(self.text.tag_names(f"{line}.0"))
        for tag in _ALIGN_TAGS:
            if tag in tags:
                return tag.removeprefix("align_")
        return "left"

    def _tag_alignment(self, alignment: str, start: str, end: str) -> None:
        if alignment and alignment != "left":
            self.text.tag_add(f"align_{alignment}", start, end)

    def _insert_link(self) -> None:
        selected = self._selection_range()
        if selected is None:
            messagebox.showinfo("Lien", "Sélectionnez d'abord le texte du lien.")
            return
        href = simpledialog.askstring("Insérer un lien", "URL ou chemin interne (ex. /billets/index.html) :", parent=self)
        if not href:
            return
        start, end = selected
        tag = self._new_tag("link")
        self.link_data[tag] = href
        self.text.tag_add(tag, start, end)
        self.text.tag_add("link_style", start, end)

    def _insert_image(self) -> None:
        source = filedialog.askopenfilename(
            title="Choisir une image",
            filetypes=[("Images", "*.jpg *.jpeg *.png *.gif *.webp"), ("Tous les fichiers", "*.*")],
        )
        if not source:
            return
        alt = simpledialog.askstring("Image", "Texte alternatif (description de l'image) :", parent=self) or ""
        src_repr = copy_into_images_dir(Path(source), self.images_dir, self._doc_dir())
        self._insert_image_widget("insert", src_repr, alt)

    def _doc_dir(self) -> Path:
        """Directory Markdown image paths should be written/resolved
        relative to — the post/page's own file location, matching how the
        Pandoc/TEI/site-build pipeline resolves them. Falls back to the
        directory this unsaved document will be saved into (``pages_dir``
        or ``posts_dir`` depending on ``current_kind`` — they aren't
        guaranteed to be at the same depth, both are freely reconfigurable
        in the "Chemins" tab), so the relative path still lands correctly
        once saved.
        """
        if self.current_path is not None:
            return self.current_path.parent
        kind = self.current_kind or "page"
        return self.pages_dir if kind == "page" else self.posts_dir

    def _insert_image_widget(
        self,
        index: str,
        src: str,
        alt: str,
        *,
        width: int | None = None,
        height: int | None = None,
        align: str | None = None,
    ) -> ImageWidget:
        at = self.text.index(index)
        widget = ImageWidget(
            self.text,
            images_dir=self.images_dir,
            doc_dir=self._doc_dir(),
            src=src,
            alt=alt,
            width=width,
            height=height,
            align=align,
        )
        self.text.window_create(at, window=widget)
        # Purely cosmetic: center the widget in the editor regardless of the
        # image's own alignment (left/center/right), which only affects the
        # published page — Tk's Text has no floats, so that alignment can't
        # be simulated visually here anyway (see ImageWidget's docstring).
        line = at.split(".")[0]
        self.text.tag_add("image_center", f"{line}.0", f"{line}.end")
        return widget

    def _insert_table(self) -> None:
        rows = simpledialog.askinteger("Tableau", "Nombre de lignes (en-tête incluse) :", initialvalue=3, minvalue=2, parent=self)
        if not rows:
            return
        cols = simpledialog.askinteger("Tableau", "Nombre de colonnes :", initialvalue=2, minvalue=1, parent=self)
        if not cols:
            return

        header = Block(kind="table_row", children=[
            Block(kind="table_cell", runs=[InlineRun(text=f"Colonne {c + 1}")]) for c in range(cols)
        ])
        body_rows = [
            Block(kind="table_row", children=[Block(kind="table_cell", runs=[InlineRun(text="")]) for _ in range(cols)])
            for _ in range(rows - 1)
        ]
        table = Block(kind=TABLE, children=[header, *body_rows])
        table_text = blocks_to_markdown([table]).rstrip("\n")

        insert_at = self.text.index("insert")
        if self.text.get(f"{insert_at.split('.')[0]}.0", insert_at).strip():
            self.text.insert(insert_at, "\n")
            insert_at = self.text.index("insert")
        self.text.insert(insert_at, table_text + "\n")
        end_line = int(insert_at.split(".")[0]) + table_text.count("\n")
        for line in range(int(insert_at.split(".")[0]), end_line + 1):
            for existing in _BLOCK_LINE_TAGS:
                self.text.tag_remove(existing, f"{line}.0", f"{line}.end")
            self.text.tag_add("table_source", f"{line}.0", f"{line}.end")
