"""Banner settings panel."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from bloggen.config.models import BannerConfig
from bloggen.ui.tooltip import add_tooltip


class BannerPanel(ttk.Frame):
    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master)
        self.enabled_var = tk.BooleanVar(value=False)
        self.image_var = tk.StringVar(value="")
        self.link_var = tk.StringVar(value="/index.html")
        self.alt_var = tk.StringVar(value="")
        self.show_title_overlay_var = tk.BooleanVar(value=False)
        self.height_var = tk.IntVar(value=220)
        self._build_ui()

    def _build_ui(self) -> None:
        ttk.Label(
            self,
            text=(
                "Image large affichée en haut de la page d'accueil (et éventuellement des "
                "autres pages), au-dessus du menu ou du titre."
            ),
            wraplength=680,
            justify="left",
            foreground="#444444",
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=8, pady=(4, 10))

        enable_cb = ttk.Checkbutton(
            self, text="Activer la bannière", variable=self.enabled_var
        )
        enable_cb.grid(row=1, column=0, columnspan=2, sticky="w", padx=8, pady=6)
        add_tooltip(enable_cb, "Si désactivé, aucune bannière n'est affichée et les autres champs sont ignorés.")

        image_entry = _add_entry_row(self, 2, "Image", self.image_var)
        add_tooltip(
            image_entry,
            "Chemin de l'image de bannière, relatif au dossier assets (onglet Chemins).\n"
            "Exemple : assets/images/banniere.jpg",
        )

        link_entry = _add_entry_row(self, 3, "Lien", self.link_var)
        add_tooltip(
            link_entry,
            "Page ouverte lorsqu'on clique sur la bannière (chemin interne commençant "
            "par / ou URL externe complète).\n"
            "Exemple : /index.html",
        )

        alt_entry = _add_entry_row(self, 4, "Alt", self.alt_var)
        add_tooltip(
            alt_entry,
            "Texte alternatif de l'image, lu par les lecteurs d'écran et affiché si "
            "l'image ne charge pas. Important pour l'accessibilité.\n"
            "Exemple : Vue aérienne du campus au printemps",
        )

        height_entry = _add_entry_row(self, 5, "Hauteur (px)", self.height_var)
        add_tooltip(
            height_entry,
            "Hauteur d'affichage de la bannière en pixels (nombre entier). L'image est "
            "recadrée pour remplir cette hauteur.\n"
            "Exemple : 220",
        )

        overlay_cb = ttk.Checkbutton(
            self,
            text="Afficher le titre sur l'image",
            variable=self.show_title_overlay_var,
        )
        overlay_cb.grid(row=6, column=0, columnspan=2, sticky="w", padx=8, pady=6)
        add_tooltip(
            overlay_cb,
            "Si activé, le titre du site (onglet Site) est superposé en texte sur "
            "la bannière plutôt qu'affiché séparément en dessous.",
        )
        self.grid_columnconfigure(1, weight=1)

    def set_data(self, banner: BannerConfig) -> None:
        self.enabled_var.set(banner.enabled)
        self.image_var.set(banner.image)
        self.link_var.set(banner.link)
        self.alt_var.set(banner.alt)
        self.show_title_overlay_var.set(banner.show_title_overlay)
        self.height_var.set(banner.height_px)

    def get_data(self) -> BannerConfig:
        return BannerConfig(
            enabled=self.enabled_var.get(),
            image=self.image_var.get().strip(),
            link=self.link_var.get().strip(),
            alt=self.alt_var.get().strip(),
            show_title_overlay=self.show_title_overlay_var.get(),
            height_px=self.height_var.get(),
        )


def _add_entry_row(
    master: tk.Misc,
    row: int,
    label: str,
    variable: tk.StringVar | tk.IntVar,
) -> ttk.Entry:
    ttk.Label(master, text=label).grid(row=row, column=0, sticky="w", padx=8, pady=4)
    entry = ttk.Entry(master, textvariable=variable)
    entry.grid(row=row, column=1, sticky="ew", padx=8, pady=4)
    return entry
