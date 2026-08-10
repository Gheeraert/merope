"""Small Tk dialogs used by menu editors."""

from __future__ import annotations

import tkinter as tk
from tkinter import simpledialog, ttk

from bloggen.config.models import MenuLink, SideMenuSection, SideMenuSubSection
from bloggen.ui.tooltip import add_tooltip


class MenuLinkDialog(simpledialog.Dialog):
    _POINTING_INTERNAL = "Lien interne (une page de ce site)"
    _POINTING_EXTERNAL = "Lien externe (un autre site)"
    _PICKER_PLACEHOLDER = "— choisir dans la liste —"

    def __init__(
        self,
        parent: tk.Misc,
        title: str,
        initial: MenuLink | None = None,
        *,
        content_targets: list[tuple[str, str]] | None = None,
    ) -> None:
        self.initial = initial or MenuLink(label="", target="")
        self.content_targets = content_targets or []
        self.result: MenuLink | None = None
        super().__init__(parent, title)

    def body(self, master: tk.Misc) -> tk.Widget:
        self.label_var = tk.StringVar(value=self.initial.label)
        self.target_var = tk.StringVar(value=self.initial.target)
        self.enabled_var = tk.BooleanVar(value=self.initial.enabled)
        self.pointing_type_var = tk.StringVar(
            value=self._POINTING_EXTERNAL if self.initial.target_type == "external" else self._POINTING_INTERNAL
        )
        self._url_by_label = dict(self.content_targets)
        matching_label = next(
            (label for label, url in self.content_targets if url == self.initial.target), ""
        )
        self.picker_var = tk.StringVar(value=matching_label or self._PICKER_PLACEHOLDER)

        label_caption = ttk.Label(master, text="Label")
        label_caption.grid(row=0, column=0, sticky="w", padx=4, pady=4)
        label_entry = ttk.Entry(master, textvariable=self.label_var, width=44)
        label_entry.grid(row=0, column=1, sticky="ew", padx=4, pady=4)
        label_tip = (
            "Texte affiché pour ce lien dans le menu. Obligatoire.\n"
            "Exemple : Accueil"
        )
        add_tooltip(label_caption, label_tip)
        add_tooltip(label_entry, label_tip)

        ttk.Label(master, text="Entrée de menu pointant vers :").grid(
            row=1, column=0, sticky="w", padx=4, pady=4
        )
        pointing_combo = ttk.Combobox(
            master,
            textvariable=self.pointing_type_var,
            values=[self._POINTING_INTERNAL, self._POINTING_EXTERNAL],
            state="readonly",
            width=32,
        )
        pointing_combo.grid(row=1, column=1, sticky="w", padx=4, pady=4)
        pointing_combo.bind("<<ComboboxSelected>>", self._on_pointing_type_changed)
        add_tooltip(
            pointing_combo,
            "Lien interne : une page ou un billet déjà présent sur ce site — "
            "choisissez-le directement dans la liste juste en dessous.\n"
            "Lien externe : un autre site web. Il ne s'ouvre pas ailleurs : la page "
            "générée affiche ce site externe intégré dans un cadre (iframe), en "
            "conservant le menu latéral et le haut de la page de ce site. Certains "
            "sites refusent d'être ainsi intégrés (limite du site externe, pas de ce "
            "logiciel) ; un lien de secours vers le site est alors affiché.",
        )

        self._picker_label = ttk.Label(master, text="Page ou billet")
        self._picker_label.grid(row=2, column=0, sticky="w", padx=4, pady=4)
        self._picker_combo = ttk.Combobox(
            master,
            textvariable=self.picker_var,
            values=[self._PICKER_PLACEHOLDER, *(label for label, _url in self.content_targets)],
            state="readonly",
            width=44,
        )
        self._picker_combo.grid(row=2, column=1, sticky="ew", padx=4, pady=4)
        self._picker_combo.bind("<<ComboboxSelected>>", self._on_picker_changed)
        add_tooltip(
            self._picker_combo,
            "Choisissez la page ou le billet déjà existant vers lequel ce lien doit "
            "pointer. Remplit automatiquement le champ Destination ci-dessous.",
        )

        destination_caption = ttk.Label(master, text="Destination")
        destination_caption.grid(row=3, column=0, sticky="w", padx=4, pady=4)
        target_entry = ttk.Entry(master, textvariable=self.target_var, width=44)
        target_entry.grid(row=3, column=1, sticky="ew", padx=4, pady=4)
        destination_tip = (
            "Chemin ou URL vers laquelle ce lien pointe réellement. Obligatoire. "
            "Rempli automatiquement par le sélecteur ci-dessus pour un lien interne, "
            "mais reste modifiable.\n"
            "- Interne : chemin commençant par / vers une page du site généré.\n"
            "  Exemple : /billets/index.html\n"
            "- Externe : adresse web complète.\n"
            "  Exemple : https://example.org"
        )
        add_tooltip(destination_caption, destination_tip)
        add_tooltip(target_entry, destination_tip)

        enabled_cb = ttk.Checkbutton(master, text="Activé", variable=self.enabled_var)
        enabled_cb.grid(row=4, column=0, sticky="w", padx=4, pady=4)
        add_tooltip(
            enabled_cb,
            "Si décoché, ce lien est conservé dans la configuration mais n'apparaît "
            "pas dans le menu du site généré.",
        )
        master.grid_columnconfigure(1, weight=1)
        self._update_picker_visibility()
        return label_entry

    def _on_pointing_type_changed(self, _event: object = None) -> None:
        self._update_picker_visibility()

    def _update_picker_visibility(self) -> None:
        if self.pointing_type_var.get() == self._POINTING_INTERNAL:
            self._picker_label.grid()
            self._picker_combo.grid()
        else:
            self._picker_label.grid_remove()
            self._picker_combo.grid_remove()

    def _on_picker_changed(self, _event: object = None) -> None:
        selected = self.picker_var.get()
        url = self._url_by_label.get(selected)
        if url is not None:
            self.target_var.set(url)

    def validate(self) -> bool:
        return bool(self.label_var.get().strip()) and bool(self.target_var.get().strip())

    def apply(self) -> None:
        target_type = "internal" if self.pointing_type_var.get() == self._POINTING_INTERNAL else "external"
        self.result = MenuLink(
            label=self.label_var.get().strip(),
            target=self.target_var.get().strip(),
            target_type=target_type,
            enabled=self.enabled_var.get(),
            new_tab=False,
        )


