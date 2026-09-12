"""The footnotes side panel: build/refresh, per-note Text widgets,
insert/delete/renumber."""

from __future__ import annotations

from tkinter import font as tkfont, messagebox, simpledialog, ttk
import tkinter as tk
from bloggen.content.footnotes import (
    plan_footnote_renumbering,
    register_footnote,
    remove_footnote,
)
from bloggen.markdown.rich_text_model import InlineRun
from bloggen.ui.tooltip import add_tooltip

class NotesMixin:
    """The footnotes side panel: build/refresh, per-note Text widgets,
    insert/delete/renumber."""

    def _build_notes_panel(self, master: tk.Misc) -> None:
        ttk.Label(master, text="Notes de bas de page", foreground="#444444").pack(
            anchor="w", padx=4, pady=(2, 4)
        )

        container = ttk.Frame(master)
        container.pack(fill="both", expand=True)

        self._notes_canvas = tk.Canvas(container, height=90, highlightthickness=0)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=self._notes_canvas.yview)
        self.notes_list_frame = ttk.Frame(self._notes_canvas)
        self.notes_list_frame.bind(
            "<Configure>",
            lambda _e: self._notes_canvas.configure(scrollregion=self._notes_canvas.bbox("all")),
        )
        self._notes_canvas.create_window((0, 0), window=self.notes_list_frame, anchor="nw")
        self._notes_canvas.configure(yscrollcommand=scrollbar.set)
        self._notes_canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self._notes_canvas.bind("<Control-MouseWheel>", self._on_ctrl_mousewheel)
        self.notes_list_frame.bind("<Control-MouseWheel>", self._on_ctrl_mousewheel)

        self._refresh_notes_panel()

    def _refresh_notes_panel(self) -> None:
        # Pull whatever is currently displayed in each note's editor back
        # into footnote_definitions before tearing the rows down below —
        # otherwise an edit not yet synced (bold/italic/link just toggled,
        # or text just typed) would be silently discarded the next time a
        # note is added or removed elsewhere.
        self._sync_footnote_widgets_to_model()

        for child in self.notes_list_frame.winfo_children():
            child.destroy()
        self._footnote_text_widgets = {}
        self._footnote_rows = {}
        # Every note's Text widget is rebuilt from scratch below (and note
        # ids can be reassigned to a different note by renumbering after a
        # delete), so any quote-parity state tracked against the old
        # widgets no longer means anything — start each one fresh rather
        # than risk carrying a stale id's parity onto an unrelated note.
        self._note_quote_parity = {}

        if not self.footnote_definitions:
            ttk.Label(
                self.notes_list_frame, text="Aucune note pour l'instant.", foreground="#777777"
            ).pack(anchor="w", padx=4, pady=4)
            return

        for note_id in sorted(self.footnote_definitions, key=int):
            row = ttk.Frame(self.notes_list_frame)
            row.pack(fill="x", padx=4, pady=2)
            ttk.Label(row, text=f"[{note_id}]", width=4).pack(side="left", anchor="n")

            note_text = tk.Text(
                row, height=2, wrap="word", undo=True, font=self._notes_font
            )
            note_text.configure(inactiveselectbackground=note_text.cget("selectbackground"))
            self._configure_note_tags(note_text)
            self._populate_note_widget(note_text, self.footnote_definitions[note_id])
            note_text.pack(side="left", fill="x", expand=True, padx=4)
            note_text.bind("<Control-MouseWheel>", self._on_ctrl_mousewheel)
            note_text.bind(
                "<KeyRelease>",
                lambda e, nid=note_id, w=note_text: self._on_note_key_release(e, w, nid),
            )
            add_tooltip(
                note_text,
                "Texte de la note, modifiable directement ici (gras, italique, lien).",
            )

            buttons_frame = ttk.Frame(row)
            buttons_frame.pack(side="left", padx=(0, 4))
            bold_button = ttk.Button(
                buttons_frame, text="G", width=2,
                command=lambda w=note_text, nid=note_id: self._toggle_note_tag(w, nid, "bold"),
            )
            bold_button.pack(side="top")
            add_tooltip(bold_button, "Gras : met en gras le texte sélectionné dans la note.")
            italic_button = ttk.Button(
                buttons_frame, text="I", width=2,
                command=lambda w=note_text, nid=note_id: self._toggle_note_tag(w, nid, "italic"),
            )
            italic_button.pack(side="top")
            add_tooltip(italic_button, "Italique : met en italique le texte sélectionné dans la note.")
            link_button = ttk.Button(
                buttons_frame, text="Lien", width=4,
                command=lambda w=note_text, nid=note_id: self._insert_note_link(w, nid),
            )
            link_button.pack(side="top")
            add_tooltip(link_button, "Lien : transforme le texte sélectionné en lien hypertexte (interne ou externe).")

            delete_button = ttk.Button(row, text="Supprimer", command=lambda nid=note_id: self._delete_footnote(nid))
            delete_button.pack(side="left", anchor="n")
            add_tooltip(delete_button, "Supprime cette note (les appels de note existants ne sont pas retirés du texte).")

            self._footnote_text_widgets[note_id] = note_text
            self._footnote_rows[note_id] = row

    def _configure_note_tags(self, widget: tk.Text) -> None:
        base_font = tkfont.Font(font=widget.cget("font"))
        bold_font = base_font.copy()
        bold_font.configure(weight="bold")
        italic_font = base_font.copy()
        italic_font.configure(slant="italic")
        superscript_font = base_font.copy()
        superscript_font.configure(size=max(6, int(base_font.cget("size") * 0.75)))
        self._note_font_refs.extend([bold_font, italic_font, superscript_font])
        widget.tag_configure("bold", font=bold_font)
        widget.tag_configure("italic", font=italic_font)
        widget.tag_configure("underline", underline=True)
        widget.tag_configure("link_style", foreground="#1a73e8", underline=True)
        widget.tag_configure("superscript", offset=6, font=superscript_font)

    def _on_note_key_release(self, event: tk.Event, widget: tk.Text, note_id: str) -> None:
        """A note's own Text widget has no <<Modified>>-driven pipeline of
        its own — this is the only place typing inside it is observed, so
        it both applies the same French-typography-as-you-type
        autoformatting as the main body (see :meth:`bloggen.ui.
        content_editor.typography.TypographyMixin._apply_typing_autoformat`,
        which was previously only ever wired to the main editor's Text
        widget — notes got none of it) and keeps ``footnote_definitions``
        in sync with what's now on screen.
        """
        opening_next = self._note_quote_parity.get(note_id, True)
        self._note_quote_parity[note_id] = self._apply_typing_autoformat(
            widget, event.char, opening_next=opening_next
        )
        self.footnote_definitions[note_id] = self._extract_note_runs(widget)

    def _populate_note_widget(self, widget: tk.Text, runs: list[InlineRun]) -> None:
        widget.delete("1.0", "end")
        for run in runs:
            start = widget.index("end-1c")
            widget.insert("end", run.text)
            end = widget.index("end-1c")
            if run.bold:
                widget.tag_add("bold", start, end)
            if run.italic:
                widget.tag_add("italic", start, end)
            if run.underline:
                widget.tag_add("underline", start, end)
            if run.link_href:
                tag = self._new_tag("note_link")
                self._note_link_data[tag] = run.link_href
                widget.tag_add(tag, start, end)
                widget.tag_add("link_style", start, end)

    def _extract_note_runs(self, widget: tk.Text) -> list[InlineRun]:
        runs: list[InlineRun] = []
        active: set[str] = set()
        buffer = ""

        def flush() -> None:
            nonlocal buffer
            if not buffer:
                return
            link_tag = next((t for t in active if t in self._note_link_data), None)
            runs.append(
                InlineRun(
                    text=buffer,
                    bold="bold" in active,
                    italic="italic" in active,
                    underline="underline" in active,
                    link_href=self._note_link_data.get(link_tag) if link_tag else None,
                )
            )
            buffer = ""

        for key, value, _index in widget.dump("1.0", "end-1c", tag=True, text=True):
            if key == "tagon":
                flush()
                active.add(value)
            elif key == "tagoff":
                flush()
                active.discard(value)
            elif key == "text":
                buffer += value
        flush()
        return runs or [InlineRun(text="")]

    def _sync_footnote_widgets_to_model(self) -> None:
        for note_id, widget in self._footnote_text_widgets.items():
            if widget.winfo_exists():
                self.footnote_definitions[note_id] = self._extract_note_runs(widget)

    def _toggle_note_tag(self, widget: tk.Text, note_id: str, tag: str) -> None:
        ranges = widget.tag_ranges("sel")
        if not ranges:
            return
        start, end = str(ranges[0]), str(ranges[1])
        count = int(widget.count(start, end, "chars")[0])
        fully_tagged = all(
            tag in widget.tag_names(f"{start}+{i}c") for i in range(count)
        )
        if fully_tagged:
            widget.tag_remove(tag, start, end)
        else:
            widget.tag_add(tag, start, end)
        self.footnote_definitions[note_id] = self._extract_note_runs(widget)

    def _insert_note_link(self, widget: tk.Text, note_id: str) -> None:
        ranges = widget.tag_ranges("sel")
        if not ranges:
            messagebox.showinfo("Lien", "Sélectionnez d'abord le texte du lien.")
            return
        start, end = str(ranges[0]), str(ranges[1])
        href = simpledialog.askstring(
            "Insérer un lien", "URL ou chemin interne (ex. /billets/index.html) :", parent=self
        )
        if not href:
            widget.focus_set()
            return
        tag = self._new_tag("note_link")
        self._note_link_data[tag] = href
        widget.tag_add(tag, start, end)
        widget.tag_add("link_style", start, end)
        self.footnote_definitions[note_id] = self._extract_note_runs(widget)
        # The dialog just closing hands focus back to the editor's main
        # Toplevel (see window.py's _on_toplevel_focus_in), which would
        # otherwise redirect it to the main text widget — this note's own
        # editor is where the user was actually working and where editing
        # should resume.
        widget.focus_set()

    def _delete_footnote(self, note_id: str) -> None:
        # Drop the widget/row entries too, not just the model: otherwise
        # _refresh_notes_panel's leading _sync_footnote_widgets_to_model()
        # call reads this note's (still-alive, not-yet-destroyed) Text
        # widget and writes it straight back into footnote_definitions,
        # silently undoing the deletion — most visible on an empty note,
        # where "deleting" it just brings back an identical empty row.
        remove_footnote(self.footnote_definitions, note_id)
        self._footnote_text_widgets.pop(note_id, None)
        self._footnote_rows.pop(note_id, None)
        self._refresh_notes_panel()

    def _focus_footnote_row(self, note_id: str) -> None:
        row = self._footnote_rows.get(note_id)
        if row is None:
            return
        widget = self._footnote_text_widgets.get(note_id)
        if widget is not None and widget.winfo_exists():
            widget.focus_set()

    # -- typographie française -----------------------------------------------

    def _insert_footnote(self) -> None:
        note_text = simpledialog.askstring("Note de bas de page", "Texte de la note :", parent=self)
        if not note_text:
            return
        note_id = self._register_new_footnote(note_text)
        self._insert_footnote_marker(self.text.index("insert"), note_id)
        self._refresh_notes_panel()

    def _register_new_footnote(self, note_content: str | list[InlineRun]) -> str:
        """Allocate the next free footnote id and record its definition.
        Used by the "Note..." dialog (always plain text — a simple input
        box) — the only live path that inserts a real footnote reference
        while typing. The "((note))" shorthand is deliberately left as
        plain text instead (see :mod:`bloggen.markdown.note_shortcuts`) and
        never goes through this method in the editor; it is resolved to a
        footnote straight from Markdown, at preview/build time.
        """
        return register_footnote(self.footnote_definitions, note_content)

    def _insert_footnote_marker(self, index: str, note_id: str) -> str:
        """Insert a clickable "[id]" footnote marker at ``index`` (a
        concrete Tk index — not "insert"/"end" — so this works from both
        the append-only load path and cursor-relative insertion). Returns
        the index right after the inserted marker.
        """
        tag = self._new_tag("fnref")
        self.footnote_ref_data[tag] = note_id
        self.text.insert(index, f"[{note_id}]")
        end = self.text.index(f"{index}+{len(note_id) + 2}c")
        self.text.tag_add(tag, index, end)
        self.text.tag_add("footnote_style", index, end)
        self.text.tag_bind(tag, "<Button-1>", lambda _e, nid=note_id: self._focus_footnote_row(nid))
        return end

    def _renumber_footnotes(self) -> None:
        """Renumber every footnote to match its order of appearance in the
        text (1, 2, 3, ...), called right before save.

        Note ids are otherwise just "first free integer at the moment the
        note was created" (see :meth:`_register_new_footnote`), which
        drifts out of reading order the moment a human editor reorders
        paragraphs, deletes a note in the middle, or pastes a note-bearing
        paragraph somewhere else — exactly the kind of free-form editing
        this is meant to support. A definition with no marker left in the
        text (its "[n]" call was deleted by hand rather than through the
        notes panel) is kept, not silently dropped, but pushed after every
        referenced note so it never disturbs the reading-order numbering.
        """
        self._sync_footnote_widgets_to_model()

        seen: list[str] = []
        for key, value, _index in self.text.dump("1.0", "end-1c", tag=True):
            if key == "tagon" and value in self.footnote_ref_data:
                note_id = self.footnote_ref_data[value]
                if note_id not in seen:
                    seen.append(note_id)

        renumbering = plan_footnote_renumbering(self.footnote_definitions, seen)
        mapping = renumbering.mapping

        if not renumbering.changed:
            return

        def sort_key(index: str) -> tuple[int, int]:
            line, col = index.split(".")
            return (int(line), int(col))

        changed_ranges: list[tuple[str, str, str, str]] = []  # (old_tag, start, end, new_id)
        for tag, old_id in self.footnote_ref_data.items():
            new_id = mapping.get(old_id)
            if new_id is None or new_id == old_id:
                continue
            tag_ranges = self.text.tag_ranges(tag)
            for i in range(0, len(tag_ranges), 2):
                changed_ranges.append((tag, str(tag_ranges[i]), str(tag_ranges[i + 1]), new_id))

        # Rewrite from the last marker to the first: a renumbered marker's
        # text can change length (e.g. "[10]" -> "[3]"), which would shift
        # every index further on in the document out from under a
        # not-yet-processed range.
        changed_ranges.sort(key=lambda r: sort_key(r[1]), reverse=True)
        for old_tag, start, end, new_id in changed_ranges:
            self.text.delete(start, end)
            self._insert_footnote_marker(start, new_id)
            self.text.tag_delete(old_tag)
            self.footnote_ref_data.pop(old_tag, None)

        self.footnote_definitions = renumbering.definitions
        self._refresh_notes_panel()

    # -- extraction (Text widget -> Block model) ---------------------------
