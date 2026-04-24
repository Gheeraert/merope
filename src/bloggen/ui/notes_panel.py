"""Notes rendering settings panel."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from bloggen.config.models import NotesRenderingConfig


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
        _add_row(self, 0, "Mode", self.mode_var)
        ttk.Checkbutton(self, text="Activer notes marginales", variable=self.enable_margin_var).grid(
            row=1, column=0, columnspan=2, sticky="w", padx=8, pady=4
        )
        ttk.Checkbutton(self, text="Activer notes complètes", variable=self.enable_footnotes_var).grid(
            row=2, column=0, columnspan=2, sticky="w", padx=8, pady=4
        )
        _add_row(self, 3, "Amorce (mots)", self.excerpt_words_var)
        _add_row(self, 4, "Amorce (caractères)", self.excerpt_chars_var)
        ttk.Checkbutton(
            self,
            text="Préférer le comptage en mots",
            variable=self.prefer_words_var,
        ).grid(row=5, column=0, columnspan=2, sticky="w", padx=8, pady=4)
        _add_row(self, 6, "Emplacement notes finales", self.location_var)
        self.grid_columnconfigure(1, weight=1)

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
) -> None:
    ttk.Label(master, text=label).grid(row=row, column=0, sticky="w", padx=8, pady=4)
    ttk.Entry(master, textvariable=variable).grid(row=row, column=1, sticky="ew", padx=8, pady=4)
