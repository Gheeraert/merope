"""Standalone dialog windows used by the content editor: the metadata
form (title/slug/date/author/...) and the non-modal find/replace panel.
"""

from __future__ import annotations

from datetime import date
from tkinter import messagebox, simpledialog, ttk
import tkinter as tk

from bloggen.content.metadata import is_valid_iso_date, normalize_orcid
from bloggen.content.slugify import is_valid_slug_format
from bloggen.content.writer import suggest_slug
from bloggen.ui.tooltip import add_tooltip


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
        self.updated_var = tk.StringVar(value=self.initial.get("updated", ""))
        self.author_var = tk.StringVar(value=self.initial.get("author", ""))
        self.orcid_var = tk.StringVar(value=self.initial.get("orcid", ""))
        self.keywords_var = tk.StringVar(value=self.initial.get("keywords", ""))
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

        ttk.Label(master, text="Mis à jour le (AAAA-MM-JJ)").grid(row=row, column=0, sticky="w", padx=4, pady=4)
        updated_entry = ttk.Entry(master, textvariable=self.updated_var, width=20)
        updated_entry.grid(row=row, column=1, sticky="w", padx=4, pady=4)
        add_tooltip(
            updated_entry,
            "Date éditoriale de dernière modification, utilisée pour le sitemap (SEO). "
            "Optionnel : à défaut, la date du fichier sur le disque est utilisée, "
            "mais celle-ci peut être faussée par un déplacement de fichiers ou un "
            "changement de branche Git.\nExemple : 2026-08-08",
        )
        row += 1

        ttk.Label(master, text="Auteur").grid(row=row, column=0, sticky="w", padx=4, pady=4)
        ttk.Entry(master, textvariable=self.author_var, width=40).grid(
            row=row, column=1, sticky="ew", padx=4, pady=4
        )
        row += 1

        ttk.Label(master, text="ORCID de l'auteur").grid(row=row, column=0, sticky="w", padx=4, pady=4)
        orcid_entry = ttk.Entry(master, textvariable=self.orcid_var, width=40)
        orcid_entry.grid(row=row, column=1, sticky="ew", padx=4, pady=4)
        add_tooltip(
            orcid_entry,
            "Identifiant ORCID de l'auteur, optionnel — accepté sous forme complète "
            "(https://orcid.org/...) ou compacte.\nExemple : 0000-0002-1825-0097",
        )
        row += 1

        ttk.Label(master, text="Mots-clés").grid(row=row, column=0, sticky="w", padx=4, pady=4)
        keywords_entry = ttk.Entry(master, textvariable=self.keywords_var, width=40)
        keywords_entry.grid(row=row, column=1, sticky="ew", padx=4, pady=4)
        add_tooltip(keywords_entry, "Séparés par des virgules, optionnel.\nExemple : rhétorique, Bossuet, XVIIe siècle")
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
        if not is_valid_slug_format(slug):
            messagebox.showerror(
                "Métadonnées",
                f"Slug invalide « {slug} » : utilisez uniquement des lettres minuscules, "
                "des chiffres et des tirets simples (ex. « mon-article »).",
                parent=self,
            )
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
        updated = self.updated_var.get().strip()
        if updated and not is_valid_iso_date(updated):
            messagebox.showerror(
                "Métadonnées", "La date de mise à jour doit être au format AAAA-MM-JJ.", parent=self
            )
            return False
        orcid = self.orcid_var.get().strip()
        if orcid and normalize_orcid(orcid) is None:
            messagebox.showerror(
                "Métadonnées",
                "ORCID invalide : attendu 0000-0000-0000-000X, avec une clé de contrôle correcte.",
                parent=self,
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
        if self.updated_var.get().strip():
            metadata["updated"] = self.updated_var.get().strip()
        if self.author_var.get().strip():
            metadata["author"] = self.author_var.get().strip()
        if self.orcid_var.get().strip():
            metadata["orcid"] = normalize_orcid(self.orcid_var.get().strip()) or self.orcid_var.get().strip()
        if self.keywords_var.get().strip():
            metadata["keywords"] = self.keywords_var.get().strip()
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


