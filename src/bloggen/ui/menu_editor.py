"""Top and side menu editors + pure manipulation helpers."""

from __future__ import annotations

from typing import Callable
import tkinter as tk
from tkinter import messagebox, ttk

from bloggen.config.models import MenuLink, SideMenuSection, SideMenuSubSection
from bloggen.ui.dialogs import ask_menu_link, ask_side_section, ask_side_subsection
from bloggen.ui.tooltip import add_tooltip


def add_top_menu_item(items: list[MenuLink], item: MenuLink) -> None:
    items.append(item)


def update_top_menu_item(items: list[MenuLink], index: int, item: MenuLink) -> None:
    items[index] = item


def remove_top_menu_item(items: list[MenuLink], index: int) -> MenuLink:
    return items.pop(index)


def move_top_menu_item_up(items: list[MenuLink], index: int) -> int:
    return _move_up(items, index)


def move_top_menu_item_down(items: list[MenuLink], index: int) -> int:
    return _move_down(items, index)


def toggle_top_menu_item(items: list[MenuLink], index: int) -> None:
    item = items[index]
    items[index] = MenuLink(
        label=item.label,
        target=item.target,
        target_type=item.target_type,
        enabled=not item.enabled,
        new_tab=item.new_tab,
    )


def add_side_section(sections: list[SideMenuSection], section: SideMenuSection) -> None:
    sections.append(section)


def update_side_section(sections: list[SideMenuSection], index: int, section: SideMenuSection) -> None:
    sections[index] = section


def remove_side_section(sections: list[SideMenuSection], index: int) -> SideMenuSection:
    return sections.pop(index)


def move_side_section_up(sections: list[SideMenuSection], index: int) -> int:
    return _move_up(sections, index)


def move_side_section_down(sections: list[SideMenuSection], index: int) -> int:
    return _move_down(sections, index)


def toggle_side_section(sections: list[SideMenuSection], index: int) -> None:
    section = sections[index]
    sections[index] = SideMenuSection(
        label=section.label,
        enabled=not section.enabled,
        target=section.target,
        target_type=section.target_type,
        numbered=section.numbered,
        children=list(section.children),
        subsections=list(section.subsections),
    )


def add_side_subsection(section: SideMenuSection, subsection: SideMenuSubSection) -> None:
    section.subsections.append(subsection)


def update_side_subsection(section: SideMenuSection, index: int, subsection: SideMenuSubSection) -> None:
    section.subsections[index] = subsection


def remove_side_subsection(section: SideMenuSection, index: int) -> SideMenuSubSection:
    return section.subsections.pop(index)


def move_side_subsection_up(section: SideMenuSection, index: int) -> int:
    return _move_up(section.subsections, index)


def move_side_subsection_down(section: SideMenuSection, index: int) -> int:
    return _move_down(section.subsections, index)


def toggle_side_subsection(section: SideMenuSection, index: int) -> None:
    subsection = section.subsections[index]
    section.subsections[index] = SideMenuSubSection(
        label=subsection.label,
        enabled=not subsection.enabled,
        target=subsection.target,
        target_type=subsection.target_type,
        children=list(subsection.children),
    )


# The following also work unmodified on a ``SideMenuSubSection`` (duck-typed
# on ``.children`): a subsection's leaf links are managed the same way as a
# section's direct children.
def add_side_child(section: SideMenuSection | SideMenuSubSection, child: MenuLink) -> None:
    section.children.append(child)


def update_side_child(section: SideMenuSection | SideMenuSubSection, index: int, child: MenuLink) -> None:
    section.children[index] = child


def remove_side_child(section: SideMenuSection | SideMenuSubSection, index: int) -> MenuLink:
    return section.children.pop(index)


def move_side_child_up(section: SideMenuSection | SideMenuSubSection, index: int) -> int:
    return _move_up(section.children, index)


def move_side_child_down(section: SideMenuSection | SideMenuSubSection, index: int) -> int:
    return _move_down(section.children, index)


def toggle_side_child(section: SideMenuSection | SideMenuSubSection, index: int) -> None:
    child = section.children[index]
    section.children[index] = MenuLink(
        label=child.label,
        target=child.target,
        target_type=child.target_type,
        enabled=not child.enabled,
        new_tab=child.new_tab,
    )


