"""« Référencement » tab: search-engine verification files.

Files chosen here are copied into ``<project_root>/root-files/`` (never
referenced by their original location) and their bare names stored in
``seo.verification_files``. The build copies them to the site root.
"""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from bloggen.build.verification_files import (
    ROOT_FILES_DIRNAME,
    VerificationFileExistsError,
    check_verification_filename,
    delete_local_copy,
    import_verification_file,
)
from bloggen.config.models import SeoConfig
from bloggen.ui.tooltip import add_tooltip

_FILETYPES = [
    ("Fichiers de validation (*.html, *.xml, *.txt)", "*.html *.xml *.txt"),
    ("Tous les fichiers", "*.*"),
]


class SeoPanel(ttk.Frame):
    def __init__(
        self,
        master: tk.Misc,
        *,
        resolve_project_root: Callable[[], Path | None],
        pick_file: Callable[[], str] | None = None,
        confirm_overwrite: Callable[[str], bool] | None = None,
        ask_delete_copy: Callable[[str], bool | None] | None = None,
        show_error: Callable[[str], None] | None = None,
    ) -> None:
        """``resolve_project_root`` is called lazily, at click time (the
        Chemins tab that owns ``project_root`` can change at any moment).
        The remaining callables replace the native dialogs (for tests)."""
        super().__init__(master)
        self._resolve_project_root = resolve_project_root
        self._pick_file = pick_file or self._default_pick_file
        self._confirm_overwrite = confirm_overwrite or self._default_confirm_overwrite
        self._ask_delete_copy = ask_delete_copy or self._default_ask_delete_copy
        self._show_error = show_error or (lambda msg: messagebox.showerror("Référencement", msg))
        self._files: list[str] = []
        self._build_ui()

    # -- data bridge (same shape as the other panels) ------------------------

    def set_data(self, config: SeoConfig) -> None:
        self._files = list(config.verification_files)
        self._refresh()

    def get_data(self) -> SeoConfig:
        return SeoConfig(verification_files=list(self._files))

    # -- UI -----------------------------------------------------------------

    def _build_ui(self) -> None:
        ttk.Label(
            self,
            text=(
                "Référencement du site. Les fichiers de validation (Google Search Console, "
                "Bing…) sont conservés dans le dossier « "
                f"{ROOT_FILES_DIRNAME}/ » du projet et recopiés à la racine du site à chaque "
                "génération : le dossier de sortie reste jetable. Les options sitemap.xml et "
                "robots.txt se règlent dans l'onglet Génération."
            ),
            wraplength=680,
            justify="left",
            foreground="#444444",
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=8, pady=(4, 10))

        ttk.Label(self, text="Fichiers de validation des moteurs de recherche").grid(
            row=1, column=0, columnspan=2, sticky="w", padx=8
        )
        self.listbox = tk.Listbox(self, height=8, width=60, exportselection=False)
        self.listbox.grid(row=2, column=0, rowspan=3, sticky="nsew", padx=8, pady=4)

        self.add_button = ttk.Button(self, text="Ajouter un fichier…", command=self.on_add_clicked)
        self.add_button.grid(row=2, column=1, sticky="new", padx=(0, 8), pady=4)
        add_tooltip(
            self.add_button,
            "Choisit le fichier fourni par le service (ex. google123456789abcdef.html) et "
            f"en garde une copie exacte dans {ROOT_FILES_DIRNAME}/.",
        )
        self.remove_button = ttk.Button(self, text="Supprimer", command=self.on_remove_clicked)
        self.remove_button.grid(row=3, column=1, sticky="new", padx=(0, 8), pady=4)
        add_tooltip(
            self.remove_button,
            "Retire le fichier sélectionné de la configuration ; une confirmation propose "
            "de supprimer aussi sa copie dans le projet.",
        )
        self.columnconfigure(0, weight=1)

    def _refresh(self) -> None:
        self.listbox.delete(0, "end")
        for name in self._files:
            self.listbox.insert("end", name)

    # -- actions ------------------------------------------------------------

    def on_add_clicked(self) -> None:
        selected = self._pick_file()
        if selected:
            self.add_file(Path(selected))

    def add_file(self, source: Path) -> bool:
        """Copy ``source`` into root-files/ and register its bare name.
        False if refused or cancelled."""
        try:
            project_root = self._resolve_project_root()
        except Exception as exc:  # never let a callback error escape a button handler
            self._show_error(f"Racine du projet indéterminée :\n{exc}")
            return False
        if project_root is None:
            self._show_error(
                "Créez ou enregistrez d'abord le projet avant d'ajouter un fichier de validation."
            )
            return False
        name = source.name
        problem = check_verification_filename(name)
        if problem:
            self._show_error(f"Fichier refusé : {problem}")
            return False
        try:
            try:
                import_verification_file(source, project_root)
            except VerificationFileExistsError:
                if not self._confirm_overwrite(name):
                    return False
                import_verification_file(source, project_root, overwrite=True)
        except (OSError, ValueError) as exc:
            self._show_error(f"Impossible d'importer le fichier :\n{exc}")
            return False
        if name not in self._files:
            self._files.append(name)
        self._refresh()
        return True

    def on_remove_clicked(self) -> None:
        selection = self.listbox.curselection()
        if selection:
            self.remove_file(self._files[selection[0]])

    def remove_file(self, name: str) -> bool:
        """Unregister ``name``; the local copy in root-files/ is deleted
        only if the user says so. False if the user cancelled."""
        if name not in self._files:
            return False
        choice = self._ask_delete_copy(name)
        if choice is None:
            return False
        if choice:
            try:
                project_root = self._resolve_project_root()
                if project_root is None:
                    raise ValueError("racine du projet indéterminée")
                delete_local_copy(name, project_root)
            except Exception as exc:
                self._show_error(f"Copie locale non supprimée :\n{exc}")
        self._files.remove(name)
        self._refresh()
        return True

    # -- native dialogs -----------------------------------------------------

    def _default_pick_file(self) -> str:
        return filedialog.askopenfilename(
            parent=self, title="Choisir un fichier de validation", filetypes=_FILETYPES
        )

    def _default_confirm_overwrite(self, name: str) -> bool:
        return messagebox.askyesno(
            "Référencement",
            f"« {name} » existe déjà dans {ROOT_FILES_DIRNAME}/.\nLe remplacer ?",
            parent=self,
        )

    def _default_ask_delete_copy(self, name: str) -> bool | None:
        return messagebox.askyesnocancel(
            "Référencement",
            f"Retirer « {name} » de la configuration.\n\n"
            f"Supprimer aussi sa copie dans {ROOT_FILES_DIRNAME}/ ?\n"
            "Oui : la copie est supprimée. Non : elle est conservée dans le projet.",
            parent=self,
        )
