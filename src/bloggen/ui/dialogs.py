"""Small Tk dialogs used by menu editors."""

from __future__ import annotations

import tkinter as tk
from tkinter import simpledialog, ttk

from bloggen.config.models import MenuLink, SideMenuSection


class MenuLinkDialog(simpledialog.Dialog):
    def __init__(self, parent: tk.Misc, title: str, initial: MenuLink | None = None) -> None:
        self.initial = initial or MenuLink(label="", target="")
        self.result: MenuLink | None = None
        super().__init__(parent, title)

    def body(self, master: tk.Misc) -> tk.Widget:
        self.label_var = tk.StringVar(value=self.initial.label)
        self.target_var = tk.StringVar(value=self.initial.target)
        self.target_type_var = tk.StringVar(value=self.initial.target_type)
        self.enabled_var = tk.BooleanVar(value=self.initial.enabled)
        self.new_tab_var = tk.BooleanVar(value=self.initial.new_tab)

        ttk.Label(master, text="Label").grid(row=0, column=0, sticky="w", padx=4, pady=4)
        label_entry = ttk.Entry(master, textvariable=self.label_var, width=40)
        label_entry.grid(row=0, column=1, sticky="ew", padx=4, pady=4)

        ttk.Label(master, text="Target").grid(row=1, column=0, sticky="w", padx=4, pady=4)
        ttk.Entry(master, textvariable=self.target_var, width=40).grid(
            row=1, column=1, sticky="ew", padx=4, pady=4
        )

        ttk.Label(master, text="Type").grid(row=2, column=0, sticky="w", padx=4, pady=4)
        type_combo = ttk.Combobox(
            master,
            textvariable=self.target_type_var,
            values=["internal", "external"],
            state="readonly",
            width=20,
        )
        type_combo.grid(row=2, column=1, sticky="w", padx=4, pady=4)

        ttk.Checkbutton(master, text="Activé", variable=self.enabled_var).grid(
            row=3, column=0, sticky="w", padx=4, pady=4
        )
        ttk.Checkbutton(master, text="Nouvel onglet", variable=self.new_tab_var).grid(
            row=3, column=1, sticky="w", padx=4, pady=4
        )
        master.grid_columnconfigure(1, weight=1)
        return label_entry

    def validate(self) -> bool:
        return bool(self.label_var.get().strip()) and bool(self.target_var.get().strip())

    def apply(self) -> None:
        self.result = MenuLink(
            label=self.label_var.get().strip(),
            target=self.target_var.get().strip(),
            target_type=self.target_type_var.get().strip() or "internal",
            enabled=self.enabled_var.get(),
            new_tab=self.new_tab_var.get(),
        )


class SideSectionDialog(simpledialog.Dialog):
    def __init__(
        self,
        parent: tk.Misc,
        title: str,
        initial: SideMenuSection | None = None,
    ) -> None:
        self.initial = initial or SideMenuSection(label="")
        self.result: SideMenuSection | None = None
        super().__init__(parent, title)

    def body(self, master: tk.Misc) -> tk.Widget:
        self.label_var = tk.StringVar(value=self.initial.label)
        self.enabled_var = tk.BooleanVar(value=self.initial.enabled)

        ttk.Label(master, text="Section").grid(row=0, column=0, sticky="w", padx=4, pady=4)
        entry = ttk.Entry(master, textvariable=self.label_var, width=40)
        entry.grid(row=0, column=1, sticky="ew", padx=4, pady=4)
        ttk.Checkbutton(master, text="Activée", variable=self.enabled_var).grid(
            row=1, column=0, sticky="w", padx=4, pady=4
        )
        master.grid_columnconfigure(1, weight=1)
        return entry

    def validate(self) -> bool:
        return bool(self.label_var.get().strip())

    def apply(self) -> None:
        self.result = SideMenuSection(
            label=self.label_var.get().strip(),
            enabled=self.enabled_var.get(),
            children=list(self.initial.children),
        )


def ask_menu_link(parent: tk.Misc, title: str, initial: MenuLink | None = None) -> MenuLink | None:
    dialog = MenuLinkDialog(parent, title=title, initial=initial)
    return dialog.result


def ask_side_section(
    parent: tk.Misc,
    title: str,
    initial: SideMenuSection | None = None,
) -> SideMenuSection | None:
    dialog = SideSectionDialog(parent, title=title, initial=initial)
    return dialog.result
