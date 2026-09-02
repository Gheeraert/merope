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

import re
from datetime import date
from pathlib import Path
from tkinter import font as tkfont, messagebox, filedialog, simpledialog, ttk
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
from bloggen.markdown.html_paste_import import html_to_blocks
from bloggen.markdown.note_shortcuts import (
    DOUBLE_PAREN_NOTE_RE,
    convert_double_paren_notes_in_blocks,
    split_double_paren_notes,
)
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
)
from bloggen.markdown.typography import (
    CENTURY_RE,
    CLOSING_GUILLEMET,
    DOUBLE_PUNCTUATION,
    NBSP,
    OPENING_GUILLEMET,
    PAGE_ABBREVIATION_TYPED_RE,
    convert_curly_quotes_to_guillemets,
    convert_straight_quotes_stateful,
    fix_double_punctuation_spacing,
    fix_guillemet_spacing,
    fix_page_number_spacing,
    is_valid_century_ordinal,
)
from bloggen.ui import toolbar_icons
from bloggen.ui.clipboard_html import read_html_clipboard
from bloggen.ui.image_widget import ImageWidget, copy_into_images_dir
from bloggen.ui.tooltip import add_tooltip

_HEADING_TAGS = ("h1", "h2", "h3", "h4")
_BLOCK_LINE_TAGS = {"h1", "h2", "h3", "h4", "blockquote", "bullet_item", "ordered_item", "table_source", "verbatim"}
_CHAR_TAGS = ("bold", "italic", "strike", "superscript")
# Alignment is orthogonal to _BLOCK_LINE_TAGS (a paragraph or blockquote line
# can carry both its block-type tag and one of these). Only meaningful for
# PARAGRAPH/BLOCKQUOTE on export (see bloggen.markdown.paragraph_alignment).
_ALIGN_TAGS = ("align_left", "align_center", "align_right", "align_justify")
_TYPOGRAPHY_TRIGGER_CHARS = '"' + OPENING_GUILLEMET + CLOSING_GUILLEMET + DOUBLE_PUNCTUATION
# Same shorthand as bloggen.markdown.note_shortcuts.DOUBLE_PAREN_NOTE_RE, but
# anchored to the end of the string: used to detect the pattern right as its
# closing "))" is typed, one line-prefix at a time.
_DOUBLE_PAREN_NOTE_TYPED_RE = re.compile(r"\(\((.+?)\)\)$")
# Name of the sibling folder (next to the .md file itself) where each save
# archives the previous on-disk version before overwriting it.
_VERSIONS_DIRNAME = ".versions"
_VERSION_FILENAME_RE_TEMPLATE = r"^{stem}\.v(\d+){suffix}$"


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