class SideSectionDialog(simpledialog.Dialog):
    _POINTING_NONE = "Aucun (juste un titre de groupe)"
    _POINTING_INTERNAL = "Lien interne (une page de ce site)"
    _POINTING_EXTERNAL = "Lien externe (un autre site)"
    _PICKER_PLACEHOLDER = "— choisir dans la liste —"

    def __init__(
        self,
        parent: tk.Misc,
        title: str,
        initial: SideMenuSection | None = None,
        *,
        content_targets: list[tuple[str, str]] | None = None,
    ) -> None:
        self.initial = initial or SideMenuSection(label="")
        self.content_targets = content_targets or []
        self.result: SideMenuSection | None = None
        super().__init__(parent, title)

    def body(self, master: tk.Misc) -> tk.Widget:
        self.label_var = tk.StringVar(value=self.initial.label)
        self.enabled_var = tk.BooleanVar(value=self.initial.enabled)
        self.target_var = tk.StringVar(value=self.initial.target)
        if (self.initial.target or "").strip():
            default_pointing = self._POINTING_EXTERNAL if self.initial.target_type == "external" else self._POINTING_INTERNAL
        else:
            default_pointing = self._POINTING_NONE
        self.pointing_type_var = tk.StringVar(value=default_pointing)
        self._url_by_label = dict(self.content_targets)
        matching_label = next(
            (label for label, url in self.content_targets if url == self.initial.target), ""
        )
        self.picker_var = tk.StringVar(value=matching_label or self._PICKER_PLACEHOLDER)

        ttk.Label(master, text="Section").grid(row=0, column=0, sticky="w", padx=4, pady=4)
        entry = ttk.Entry(master, textvariable=self.label_var, width=44)
        entry.grid(row=0, column=1, sticky="ew", padx=4, pady=4)
        add_tooltip(
            entry,
            "Titre affiché pour ce groupe de liens dans le menu latéral. Obligatoire.\n"
            "Exemple : Navigation",
        )

        ttk.Label(master, text="Titre de section pointant vers :").grid(
            row=1, column=0, sticky="w", padx=4, pady=4
        )
        pointing_combo = ttk.Combobox(
            master,
            textvariable=self.pointing_type_var,
            values=[self._POINTING_NONE, self._POINTING_INTERNAL, self._POINTING_EXTERNAL],
            state="readonly",
            width=32,
        )
        pointing_combo.grid(row=1, column=1, sticky="w", padx=4, pady=4)
        pointing_combo.bind("<<ComboboxSelected>>", self._on_pointing_type_changed)
        add_tooltip(
            pointing_combo,
            "Aucun : le titre de section n'est pas cliquable, comme aujourd'hui — utile "
            "si vous voulez seulement regrouper des sous-entrées.\n"
            "Lien interne : le titre de section devient lui-même cliquable, vers une "
            "page ou un billet déjà présent — choisissez-le dans la liste juste en "
            "dessous. Fonctionne avec ou sans sous-entrées.\n"
            "Lien externe : le titre de section pointe vers un autre site, intégré "
            "dans un cadre (iframe) en conservant le menu et la bannière de ce site.",
        )

        self._picker_label = ttk.Label(master, text="Page ou billet")
        self._picker_label.grid(row=2, column=0, sticky="w", padx=4, pady=4)
        self._picker_combo = ttk.Combobox(
            master,
            textvariable=self.picker_var,
            values=[self._PICKER_PLACEHOLDER, *(label for label, _url in self.content_targets)],
            state="readonly",
            width=44,
        )
        self._picker_combo.grid(row=2, column=1, sticky="ew", padx=4, pady=4)
        self._picker_combo.bind("<<ComboboxSelected>>", self._on_picker_changed)
        add_tooltip(
            self._picker_combo,
            "Choisissez la page ou le billet déjà existant vers lequel ce titre de "
            "section doit pointer. Remplit automatiquement le champ Destination.",
        )

        self._target_label = ttk.Label(master, text="Destination")
        self._target_label.grid(row=3, column=0, sticky="w", padx=4, pady=4)
        self._target_entry = ttk.Entry(master, textvariable=self.target_var, width=44)
        self._target_entry.grid(row=3, column=1, sticky="ew", padx=4, pady=4)
        add_tooltip(
            self._target_entry,
            "Chemin ou URL vers laquelle ce titre de section pointe réellement. "
            "Rempli automatiquement par le sélecteur ci-dessus pour un lien interne, "
            "mais reste modifiable.\n"
            "- Interne : chemin commençant par / vers une page du site généré.\n"
            "  Exemple : /billets/index.html\n"
            "- Externe : adresse web complète.\n"
            "  Exemple : https://example.org",
        )

        enabled_cb = ttk.Checkbutton(master, text="Activée", variable=self.enabled_var)
        enabled_cb.grid(row=4, column=0, sticky="w", padx=4, pady=4)
        add_tooltip(
            enabled_cb,
            "Si décochée, toute la section (et ses sous-entrées) est masquée dans le "
            "menu du site généré, sans être supprimée de la configuration.",
        )

        self.numbered_var = tk.BooleanVar(value=self.initial.numbered)
        numbered_cb = ttk.Checkbutton(
            master, text="Numérotée (I., II., III. + A., B., C. pour les sous-sections)", variable=self.numbered_var
        )
        numbered_cb.grid(row=5, column=0, columnspan=2, sticky="w", padx=4, pady=4)
        add_tooltip(
            numbered_cb,
            "Si coché, cette section est automatiquement préfixée « I. », « II. », "
            "« III. »... selon sa position parmi les sections numérotées (le numéro "
            "n'est pas tapé dans le titre : il est recalculé à chaque génération). "
            "Ses sous-sections (colonne du milieu -> « + Sous-section ») sont alors "
            "elles-mêmes préfixées « A. », « B. », « C. »... Utile pour un plan de "
            "type « I. Rhétorique / A. Bossuet et la rhétorique chrétienne / "
            "<billets> ».",
        )

        master.grid_columnconfigure(1, weight=1)
        self._update_pointing_fields_visibility()
        return entry

    def _on_pointing_type_changed(self, _event: object = None) -> None:
        self._update_pointing_fields_visibility()

    def _update_pointing_fields_visibility(self) -> None:
        pointing = self.pointing_type_var.get()
        if pointing == self._POINTING_NONE:
            self._picker_label.grid_remove()
            self._picker_combo.grid_remove()
            self._target_label.grid_remove()
            self._target_entry.grid_remove()
            self.target_var.set("")
        elif pointing == self._POINTING_INTERNAL:
            self._picker_label.grid()
            self._picker_combo.grid()
            self._target_label.grid()
            self._target_entry.grid()
        else:
            self._picker_label.grid_remove()
            self._picker_combo.grid_remove()
            self._target_label.grid()
            self._target_entry.grid()

    def _on_picker_changed(self, _event: object = None) -> None:
        selected = self.picker_var.get()
        url = self._url_by_label.get(selected)
        if url is not None:
            self.target_var.set(url)

    def validate(self) -> bool:
        if not self.label_var.get().strip():
            return False
        if self.pointing_type_var.get() != self._POINTING_NONE and not self.target_var.get().strip():
            return False
        return True

    def apply(self) -> None:
        pointing = self.pointing_type_var.get()
        if pointing == self._POINTING_NONE:
            target, target_type = "", "internal"
        else:
            target = self.target_var.get().strip()
            target_type = "internal" if pointing == self._POINTING_INTERNAL else "external"
        self.result = SideMenuSection(
            label=self.label_var.get().strip(),
            enabled=self.enabled_var.get(),
            target=target,
            target_type=target_type,
            numbered=self.numbered_var.get(),
            children=list(self.initial.children),
            subsections=list(self.initial.subsections),
        )


