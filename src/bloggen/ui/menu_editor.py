"""Top and side menu editors + pure manipulation helpers."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from bloggen.config.models import MenuLink, SideMenuSection
from bloggen.ui.dialogs import ask_menu_link, ask_side_section


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
        children=list(section.children),
    )


def add_side_child(section: SideMenuSection, child: MenuLink) -> None:
    section.children.append(child)


def update_side_child(section: SideMenuSection, index: int, child: MenuLink) -> None:
    section.children[index] = child


def remove_side_child(section: SideMenuSection, index: int) -> MenuLink:
    return section.children.pop(index)


def move_side_child_up(section: SideMenuSection, index: int) -> int:
    return _move_up(section.children, index)


def move_side_child_down(section: SideMenuSection, index: int) -> int:
    return _move_down(section.children, index)


def toggle_side_child(section: SideMenuSection, index: int) -> None:
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


class TopMenuEditor(ttk.Frame):
    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master)
        self.items: list[MenuLink] = []
        self._build_ui()

    def _build_ui(self) -> None:
        self.listbox = tk.Listbox(self, height=12, exportselection=False)
        self.listbox.grid(row=0, column=0, rowspan=7, sticky="nsew", padx=8, pady=8)

        buttons = [
            ("Ajouter", self._add_item),
            ("Modifier", self._edit_item),
            ("Supprimer", self._delete_item),
            ("Monter", self._move_up),
            ("Descendre", self._move_down),
            ("Activer/Désactiver", self._toggle_item),
        ]
        for idx, (label, callback) in enumerate(buttons):
            ttk.Button(self, text=label, command=callback).grid(
                row=idx, column=1, sticky="ew", padx=8, pady=4
            )
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(6, weight=1)

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
        item = ask_menu_link(self, "Ajouter un item de menu")
        if item is None:
            return
        add_top_menu_item(self.items, item)
        self._refresh()
        self.listbox.selection_set(tk.END)

    def _edit_item(self) -> None:
        index = self._selected_index()
        if index is None:
            return
        edited = ask_menu_link(self, "Modifier un item de menu", self.items[index])
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
    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master)
        self.sections: list[SideMenuSection] = []
        self._build_ui()

    def _build_ui(self) -> None:
        self.section_list = tk.Listbox(self, height=12, exportselection=False)
        self.section_list.grid(row=0, column=0, rowspan=7, sticky="nsew", padx=8, pady=8)
        self.section_list.bind("<<ListboxSelect>>", self._on_section_select)

        self.child_list = tk.Listbox(self, height=12, exportselection=False)
        self.child_list.grid(row=0, column=2, rowspan=7, sticky="nsew", padx=8, pady=8)

        section_buttons = [
            ("+ Section", self._add_section),
            ("Modifier", self._edit_section),
            ("Supprimer", self._delete_section),
            ("Monter", self._move_section_up),
            ("Descendre", self._move_section_down),
            ("Activer/Désactiver", self._toggle_section),
        ]
        for idx, (label, callback) in enumerate(section_buttons):
            ttk.Button(self, text=label, command=callback).grid(
                row=idx, column=1, sticky="ew", padx=8, pady=4
            )

        child_buttons = [
            ("+ Sous-entrée", self._add_child),
            ("Modifier", self._edit_child),
            ("Supprimer", self._delete_child),
            ("Monter", self._move_child_up),
            ("Descendre", self._move_child_down),
            ("Activer/Désactiver", self._toggle_child),
        ]
        for idx, (label, callback) in enumerate(child_buttons):
            ttk.Button(self, text=label, command=callback).grid(
                row=idx, column=3, sticky="ew", padx=8, pady=4
            )

        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(2, weight=1)
        self.grid_rowconfigure(6, weight=1)

    def get_sections(self) -> list[SideMenuSection]:
        return [
            SideMenuSection(
                label=section.label,
                enabled=section.enabled,
                children=[_clone_menu_link(child) for child in section.children],
            )
            for section in self.sections
        ]

    def set_sections(self, sections: list[SideMenuSection]) -> None:
        self.sections = [
            SideMenuSection(
                label=section.label,
                enabled=section.enabled,
                children=[_clone_menu_link(child) for child in section.children],
            )
            for section in sections
        ]
        self._refresh_sections()

    def _refresh_sections(self) -> None:
        self.section_list.delete(0, tk.END)
        for section in self.sections:
            marker = "ON" if section.enabled else "OFF"
            self.section_list.insert(tk.END, f"[{marker}] {section.label}")
        self._refresh_children()

    def _refresh_children(self) -> None:
        self.child_list.delete(0, tk.END)
        section = self._current_section()
        if section is None:
            return
        for child in section.children:
            marker = "ON" if child.enabled else "OFF"
            self.child_list.insert(tk.END, f"[{marker}] {child.label} -> {child.target}")

    def _current_section_index(self) -> int | None:
        selected = self.section_list.curselection()
        if not selected:
            return None
        return int(selected[0])

    def _current_child_index(self) -> int | None:
        selected = self.child_list.curselection()
        if not selected:
            return None
        return int(selected[0])

    def _current_section(self) -> SideMenuSection | None:
        section_idx = self._current_section_index()
        if section_idx is None or section_idx >= len(self.sections):
            return None
        return self.sections[section_idx]

    def _on_section_select(self, _event: tk.Event[tk.Listbox]) -> None:
        self._refresh_children()

    def _add_section(self) -> None:
        section = ask_side_section(self, "Ajouter une section")
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
        updated = ask_side_section(self, "Modifier une section", self.sections[index])
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

    def _add_child(self) -> None:
        section = self._current_section()
        if section is None:
            return
        child = ask_menu_link(self, "Ajouter une sous-entrée")
        if child is None:
            return
        add_side_child(section, child)
        self._refresh_children()
        self.child_list.selection_set(len(section.children) - 1)

    def _edit_child(self) -> None:
        section = self._current_section()
        child_index = self._current_child_index()
        if section is None or child_index is None:
            return
        updated = ask_menu_link(self, "Modifier une sous-entrée", section.children[child_index])
        if updated is None:
            return
        update_side_child(section, child_index, updated)
        self._refresh_children()
        self.child_list.selection_set(child_index)

    def _delete_child(self) -> None:
        section = self._current_section()
        child_index = self._current_child_index()
        if section is None or child_index is None:
            return
        remove_side_child(section, child_index)
        self._refresh_children()

    def _move_child_up(self) -> None:
        section = self._current_section()
        child_index = self._current_child_index()
        if section is None or child_index is None:
            return
        new_index = move_side_child_up(section, child_index)
        self._refresh_children()
        self.child_list.selection_set(new_index)

    def _move_child_down(self) -> None:
        section = self._current_section()
        child_index = self._current_child_index()
        if section is None or child_index is None:
            return
        new_index = move_side_child_down(section, child_index)
        self._refresh_children()
        self.child_list.selection_set(new_index)

    def _toggle_child(self) -> None:
        section = self._current_section()
        child_index = self._current_child_index()
        if section is None or child_index is None:
            return
        toggle_side_child(section, child_index)
        self._refresh_children()
        self.child_list.selection_set(child_index)
