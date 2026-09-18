"""Notes rendering settings panel."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from bloggen.config.models import NotesRenderingConfig
from bloggen.ui.form_validation import parse_int_field
from bloggen.ui.tooltip import add_tooltip


class NotesPanel(ttk.Frame):
    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master)
        # Kept internally for lossless GUI round-trips of existing site.json files.
        self.mode_var = tk.StringVar(value="margin_excerpt_plus_footnote")
        self.enable_margin_var = tk.BooleanVar(value=False)
        self.enable_footnotes_var = tk.BooleanVar(value=True)
        self.excerpt_words_var = tk.StringVar(value="8")
        self.excerpt_chars_var = tk.StringVar(value="80")
        self.prefer_words_var = tk.BooleanVar(value=True)
        self.location_var = tk.StringVar(value="end_of_article")
        self._build_ui()

    def _build_ui(self) -> None:
        ttk.Label(
            self,
            text=(
                "Réglage de l'affichage des notes dans le site HTML généré. Les appels de "
                "note sont produits à partir du contenu ; l'option ci-dessous contrôle "
                "l'affichage de la liste complète des notes en fin de page."
            ),
            wraplength=680,
            justify="left",
            foreground="#444444",
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=8, pady=(4, 10))

        footnotes_cb = ttk.Checkbutton(
            self,
            text="Afficher les notes complètes en fin de page",
            variable=self.enable_footnotes_var,
        )
        footnotes_cb.grid(row=1, column=0, columnspan=2, sticky="w", padx=8, pady=4)
        add_tooltip(
            footnotes_cb,
            "Si activé, la liste complète des notes est conservée dans le HTML généré. "
            "Si désactivé, cette liste est retirée du HTML. Les notes restent présentes "
            "dans le TEI généré.",
        )
        self.grid_columnconfigure(3, weight=1)

    def set_data(self, notes: NotesRenderingConfig) -> None:
        self.mode_var.set(notes.mode)
        self.enable_margin_var.set(notes.enable_margin_notes)
        self.enable_footnotes_var.set(notes.enable_footnotes)
        self.excerpt_words_var.set(str(notes.margin_excerpt_words))
        self.excerpt_chars_var.set(str(notes.margin_excerpt_chars))
        self.prefer_words_var.set(notes.prefer_words_over_chars)
        self.location_var.set(notes.footnotes_location)

    def get_data(self) -> NotesRenderingConfig:
        return NotesRenderingConfig(
            mode=self.mode_var.get().strip(),
            enable_margin_notes=self.enable_margin_var.get(),
            enable_footnotes=self.enable_footnotes_var.get(),
            margin_excerpt_words=parse_int_field(self.excerpt_words_var.get(), "Amorce (mots)", minimum=0),
            margin_excerpt_chars=parse_int_field(self.excerpt_chars_var.get(), "Amorce (caractères)", minimum=0),
            prefer_words_over_chars=self.prefer_words_var.get(),
            footnotes_location=self.location_var.get().strip(),
        )