class SideSubSectionDialog(simpledialog.Dialog):
    """Third menu level: a lettered (A., B., C.) group nested inside a
    numbered ``SideMenuSection``, holding its own leaf links. Deliberately
    close to :class:`SideSectionDialog` minus the "numbered" checkbox —
    lettering is inherited from the parent section, not set per subsection.
    """

    _POINTING_NONE = "Aucun (juste un titre de groupe)"
    _POINTING_INTERNAL = "Lien interne (une page de ce site)"
    _POINTING_EXTERNAL = "Lien externe (un autre site)"
    _PICKER_PLACEHOLDER = "— choisir dans la liste —"

    def __init__(
        self,
        parent: tk.Misc,
        title: str,
        initial: SideMenuSubSection | None = None,
        *,
        content_targets: list[tuple[str, str]] | None = None,
    ) -> None:
        self.initial = initial or SideMenuSubSection(label="")
        self.content_targets = content_targets or []
        self.result: SideMenuSubSection | None = None
        super().__init__(parent, title)

    def body(self, master: tk.Misc) -> tk.Widget:
        self.label_var = tk.StringVar(value=self.initial.label)
        self.enabled_var = tk.BooleanVar(value=self.initial.enabled)
        self.target_var = tk.StringVar(value=self.initial.target)
        if (self.initial.target or "").strip():
            default_pointing = self._POINTING_EXTERNAL if self.initial.target_type == "external" else self._POINTING_INTERNAL
        else:
            default_pointing = self._POINTING_NONE
        self.pointing_type_var = tk.StringVar(value=default_pointing)
        self._url_by_label = dict(self.content_targets)
        matching_label = next(
            (label for label, url in self.content_targets if url == self.initial.target), ""
        )
        self.picker_var = tk.StringVar(value=matching_label or self._PICKER_PLACEHOLDER)

        ttk.Label(master, text="Sous-section").grid(row=0, column=0, sticky="w", padx=4, pady=4)
        entry = ttk.Entry(master, textvariable=self.label_var, width=44)
        entry.grid(row=0, column=1, sticky="ew", padx=4, pady=4)
        add_tooltip(
            entry,
            "Titre affiché pour ce sous-groupe de liens, sous la section. Obligatoire.\n"
            "Exemple : Bossuet et la rhétorique chrétienne",
        )

        ttk.Label(master, text="Titre de sous-section pointant vers :").grid(
            row=1, column=0, sticky="w", padx=4, pady=4
        )
        pointing_combo = ttk.Combobox(
            master,
            textvariable=self.pointing_type_var,
            values=[self._POINTING_NONE, self._POINTING_INTERNAL, self._POINTING_EXTERNAL],
            state="readonly",
            width=32,
        )
        pointing_combo.grid(row=1, column=1, sticky="w", padx=4, pady=4)
        pointing_combo.bind("<<ComboboxSelected>>", self._on_pointing_type_changed)
        add_tooltip(
            pointing_combo,
            "Aucun : le titre de sous-section n'est pas cliquable — utile si vous "
            "voulez seulement regrouper des billets sous cette lettre.\n"
            "Lien interne : le titre de sous-section devient lui-même cliquable, vers "
            "une page ou un billet déjà présent.\n"
            "Lien externe : le titre de sous-section pointe vers un autre site, "
            "intégré dans un cadre (iframe).",
        )

        self._picker_label = ttk.Label(master, text="Page ou billet")
        self._picker_label.grid(row=2, column=0, sticky="w", padx=4, pady=4)
        self._picker_combo = ttk.Combobox(
            master,
            textvariable=self.picker_var,
            values=[self._PICKER_PLACEHOLDER, *(label for label, _url in self.content_targets)],
            state="readonly",
            width=44,
        )
        self._picker_combo.grid(row=2, column=1, sticky="ew", padx=4, pady=4)
        self._picker_combo.bind("<<ComboboxSelected>>", self._on_picker_changed)
        add_tooltip(
            self._picker_combo,
            "Choisissez la page ou le billet déjà existant vers lequel ce titre de "
            "sous-section doit pointer. Remplit automatiquement le champ Destination.",
        )

        self._target_label = ttk.Label(master, text="Destination")
        self._target_label.grid(row=3, column=0, sticky="w", padx=4, pady=4)
        self._target_entry = ttk.Entry(master, textvariable=self.target_var, width=44)
        self._target_entry.grid(row=3, column=1, sticky="ew", padx=4, pady=4)
        add_tooltip(
            self._target_entry,
            "Chemin ou URL vers laquelle ce titre de sous-section pointe réellement. "
            "Rempli automatiquement par le sélecteur ci-dessus pour un lien interne, "
            "mais reste modifiable.\n"
            "- Interne : chemin commençant par / vers une page du site généré.\n"
            "  Exemple : /billets/index.html\n"
            "- Externe : adresse web complète.\n"
            "  Exemple : https://example.org",
        )

        enabled_cb = ttk.Checkbutton(master, text="Activée", variable=self.enabled_var)
        enabled_cb.grid(row=4, column=0, sticky="w", padx=4, pady=4)
        add_tooltip(
            enabled_cb,
            "Si décochée, cette sous-section (et ses billets) est masquée dans le "
            "menu du site généré, sans être supprimée de la configuration.",
        )
        master.grid_columnconfigure(1, weight=1)
        self._update_pointing_fields_visibility()
        return entry

    def _on_pointing_type_changed(self, _event: object = None) -> None:
        self._update_pointing_fields_visibility()

    def _update_pointing_fields_visibility(self) -> None:
        pointing = self.pointing_type_var.get()
        if pointing == self._POINTING_NONE:
            self._picker_label.grid_remove()
            self._picker_combo.grid_remove()
            self._target_label.grid_remove()
            self._target_entry.grid_remove()
            self.target_var.set("")
        elif pointing == self._POINTING_INTERNAL:
            self._picker_label.grid()
            self._picker_combo.grid()
            self._target_label.grid()
            self._target_entry.grid()
        else:
            self._picker_label.grid_remove()
            self._picker_combo.grid_remove()
            self._target_label.grid()
            self._target_entry.grid()

    def _on_picker_changed(self, _event: object = None) -> None:
        selected = self.picker_var.get()
        url = self._url_by_label.get(selected)
        if url is not None:
            self.target_var.set(url)

    def validate(self) -> bool:
        if not self.label_var.get().strip():
            return False
        if self.pointing_type_var.get() != self._POINTING_NONE and not self.target_var.get().strip():
            return False
        return True

    def apply(self) -> None:
        pointing = self.pointing_type_var.get()
        if pointing == self._POINTING_NONE:
            target, target_type = "", "internal"
        else:
            target = self.target_var.get().strip()
            target_type = "internal" if pointing == self._POINTING_INTERNAL else "external"
        self.result = SideMenuSubSection(
            label=self.label_var.get().strip(),
            enabled=self.enabled_var.get(),
            target=target,
            target_type=target_type,
            children=list(self.initial.children),
        )


def ask_menu_link(
    parent: tk.Misc,
    title: str,
    initial: MenuLink | None = None,
    *,
    content_targets: list[tuple[str, str]] | None = None,
) -> MenuLink | None:
    dialog = MenuLinkDialog(parent, title=title, initial=initial, content_targets=content_targets)
    return dialog.result


def ask_side_section(
    parent: tk.Misc,
    title: str,
    initial: SideMenuSection | None = None,
    *,
    content_targets: list[tuple[str, str]] | None = None,
) -> SideMenuSection | None:
    dialog = SideSectionDialog(parent, title=title, initial=initial, content_targets=content_targets)
    return dialog.result


def ask_side_subsection(
    parent: tk.Misc,
    title: str,
    initial: SideMenuSubSection | None = None,
    *,
    content_targets: list[tuple[str, str]] | None = None,
) -> SideMenuSubSection | None:
    dialog = SideSubSectionDialog(parent, title=title, initial=initial, content_targets=content_targets)
    return dialog.result