def _move_up(items: list[object], index: int) -> int:
    if index <= 0 or index >= len(items):
        return index
    items[index - 1], items[index] = items[index], items[index - 1]
    return index - 1


def _move_down(items: list[object], index: int) -> int:
    if index < 0 or index >= len(items) - 1:
        return index
    items[index + 1], items[index] = items[index], items[index + 1]
    return index + 1


def _clone_menu_link(item: MenuLink) -> MenuLink:
    return MenuLink(
        label=item.label,
        target=item.target,
        target_type=item.target_type,
        enabled=item.enabled,
        new_tab=item.new_tab,
    )


def _clone_side_subsection(subsection: SideMenuSubSection) -> SideMenuSubSection:
    return SideMenuSubSection(
        label=subsection.label,
        enabled=subsection.enabled,
        target=subsection.target,
        target_type=subsection.target_type,
        children=[_clone_menu_link(child) for child in subsection.children],
    )


class TopMenuEditor(ttk.Frame):
    def __init__(
        self,
        master: tk.Misc,
        *,
        get_content_targets: Callable[[], list[tuple[str, str]]] | None = None,
    ) -> None:
        super().__init__(master)
        self.items: list[MenuLink] = []
        self._get_content_targets = get_content_targets or (lambda: [])
        self._build_ui()

    def _build_ui(self) -> None:
        ttk.Label(
            self,
            text=(
                "Liens affichés dans la barre de menu en haut de chaque page (ex. Accueil, "
                "Billets). L'ordre de la liste est l'ordre d'affichage."
            ),
            wraplength=680,
            justify="left",
            foreground="#444444",
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=8, pady=(4, 8))

        self.listbox = tk.Listbox(self, height=12, exportselection=False)
        self.listbox.grid(row=1, column=0, rowspan=7, sticky="nsew", padx=8, pady=8)
        add_tooltip(
            self.listbox,
            "Chaque ligne est un lien de menu : [ON/OFF] Label -> Cible. "
            "Sélectionnez une ligne puis utilisez les boutons à droite.",
        )

        buttons = [
            (
                "Ajouter",
                self._add_item,
                "Ouvre une fenêtre pour créer un nouveau lien de menu (label, page/site "
                "de destination, activé).",
            ),
            (
                "Modifier",
                self._edit_item,
                "Édite le lien actuellement sélectionné dans la liste.",
            ),
            (
                "Supprimer",
                self._delete_item,
                "Retire définitivement le lien sélectionné du menu.",
            ),
            (
                "Monter",
                self._move_up,
                "Déplace le lien sélectionné d'une position vers le haut (affiché plus tôt).",
            ),
            (
                "Descendre",
                self._move_down,
                "Déplace le lien sélectionné d'une position vers le bas (affiché plus tard).",
            ),
            (
                "Activer/Désactiver",
                self._toggle_item,
                "Active ou désactive le lien sans le supprimer : un lien désactivé "
                "n'apparaît pas dans le menu du site généré.",
            ),
        ]
        for idx, (label, callback, help_text) in enumerate(buttons):
            button = ttk.Button(self, text=label, command=callback)
            button.grid(row=idx + 1, column=1, sticky="ew", padx=8, pady=4)
            add_tooltip(button, help_text)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(7, weight=1)

    def get_items(self) -> list[MenuLink]:
        return [_clone_menu_link(item) for item in self.items]

    def set_items(self, items: list[MenuLink]) -> None:
        self.items = [_clone_menu_link(item) for item in items]
        self._refresh()

    def _refresh(self) -> None:
        self.listbox.delete(0, tk.END)
        for item in self.items:
            marker = "ON" if item.enabled else "OFF"
            self.listbox.insert(tk.END, f"[{marker}] {item.label} -> {item.target}")

    def _selected_index(self) -> int | None:
        selected = self.listbox.curselection()
        if not selected:
            return None
        return int(selected[0])

    def _add_item(self) -> None:
        item = ask_menu_link(self, "Ajouter un item de menu", content_targets=self._get_content_targets())
        if item is None:
            return
        add_top_menu_item(self.items, item)
        self._refresh()
        self.listbox.selection_set(tk.END)

    def _edit_item(self) -> None:
        index = self._selected_index()
        if index is None:
            return
        edited = ask_menu_link(
            self, "Modifier un item de menu", self.items[index], content_targets=self._get_content_targets()
        )
        if edited is None:
            return
        update_top_menu_item(self.items, index, edited)
        self._refresh()
        self.listbox.selection_set(index)

    def _delete_item(self) -> None:
        index = self._selected_index()
        if index is None:
            return
        remove_top_menu_item(self.items, index)
        self._refresh()

    def _move_up(self) -> None:
        index = self._selected_index()
        if index is None:
            return
        new_index = move_top_menu_item_up(self.items, index)
        self._refresh()
        self.listbox.selection_set(new_index)

    def _move_down(self) -> None:
        index = self._selected_index()
        if index is None:
            return
        new_index = move_top_menu_item_down(self.items, index)
        self._refresh()
        self.listbox.selection_set(new_index)

    def _toggle_item(self) -> None:
        index = self._selected_index()
        if index is None:
            return
        toggle_top_menu_item(self.items, index)
        self._refresh()
        self.listbox.selection_set(index)


