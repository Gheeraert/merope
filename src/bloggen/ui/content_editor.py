"""WYSIWYG content editor: create/edit pages and posts as real Markdown files.

The Tk ``Text`` widget only ever holds display text plus tags; all Markdown
knowledge lives in :mod:`bloggen.markdown.rich_text_model`,
:mod:`bloggen.markdown.rich_text_export` and
:mod:`bloggen.markdown.rich_text_import`. This module is the thin (and
therefore not unit-tested) bridge between the two: it walks the widget's
tags to build a ``Block`` list on save, and walks a ``Block`` list to
populate the widget on load.
"""

from __future__ import annotations

import shutil
from datetime import date
from pathlib import Path
from tkinter import messagebox, filedialog, simpledialog, ttk
import tkinter as tk

from bloggen.content.metadata import is_valid_iso_date
from bloggen.content.writer import (
    default_filename,
    read_content_file,
    scan_existing_slugs,
    suggest_slug,
    write_content_file,
)
from bloggen.markdown.front_matter import parse_front_matter
from bloggen.markdown.rich_text_export import blocks_to_markdown
from bloggen.markdown.rich_text_import import markdown_to_blocks, parse_table_lines
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
    plain_text,
)
from bloggen.ui.tooltip import add_tooltip

_HEADING_TAGS = ("h1", "h2", "h3", "h4")
_BLOCK_LINE_TAGS = {"h1", "h2", "h3", "h4", "blockquote", "bullet_item", "ordered_item", "table_source", "verbatim"}
_CHAR_TAGS = ("bold", "italic", "strike")