class FindReplaceDialog(tk.Toplevel):
    """Non-modal Ctrl+F / Ctrl+H dialog, kept open across repeated searches
    (unlike the modal ``simpledialog`` dialogs elsewhere in this module) so
    "Suivant"/"Remplacer" can be clicked repeatedly without reopening it.
    """

    def __init__(self, master: "ContentEditorWindow", *, show_replace: bool) -> None:
        super().__init__(master)
        self.editor = master
        self.show_replace = show_replace
        self.title("Rechercher et remplacer" if show_replace else "Rechercher")
        self.resizable(False, False)
        self.transient(master)

        row = 0
        ttk.Label(self, text="Rechercher :").grid(row=row, column=0, sticky="w", padx=4, pady=4)
        self.find_var = tk.StringVar()
        find_entry = ttk.Entry(self, textvariable=self.find_var, width=30)
        find_entry.grid(row=row, column=1, columnspan=2, sticky="ew", padx=4, pady=4)
        find_entry.bind("<Return>", lambda _e: self.find_next())
        row += 1

        self.replace_var = tk.StringVar()
        if show_replace:
            ttk.Label(self, text="Remplacer par :").grid(row=row, column=0, sticky="w", padx=4, pady=4)
            replace_entry = ttk.Entry(self, textvariable=self.replace_var, width=30)
            replace_entry.grid(row=row, column=1, columnspan=2, sticky="ew", padx=4, pady=4)
            replace_entry.bind("<Return>", lambda _e: self.replace_current())
            row += 1

        self.case_sensitive_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(self, text="Respecter la casse", variable=self.case_sensitive_var).grid(
            row=row, column=0, columnspan=3, sticky="w", padx=4, pady=(0, 4)
        )
        row += 1

        ttk.Button(self, text="Suivant", command=self.find_next).grid(
            row=row, column=0, padx=4, pady=4, sticky="ew"
        )
        if show_replace:
            ttk.Button(self, text="Remplacer", command=self.replace_current).grid(
                row=row, column=1, padx=4, pady=4, sticky="ew"
            )
            ttk.Button(self, text="Tout remplacer", command=self.replace_all).grid(
                row=row, column=2, padx=4, pady=4, sticky="ew"
            )
        row += 1

        self.status_var = tk.StringVar(value="")
        ttk.Label(self, textvariable=self.status_var, foreground="#777777").grid(
            row=row, column=0, columnspan=3, sticky="w", padx=4, pady=(0, 4)
        )

        self.grid_columnconfigure(1, weight=1)
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.bind("<Escape>", lambda _e: self.close())
        find_entry.focus_set()

    def close(self) -> None:
        self.editor.text.tag_remove("search_match", "1.0", "end")
        self.editor._find_dialog = None
        self.destroy()

    def find_next(self) -> None:
        text = self.editor.text
        pattern = self.find_var.get()
        text.tag_remove("search_match", "1.0", "end")
        if not pattern:
            return
        nocase = not self.case_sensitive_var.get()
        start = text.index("insert")
        idx = text.search(pattern, start, stopindex="end", nocase=nocase)
        if not idx:
            idx = text.search(pattern, "1.0", stopindex="end", nocase=nocase)
        if not idx:
            self.status_var.set("Aucune occurrence trouvée.")
            return
        end = f"{idx}+{len(pattern)}c"
        text.tag_remove("sel", "1.0", "end")
        text.tag_add("sel", idx, end)
        text.tag_add("search_match", idx, end)
        text.mark_set("insert", end)
        text.see(idx)
        self.status_var.set("")

    def replace_current(self) -> None:
        text = self.editor.text
        match = text.tag_ranges("search_match")
        if not match:
            self.find_next()
            match = text.tag_ranges("search_match")
            if not match:
                return
        start, end = str(match[0]), str(match[1])
        replacement = self.replace_var.get()
        self.editor._replace_range_preserving_tags(start, end, replacement)
        text.mark_set("insert", f"{start}+{len(replacement)}c")
        self.find_next()

    def replace_all(self) -> None:
        text = self.editor.text
        pattern = self.find_var.get()
        if not pattern:
            return
        replacement = self.replace_var.get()
        nocase = not self.case_sensitive_var.get()
        count = 0
        idx = "1.0"
        while True:
            idx = text.search(pattern, idx, stopindex="end", nocase=nocase)
            if not idx:
                break
            end = f"{idx}+{len(pattern)}c"
            self.editor._replace_range_preserving_tags(idx, end, replacement)
            idx = f"{idx}+{len(replacement)}c"
            count += 1
        text.tag_remove("search_match", "1.0", "end")
        self.status_var.set(f"{count} remplacement(s) effectué(s).")


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
        self.footnote_definitions: dict[str, list[InlineRun]] = {}
        self.link_data: dict[str, str] = {}
        self.footnote_ref_data: dict[str, str] = {}
        self._tag_counter = 0
        self._file_entries: list[tuple[str, Path]] = []  # (kind, path)
        self._note_link_data: dict[str, str] = {}
        self._footnote_text_widgets: dict[str, tk.Text] = {}
        self._footnote_rows: dict[str, ttk.Frame] = {}
        self._note_font_refs: list[tkfont.Font] = []
        self._quote_parity_opening = True
        # Tk garbage-collects a PhotoImage/Font once its last Python
        # reference disappears, even though the button still displays it —
        # toolbar icons and their bold/italic/strikethrough label fonts are
        # kept alive here for the editor window's lifetime.
        self._toolbar_icon_refs: list[tk.PhotoImage] = []
        self._toolbar_fonts: list[tkfont.Font] = []
        self._find_dialog: FindReplaceDialog | None = None

        # -- unified undo/redo (see _on_text_modified / _perform_undo) -----
        # Tk's own ``-undo`` mechanism only tracks insert/delete, never
        # tag_add/tag_remove — so a pure formatting change (bold, heading,
        # alignment...) is otherwise silently impossible to undo. This
        # stack sits alongside Tk's, recording either an opaque "text"
        # marker (delegated to text.edit_undo/edit_redo) or an explicit
        # ("format", undo_fn, redo_fn) entry pushed by the formatting
        # toggles below, so Ctrl+Z/Ctrl+Y walk both kinds of change in the
        # single chronological order the user actually made them.
        self._undo_stack: list[tuple] = []
        self._redo_stack: list[tuple] = []
        self._current_edit_kind: str | None = None
        self._last_char_count = 0
        self._suppress_undo_tracking = False

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
            (
                "Importer...",
                self._import_markdown_file,
                "Importe un fichier Markdown existant (venant d'ailleurs que ce projet) "
                "dans l'éditeur, pour compléter ses métadonnées et l'enregistrer ici.",
            ),
            (
                "Convertir en page/billet",
                self._convert_selected_kind,
                "Transforme le fichier sélectionné de page en billet (ou l'inverse) : le "
                "déplace vers le bon dossier, ajuste son nom de fichier (les billets sont "
                "préfixés par leur date) et met à jour son type dans le front matter. "
                "L'URL du contenu change en conséquence — les liens existants vers "
                "l'ancienne adresse ne sont pas mis à jour automatiquement.",
            ),
            ("Supprimer", self._delete_selected, "Supprime définitivement le fichier sélectionné."),
            ("Actualiser", self._refresh_file_list, "Recharge la liste depuis le disque."),
        ]
        for label, command, tip in buttons:
            button = ttk.Button(master, text=label, command=command)
            button.pack(fill="x", pady=2)
            add_tooltip(button, tip)

    def _build_editor(self, master: tk.Misc) -> None:
        toolbar_row1 = ttk.Frame(master)
        toolbar_row1.pack(fill="x", pady=(0, 2))
        toolbar_row2 = ttk.Frame(master)
        toolbar_row2.pack(fill="x", pady=(0, 4))

        toolbar_icons.configure_colors(
            self._resolve_color("SystemButtonFace", "#f0f0f0"),
            self._resolve_color("SystemButtonText", "#1e1e1e"),
        )

        # Bold/italic/strikethrough keep their existing single-letter labels
        # (French initials: G-ras, I-talique, S-barré) but rendered in the
        # style they apply, same convention as Word's B/I/U buttons — no
        # icon reads as clearly as the real thing.
        default_font = tkfont.nametofont("TkDefaultFont")
        bold_font = tkfont.Font(
            family=default_font.cget("family"), size=default_font.cget("size"), weight="bold"
        )
        italic_font = tkfont.Font(
            family=default_font.cget("family"), size=default_font.cget("size"), slant="italic"
        )
        strike_font = tkfont.Font(
            family=default_font.cget("family"), size=default_font.cget("size"), overstrike=1
        )
        self._toolbar_fonts.extend([bold_font, italic_font, strike_font])
        # ttk widgets take their font from a named style, not a direct
        # "font" option (unlike classic tk.Button) — one throwaway style
        # per button is the simplest way to give each its own font.
        style = ttk.Style(self)
        style.configure("ToolbarBold.TButton", font=bold_font)
        style.configure("ToolbarItalic.TButton", font=italic_font)
        style.configure("ToolbarStrike.TButton", font=strike_font)

        char_buttons = [
            ("G", "ToolbarBold.TButton", lambda: self._toggle_char_tag("bold"), "Gras (Ctrl+B)."),
            ("I", "ToolbarItalic.TButton", lambda: self._toggle_char_tag("italic"), "Italique (Ctrl+I)."),
            ("S", "ToolbarStrike.TButton", lambda: self._toggle_char_tag("strike"), "Barré (Ctrl+Maj+S)."),
            (
                "x²",
                None,
                lambda: self._toggle_char_tag("superscript"),
                "Exposant (ex. 2e, XXe, notes de calcul). Raccourci : Ctrl+Maj+= (Ctrl++).",
            ),
        ]
        for label, button_style, command, tip in char_buttons:
            kwargs = {"style": button_style} if button_style is not None else {}
            b = ttk.Button(toolbar_row1, text=label, width=3, command=command, **kwargs)
            b.pack(side="left", padx=1)
            add_tooltip(b, tip)

        ttk.Separator(toolbar_row1, orient="vertical").pack(side="left", fill="y", padx=4)

        for level in range(1, 5):
            b = ttk.Button(
                toolbar_row1, text=f"H{level}", width=3, command=lambda lv=level: self._toggle_heading(lv)
            )
            b.pack(side="left", padx=1)
            add_tooltip(b, f"Titre de niveau {level} pour la ligne courante.")

        p_button = ttk.Button(toolbar_row1, text="P", width=3, command=self._set_paragraph_normal)
        p_button.pack(side="left", padx=1)
        add_tooltip(
            p_button,
            "Paragraphe normal : retire la mise en forme de titre, citation ou liste "
            "de la ligne courante (ou de la sélection) pour revenir à un paragraphe "
            "simple.",
        )

        ttk.Separator(toolbar_row1, orient="vertical").pack(side="left", fill="y", padx=4)

        block_buttons = [
            (
                toolbar_icons.icon_blockquote(),
                lambda: self._toggle_line_tag("blockquote"),
                "Citation : transforme la ligne en citation.",
            ),
            (
                toolbar_icons.icon_bullet_list(),
                lambda: self._toggle_line_tag("bullet_item"),
                "Liste à puces : transforme la ligne en élément de liste à puces.",
            ),
            (
                toolbar_icons.icon_ordered_list(),
                lambda: self._toggle_line_tag("ordered_item"),
                "Liste numérotée : transforme la ligne en élément de liste numérotée.",
            ),
        ]
        for icon, command, tip in block_buttons:
            self._toolbar_icon_refs.append(icon)
            b = ttk.Button(toolbar_row1, image=icon, command=command)
            b.pack(side="left", padx=1)
            add_tooltip(b, tip)

        ttk.Separator(toolbar_row1, orient="vertical").pack(side="left", fill="y", padx=4)

        align_buttons = [
            (toolbar_icons.icon_align_left(), "left", "Aligne le paragraphe à gauche (par défaut)."),
            (toolbar_icons.icon_align_center(), "center", "Centre le paragraphe."),
            (toolbar_icons.icon_align_right(), "right", "Aligne le paragraphe à droite."),
            (
                toolbar_icons.icon_align_justify(),
                "justify",
                "Justifié : texte étiré pour toucher les deux marges. "
                "Rendu réel uniquement sur le site généré : l'aperçu dans cet éditeur "
                "affiche un alignement à gauche par simplification. "
                "Raccourci : Alt+J (bascule entre gauche et justifié, comme sous WordPress).",
            ),
        ]
        for icon, alignment, tip in align_buttons:
            self._toolbar_icon_refs.append(icon)
            b = ttk.Button(toolbar_row1, image=icon, command=lambda a=alignment: self._set_alignment(a))
            b.pack(side="left", padx=1)
            add_tooltip(b, tip)

        insert_buttons = [
            (
                "␣",
                None,
                self._insert_nbsp,
                "Espace insécable : insère une espace insécable au curseur (empêche la "
                "coupure entre deux mots, ex. avant « : » ou dans « 10 km »). Déjà posée "
                "automatiquement par la typographie française avant ; : ! ? et dans les "
                "guillemets. Raccourci : Alt+Espace.",
            ),
            (None, toolbar_icons.icon_link(), self._insert_link, "Lien : transforme la sélection en lien hypertexte."),
            (None, toolbar_icons.icon_image(), self._insert_image, "Image : insère une image depuis un fichier existant."),
            (None, toolbar_icons.icon_table(), self._insert_table, "Tableau : insère un tableau simple."),
            ("†", None, self._insert_footnote, "Note : insère une note de bas de page."),
        ]
        for label, icon, command, tip in insert_buttons:
            if icon is not None:
                self._toolbar_icon_refs.append(icon)
                b = ttk.Button(toolbar_row2, image=icon, command=command)
            else:
                b = ttk.Button(toolbar_row2, text=label, width=3, command=command)
            b.pack(side="left", padx=1)
            add_tooltip(b, tip)

        ttk.Separator(toolbar_row2, orient="vertical").pack(side="left", fill="y", padx=4)

        typo_button = ttk.Button(
            toolbar_row2, text="Aa", width=3, command=self._apply_typography_to_selection
        )
        typo_button.pack(side="left", padx=1)
        add_tooltip(
            typo_button,
            "Corriger la typographie : applique aux guillemets et à la ponctuation "
            "double ( ; : ! ? ) de la sélection les mêmes règles typographiques que la "
            "saisie en direct (guillemets français, espaces insécables). Utile après un "
            "collage. La mise en forme (gras, italique, citations...) de la sélection "
            "est conservée.",
        )

        ttk.Separator(toolbar_row2, orient="vertical").pack(side="left", fill="y", padx=4)

        find_button = ttk.Button(toolbar_row2, text="🔍", width=3, command=self._open_find)
        find_button.pack(side="left", padx=1)
        add_tooltip(find_button, "Rechercher (Ctrl+F).")

        replace_button = ttk.Button(toolbar_row2, text="🔍↔", width=4, command=self._open_replace)
        replace_button.pack(side="left", padx=1)
        add_tooltip(replace_button, "Rechercher et remplacer (Ctrl+H).")

        ttk.Separator(toolbar_row2, orient="vertical").pack(side="left", fill="y", padx=4)

        meta_button = ttk.Button(toolbar_row2, text="⚙", width=3, command=self._edit_metadata)
        meta_button.pack(side="left", padx=1)
        add_tooltip(meta_button, "Métadonnées : titre, slug, date, auteur, description...")

        save_icon = toolbar_icons.icon_save()
        self._toolbar_icon_refs.append(save_icon)
        save_button = ttk.Button(
            toolbar_row2, text="Enregistrer", image=save_icon, compound="left", command=self._save
        )
        save_button.pack(side="right", padx=1)
        add_tooltip(save_button, "Enregistrer : écrit ce contenu dans son fichier Markdown.")

        vertical_paned = ttk.PanedWindow(master, orient="vertical")
        vertical_paned.pack(fill="both", expand=True)

        text_frame = ttk.Frame(vertical_paned)
        vertical_paned.add(text_frame, weight=5)
        self.text = tk.Text(text_frame, wrap="word", undo=True, font=("TkDefaultFont", 11))
        # Clicking a toolbar button moves keyboard focus away from the text
        # widget, and Tk's default "inactiveselectbackground" is pale/absent
        # on most themes — the selection is still there, it just visually
        # looks deselected right when the user applies a format to it. Keep
        # it exactly as visible whether or not the widget has focus.
        self.text.configure(inactiveselectbackground=self.text.cget("selectbackground"))
        text_scrollbar = ttk.Scrollbar(text_frame, orient="vertical", command=self.text.yview)
        self.text.configure(yscrollcommand=text_scrollbar.set)
        text_scrollbar.pack(side="right", fill="y")
        self.text.pack(side="left", fill="both", expand=True)
        add_tooltip(text_scrollbar, "Fait défiler le texte vers le haut ou le bas.")
        add_tooltip(
            self.text,
            "Ctrl+molette : agrandit/réduit le texte et les notes. "
            "Raccourcis : Ctrl+B (gras), Ctrl+I (italique), Ctrl+Maj+S (barré), "
            "Ctrl+Maj+= (exposant), Alt+Espace (espace insécable), "
            "Alt+J (bascule gauche/justifié).",
        )
        self._configure_tags()
        self._init_zoom()
        self.text.bind("<KeyRelease>", self._on_key_release, add="+")
        self.text.bind("<<Modified>>", self._on_text_modified)
        self.text.bind("<<Paste>>", self._on_paste)
        self.text.bind("<Control-MouseWheel>", self._on_ctrl_mousewheel)
        self.text.bind("<Control-b>", self._shortcut_bold)
        self.text.bind("<Control-i>", self._shortcut_italic)
        self.text.bind("<Control-Shift-S>", self._shortcut_strike)
        self.text.bind("<Control-plus>", self._shortcut_superscript)
        self.text.bind("<Alt-space>", self._shortcut_nbsp)
        self.text.bind("<Alt-j>", self._shortcut_toggle_justify)
        self.text.bind("<Control-f>", self._shortcut_find)
        self.text.bind("<Control-h>", self._shortcut_replace)
        self.text.bind("<Control-z>", self._shortcut_undo)
        self.text.bind("<Control-y>", self._shortcut_redo)
        self.text.bind("<Control-Shift-Z>", self._shortcut_redo)
        self.bind("<Control-f>", self._shortcut_find)
        self.bind("<Control-h>", self._shortcut_replace)

        notes_frame = ttk.Frame(vertical_paned)
        vertical_paned.add(notes_frame, weight=1)
        self._build_notes_panel(notes_frame)

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
        text.tag_configure("align_left", justify="left")
        text.tag_configure("align_center", justify="center")
        text.tag_configure("align_right", justify="right")
        # Tk's Text widget has no true "justify" (fill) rendering; "left" is
        # the closest visual approximation. The chosen alignment is still
        # tracked and exported correctly (real CSS text-align: justify on
        # the generated site, see resources/css/site.css).
        text.tag_configure("align_justify", justify="left")
        text.tag_configure("bold", font=("TkDefaultFont", 11, "bold"))
        text.tag_configure("italic", font=("TkDefaultFont", 11, "italic"))
        text.tag_configure("strike", overstrike=True)
        text.tag_configure("superscript", offset=6, font=("TkDefaultFont", 8))
        text.tag_configure("link_style", foreground="#1a73e8", underline=True)
        text.tag_configure("image_style", background="#e8f0fe")
        text.tag_configure("footnote_style", foreground="#1a73e8")
        text.tag_configure("search_match", background="#ffe08a")
        for tag in ("bold", "italic", "strike", "superscript", "link_style", "image_style", "footnote_style"):
            text.tag_raise(tag)

    # -- zoom (Ctrl+molette) -------------------------------------------------

    def _init_zoom(self) -> None:
        self._zoom_scale = 1.0
        # Reference ("100%") sizes matching _configure_tags above.
        self._base_font_sizes = {
            "h1": 20,
            "h2": 17,
            "h3": 14,
            "h4": 12,
            "body": 11,
            "mono": 10,
            "superscript": 8,
            "superscript_offset": 6,
        }
        self._notes_font = tkfont.Font(family="TkDefaultFont", size=self._base_font_sizes["body"])

    def _on_ctrl_mousewheel(self, event: tk.Event) -> str:
        step = 0.1 if event.delta > 0 else -0.1
        self._zoom_scale = min(3.0, max(0.5, self._zoom_scale + step))
        self._apply_zoom()
        return "break"

    def _apply_zoom(self) -> None:
        scale = self._zoom_scale
        sizes = {key: max(6, round(value * scale)) for key, value in self._base_font_sizes.items()}
        text = self.text
        text.configure(font=("TkDefaultFont", sizes["body"]))
        text.tag_configure("h1", font=("TkDefaultFont", sizes["h1"], "bold"))
        text.tag_configure("h2", font=("TkDefaultFont", sizes["h2"], "bold"))
        text.tag_configure("h3", font=("TkDefaultFont", sizes["h3"], "bold"))
        text.tag_configure("h4", font=("TkDefaultFont", sizes["h4"], "bold"))
        text.tag_configure("bold", font=("TkDefaultFont", sizes["body"], "bold"))
        text.tag_configure("italic", font=("TkDefaultFont", sizes["body"], "italic"))
        text.tag_configure("table_source", font=("Courier New", sizes["mono"]))
        text.tag_configure("verbatim", font=("Courier New", sizes["mono"]))
        text.tag_configure(
            "superscript", offset=sizes["superscript_offset"], font=("TkDefaultFont", sizes["superscript"])
        )
        self._notes_font.configure(size=sizes["body"])

    # -- keyboard shortcuts ---------------------------------------------------

    def _shortcut_bold(self, _event: tk.Event) -> str:
        self._toggle_char_tag("bold")
        return "break"

    def _shortcut_italic(self, _event: tk.Event) -> str:
        self._toggle_char_tag("italic")
        return "break"

    def _shortcut_strike(self, _event: tk.Event) -> str:
        self._toggle_char_tag("strike")
        return "break"

    def _shortcut_superscript(self, _event: tk.Event) -> str:
        self._toggle_char_tag("superscript")
        return "break"

    def _shortcut_nbsp(self, _event: tk.Event) -> str:
        self._insert_nbsp()
        return "break"

    def _shortcut_find(self, _event: tk.Event) -> str:
        self._open_find()
        return "break"

    def _shortcut_replace(self, _event: tk.Event) -> str:
        self._open_replace()
        return "break"

    def _shortcut_undo(self, _event: tk.Event) -> str:
        self._perform_undo()
        return "break"

    def _shortcut_redo(self, _event: tk.Event) -> str:
        self._perform_redo()
        return "break"

    # -- unified undo/redo ---------------------------------------------------

    def _char_count(self) -> int:
        return int(self.text.count("1.0", "end", "chars")[0])

    def _on_text_modified(self, _event: tk.Event | None = None) -> None:
        """Track every insert/delete as one coalesced "text" marker on our
        own undo stack, so it interleaves in the right order with the
        "format" markers pushed by :meth:`_push_format_undo`. Consecutive
        edits of the same kind (insert-only, or delete-only) are folded
        into a single marker, matching how Tk itself groups them into one
        native undo step (a switch between inserting and deleting — or an
        explicit ``edit_separator()`` — is what starts a new Tk group).
        """
        if not self.text.edit_modified():
            return
        self.text.edit_modified(False)
        new_count = self._char_count()
        if self._suppress_undo_tracking:
            self._last_char_count = new_count
            self._current_edit_kind = None
            return
        if new_count > self._last_char_count:
            kind = "insert"
        elif new_count < self._last_char_count:
            kind = "delete"
        else:
            kind = self._current_edit_kind or "insert"
        if kind != self._current_edit_kind:
            self._undo_stack.append(("text",))
            self._redo_stack.clear()
        self._current_edit_kind = kind
        self._last_char_count = new_count

    def _push_format_undo(self, undo_fn, redo_fn) -> None:
        """Record a pure formatting change (no character inserted/deleted)
        so it can be undone/redone alongside ordinary text edits.

        ``tag_add``/``tag_remove`` are invisible to Tk's own undo stack, so
        without an explicit separator here Tk would happily merge an insert
        made *before* this formatting change with one made *after* it into
        a single native undo group (nothing it saw told it they were
        different actions) — then a single Ctrl+Z on our "text" marker for
        the second insert would silently also erase the first, unrelated
        one. The separator keeps Tk's own grouping in sync with ours.
        """
        self.text.edit_separator()
        self._undo_stack.append(("format", undo_fn, redo_fn))
        self._redo_stack.clear()
        self._current_edit_kind = None

    def _perform_undo(self) -> None:
        if not self._undo_stack:
            return
        entry = self._undo_stack.pop()
        if entry[0] == "text":
            try:
                self.text.edit_undo()
            except tk.TclError:
                pass
        else:
            entry[1]()
        self._redo_stack.append(entry)
        self._current_edit_kind = None
        self._last_char_count = self._char_count()

    def _perform_redo(self) -> None:
        if not self._redo_stack:
            return
        entry = self._redo_stack.pop()
        if entry[0] == "text":
            try:
                self.text.edit_redo()
            except tk.TclError:
                pass
        else:
            entry[2]()
        self._undo_stack.append(entry)
        self._current_edit_kind = None
        self._last_char_count = self._char_count()

    def _mark_range(self, start: str, end: str) -> tuple[str, str]:
        """Turn a snapshot of a "start"/"end" index pair into a pair of Tk
        marks, so a formatting undo/redo closure captured now still points
        at the right text later even if unrelated edits before it have
        since shifted line/column numbers.
        """
        self._tag_counter += 1
        mark_start, mark_end = f"_undo_start_{self._tag_counter}", f"_undo_end_{self._tag_counter}"
        self.text.mark_set(mark_start, start)
        self.text.mark_gravity(mark_start, "left")
        self.text.mark_set(mark_end, end)
        self.text.mark_gravity(mark_end, "right")
        return mark_start, mark_end

    def _open_find(self) -> None:
        self._show_find_dialog(show_replace=False)

    def _open_replace(self) -> None:
        self._show_find_dialog(show_replace=True)

    def _show_find_dialog(self, *, show_replace: bool) -> None:
        if self._find_dialog is not None and self._find_dialog.winfo_exists():
            self._find_dialog.destroy()
        self._find_dialog = FindReplaceDialog(self, show_replace=show_replace)

    def _replace_range_preserving_tags(self, start: str, end: str, replacement: str) -> None:
        """Delete ``start``..``end`` and insert ``replacement`` in its place,
        reapplying whatever Tk tags (bold, headings, links...) were present
        at ``start`` so a find/replace edit doesn't strip formatting.
        """
        tags = [t for t in self.text.tag_names(start) if t not in ("sel", "search_match")]
        self.text.delete(start, end)
        self.text.insert(start, replacement)
        new_end = f"{start}+{len(replacement)}c"
        for tag in tags:
            self.text.tag_add(tag, start, new_end)

    def _shortcut_toggle_justify(self, _event: tk.Event) -> str:
        """Alt+J: toggle the current paragraph between left and justify,
        the same two-state shortcut convention as WordPress/Gutenberg."""
        current = self._line_alignment(self._current_line())
        self._set_alignment("left" if current == "justify" else "justify")
        return "break"

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
                lambda _e, nid=note_id, w=note_text: self.footnote_definitions.__setitem__(
                    nid, self._extract_note_runs(w)
                ),
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
        self._note_font_refs.extend([bold_font, italic_font])
        widget.tag_configure("bold", font=bold_font)
        widget.tag_configure("italic", font=italic_font)
        widget.tag_configure("link_style", foreground="#1a73e8", underline=True)

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
            return
        tag = self._new_tag("note_link")
        self._note_link_data[tag] = href
        widget.tag_add(tag, start, end)
        widget.tag_add("link_style", start, end)
        self.footnote_definitions[note_id] = self._extract_note_runs(widget)

    def _delete_footnote(self, note_id: str) -> None:
        self.footnote_definitions.pop(note_id, None)
        self._refresh_notes_panel()

    def _focus_footnote_row(self, note_id: str) -> None:
        row = self._footnote_rows.get(note_id)
        if row is None:
            return
        widget = self._footnote_text_widgets.get(note_id)
        if widget is not None and widget.winfo_exists():
            widget.focus_set()

    # -- typographie française -----------------------------------------------

    def _current_line_is_raw(self) -> bool:
        line = self._current_line()
        tags = set(self.text.tag_names(f"{line}.0"))
        return "table_source" in tags or "verbatim" in tags

    def _on_key_release(self, event: tk.Event) -> None:
        if self._current_line_is_raw():
            return
        char = event.char
        if char and char in _TYPOGRAPHY_TRIGGER_CHARS:
            self._autoformat_last_typed_char(char)
        self._autoformat_century_ordinal()
        if char == ")":
            self._autoformat_double_paren_note()
        elif char.isdigit():
            self._autoformat_page_number_space()

    def _autoformat_last_typed_char(self, char: str) -> None:
        # Index expressions with arithmetic (e.g. "1.8-1c") are re-evaluated
        # against the *current* buffer on every call, so they silently drift
        # once a delete/insert has changed the line's length. Resolve each
        # index to a concrete "line.col" string up front and reuse only that.
        insert_index = self.text.index("insert")
        char_index = self.text.index(f"{insert_index}-1c")

        if char == '"':
            self.text.delete(char_index, insert_index)
            if self._quote_parity_opening:
                self.text.insert(char_index, OPENING_GUILLEMET + NBSP)
            else:
                self.text.insert(char_index, NBSP + CLOSING_GUILLEMET)
            self._quote_parity_opening = not self._quote_parity_opening
            return

        if char == OPENING_GUILLEMET:
            self.text.insert(insert_index, NBSP)
            return
        if char == CLOSING_GUILLEMET:
            self.text.insert(char_index, NBSP)
            return

        if char in DOUBLE_PUNCTUATION:
            preceding_index = self.text.index(f"{char_index}-1c")
            preceding = self.text.get(preceding_index, char_index)
            if preceding == NBSP:
                return
            if preceding == " ":
                self.text.delete(preceding_index, char_index)
                self.text.insert(preceding_index, NBSP)
            else:
                self.text.insert(char_index, NBSP)

    def _autoformat_century_ordinal(self) -> None:
        """Detect "<numeral>er/e siecle" just typed (e.g. "XXIe siecle") and
        superscript the ordinal suffix in place, matching the same rule
        used for pasted/imported content (:func:`bloggen.markdown.
        typography.split_century_ordinals`).
        """
        cursor = self.text.index("insert")
        line = int(cursor.split(".")[0])
        text_before = self.text.get(f"{line}.0", cursor)
        # .search() would only ever find the first match on the line, so a
        # second (still unconverted) occurrence would be permanently
        # skipped once the first is tagged; check every match instead.
        for match in CENTURY_RE.finditer(text_before):
            numeral, suffix = match.group(1), match.group(2)
            if not is_valid_century_ordinal(numeral, suffix):
                continue

            chars_after_suffix_start = len(text_before) - match.start(2)
            chars_after_suffix_end = len(text_before) - match.end(2)
            suffix_start = self.text.index(f"{cursor}-{chars_after_suffix_start}c")
            suffix_end = self.text.index(f"{cursor}-{chars_after_suffix_end}c")
            if "superscript" in self.text.tag_names(suffix_start):
                continue
            self.text.tag_add("superscript", suffix_start, suffix_end)

    def _autoformat_page_number_space(self) -> None:
        """Detect a page number's first digit just typed right after
        "p. "/"pp. " (e.g. "p. 12") and turn that regular space into a
        non-breaking one in place, the same convention as the NBSP already
        enforced before ``; : ! ?`` — see :func:`bloggen.markdown.
        typography.fix_page_number_spacing`, applied the same way to
        pasted/imported content.
        """
        cursor = self.text.index("insert")
        line = int(cursor.split(".")[0])
        text_before = self.text.get(f"{line}.0", cursor)
        if PAGE_ABBREVIATION_TYPED_RE.search(text_before) is None:
            return
        # The digit just typed is the last character; the space to convert
        # is the one right before it.
        space_start = self.text.index(f"{cursor}-2c")
        space_end = self.text.index(f"{cursor}-1c")
        self.text.delete(space_start, space_end)
        self.text.insert(space_start, NBSP)

    def _autoformat_double_paren_note(self) -> None:
        """Detect "((note text))" (Hypothèses/WordPress note shorthand)
        just completed by the closing "))" that triggered this call, and
        replace it in place with a real footnote reference — same
        conversion as :func:`bloggen.markdown.note_shortcuts.
        split_double_paren_notes` applied to pasted/imported content, but
        driven off the live cursor instead of a static block tree. Not
        gated on what follows (space, punctuation, end of line...): the
        note is often placed right before the sentence's closing
        punctuation, e.g. "((note)).".
        """
        cursor = self.text.index("insert")
        line = int(cursor.split(".")[0])
        text_before = self.text.get(f"{line}.0", cursor)
        match = _DOUBLE_PAREN_NOTE_TYPED_RE.search(text_before)
        if match is None:
            return
        note_text = match.group(1).strip()
        if not note_text:
            return

        # Resolve indices up front from the *current* buffer, for the same
        # reason as _autoformat_last_typed_char: they must not be
        # re-evaluated after the delete/insert below has changed line length.
        chars_after_start = len(text_before) - match.start()
        start_index = self.text.index(f"{cursor}-{chars_after_start}c")

        self.text.delete(start_index, cursor)
        note_id = self._register_new_footnote(note_text)
        self._insert_footnote_marker(start_index, note_id)
        self._refresh_notes_panel()

    def _apply_typography_to_selection(self) -> None:
        """Same rules as :func:`bloggen.markdown.typography.apply_french_typography`,
        but rewrites the selection run by run (each contiguous stretch of
        unchanged Tk tags) instead of as one flat string, so that character
        formatting (bold/italic/strike/links...) and block formatting
        (blockquote, headings, alignment...) already on the selection survive
        the edit. Quote-parity tracking still threads across runs, matching
        :func:`bloggen.markdown.html_paste_import._normalize_typography`,
        which applies the same rules run by run for pasted content.
        """
        selected = self._selection_range()
        if selected is None:
            messagebox.showinfo("Typographie", "Sélectionnez d'abord le texte à corriger.")
            return
        start, end = selected
        runs = self._dump_tagged_runs(start, end)
        if not runs:
            return

        fixed_runs: list[tuple[frozenset[str], str, str, str]] = []
        opening_next = True
        changed = False
        counters = {
            "guillemets": 0,
            "espaces": 0,
            "ponctuation": 0,
            "numeros_page": 0,
        }
        for tags, text, run_start, run_end in runs:
            step = convert_curly_quotes_to_guillemets(text)
            step, opening_next = convert_straight_quotes_stateful(step, opening_next=opening_next)
            if step != text:
                counters["guillemets"] += 1
            after_quotes = step

            step = fix_guillemet_spacing(step)
            if step != after_quotes:
                counters["espaces"] += 1
            after_spacing = step

            step = fix_double_punctuation_spacing(step)
            if step != after_spacing:
                counters["ponctuation"] += 1
            after_punctuation = step

            step = fix_page_number_spacing(step)
            if step != after_punctuation:
                counters["numeros_page"] += 1

            fixed = step
            if fixed != text:
                changed = True
            fixed_runs.append((tags, fixed, run_start, run_end))

        if not changed:
            messagebox.showinfo(
                "Typographie",
                "Aucune correction nécessaire : la sélection respecte déjà les règles "
                "typographiques.",
            )
            return

        # Rewrite runs back-to-front: editing a run never changes the
        # widget indices of anything before it, so the start/end positions
        # captured above (against the original, unedited content) stay
        # valid for every run still to come.
        for tags, fixed, run_start, run_end in reversed(fixed_runs):
            self.text.delete(run_start, run_end)
            self.text.insert(run_start, fixed)
            for tag in tags:
                if tag == "sel":
                    continue
                self.text.tag_add(tag, run_start, f"{run_start}+{len(fixed)}c")

        labels = {
            "guillemets": "Guillemets convertis en chevrons français",
            "espaces": "Espaces autour des guillemets corrigées",
            "ponctuation": "Espaces insécables ajoutées avant ; : ! ?",
            "numeros_page": "Espaces insécables ajoutées dans les numéros de page",
        }
        lines = [f"• {labels[key]}" for key, count in counters.items() if count]
        messagebox.showinfo(
            "Typographie",
            "Corrections appliquées à la sélection :\n" + "\n".join(lines),
        )

    def _dump_tagged_runs(
        self, start: str, end: str
    ) -> list[tuple[frozenset[str], str, str, str]]:
        """Split ``start``..``end`` into runs of unbroken tag combinations,
        in document order: each run is ``(tags, text, run_start, run_end)``.
        """
        runs: list[tuple[frozenset[str], str, str, str]] = []
        active: set[str] = set()
        run_start = start
        run_text: list[str] = []
        for key, value, index in self.text.dump(start, end, tag=True, text=True):
            if key == "text":
                run_text.append(value)
                continue
            if run_text:
                runs.append((frozenset(active), "".join(run_text), run_start, index))
            run_text = []
            run_start = index
            if key == "tagon":
                active.add(value)
            elif key == "tagoff":
                active.discard(value)
        if run_text:
            runs.append((frozenset(active), "".join(run_text), run_start, end))
        return runs

    # -- rich paste (Word / Google Docs) -------------------------------------

    def _on_paste(self, _event: tk.Event) -> str | None:
        """Handle ``<<Paste>>``: if the clipboard holds HTML (as Word,
        Google Docs, or a browser puts there alongside plain text), convert
        and insert it with formatting instead of Tk's default plain-text
        paste. Falls through to that default (return ``None``) whenever
        rich paste isn't applicable, so a normal ``Ctrl+V`` never breaks.

        Either way, any "((note text))" shorthand found in the pasted
        content (the Hypothèses/WordPress convention — see
        :mod:`bloggen.markdown.note_shortcuts`) is converted to a real
        footnote reference before insertion.
        """
        if self._current_line_is_raw():
            return None
        html = read_html_clipboard()
        if html:
            try:
                blocks = html_to_blocks(html, images_dir=self.images_dir)
            except Exception:
                return None
            if not blocks:
                return None
            convert_double_paren_notes_in_blocks(blocks, self._register_new_footnote)
            self._insert_pasted_blocks_at_cursor(blocks)
            self._refresh_notes_panel()
            return "break"

        # No HTML on the clipboard (e.g. copied from a plain-text editor):
        # only take over the default plain-text paste when the shorthand is
        # actually present, so the ordinary Ctrl+V path is left untouched
        # otherwise.
        try:
            plain = self.clipboard_get()
        except tk.TclError:
            return None
        if not DOUBLE_PAREN_NOTE_RE.search(plain):
            return None
        runs = split_double_paren_notes([InlineRun(text=plain)], self._register_new_footnote)
        self._insert_runs_at_cursor(runs)
        self._refresh_notes_panel()
        return "break"

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

    def _refresh_file_list(self) -> None:
        self.file_listbox.delete(0, "end")
        self._file_entries = []
        entries: list[tuple[str, str, Path]] = []  # (kind, title, path)
        for kind, directory in (("page", self.pages_dir), ("post", self.posts_dir)):
            if not directory.exists():
                continue
            for path in sorted(directory.rglob("*.md")):
                if _VERSIONS_DIRNAME in path.parts:
                    continue
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

    def _import_markdown_file(self) -> None:
        source = filedialog.askopenfilename(
            title="Importer un fichier Markdown",
            filetypes=[("Markdown", "*.md *.markdown"), ("Tous les fichiers", "*.*")],
        )
        if not source:
            return
        try:
            text = Path(source).read_text(encoding="utf-8")
        except OSError as exc:
            messagebox.showerror("Importer", f"Impossible de lire le fichier :\n{exc}")
            return

        result = parse_front_matter(text)
        kind = result.metadata.get("type") if result.metadata.get("type") in ("page", "post") else "page"
        self._new_document(kind)
        self._populate_from_blocks(markdown_to_blocks(result.body))
        self.metadata = dict(result.metadata)
        self.metadata.setdefault("type", kind)
        self.current_kind = kind
        messagebox.showinfo(
            "Importer",
            "Fichier importé dans l'éditeur. Vérifiez/complétez les métadonnées "
            "(bouton Métadonnées...) puis enregistrez pour l'ajouter au projet.",
        )

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

    def _convert_selected_kind(self) -> None:
        entry = self._selected_entry()
        if entry is None:
            messagebox.showinfo("Convertir", "Sélectionnez d'abord une page ou un billet dans la liste.")
            return
        kind, path = entry
        new_kind = "post" if kind == "page" else "page"
        new_label, source_label = ("billet", "page") if new_kind == "post" else ("page", "billet")

        try:
            metadata, body = read_content_file(path)
        except OSError as exc:
            messagebox.showerror("Convertir", f"Impossible de lire le fichier :\n{exc}")
            return

        date_value = metadata.get("date", "").strip()
        if new_kind == "post":
            entered = simpledialog.askstring(
                "Convertir en billet",
                "Date de publication (AAAA-MM-JJ) :",
                initialvalue=date_value or date.today().isoformat(),
                parent=self,
            )
            if entered is None:
                return
            date_value = entered.strip()
            if not is_valid_iso_date(date_value):
                messagebox.showerror("Convertir", "La date doit être au format AAAA-MM-JJ.")
                return

        if not messagebox.askyesno(
            "Convertir",
            f"Transformer cette {source_label} en {new_label} ?\n\n"
            "Le fichier est déplacé vers le bon dossier et son URL change en conséquence "
            "(dossier des pages ou archive des billets). Les liens existants vers "
            "l'ancienne adresse ne sont pas mis à jour automatiquement.",
            parent=self,
        ):
            return

        metadata = dict(metadata)
        metadata["type"] = new_kind
        if new_kind == "post":
            metadata["date"] = date_value
        else:
            metadata.pop("date", None)

        target_dir = self.posts_dir if new_kind == "post" else self.pages_dir
        filename = default_filename(new_kind, metadata.get("slug", "").strip(), date=metadata.get("date"))

        try:
            written = write_content_file(target_dir, filename, metadata, body)
            if written != path:
                path.unlink(missing_ok=True)
        except OSError as exc:
            messagebox.showerror("Convertir", f"Impossible d'écrire le fichier :\n{exc}")
            return

        if self.current_path == path:
            self.current_path = written
            self.current_kind = new_kind
            self.metadata = metadata

        self._refresh_file_list()
        messagebox.showinfo("Convertir", f"Converti en {new_label} : {written}")

    def _new_document(self, kind: str) -> None:
        self._destroy_embedded_images()
        self.text.delete("1.0", "end")
        self.footnote_definitions.clear()
        self.link_data.clear()
        self.footnote_ref_data.clear()
        self._note_link_data.clear()
        self._footnote_text_widgets.clear()
        self.metadata = {}
        self.current_kind = kind
        self.current_path = None
        self._quote_parity_opening = True
        self._refresh_notes_panel()
        self.text.edit_reset()
        self._undo_stack.clear()
        self._redo_stack.clear()
        self._current_edit_kind = None
        self._last_char_count = self._char_count()

    def _destroy_embedded_images(self) -> None:
        # Text.delete() does not destroy windows embedded via window_create;
        # left alone they'd leak as orphaned Tk widgets on every reload.
        for path in self.text.window_names():
            widget = self.text.nametowidget(path)
            widget.destroy()

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

    def _toggle_line_tag(self, tag: str) -> None:
        start_line, end_line = self._selected_lines()
        changes: list[tuple[str, str, set[str], set[str]]] = []
        for line in range(start_line, end_line + 1):
            line_start, line_end = f"{line}.0", f"{line}.end"
            before = set(self.text.tag_names(line_start)) & _BLOCK_LINE_TAGS
            already = tag in before
            for existing in _BLOCK_LINE_TAGS:
                self.text.tag_remove(existing, line_start, line_end)
            after: set[str] = set()
            if not already:
                self.text.tag_add(tag, line_start, line_end)
                after = {tag}
            changes.append((line_start, line_end, before, after))
        self._push_line_tag_undo(_BLOCK_LINE_TAGS, changes)

    def _set_paragraph_normal(self) -> None:
        """Clear the block-level formatting (heading/citation/liste) of the
        selected (or current) lines, back to a plain paragraph — the
        counterpart to the H1-H4/citation/liste buttons, none of which can
        otherwise be turned back off once applied.
        """
        start_line, end_line = self._selected_lines()
        changes: list[tuple[str, str, set[str], set[str]]] = []
        for line in range(start_line, end_line + 1):
            line_start, line_end = f"{line}.0", f"{line}.end"
            before = set(self.text.tag_names(line_start)) & _BLOCK_LINE_TAGS
            if not before:
                continue
            for existing in _BLOCK_LINE_TAGS:
                self.text.tag_remove(existing, line_start, line_end)
            changes.append((line_start, line_end, before, set()))
        self._push_line_tag_undo(_BLOCK_LINE_TAGS, changes)

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
        src_repr = copy_into_images_dir(Path(source), self.images_dir)
        self._insert_image_widget("insert", src_repr, alt)

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
        widget = ImageWidget(
            self.text,
            images_dir=self.images_dir,
            src=src,
            alt=alt,
            width=width,
            height=height,
            align=align,
        )
        self.text.window_create(index, window=widget)
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

    def _insert_footnote(self) -> None:
        note_text = simpledialog.askstring("Note de bas de page", "Texte de la note :", parent=self)
        if not note_text:
            return
        note_id = self._register_new_footnote(note_text)
        self._insert_footnote_marker(self.text.index("insert"), note_id)
        self._refresh_notes_panel()

    def _register_new_footnote(self, note_text: str) -> str:
        """Allocate the next free footnote id and record its definition.
        Shared by the "Note..." dialog, the ((...)) typing shorthand, and
        ((...)) found in pasted/imported content — each needs a fresh,
        non-colliding id, and calling this repeatedly (e.g. for several
        notes found in one paste) keeps allocating past ids already handed
        out earlier in the same batch.
        """
        next_id = 1
        while str(next_id) in self.footnote_definitions:
            next_id += 1
        note_id = str(next_id)
        self.footnote_definitions[note_id] = [InlineRun(text=note_text)]
        return note_id

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

        self._quote_parity_opening = True
        self._refresh_notes_panel()
        self.text.edit_reset()
        self._undo_stack.clear()
        self._redo_stack.clear()
        self._current_edit_kind = None
        self._last_char_count = self._char_count()
        self._suppress_undo_tracking = False

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

    def _archive_previous_version(self, path: Path) -> None:
        """Before a save overwrites ``path``, copy its current on-disk
        content into a sibling ``.versions`` folder under a numbered
        filename (``slug.v1.md``, ``slug.v2.md``, ...), so past edits stay
        recoverable. No-op the first time a file is saved (nothing to
        archive yet).
        """
        if not path.exists():
            return
        versions_dir = path.parent / _VERSIONS_DIRNAME
        versions_dir.mkdir(exist_ok=True)
        pattern = re.compile(
            _VERSION_FILENAME_RE_TEMPLATE.format(stem=re.escape(path.stem), suffix=re.escape(path.suffix))
        )
        next_number = 1
        for existing in versions_dir.glob(f"{path.stem}.v*{path.suffix}"):
            match = pattern.match(existing.name)
            if match:
                next_number = max(next_number, int(match.group(1)) + 1)
        version_path = versions_dir / f"{path.stem}.v{next_number}{path.suffix}"
        version_path.write_bytes(path.read_bytes())

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
            self._archive_previous_version(target_dir / filename)
            written = write_content_file(target_dir, filename, self.metadata, body)
        except OSError as exc:
            messagebox.showerror("Enregistrement", f"Impossible d'écrire le fichier :\n{exc}")
            return

        self.current_path = written
        self._refresh_file_list()
        messagebox.showinfo("Enregistrement", f"Contenu enregistré : {written}")
