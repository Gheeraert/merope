"""Clipboard paste handling: rich HTML (async, off the Tk main
thread), plain text, and images."""

from __future__ import annotations

import queue
import threading
from tkinter import messagebox
import tkinter as tk
from bloggen.markdown.html_paste_import import html_to_blocks
from bloggen.markdown.rich_text_model import (
    BLOCKQUOTE,
    BULLET_LIST,
    HEADING,
    ORDERED_LIST,
    PARAGRAPH,
    Block,
    InlineRun,
)
from bloggen.ui.clipboard_html import read_html_clipboard
from bloggen.ui.image_widget import ask_caption, grab_clipboard_image, save_clipboard_image

class PasteMixin:
    """Clipboard paste handling: rich HTML (async, off the Tk main
    thread), plain text, and images."""

    def _on_paste(self, _event: tk.Event) -> str | None:
        """Handle ``<<Paste>>``: if the clipboard holds HTML (as Word,
        Google Docs, or a browser puts there alongside plain text), convert
        and insert it with formatting instead of Tk's default plain-text
        paste. Falls through to that default (return ``None``) whenever
        rich paste isn't applicable, so a normal ``Ctrl+V`` never breaks —
        including plain-text clipboard content, which needs no special
        handling here: the "((note))" shorthand (see
        :mod:`bloggen.markdown.note_shortcuts`) is deliberately left
        literal until preview/build time, so it does not need converting
        on the way in.
        """
        if self._current_line_is_raw(self.text):
            return None
        self._before_delete_selection()
        if self._paste_image_from_clipboard():
            return "break"
        html = read_html_clipboard()
        if html:
            self._start_async_html_paste(html)
            return "break"
        return None

    def _start_async_html_paste(self, html: str) -> None:
        """Parse (and insert) pasted HTML off the Tk main thread.

        ``html_to_blocks`` can synchronously download a remote ``<img>``
        (up to 5s per image, see ``html_paste_import._download_image``),
        which would otherwise freeze the whole editor — with no visual
        indication why — for that long on every such paste. A Tk mark
        (rather than a plain index string) anchors the insertion point, so
        it still tracks the right place even if the user keeps typing
        elsewhere while the paste is in flight.
        """
        doc_dir = self._doc_dir()
        images_dir = self.images_dir
        mark = self._new_tag("paste_anchor")
        self.text.mark_set(mark, "insert")
        self.text.mark_gravity(mark, "left")
        self._set_paste_busy(True)

        result_queue: queue.Queue = queue.Queue(maxsize=1)

        def worker() -> None:
            try:
                result_queue.put(("ok", html_to_blocks(html, images_dir=images_dir, doc_dir=doc_dir)))
            except Exception:
                result_queue.put(("error", None))

        threading.Thread(target=worker, daemon=True).start()
        self._poll_async_html_paste(result_queue, mark)

    def _poll_async_html_paste(self, result_queue: "queue.Queue", mark: str) -> None:
        if not self.winfo_exists():
            return
        try:
            status, blocks = result_queue.get_nowait()
        except queue.Empty:
            self.after(50, lambda: self._poll_async_html_paste(result_queue, mark))
            return

        self._set_paste_busy(False)
        self.text.mark_set("insert", mark)
        self.text.mark_unset(mark)

        if status == "ok" and blocks:
            self._insert_pasted_blocks_at_cursor(blocks)
            return

        # Parsing failed or produced nothing usable: fall back to the
        # clipboard's own plain text, the same as an ordinary Ctrl+V would
        # have done (see the plain-text branch of _on_paste).
        try:
            plain = self.clipboard_get()
        except tk.TclError:
            return
        self.text.insert("insert", plain)

    def _set_paste_busy(self, busy: bool) -> None:
        self.text.configure(cursor="watch" if busy else "")

    def _insert_pasted_blocks_at_cursor(self, blocks: list[Block]) -> None:
        """Cursor-relative counterpart to :meth:`_insert_block`/
        :meth:`_insert_runs` (which always append at "end", for whole-
        document loading). Deliberately separate rather than parametrized:
        this session already found two subtle Tk index bugs in the
        append-only path, so a small amount of duplication here is worth
        not risking that already-tested code. Only PARAGRAPH/HEADING/
        BLOCKQUOTE/BULLET_LIST/ORDERED_LIST are handled: the HTML paste
        importer never produces TABLE/VERBATIM/FOOTNOTE_DEFINITION blocks.
        """
        for index, block in enumerate(blocks):
            if index > 0:
                self.text.insert("insert", "\n\n")
            self._insert_block_at_cursor(block)

    def _insert_block_at_cursor(self, block: Block) -> None:
        if block.kind == PARAGRAPH:
            start = self.text.index("insert")
            self._insert_runs_at_cursor(block.runs)
            self.text.tag_add("plain", start, self.text.index("insert"))
            self._tag_alignment(block.alignment, start, self.text.index("insert"))
        elif block.kind == HEADING:
            start = self.text.index("insert")
            self._insert_runs_at_cursor(block.runs)
            self.text.tag_add(f"h{block.level or 1}", start, self.text.index("insert"))
        elif block.kind == BLOCKQUOTE:
            start = self.text.index("insert")
            self._insert_runs_at_cursor(block.runs)
            self.text.tag_add("blockquote", start, self.text.index("insert"))
            self._tag_alignment(block.alignment, start, self.text.index("insert"))
        elif block.kind in (BULLET_LIST, ORDERED_LIST):
            tag = "bullet_item" if block.kind == BULLET_LIST else "ordered_item"
            for i, item in enumerate(block.children):
                if i > 0:
                    self.text.insert("insert", "\n")
                start = self.text.index("insert")
                self.text.insert("insert", self._list_marker_text(tag, i + 1))
                self.text.tag_add("list_marker", start, self.text.index("insert"))
                self._insert_runs_at_cursor(item.runs)
                self.text.tag_add(tag, start, self.text.index("insert"))

    def _insert_runs_at_cursor(self, runs: list[InlineRun]) -> None:
        for run in runs:
            if run.image_src is not None:
                width = int(run.image_width) if run.image_width else None
                height = int(run.image_height) if run.image_height else None
                self._insert_image_widget(
                    "insert",
                    run.image_src,
                    run.image_alt or "",
                    width=width,
                    height=height,
                    align=run.image_align,
                )
                continue
            if run.footnote_ref is not None:
                index = self.text.index("insert")
                end = self._insert_footnote_marker(index, run.footnote_ref)
                self.text.mark_set("insert", end)
                continue

            start = self.text.index("insert")
            self.text.insert("insert", run.text)
            end = self.text.index("insert")
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

    # -- file list ----------------------------------------------------------

    def _paste_image_from_clipboard(self) -> bool:
        """Insert whatever image is on the clipboard at the cursor, sized
        for immediate viewing and centered by default (unlike a file-based
        insert, which keeps its natural position in the text flow).
        ``ImageWidget`` still lets the user recenter/resize afterward.
        """
        image = grab_clipboard_image()
        if image is None:
            return False
        size_var = tk.StringVar(value="petit")
        caption = (
            ask_caption(
                self,
                "Image collée",
                "Légende (affichée sous l'image sur le site publié ; laissez vide pour ne pas en mettre) :",
                size_var=size_var,
            )
            or ""
        )
        src = save_clipboard_image(image, self.images_dir, self._doc_dir())
        self._insert_image_widget("insert", src, caption, align="center", size_preset=size_var.get())
        return True

    def _paste_image_button(self) -> None:
        if not self._paste_image_from_clipboard():
            messagebox.showinfo("Coller une image", "Le presse-papiers ne contient pas d'image.")

    def _paste_as_plain_text(self) -> None:
        """Force a plain-text paste, discarding any HTML formatting the
        clipboard might also carry (bold/links/tables from Word, Google
        Docs, a browser...) — the counterpart to :meth:`_on_paste`'s
        automatic rich paste, for pasting content whose source formatting
        should not carry over.
        """
        if self._current_line_is_raw(self.text):
            return
        try:
            plain = self.clipboard_get()
        except tk.TclError:
            return
        if not plain:
            return
        self._insert_runs_at_cursor([InlineRun(text=plain)])

    def _shortcut_paste_plain(self, _event: tk.Event) -> str:
        self._paste_as_plain_text()
        return "break"
