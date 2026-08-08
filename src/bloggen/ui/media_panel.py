"""Media settings panel."""

from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, ttk

from bloggen.config.models import MediaHandlingConfig
from bloggen.ui.tooltip import add_tooltip


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
        ttk.Label(
            self,
            text=(
                "Comment les images référencées dans vos billets/pages sont récupérées, "
                "copiées et affichées (agrandissement au clic)."
            ),
            wraplength=680,
            justify="left",
            foreground="#444444",
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=8, pady=(4, 10))

        strategy_entry = _add_row(self, 1, "Stratégie", self.strategy_var)
        add_tooltip(
            strategy_entry,
            "Méthode de récupération des médias référencés dans le contenu : "
            "« copy_local_assets » copie les fichiers déjà présents localement vers "
            "le dossier images de sortie.\n"
            "Exemple : copy_local_assets",
        )

        images_entry = _add_row(self, 2, "Dossier images", self.images_dir_var)
        add_tooltip(
            images_entry,
            "Dossier (relatif à la racine projet) où sont copiées les images utilisées "
            "dans le site généré.\n"
            "Exemple : assets/images",
        )
        images_browse = ttk.Button(self, text="Parcourir...", command=self._browse_images_dir)
        images_browse.grid(row=2, column=2, sticky="w", padx=(0, 8), pady=4)
        add_tooltip(images_browse, "Ouvre un sélecteur pour choisir un dossier existant sur le disque.")

        copy_cb = ttk.Checkbutton(
            self, text="Copier les médias vers la sortie", variable=self.copy_media_var
        )
        copy_cb.grid(row=3, column=0, columnspan=2, sticky="w", padx=8, pady=4)
        add_tooltip(
            copy_cb,
            "Si activé, les images sont copiées dans le dossier de sortie à chaque "
            "génération. À désactiver seulement si vous gérez les images vous-même.",
        )

        clickable_cb = ttk.Checkbutton(
            self,
            text="Figures cliquables",
            variable=self.clickable_figures_var,
        )
        clickable_cb.grid(row=4, column=0, columnspan=2, sticky="w", padx=8, pady=4)
        add_tooltip(
            clickable_cb,
            "Si activé, chaque image insérée dans un article devient cliquable pour "
            "s'afficher en grand (lightbox).",
        )

        group_cb = ttk.Checkbutton(
            self, text="Regrouper les figures par article", variable=self.group_posts_var
        )
        group_cb.grid(row=5, column=0, columnspan=2, sticky="w", padx=8, pady=4)
        add_tooltip(
            group_cb,
            "Si activé, les images d'un même article forment un groupe dans la "
            "visionneuse : on peut naviguer entre elles avec les flèches sans en "
            "sortir. Nécessite le moteur lightbox « fancybox » (onglet Rendu).",
        )

        caption_cb = ttk.Checkbutton(
            self,
            text="Utiliser les légendes comme légendes lightbox",
            variable=self.caption_var,
        )
        caption_cb.grid(row=6, column=0, columnspan=2, sticky="w", padx=8, pady=4)
        add_tooltip(
            caption_cb,
            "Si activé, la légende Markdown d'une image (texte sous l'image) est "
            "réutilisée comme légende dans la visionneuse plein écran.",
        )
        self.grid_columnconfigure(3, weight=1)

    def _browse_images_dir(self) -> None:
        selected = filedialog.askdirectory(
            title="Choisir le dossier images", initialdir=self.images_dir_var.get() or "."
        )
        if selected:
            self.images_dir_var.set(selected)

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


def _add_row(master: tk.Misc, row: int, label: str, variable: tk.StringVar) -> ttk.Entry:
    ttk.Label(master, text=label).grid(row=row, column=0, sticky="w", padx=8, pady=4)
    entry = ttk.Entry(master, textvariable=variable, width=55)
    entry.grid(row=row, column=1, sticky="w", padx=8, pady=4)
    return entry