class SideMenuEditor(ttk.Frame):
    def __init__(
        self,
        master: tk.Misc,
        *,
        get_content_targets: Callable[[], list[tuple[str, str]]] | None = None,
    ) -> None:
        super().__init__(master)
        self.sections: list[SideMenuSection] = []
        self.title_var = tk.StringVar(value="")
        # Parallel to child_list's rows: ("child", index-in-section.children)
        # or ("subsection", index-in-section.subsections).
        self._middle_rows: list[tuple[str, int]] = []
        self._get_content_targets = get_content_targets or (lambda: [])
        self._build_ui()

    def _build_ui(self) -> None:
        ttk.Label(self, text="Titre du menu").grid(row=0, column=0, sticky="w", padx=8, pady=(8, 4))
        title_entry = ttk.Entry(self, textvariable=self.title_var, width=40)
        title_entry.grid(row=0, column=1, columnspan=3, sticky="w", padx=8, pady=(8, 4))
        add_tooltip(
            title_entry,
            "Titre facultatif affiché en tête du menu latéral sur le site généré, dans "
            "une mise en forme discrète qui le distingue des sections en dessous "
            "(ex. « Menu », « Sommaire »). Laissez vide pour ne rien afficher.\n"
            "Exemple : Menu",
        )

        ttk.Label(
            self,
            text=(
                "Menu affiché sur le côté des pages, organisé en trois niveaux : "
                "1) créez d'abord une ou plusieurs « sections » (colonne de gauche, "
                "ex. « Rhétorique ») avec le bouton « + Section » ; "
                "2) sélectionnez une section pour lui ajouter, colonne du milieu, des "
                "sous-entrées cliquables directes (« + Billet ») et/ou des "
                "sous-sections (« + Sous-section », ex. « Bossuet et la rhétorique "
                "chrétienne »), qui regroupent elles-mêmes des liens ; "
                "3) sélectionnez une sous-section pour lui ajouter des billets/pages, "
                "colonne de droite (« + Billet »). Aucun niveau n'est obligatoire au-delà "
                "des sections : une section seule (sans rien en dessous) fonctionne déjà "
                "comme un lien de menu simple. Cochez « Numérotée » en créant/modifiant "
                "une section pour préfixer automatiquement son titre « I. », « II. »... "
                "et ses sous-sections « A. », « B. »... — utile pour un plan du type "
                "« I. Rhétorique / A. Bossuet et la rhétorique chrétienne / <billets> »."
            ),
            wraplength=900,
            justify="left",
            foreground="#444444",
        ).grid(row=1, column=0, columnspan=6, sticky="w", padx=8, pady=(4, 8))

        ttk.Label(self, text="1. Sections", font=("TkDefaultFont", 9, "bold")).grid(
            row=2, column=0, sticky="w", padx=8
        )
        ttk.Label(
            self,
            text="2. Sous-entrées / sous-sections de la section sélectionnée",
            font=("TkDefaultFont", 9, "bold"),
        ).grid(row=2, column=2, sticky="w", padx=8)
        ttk.Label(
            self,
            text="3. Billets de la sous-section sélectionnée",
            font=("TkDefaultFont", 9, "bold"),
        ).grid(row=2, column=4, sticky="w", padx=8)

        self.section_list = tk.Listbox(self, height=14, exportselection=False)
        self.section_list.grid(row=3, column=0, rowspan=8, sticky="nsew", padx=8, pady=(2, 8))
        self.section_list.bind("<<ListboxSelect>>", self._on_section_select)
        add_tooltip(
            self.section_list,
            "Liste des sections du menu latéral : [ON/OFF] Nom de section (-> destination "
            "si le titre de section est lui-même un lien). "
            "Sélectionnez une section pour voir/éditer son contenu au milieu.",
        )

        self.child_list = tk.Listbox(self, height=14, exportselection=False)
        self.child_list.grid(row=3, column=2, rowspan=8, sticky="nsew", padx=8, pady=(2, 8))
        self.child_list.bind("<<ListboxSelect>>", self._on_middle_select)
        add_tooltip(
            self.child_list,
            "Contenu de la section sélectionnée à gauche : sous-entrées directes "
            "([ON/OFF] Label -> Cible) et sous-sections ([ON/OFF] § Label, un "
            "sous-groupe de liens). Sélectionnez une sous-section pour voir/éditer "
            "ses billets à droite. Vide si aucune section n'est sélectionnée, ou si "
            "la section sélectionnée est un simple lien sans rien en dessous.",
        )

        self.leaf_list = tk.Listbox(self, height=14, exportselection=False)
        self.leaf_list.grid(row=3, column=4, rowspan=8, sticky="nsew", padx=8, pady=(2, 8))
        add_tooltip(
            self.leaf_list,
            "Billets/pages de la sous-section sélectionnée au milieu : "
            "[ON/OFF] Label -> Cible. Vide tant qu'aucune sous-section n'est "
            "sélectionnée au milieu.",
        )

        section_buttons = [
            (
                "+ Section",
                self._add_section,
                "Crée une nouvelle section (regroupement de liens) dans le menu latéral. "
                "À faire en premier : les colonnes suivantes restent vides tant qu'aucune "
                "section n'existe.",
            ),
            ("Modifier", self._edit_section, "Renomme la section sélectionnée."),
            (
                "Supprimer",
                self._delete_section,
                "Supprime la section sélectionnée ainsi que tout son contenu.",
            ),
            ("Monter", self._move_section_up, "Déplace la section sélectionnée vers le haut."),
            ("Descendre", self._move_section_down, "Déplace la section sélectionnée vers le bas."),
            (
                "Activer/Désactiver",
                self._toggle_section,
                "Active ou désactive toute la section sans la supprimer.",
            ),
        ]
        for idx, (label, callback, help_text) in enumerate(section_buttons):
            button = ttk.Button(self, text=label, command=callback)
            button.grid(row=idx + 3, column=1, sticky="ew", padx=8, pady=4)
            add_tooltip(button, help_text)

        middle_buttons = [
            (
                "+ Sous-section",
                self._add_subsection,
                "Ajoute une sous-section (un sous-groupe de liens, ex. « Bossuet et la "
                "rhétorique chrétienne ») dans la section sélectionnée à gauche. "
                "Sélectionnez ou créez d'abord une section.",
            ),
            (
                "+ Billet",
                self._add_child,
                "Ajoute un lien (billet, page...) dans la sous-section sélectionnée au "
                "milieu. Sélectionnez ou créez d'abord une sous-section.",
            ),
            ("Modifier", self._edit_middle, "Édite la sous-entrée ou la sous-section sélectionnée."),
            ("Supprimer", self._delete_middle, "Supprime la sous-entrée ou la sous-section sélectionnée."),
            ("Monter", self._move_middle_up, "Déplace l'élément sélectionné vers le haut."),
            ("Descendre", self._move_middle_down, "Déplace l'élément sélectionné vers le bas."),
            (
                "Activer/Désactiver",
                self._toggle_middle,
                "Active ou désactive l'élément sélectionné sans le supprimer.",
            ),
        ]
        for idx, (label, callback, help_text) in enumerate(middle_buttons):
            button = ttk.Button(self, text=label, command=callback)
            button.grid(row=idx + 3, column=3, sticky="ew", padx=8, pady=4)
            add_tooltip(button, help_text)

        leaf_buttons = [
            (
                "+ Billet",
                self._add_leaf,
                "Ajoute un lien (billet, page...) dans la sous-section sélectionnée au "
                "milieu. Sélectionnez ou créez d'abord une sous-section.",
            ),
            ("Modifier", self._edit_leaf, "Édite le billet sélectionné."),
            ("Supprimer", self._delete_leaf, "Supprime le billet sélectionné."),
            ("Monter", self._move_leaf_up, "Déplace le billet sélectionné vers le haut."),
            ("Descendre", self._move_leaf_down, "Déplace le billet sélectionné vers le bas."),
            (
                "Activer/Désactiver",
                self._toggle_leaf,
                "Active ou désactive le billet sélectionné sans le supprimer.",
            ),
        ]
        for idx, (label, callback, help_text) in enumerate(leaf_buttons):
            button = ttk.Button(self, text=label, command=callback)
            button.grid(row=idx + 3, column=5, sticky="ew", padx=8, pady=4)
            add_tooltip(button, help_text)

        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(2, weight=1)
        self.grid_columnconfigure(4, weight=1)
        self.grid_rowconfigure(10, weight=1)

    def get_sections(self) -> list[SideMenuSection]:
        return [
            SideMenuSection(
                label=section.label,
                enabled=section.enabled,
                target=section.target,
                target_type=section.target_type,
                numbered=section.numbered,
                children=[_clone_menu_link(child) for child in section.children],
                subsections=[_clone_side_subsection(sub) for sub in section.subsections],
            )
            for section in self.sections
        ]

    def set_sections(self, sections: list[SideMenuSection]) -> None:
        self.sections = [
            SideMenuSection(
                label=section.label,
                enabled=section.enabled,
                target=section.target,
                target_type=section.target_type,
                numbered=section.numbered,
                children=[_clone_menu_link(child) for child in section.children],
                subsections=[_clone_side_subsection(sub) for sub in section.subsections],
            )
            for section in sections
        ]
        self._refresh_sections()

    def get_title(self) -> str:
        return self.title_var.get().strip()

    def set_title(self, title: str) -> None:
        self.title_var.set(title)

    def _refresh_sections(self) -> None:
        self.section_list.delete(0, tk.END)
        for section in self.sections:
            marker = "ON" if section.enabled else "OFF"
            link_suffix = f" -> {section.target}" if (section.target or "").strip() else ""
            numbered_suffix = " [numérotée]" if section.numbered else ""
            self.section_list.insert(tk.END, f"[{marker}] {section.label}{link_suffix}{numbered_suffix}")
        self._refresh_children()

    def _refresh_children(self) -> None:
        self.child_list.delete(0, tk.END)
        self._middle_rows = []
        section = self._current_section()
        if section is not None:
            for index, child in enumerate(section.children):
                marker = "ON" if child.enabled else "OFF"
                self.child_list.insert(tk.END, f"[{marker}] {child.label} -> {child.target}")
                self._middle_rows.append(("child", index))
            for index, subsection in enumerate(section.subsections):
                marker = "ON" if subsection.enabled else "OFF"
                link_suffix = f" -> {subsection.target}" if (subsection.target or "").strip() else ""
                billet_count = len(subsection.children)
                self.child_list.insert(
                    tk.END, f"[{marker}] § {subsection.label}{link_suffix} ({billet_count} billet(s))"
                )
                self._middle_rows.append(("subsection", index))
        self._refresh_leaves()

    def _refresh_leaves(self) -> None:
        self.leaf_list.delete(0, tk.END)
        subsection = self._current_subsection()
        if subsection is None:
            return
        for child in subsection.children:
            marker = "ON" if child.enabled else "OFF"
            self.leaf_list.insert(tk.END, f"[{marker}] {child.label} -> {child.target}")

    def _current_section_index(self) -> int | None:
        selected = self.section_list.curselection()
        if not selected:
            return None
        return int(selected[0])

    def _current_section(self) -> SideMenuSection | None:
        section_idx = self._current_section_index()
        if section_idx is None or section_idx >= len(self.sections):
            return None
        return self.sections[section_idx]

    def _current_middle_row(self) -> tuple[str, int] | None:
        selected = self.child_list.curselection()
        if not selected:
            return None
        row_index = int(selected[0])
        if row_index >= len(self._middle_rows):
            return None
        return self._middle_rows[row_index]

    def _current_child_index(self) -> int | None:
        row = self._current_middle_row()
        if row is None or row[0] != "child":
            return None
        return row[1]

    def _current_subsection_index(self) -> int | None:
        row = self._current_middle_row()
        if row is None or row[0] != "subsection":
            return None
        return row[1]

    def _current_subsection(self) -> SideMenuSubSection | None:
        section = self._current_section()
        index = self._current_subsection_index()
        if section is None or index is None or index >= len(section.subsections):
            return None
        return section.subsections[index]

    def _current_leaf_index(self) -> int | None:
        selected = self.leaf_list.curselection()
        if not selected:
            return None
        return int(selected[0])

    def _select_middle_row(self, kind: str, index: int) -> None:
        for row_index, row in enumerate(self._middle_rows):
            if row == (kind, index):
                self.child_list.selection_clear(0, tk.END)
                self.child_list.selection_set(row_index)
                return

    def _on_section_select(self, _event: tk.Event[tk.Listbox]) -> None:
        self._refresh_children()

    def _on_middle_select(self, _event: tk.Event[tk.Listbox]) -> None:
        self._refresh_leaves()

    # -- sections -----------------------------------------------------------

    def _add_section(self) -> None:
        section = ask_side_section(self, "Ajouter une section", content_targets=self._get_content_targets())
        if section is None:
            return
        add_side_section(self.sections, section)
        self._refresh_sections()
        new_index = len(self.sections) - 1
        self.section_list.selection_set(new_index)
        self._refresh_children()

    def _edit_section(self) -> None:
        index = self._current_section_index()
        if index is None:
            return
        updated = ask_side_section(
            self, "Modifier une section", self.sections[index], content_targets=self._get_content_targets()
        )
        if updated is None:
            return
        update_side_section(self.sections, index, updated)
        self._refresh_sections()
        self.section_list.selection_set(index)
        self._refresh_children()

    def _delete_section(self) -> None:
        index = self._current_section_index()
        if index is None:
            return
        remove_side_section(self.sections, index)
        self._refresh_sections()

    def _move_section_up(self) -> None:
        index = self._current_section_index()
        if index is None:
            return
        new_index = move_side_section_up(self.sections, index)
        self._refresh_sections()
        self.section_list.selection_set(new_index)
        self._refresh_children()

    def _move_section_down(self) -> None:
        index = self._current_section_index()
        if index is None:
            return
        new_index = move_side_section_down(self.sections, index)
        self._refresh_sections()
        self.section_list.selection_set(new_index)
        self._refresh_children()

    def _toggle_section(self) -> None:
        index = self._current_section_index()
        if index is None:
            return
        toggle_side_section(self.sections, index)
        self._refresh_sections()
        self.section_list.selection_set(index)
        self._refresh_children()

    # -- middle column: direct sous-entrées + sous-sections -----------------

    def _require_section(self) -> SideMenuSection | None:
        section = self._current_section()
        if section is None:
            if not self.sections:
                messagebox.showinfo(
                    "Aucune section",
                    "Créez d'abord une section avec « + Section » (colonne de gauche), "
                    "puis sélectionnez-la pour pouvoir lui ajouter du contenu.",
                )
            else:
                messagebox.showinfo(
                    "Aucune section sélectionnée",
                    "Sélectionnez d'abord une section dans la colonne de gauche.",
                )
        return section

    def _add_child(self) -> None:
        section = self._require_section()
        if section is None:
            return
        child = ask_menu_link(self, "Ajouter une sous-entrée", content_targets=self._get_content_targets())
        if child is None:
            return
        add_side_child(section, child)
        new_index = len(section.children) - 1
        self._refresh_children()
        self._select_middle_row("child", new_index)

    def _add_subsection(self) -> None:
        section = self._require_section()
        if section is None:
            return
        subsection = ask_side_subsection(
            self, "Ajouter une sous-section", content_targets=self._get_content_targets()
        )
        if subsection is None:
            return
        add_side_subsection(section, subsection)
        new_index = len(section.subsections) - 1
        self._refresh_children()
        self._select_middle_row("subsection", new_index)

    def _edit_middle(self) -> None:
        section = self._current_section()
        row = self._current_middle_row()
        if section is None or row is None:
            return
        kind, index = row
        if kind == "child":
            updated_child = ask_menu_link(
                self, "Modifier une sous-entrée", section.children[index], content_targets=self._get_content_targets()
            )
            if updated_child is None:
                return
            update_side_child(section, index, updated_child)
        else:
            updated_sub = ask_side_subsection(
                self,
                "Modifier une sous-section",
                section.subsections[index],
                content_targets=self._get_content_targets(),
            )
            if updated_sub is None:
                return
            update_side_subsection(section, index, updated_sub)
        self._refresh_children()
        self._select_middle_row(kind, index)

    def _delete_middle(self) -> None:
        section = self._current_section()
        row = self._current_middle_row()
        if section is None or row is None:
            return
        kind, index = row
        if kind == "child":
            remove_side_child(section, index)
        else:
            remove_side_subsection(section, index)
        self._refresh_children()

    def _move_middle_up(self) -> None:
        section = self._current_section()
        row = self._current_middle_row()
        if section is None or row is None:
            return
        kind, index = row
        new_index = move_side_child_up(section, index) if kind == "child" else move_side_subsection_up(section, index)
        self._refresh_children()
        self._select_middle_row(kind, new_index)

    def _move_middle_down(self) -> None:
        section = self._current_section()
        row = self._current_middle_row()
        if section is None or row is None:
            return
        kind, index = row
        new_index = (
            move_side_child_down(section, index) if kind == "child" else move_side_subsection_down(section, index)
        )
        self._refresh_children()
        self._select_middle_row(kind, new_index)

    def _toggle_middle(self) -> None:
        section = self._current_section()
        row = self._current_middle_row()
        if section is None or row is None:
            return
        kind, index = row
        if kind == "child":
            toggle_side_child(section, index)
        else:
            toggle_side_subsection(section, index)
        self._refresh_children()
        self._select_middle_row(kind, index)

    # -- right column: billets of the selected sous-section ------------------

    def _require_subsection(self) -> SideMenuSubSection | None:
        subsection = self._current_subsection()
        if subsection is None:
            if self._current_section() is None:
                messagebox.showinfo(
                    "Aucune section sélectionnée",
                    "Sélectionnez d'abord une section, puis une sous-section.",
                )
            else:
                messagebox.showinfo(
                    "Aucune sous-section sélectionnée",
                    "Créez d'abord une sous-section avec « + Sous-section » (colonne du "
                    "milieu), puis sélectionnez-la pour pouvoir lui ajouter des billets.",
                )
        return subsection

    def _add_leaf(self) -> None:
        subsection = self._require_subsection()
        if subsection is None:
            return
        child = ask_menu_link(self, "Ajouter un billet", content_targets=self._get_content_targets())
        if child is None:
            return
        add_side_child(subsection, child)
        self._refresh_leaves()
        self.leaf_list.selection_set(len(subsection.children) - 1)

    def _edit_leaf(self) -> None:
        subsection = self._current_subsection()
        leaf_index = self._current_leaf_index()
        if subsection is None or leaf_index is None:
            return
        updated = ask_menu_link(
            self, "Modifier un billet", subsection.children[leaf_index], content_targets=self._get_content_targets()
        )
        if updated is None:
            return
        update_side_child(subsection, leaf_index, updated)
        self._refresh_leaves()
        self.leaf_list.selection_set(leaf_index)

    def _delete_leaf(self) -> None:
        subsection = self._current_subsection()
        leaf_index = self._current_leaf_index()
        if subsection is None or leaf_index is None:
            return
        remove_side_child(subsection, leaf_index)
        self._refresh_leaves()

    def _move_leaf_up(self) -> None:
        subsection = self._current_subsection()
        leaf_index = self._current_leaf_index()
        if subsection is None or leaf_index is None:
            return
        new_index = move_side_child_up(subsection, leaf_index)
        self._refresh_leaves()
        self.leaf_list.selection_set(new_index)

    def _move_leaf_down(self) -> None:
        subsection = self._current_subsection()
        leaf_index = self._current_leaf_index()
        if subsection is None or leaf_index is None:
            return
        new_index = move_side_child_down(subsection, leaf_index)
        self._refresh_leaves()
        self.leaf_list.selection_set(new_index)

    def _toggle_leaf(self) -> None:
        subsection = self._current_subsection()
        leaf_index = self._current_leaf_index()
        if subsection is None or leaf_index is None:
            return
        toggle_side_child(subsection, leaf_index)
        self._refresh_leaves()
        self.leaf_list.selection_set(leaf_index)
