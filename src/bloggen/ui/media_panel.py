"""Media settings panel."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from bloggen.config.models import MediaHandlingConfig


class MediaPanel(ttk.Frame):
    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master)
        self.strategy_var = tk.StringVar(value="copy_local_assets")
        self.images_dir_var = tk.StringVar(value="assets/images")
        self.copy_media_var = tk.BooleanVar(value=True)
        self.clickable_figures_var = tk.BooleanVar(value=True)
        self.group_posts_var = tk.BooleanVar(value=True)
        self.caption_var = tk.BooleanVar(value=True)
        self._build_ui()

    def _build_ui(self) -> None:
        _add_row(self, 0, "Stratégie", self.strategy_var)
        _add_row(self, 1, "Dossier images", self.images_dir_var)
        ttk.Checkbutton(self, text="Copier les médias vers la sortie", variable=self.copy_media_var).grid(
            row=2, column=0, columnspan=2, sticky="w", padx=8, pady=4
        )
        ttk.Checkbutton(
            self,
            text="Figures cliquables",
            variable=self.clickable_figures_var,
        ).grid(row=3, column=0, columnspan=2, sticky="w", padx=8, pady=4)
        ttk.Checkbutton(self, text="Regrouper les figures par article", variable=self.group_posts_var).grid(
            row=4, column=0, columnspan=2, sticky="w", padx=8, pady=4
        )
        ttk.Checkbutton(
            self,
            text="Utiliser les légendes comme légendes lightbox",
            variable=self.caption_var,
        ).grid(row=5, column=0, columnspan=2, sticky="w", padx=8, pady=4)
        self.grid_columnconfigure(1, weight=1)

    def set_data(self, media: MediaHandlingConfig) -> None:
        self.strategy_var.set(media.strategy)
        self.images_dir_var.set(media.images_dir)
        self.copy_media_var.set(media.copy_media_to_output)
        self.clickable_figures_var.set(media.generate_clickable_figures)
        self.group_posts_var.set(media.fancybox_group_posts)
        self.caption_var.set(media.use_captions_as_fancybox_caption)

    def get_data(self) -> MediaHandlingConfig:
        return MediaHandlingConfig(
            strategy=self.strategy_var.get().strip(),
            images_dir=self.images_dir_var.get().strip(),
            copy_media_to_output=self.copy_media_var.get(),
            generate_clickable_figures=self.clickable_figures_var.get(),
            fancybox_group_posts=self.group_posts_var.get(),
            use_captions_as_fancybox_caption=self.caption_var.get(),
        )


def _add_row(master: tk.Misc, row: int, label: str, variable: tk.StringVar) -> None:
    ttk.Label(master, text=label).grid(row=row, column=0, sticky="w", padx=8, pady=4)
    ttk.Entry(master, textvariable=variable).grid(row=row, column=1, sticky="ew", padx=8, pady=4)
