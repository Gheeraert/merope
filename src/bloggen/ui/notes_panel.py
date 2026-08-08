"""Notes rendering settings panel."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from bloggen.config.models import NotesRenderingConfig
from bloggen.ui.tooltip import add_tooltip


class NotesPanel(ttk.Frame):
    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master)
        self.mode_var = tk.StringVar(value="margin_excerpt_plus_footnote")
        self.enable_margin_var = tk.BooleanVar(value=True)
        self.enable_footnotes_var = tk.BooleanVar(value=True)
        self.excerpt_words_var = tk.IntVar(value=8)
        self.excerpt_chars_var = tk.IntVar(value=80)
        self.prefer_words_var = tk.BooleanVar(value=True)
        self.location_var = tk.StringVar(value="end_of_article")
        self._build_ui()

    def _build_ui(self) -> None:
        ttk.Label(
            self,
            text=(
                "Réglage de l'affichage des notes de bas de page (appels de note dans "
                "le texte, aperçu en marge, texte complet)."
            ),
            wraplength=680,
            justify="left",
            foreground="#444444",
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=8, pady=(4, 10))

        mode_entry = _add_row(self, 1, "Mode", self.mode_var)
        add_tooltip(
            mode_entry,
            "Mode d'affichage global des notes. « margin_excerpt_plus_footnote » "
            "affiche un court aperçu en marge et le texte complet en bas de page.\n"
            "Exemple : margin_excerpt_plus_footnote",
        )

        margin_cb = ttk.Checkbutton(
            self, text="Activer notes marginales", variable=self.enable_margin_var
        )
        margin_cb.grid(row=2, column=0, columnspan=2, sticky="w", padx=8, pady=4)
        add_tooltip(
            margin_cb,
            "Si activé, un court aperçu de chaque note s'affiche dans la marge à côté "
            "du texte, en plus de l'appel de note.",
        )

        footnotes_cb = ttk.Checkbutton(
            self, text="Activer notes complètes", variable=self.enable_footnotes_var
        )
        footnotes_cb.grid(row=3, column=0, columnspan=2, sticky="w", padx=8, pady=4)
        add_tooltip(
            footnotes_cb,
            "Si activé, le texte complet de chaque note est listé (emplacement "
            "défini par « Emplacement notes finales » ci-dessous).",
        )

        words_entry = _add_row(self, 4, "Amorce (mots)", self.excerpt_words_var)
        add_tooltip(
            words_entry,
            "Longueur maximale de l'aperçu en marge, en nombre de mots (nombre entier). "
            "Utilisé si « Préférer le comptage en mots » est activé.\n"
            "Exemple : 8",
        )

        chars_entry = _add_row(self, 5, "Amorce (caractères)", self.excerpt_chars_var)
        add_tooltip(
            chars_entry,
            "Longueur maximale de l'aperçu en marge, en nombre de caractères "
            "(nombre entier). Utilisé si « Préférer le comptage en mots » est désactivé.\n"
            "Exemple : 80",
        )

        prefer_cb = ttk.Checkbutton(
            self,
            text="Préférer le comptage en mots",
            variable=self.prefer_words_var,
        )
        prefer_cb.grid(row=6, column=0, columnspan=2, sticky="w", padx=8, pady=4)
        add_tooltip(
            prefer_cb,
            "Si activé, l'aperçu en marge est tronqué selon « Amorce (mots) ». Si "
            "désactivé, il est tronqué selon « Amorce (caractères) ».",
        )

        location_entry = _add_row(self, 7, "Emplacement notes finales", self.location_var)
        add_tooltip(
            location_entry,
            "Où placer la liste des notes complètes : « end_of_article » les regroupe "
            "à la fin de chaque billet/page.\n"
            "Exemple : end_of_article",
        )
        self.grid_columnconfigure(3, weight=1)

    def set_data(self, notes: NotesRenderingConfig) -> None:
        self.mode_var.set(notes.mode)
        self.enable_margin_var.set(notes.enable_margin_notes)
        self.enable_footnotes_var.set(notes.enable_footnotes)
        self.excerpt_words_var.set(notes.margin_excerpt_words)
        self.excerpt_chars_var.set(notes.margin_excerpt_chars)
        self.prefer_words_var.set(notes.prefer_words_over_chars)
        self.location_var.set(notes.footnotes_location)

    def get_data(self) -> NotesRenderingConfig:
        return NotesRenderingConfig(
            mode=self.mode_var.get().strip(),
            enable_margin_notes=self.enable_margin_var.get(),
            enable_footnotes=self.enable_footnotes_var.get(),
            margin_excerpt_words=self.excerpt_words_var.get(),
            margin_excerpt_chars=self.excerpt_chars_var.get(),
            prefer_words_over_chars=self.prefer_words_var.get(),
            footnotes_location=self.location_var.get().strip(),
        )


def _add_row(
    master: tk.Misc,
    row: int,
    label: str,
    variable: tk.StringVar | tk.IntVar,
) -> ttk.Entry:
    ttk.Label(master, text=label).grid(row=row, column=0, sticky="w", padx=8, pady=4)
    entry = ttk.Entry(master, textvariable=variable, width=55)
    entry.grid(row=row, column=1, sticky="w", padx=8, pady=4)
    return entry
