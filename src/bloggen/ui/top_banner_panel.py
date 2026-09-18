"""Settings for the optional, unmodified image above the site banner."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from bloggen.config.models import TopBannerConfig
from bloggen.ui.banner_panel import _copy_into_dir
from bloggen.ui.tooltip import add_tooltip


class TopBannerPanel(ttk.Frame):
    def __init__(
        self,
        master: tk.Misc,
        *,
        resolve_assets_root: Callable[[], tuple[Path, str]],
    ) -> None:
        super().__init__(master)
        self._resolve_assets_root = resolve_assets_root
        self.enabled_var = tk.BooleanVar(value=False)
        self.image_var = tk.StringVar(value="")
        self.alt_var = tk.StringVar(value="")
        self.link_var = tk.StringVar(value="")
        self._build_ui()

    def _build_ui(self) -> None:
        ttk.Label(
            self,
            text=(
                "Bandeau institutionnel facultatif affiché tout en haut du site.\n"
                "L’image est conservée telle quelle, alignée à gauche sur fond blanc.\n"
                "MÉROPE ne modifie ni ses couleurs ni ses proportions."
            ),
            wraplength=680,
            justify="left",
            foreground="#444444",
        ).grid(row=0, column=0, columnspan=3, sticky="w", padx=8, pady=(4, 10))

        ttk.Checkbutton(
            self, text="Activer le bandeau supérieur", variable=self.enabled_var
        ).grid(row=1, column=0, columnspan=3, sticky="w", padx=8, pady=6)

        image_entry = self._entry_row(2, "Image", self.image_var)
        add_tooltip(
            image_entry,
            "Image affichée tout en haut du site. Elle est copiée dans les assets du projet "
            "sans recadrage ni redimensionnement.\nExemple : assets/top-banner/institution.png",
        )
        browse = ttk.Button(self, text="Parcourir...", command=self._browse_image)
        browse.grid(row=2, column=2, sticky="w", padx=(0, 8), pady=4)
        add_tooltip(browse, "Choisir une image à copier telle quelle dans les assets du projet.")

        alt_entry = self._entry_row(3, "Texte alt", self.alt_var)
        add_tooltip(
            alt_entry,
            "Texte alternatif décrivant l’image pour l’accessibilité.\n"
            "Exemple : Université de Rouen Normandie",
        )

        link_entry = self._entry_row(4, "Lien", self.link_var)
        add_tooltip(
            link_entry,
            "Lien facultatif ouvert lorsqu’on clique sur le bandeau.\n"
            "Peut être une URL externe complète ou un chemin interne.\n"
            "Laisser vide pour une image non cliquable.",
        )
        self.grid_columnconfigure(1, weight=1)

    def _entry_row(self, row: int, label: str, variable: tk.StringVar) -> ttk.Entry:
        ttk.Label(self, text=label).grid(row=row, column=0, sticky="w", padx=8, pady=4)
        entry = ttk.Entry(self, textvariable=variable, width=55)
        entry.grid(row=row, column=1, sticky="ew", padx=8, pady=4)
        return entry

    def _browse_image(self) -> None:
        selected = filedialog.askopenfilename(
            title="Choisir une image de bandeau supérieur",
            initialdir=Path(self.image_var.get()).parent if self.image_var.get() else ".",
            filetypes=[
                ("Images", "*.png *.jpg *.jpeg *.gif *.webp"),
                ("Tous les fichiers", "*.*"),
            ],
        )
        if not selected:
            return

        try:
            project_root, assets_dir = self._resolve_assets_root()
            destination_dir = (project_root / assets_dir / "top-banner").resolve()
            copied = _copy_into_dir(Path(selected), destination_dir)
            relative_path = copied.relative_to(project_root.resolve())
        except (OSError, ValueError) as exc:
            messagebox.showerror("Bandeau supérieur", f"Copie de l’image impossible :\n{exc}")
            return
        self.image_var.set(relative_path.as_posix())

    def set_data(self, top_banner: TopBannerConfig) -> None:
        self.enabled_var.set(top_banner.enabled)
        self.image_var.set(top_banner.image)
        self.alt_var.set(top_banner.alt)
        self.link_var.set(top_banner.link)

    def get_data(self) -> TopBannerConfig:
        return TopBannerConfig(
            enabled=self.enabled_var.get(),
            image=self.image_var.get().strip(),
            alt=self.alt_var.get().strip(),
            link=self.link_var.get().strip(),
        )
