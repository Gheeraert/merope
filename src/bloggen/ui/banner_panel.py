"""Banner settings panel."""

from __future__ import annotations

import shutil
import tkinter as tk
from collections.abc import Callable
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageOps

from bloggen.config.models import BannerConfig
from bloggen.ui.tooltip import add_tooltip

# Matches --page-max-width in the generated site's CSS: the banner is
# displayed at most this wide, so resizing to it (rather than the source
# image's own, possibly much larger, resolution) avoids serving an
# oversized file for no visual gain.
_DISPLAY_WIDTH_PX = 1260


class BannerPanel(ttk.Frame):
    def __init__(
        self,
        master: tk.Misc,
        *,
        resolve_assets_root: Callable[[], tuple[Path, str]] | None = None,
    ) -> None:
        """``resolve_assets_root`` is called lazily (only when the user
        actually picks an image), not at construction time — the Chemins
        tab (which owns ``project_root``/``assets_dir``) is typically built
        after this panel. It must return ``(project_root, assets_dir)``.
        Without it, a resized image is still written next to the source
        file, just not copied into the project's own assets folder.
        """
        super().__init__(master)
        self._resolve_assets_root = resolve_assets_root
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
        image_browse = ttk.Button(self, text="Parcourir...", command=self._browse_image)
        image_browse.grid(row=2, column=2, sticky="w", padx=(0, 8), pady=4)
        add_tooltip(
            image_browse,
            "Ouvre un sélecteur pour choisir une image existante sur le disque. Propose "
            "ensuite de la redimensionner aux dimensions d'affichage de la bannière, pour "
            "éviter un rendu inattendu si l'image d'origine est beaucoup plus grande ou "
            "n'a pas les mêmes proportions (ex. bannière qui paraît noire faute de bien "
            "remplir la hauteur configurée).",
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
        self.grid_columnconfigure(3, weight=1)

    def _browse_image(self) -> None:
        selected = filedialog.askopenfilename(
            title="Choisir une image de bannière",
            initialdir=Path(self.image_var.get()).parent if self.image_var.get() else ".",
            filetypes=[
                ("Images", "*.jpg *.jpeg *.png *.gif *.webp"),
                ("Tous les fichiers", "*.*"),
            ],
        )
        if not selected:
            return
        source = Path(selected)

        target_height = max(self.height_var.get(), 1)
        final_path = source
        if messagebox.askyesno(
            "Bannière",
            "Redimensionner cette image aux dimensions d'affichage de la bannière "
            f"({_DISPLAY_WIDTH_PX}×{target_height} px) ?\n\n"
            "Recommandé si l'image d'origine est beaucoup plus grande, ou n'a pas les "
            "mêmes proportions : évite un rendu inattendu (ex. bannière qui paraît "
            "noire faute de bien remplir la hauteur configurée) et réduit le poids du "
            "fichier. L'image d'origine n'est jamais modifiée, une copie est créée.",
        ):
            try:
                final_path = _resize_banner_image(source, _DISPLAY_WIDTH_PX, target_height)
            except OSError as exc:
                messagebox.showerror("Bannière", f"Redimensionnement impossible :\n{exc}")
                final_path = source

        if self._resolve_assets_root is not None:
            try:
                project_root, assets_dir = self._resolve_assets_root()
                banner_dir = (project_root / assets_dir / "banner").resolve()
                copied = _copy_into_dir(final_path, banner_dir)
                final_path = copied.relative_to(project_root.resolve())
            except (OSError, ValueError) as exc:
                messagebox.showwarning(
                    "Bannière",
                    f"L'image a été préparée mais pas copiée dans le dossier du projet "
                    f"({exc}). Ajustez le champ Image manuellement si besoin.",
                )

        self.image_var.set(str(final_path).replace("\\", "/"))

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


def _resize_banner_image(source: Path, width: int, height: int) -> Path:
    """Cover-fit ``source`` to exactly ``width``x``height`` (same crop
    logic as the generated site's own CSS ``object-fit: cover``, but baked
    into a real file instead of computed live by the browser) and save it
    as a new file next to the source. Never overwrites the source.
    """
    with Image.open(source) as opened:
        image = ImageOps.exif_transpose(opened) or opened
        fitted = ImageOps.fit(image, (width, height), method=Image.LANCZOS)
        suffix = source.suffix or ".jpg"
        destination = source.with_name(f"{source.stem}-banniere{suffix}")
        counter = 2
        while destination.exists():
            destination = source.with_name(f"{source.stem}-banniere-{counter}{suffix}")
            counter += 1
        fitted.convert("RGB").save(destination)
    return destination


def _copy_into_dir(source: Path, directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / source.name
    counter = 2
    while destination.exists() and source.resolve() != destination.resolve():
        destination = directory / f"{source.stem}-{counter}{source.suffix}"
        counter += 1
    if not destination.exists():
        shutil.copyfile(source, destination)
    return destination


def _add_entry_row(
    master: tk.Misc,
    row: int,
    label: str,
    variable: tk.StringVar | tk.IntVar,
) -> ttk.Entry:
    ttk.Label(master, text=label).grid(row=row, column=0, sticky="w", padx=8, pady=4)
    entry = ttk.Entry(master, textvariable=variable, width=55)
    entry.grid(row=row, column=1, sticky="w", padx=8, pady=4)
    return entry
