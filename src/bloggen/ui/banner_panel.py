"""Banner settings panel."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from bloggen.config.models import BannerConfig


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
        ttk.Checkbutton(self, text="Activer la bannière", variable=self.enabled_var).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=8, pady=6
        )
        _add_entry_row(self, 1, "Image", self.image_var)
        _add_entry_row(self, 2, "Lien", self.link_var)
        _add_entry_row(self, 3, "Alt", self.alt_var)
        _add_entry_row(self, 4, "Hauteur (px)", self.height_var)
        ttk.Checkbutton(
            self,
            text="Afficher le titre sur l'image",
            variable=self.show_title_overlay_var,
        ).grid(row=5, column=0, columnspan=2, sticky="w", padx=8, pady=6)
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
) -> None:
    ttk.Label(master, text=label).grid(row=row, column=0, sticky="w", padx=8, pady=4)
    ttk.Entry(master, textvariable=variable).grid(row=row, column=1, sticky="ew", padx=8, pady=4)