class ContentMetadataDialog(simpledialog.Dialog):
    """Small YAML-front-matter form, in the spirit of ``MenuLinkDialog``."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        kind: str,
        initial: dict[str, str],
        existing_slugs: set[str],
        slugify_mode: str,
    ) -> None:
        self.kind = kind
        self.initial = initial
        self.existing_slugs = existing_slugs
        self.slugify_mode = slugify_mode
        self.result: dict[str, str] | None = None
        title = "Métadonnées du billet" if kind == "post" else "Métadonnées de la page"
        super().__init__(parent, title)

    def body(self, master: tk.Misc) -> tk.Widget:
        self.title_var = tk.StringVar(value=self.initial.get("title", ""))
        self.slug_var = tk.StringVar(value=self.initial.get("slug", ""))
        self.date_var = tk.StringVar(value=self.initial.get("date", date.today().isoformat()))
        self.author_var = tk.StringVar(value=self.initial.get("author", ""))
        self.description_var = tk.StringVar(value=self.initial.get("description", ""))
        self.layout_var = tk.StringVar(value=self.initial.get("layout", ""))
        self.draft_var = tk.BooleanVar(value=self.initial.get("draft", "false") == "true")
        self._slug_auto = not self.initial.get("slug")

        row = 0
        ttk.Label(master, text="Type").grid(row=row, column=0, sticky="w", padx=4, pady=4)
        ttk.Label(master, text="Billet" if self.kind == "post" else "Page").grid(
            row=row, column=1, sticky="w", padx=4, pady=4
        )
        row += 1

        ttk.Label(master, text="Titre").grid(row=row, column=0, sticky="w", padx=4, pady=4)
        title_entry = ttk.Entry(master, textvariable=self.title_var, width=40)
        title_entry.grid(row=row, column=1, sticky="ew", padx=4, pady=4)
        add_tooltip(title_entry, "Titre affiché en haut de la page/du billet. Obligatoire.")
        title_entry.bind("<KeyRelease>", self._on_title_changed)
        row += 1

        ttk.Label(master, text="Slug (URL)").grid(row=row, column=0, sticky="w", padx=4, pady=4)
        slug_entry = ttk.Entry(master, textvariable=self.slug_var, width=40)
        slug_entry.grid(row=row, column=1, sticky="ew", padx=4, pady=4)
        add_tooltip(
            slug_entry,
            "Identifiant d'URL, suggéré automatiquement à partir du titre. "
            "Modifiez-le librement, mais il doit rester unique.\nExemple : premier-billet",
        )
        slug_entry.bind("<KeyRelease>", lambda _e: setattr(self, "_slug_auto", False))
        row += 1

        if self.kind == "post":
            ttk.Label(master, text="Date (AAAA-MM-JJ)").grid(row=row, column=0, sticky="w", padx=4, pady=4)
            date_entry = ttk.Entry(master, textvariable=self.date_var, width=20)
            date_entry.grid(row=row, column=1, sticky="w", padx=4, pady=4)
            add_tooltip(date_entry, "Date de publication du billet. Obligatoire.\nExemple : 2026-08-08")
            row += 1

        ttk.Label(master, text="Auteur").grid(row=row, column=0, sticky="w", padx=4, pady=4)
        ttk.Entry(master, textvariable=self.author_var, width=40).grid(
            row=row, column=1, sticky="ew", padx=4, pady=4
        )
        row += 1

        ttk.Label(master, text="Description").grid(row=row, column=0, sticky="w", padx=4, pady=4)
        description_entry = ttk.Entry(master, textvariable=self.description_var, width=40)
        description_entry.grid(row=row, column=1, sticky="ew", padx=4, pady=4)
        add_tooltip(description_entry, "Résumé court utilisé pour le référencement (SEO). Optionnel.")
        row += 1

        ttk.Label(master, text="Layout").grid(row=row, column=0, sticky="w", padx=4, pady=4)
        layout_entry = ttk.Entry(master, textvariable=self.layout_var, width=40)
        layout_entry.grid(row=row, column=1, sticky="ew", padx=4, pady=4)
        add_tooltip(
            layout_entry,
            "Gabarit HTML à utiliser. Laissez vide pour utiliser le gabarit par défaut "
            "défini dans l'onglet Contenus.",
        )
        row += 1

        draft_cb = ttk.Checkbutton(master, text="Brouillon (ne pas publier)", variable=self.draft_var)
        draft_cb.grid(row=row, column=0, columnspan=2, sticky="w", padx=4, pady=4)
        add_tooltip(draft_cb, "Si coché, ce contenu est ignoré lors de la génération du site.")

        master.grid_columnconfigure(1, weight=1)
        return title_entry

    def _on_title_changed(self, _event: tk.Event) -> None:
        if self._slug_auto:
            others = self.existing_slugs - {self.initial.get("slug", "")}
            self.slug_var.set(suggest_slug(self.title_var.get(), mode=self.slugify_mode, existing=others))

    def validate(self) -> bool:
        if not self.title_var.get().strip():
            messagebox.showerror("Métadonnées", "Le titre est obligatoire.", parent=self)
            return False
        slug = self.slug_var.get().strip()
        if not slug:
            messagebox.showerror("Métadonnées", "Le slug est obligatoire.", parent=self)
            return False
        others = self.existing_slugs - {self.initial.get("slug", "")}
        if slug in others:
            messagebox.showerror("Métadonnées", f"Le slug « {slug} » est déjà utilisé.", parent=self)
            return False
        if self.kind == "post":
            if not is_valid_iso_date(self.date_var.get().strip()):
                messagebox.showerror(
                    "Métadonnées", "La date doit être au format AAAA-MM-JJ.", parent=self
                )
                return False
        return True

    def apply(self) -> None:
        metadata: dict[str, str] = {
            "title": self.title_var.get().strip(),
            "slug": self.slug_var.get().strip(),
            "type": self.kind,
        }
        if self.kind == "post":
            metadata["date"] = self.date_var.get().strip()
        if self.author_var.get().strip():
            metadata["author"] = self.author_var.get().strip()
        if self.description_var.get().strip():
            metadata["description"] = self.description_var.get().strip()
        if self.layout_var.get().strip():
            metadata["layout"] = self.layout_var.get().strip()
        if self.draft_var.get():
            metadata["draft"] = "true"
        self.result = metadata


class ContentEditorWindow(tk.Toplevel):
    def __init__(
        self,
        master: tk.Misc,
        *,
        pages_dir: Path,
        posts_dir: Path,
        images_dir: Path,
        slugify_mode: str,
    ) -> None:
        super().__init__(master)
        self.title("Éditeur de contenu")
        self.geometry("1200x760")

        self.pages_dir = Path(pages_dir)
        self.posts_dir = Path(posts_dir)
        self.images_dir = Path(images_dir)
        self.slugify_mode = slugify_mode

        self.current_path: Path | None = None
        self.current_kind: str | None = None
        self.metadata: dict[str, str] = {}
        self.footnote_definitions: dict[str, str] = {}
        self.link_data: dict[str, str] = {}
        self.image_data: dict[str, tuple[str, str]] = {}
        self.footnote_ref_data: dict[str, str] = {}
        self._tag_counter = 0
        self._file_entries: list[tuple[str, Path]] = []  # (kind, path)

        self._build_ui()
        self._refresh_file_list()

    # -- layout -----------------------------------------------------------

    def _build_ui(self) -> None:
        paned = ttk.PanedWindow(self, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=8, pady=8)

        left = ttk.Frame(paned)
        paned.add(left, weight=1)
        self._build_file_list(left)

        right = ttk.Frame(paned)
        paned.add(right, weight=4)
        self._build_editor(right)

    def _build_file_list(self, master: tk.Misc) -> None:
        ttk.Label(
            master,
            text="Pages et billets existants. Double-cliquez pour ouvrir.",
            wraplength=220,
            justify="left",
        ).pack(fill="x", pady=(0, 6))

        self.file_listbox = tk.Listbox(master, exportselection=False)
        self.file_listbox.pack(fill="both", expand=True)
        self.file_listbox.bind("<Double-Button-1>", lambda _e: self._open_selected())

        buttons = [
            ("Nouvelle page", lambda: self._new_document("page"), "Crée une page vierge."),
            ("Nouveau billet", lambda: self._new_document("post"), "Crée un billet vierge."),
            ("Ouvrir", self._open_selected, "Ouvre le fichier sélectionné dans la liste."),
            ("Supprimer", self._delete_selected, "Supprime définitivement le fichier sélectionné."),
            ("Actualiser", self._refresh_file_list, "Recharge la liste depuis le disque."),
        ]
        for label, command, tip in buttons:
            button = ttk.Button(master, text=label, command=command)
            button.pack(fill="x", pady=2)
            add_tooltip(button, tip)

    def _build_editor(self, master: tk.Misc) -> None:
        toolbar = ttk.Frame(master)
        toolbar.pack(fill="x", pady=(0, 4))

        char_buttons = [
            ("G", lambda: self._toggle_char_tag("bold"), "Gras"),
            ("I", lambda: self._toggle_char_tag("italic"), "Italique"),
            ("S", lambda: self._toggle_char_tag("strike"), "Barré"),
        ]
        for label, command, tip in char_buttons:
            b = ttk.Button(toolbar, text=label, width=3, command=command)
            b.pack(side="left", padx=1)
            add_tooltip(b, tip)

        ttk.Separator(toolbar, orient="vertical").pack(side="left", fill="y", padx=4)

        for level in range(1, 5):
            b = ttk.Button(toolbar, text=f"H{level}", width=3, command=lambda lv=level: self._toggle_heading(lv))
            b.pack(side="left", padx=1)
            add_tooltip(b, f"Titre de niveau {level} pour la ligne courante.")

        ttk.Separator(toolbar, orient="vertical").pack(side="left", fill="y", padx=4)

        block_buttons = [
            ("Citation", lambda: self._toggle_line_tag("blockquote"), "Transforme la ligne en citation."),
            ("Liste à puces", lambda: self._toggle_line_tag("bullet_item"), "Transforme la ligne en élément de liste à puces."),
            ("Liste numérotée", lambda: self._toggle_line_tag("ordered_item"), "Transforme la ligne en élément de liste numérotée."),
        ]
        for label, command, tip in block_buttons:
            b = ttk.Button(toolbar, text=label, command=command)
            b.pack(side="left", padx=1)
            add_tooltip(b, tip)

        ttk.Separator(toolbar, orient="vertical").pack(side="left", fill="y", padx=4)

        insert_buttons = [
            ("Lien...", self._insert_link, "Transforme la sélection en lien hypertexte."),
            ("Image...", self._insert_image, "Insère une image depuis un fichier existant."),
            ("Tableau...", self._insert_table, "Insère un tableau simple."),
            ("Note...", self._insert_footnote, "Insère une note de bas de page."),
        ]
        for label, command, tip in insert_buttons:
            b = ttk.Button(toolbar, text=label, command=command)
            b.pack(side="left", padx=1)
            add_tooltip(b, tip)

        ttk.Separator(toolbar, orient="vertical").pack(side="left", fill="y", padx=4)

        meta_button = ttk.Button(toolbar, text="Métadonnées...", command=self._edit_metadata)
        meta_button.pack(side="left", padx=1)
        add_tooltip(meta_button, "Titre, slug, date, auteur, description...")

        save_button = ttk.Button(toolbar, text="Enregistrer", command=self._save)
        save_button.pack(side="right", padx=1)
        add_tooltip(save_button, "Écrit ce contenu dans son fichier Markdown.")

        self.text = tk.Text(master, wrap="word", undo=True, font=("TkDefaultFont", 11))
        self.text.pack(fill="both", expand=True)
        self._configure_tags()

    def _configure_tags(self) -> None:
        text = self.text
        text.tag_configure("h1", font=("TkDefaultFont", 20, "bold"))
        text.tag_configure("h2", font=("TkDefaultFont", 17, "bold"))
        text.tag_configure("h3", font=("TkDefaultFont", 14, "bold"))
        text.tag_configure("h4", font=("TkDefaultFont", 12, "bold"))
        text.tag_configure("blockquote", lmargin1=24, lmargin2=24, foreground="#555555")
        text.tag_configure("bullet_item", lmargin1=20, lmargin2=32)
        text.tag_configure("ordered_item", lmargin1=20, lmargin2=32)
        text.tag_configure("table_source", font=("Courier New", 10), background="#f5f5f5")
        text.tag_configure("verbatim", font=("Courier New", 10), background="#fff3cd")
        text.tag_configure("bold", font=("TkDefaultFont", 11, "bold"))
        text.tag_configure("italic", font=("TkDefaultFont", 11, "italic"))
        text.tag_configure("strike", overstrike=True)
        text.tag_configure("link_style", foreground="#1a73e8", underline=True)
        text.tag_configure("image_style", background="#e8f0fe")
        text.tag_configure("footnote_style", foreground="#1a73e8")
        for tag in ("bold", "italic", "strike", "link_style", "image_style", "footnote_style"):
            text.tag_raise(tag)

    # -- file list ----------------------------------------------------------

    def _refresh_file_list(self) -> None:
        self.file_listbox.delete(0, "end")
        self._file_entries = []
        entries: list[tuple[str, str, Path]] = []  # (kind, title, path)
        for kind, directory in (("page", self.pages_dir), ("post", self.posts_dir)):
            if not directory.exists():
                continue
            for path in sorted(directory.rglob("*.md")):
                try:
                    result = parse_front_matter(path.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    entries.append((kind, f"(invalide) {path.name}", path))
                    continue
                title = result.metadata.get("title") or path.stem
                entries.append((kind, title, path))

        for kind, title, path in entries:
            label = "Page" if kind == "page" else "Billet"
            self.file_listbox.insert("end", f"[{label}] {title}")
            self._file_entries.append((kind, path))

    def _selected_entry(self) -> tuple[str, Path] | None:
        selection = self.file_listbox.curselection()
        if not selection:
            return None
        return self._file_entries[selection[0]]

    def _open_selected(self) -> None:
        entry = self._selected_entry()
        if entry is None:
            return
        kind, path = entry
        metadata, body = read_content_file(path)
        blocks = markdown_to_blocks(body)
        self._populate_from_blocks(blocks)
        self.metadata = metadata
        self.current_kind = kind
        self.current_path = path

    def _delete_selected(self) -> None:
        entry = self._selected_entry()
        if entry is None:
            return
        _kind, path = entry
        if not messagebox.askyesno("Supprimer", f"Supprimer définitivement {path.name} ?"):
            return
        path.unlink(missing_ok=True)
        if self.current_path == path:
            self._new_document(self.current_kind or "page")
        self._refresh_file_list()

    def _new_document(self, kind: str) -> None:
        self.text.delete("1.0", "end")
        self.footnote_definitions.clear()
        self.link_data.clear()
        self.image_data.clear()
        self.footnote_ref_data.clear()
        self.metadata = {}
        self.current_kind = kind
        self.current_path = None

    # -- metadata -------------------------------------------------------------

    def _existing_slugs(self) -> set[str]:
        return scan_existing_slugs(self.pages_dir, self.posts_dir)

    def _edit_metadata(self) -> dict[str, str] | None:
        kind = self.current_kind or "page"
        dialog = ContentMetadataDialog(
            self,
            kind=kind,
            initial=self.metadata,
            existing_slugs=self._existing_slugs(),
            slugify_mode=self.slugify_mode,
        )
        if dialog.result is not None:
            self.metadata = dialog.result
            self.current_kind = kind
        return dialog.result

    # -- toolbar actions --------------------------------------------------

    def _selection_range(self) -> tuple[str, str] | None:
        ranges = self.text.tag_ranges("sel")
        if not ranges:
            return None
        return str(ranges[0]), str(ranges[1])

    def _toggle_char_tag(self, tag: str) -> None:
        selected = self._selection_range()
        if selected is None:
            return
        start, end = selected
        fully_tagged = all(tag in self.text.tag_names(idx) for idx in self._char_indices(start, end))
        if fully_tagged:
            self.text.tag_remove(tag, start, end)
        else:
            self.text.tag_add(tag, start, end)

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

    def _toggle_line_tag(self, tag: str) -> None:
        start_line, end_line = self._selected_lines()
        for line in range(start_line, end_line + 1):
            line_start, line_end = f"{line}.0", f"{line}.end"
            already = tag in self.text.tag_names(line_start)
            for existing in _BLOCK_LINE_TAGS:
                self.text.tag_remove(existing, line_start, line_end)
            if not already:
                self.text.tag_add(tag, line_start, line_end)

    def _new_tag(self, prefix: str) -> str:
        self._tag_counter += 1
        return f"{prefix}_{self._tag_counter}"

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

        self.images_dir.mkdir(parents=True, exist_ok=True)
        destination = self.images_dir / Path(source).name
        counter = 2
        while destination.exists() and Path(source).resolve() != destination.resolve():
            destination = self.images_dir / f"{Path(source).stem}-{counter}{Path(source).suffix}"
            counter += 1
        if not destination.exists():
            shutil.copyfile(source, destination)

        try:
            src_repr = destination.relative_to(self.images_dir.parent).as_posix()
        except ValueError:
            src_repr = destination.as_posix()

        tag = self._new_tag("img")
        self.image_data[tag] = (src_repr, alt)
        insert_at = self.text.index("insert")
        self.text.insert(insert_at, f"[image: {alt or destination.name}]")
        end_at = self.text.index("insert")
        self.text.tag_add(tag, insert_at, end_at)
        self.text.tag_add("image_style", insert_at, end_at)

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

    def _insert_footnote(self) -> None:
        note_text = simpledialog.askstring("Note de bas de page", "Texte de la note :", parent=self)
        if not note_text:
            return
        next_id = 1
        while str(next_id) in self.footnote_definitions:
            next_id += 1
        note_id = str(next_id)
        self.footnote_definitions[note_id] = note_text

        tag = self._new_tag("fnref")
        self.footnote_ref_data[tag] = note_id
        insert_at = self.text.index("insert")
        self.text.insert(insert_at, f"[{note_id}]")
        end_at = self.text.index("insert")
        self.text.tag_add(tag, insert_at, end_at)
        self.text.tag_add("footnote_style", insert_at, end_at)

    # -- extraction (Text widget -> Block model) ---------------------------

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

    def _extract_runs(self, start: str, end: str) -> list[InlineRun]:
        runs: list[InlineRun] = []
        active: set[str] = set()
        buffer = ""

        def flush() -> None:
            nonlocal buffer
            if not buffer:
                return
            image_tag = next((t for t in active if t in self.image_data), None)
            fnref_tag = next((t for t in active if t in self.footnote_ref_data), None)
            link_tag = next((t for t in active if t in self.link_data), None)
            if image_tag:
                src, alt = self.image_data[image_tag]
                runs.append(InlineRun(image_src=src, image_alt=alt))
            elif fnref_tag:
                runs.append(InlineRun(footnote_ref=self.footnote_ref_data[fnref_tag]))
            else:
                runs.append(
                    InlineRun(
                        text=buffer,
                        bold="bold" in active,
                        italic="italic" in active,
                        strikethrough="strike" in active,
                        link_href=self.link_data.get(link_tag) if link_tag else None,
                    )
                )
            buffer = ""

        for key, value, _index in self.text.dump(start, end, tag=True, text=True):
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
            if line_text.strip() == "":
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

        for note_id in sorted(self.footnote_definitions, key=int):
            blocks.append(
                Block(
                    kind=FOOTNOTE_DEFINITION,
                    footnote_id=note_id,
                    runs=[InlineRun(text=self.footnote_definitions[note_id])],
                )
            )
        return blocks

    def _build_group_block(self, group_type: str | None, start_line: int, end_line: int) -> Block:
        if group_type in ("h1", "h2", "h3", "h4"):
            return Block(kind=HEADING, level=int(group_type[1]), runs=self._extract_runs(f"{start_line}.0", f"{start_line}.end"))

        if group_type == "blockquote":
            runs = self._merge_lines_runs(start_line, end_line)
            return Block(kind=BLOCKQUOTE, runs=runs)

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
        return Block(kind=PARAGRAPH, runs=runs)

    def _merge_lines_runs(self, start_line: int, end_line: int) -> list[InlineRun]:
        runs: list[InlineRun] = []
        for i, line in enumerate(range(start_line, end_line + 1)):
            if i > 0:
                runs.append(InlineRun(text=" "))
            runs.extend(self._extract_runs(f"{line}.0", f"{line}.end"))
        return runs

    # -- population (Block model -> Text widget) ---------------------------

    def _populate_from_blocks(self, blocks: list[Block]) -> None:
        self.text.delete("1.0", "end")
        self.footnote_definitions.clear()
        self.link_data.clear()
        self.image_data.clear()
        self.footnote_ref_data.clear()

        body_blocks = [b for b in blocks if b.kind != FOOTNOTE_DEFINITION]
        for block in blocks:
            if block.kind == FOOTNOTE_DEFINITION and block.footnote_id:
                self.footnote_definitions[block.footnote_id] = plain_text(block.runs)

        for index, block in enumerate(body_blocks):
            if index > 0:
                self.text.insert("end", "\n\n")
            self._insert_block(block)

    def _insert_block(self, block: Block) -> None:
        if block.kind == PARAGRAPH:
            start = self.text.index("end-1c")
            self._insert_runs(block.runs)
            self.text.tag_add("plain", start, self.text.index("end-1c"))
        elif block.kind == HEADING:
            start = self.text.index("end-1c")
            self._insert_runs(block.runs)
            self.text.tag_add(f"h{block.level or 1}", start, self.text.index("end-1c"))
        elif block.kind == BLOCKQUOTE:
            start = self.text.index("end-1c")
            self._insert_runs(block.runs)
            self.text.tag_add("blockquote", start, self.text.index("end-1c"))
        elif block.kind in (BULLET_LIST, ORDERED_LIST):
            tag = "bullet_item" if block.kind == BULLET_LIST else "ordered_item"
            for i, item in enumerate(block.children):
                if i > 0:
                    self.text.insert("end", "\n")
                start = self.text.index("end-1c")
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
                tag = self._new_tag("img")
                self.image_data[tag] = (run.image_src, run.image_alt or "")
                start = self.text.index("end-1c")
                self.text.insert("end", f"[image: {run.image_alt or run.image_src}]")
                self.text.tag_add(tag, start, self.text.index("end-1c"))
                self.text.tag_add("image_style", start, self.text.index("end-1c"))
                continue
            if run.footnote_ref is not None:
                tag = self._new_tag("fnref")
                self.footnote_ref_data[tag] = run.footnote_ref
                start = self.text.index("end-1c")
                self.text.insert("end", f"[{run.footnote_ref}]")
                self.text.tag_add(tag, start, self.text.index("end-1c"))
                self.text.tag_add("footnote_style", start, self.text.index("end-1c"))
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
            if run.link_href:
                tag = self._new_tag("link")
                self.link_data[tag] = run.link_href
                self.text.tag_add(tag, start, end)
                self.text.tag_add("link_style", start, end)

    # -- save ---------------------------------------------------------------

    def _save(self) -> None:
        if not self.metadata.get("title") or not self.metadata.get("slug"):
            if self._edit_metadata() is None:
                return

        kind = self.current_kind or "page"
        directory = self.pages_dir if kind == "page" else self.posts_dir

        blocks = self.extract_blocks()
        body = blocks_to_markdown(blocks)

        if self.current_path is not None:
            filename = self.current_path.name
            target_dir = self.current_path.parent
        else:
            filename = default_filename(kind, self.metadata["slug"], date=self.metadata.get("date"))
            target_dir = directory

        try:
            written = write_content_file(target_dir, filename, self.metadata, body)
        except OSError as exc:
            messagebox.showerror("Enregistrement", f"Impossible d'écrire le fichier :\n{exc}")
            return

        self.current_path = written
        self._refresh_file_list()
        messagebox.showinfo("Enregistrement", f"Contenu enregistré : {written}")
