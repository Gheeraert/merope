"""Headless tests for MenuLinkDialog's pointing-type/picker logic.

Instantiates the dialog's body directly (bypassing simpledialog's modal
event loop, which needs a real user click) — same technique used to verify
other Tkinter-heavy UI code in this project.
"""

from __future__ import annotations

import tkinter as tk

import pytest

from bloggen.config.models import MenuLink, SideMenuSection, SideMenuSubSection
from bloggen.ui.dialogs import MenuLinkDialog, SideSectionDialog, SideSubSectionDialog
from bloggen.ui.menu_editor import SideMenuEditor


@pytest.fixture(scope="module")
def root():
    # A single Tk() root is reused across every test in this module: creating
    # and destroying one per test is what actually made these tests flaky
    # (Tcl/Tk get into a broken state under rapid create/destroy churn).
    window = tk.Tk()
    window.withdraw()
    yield window
    window.destroy()


def _make_dialog(root: tk.Tk, initial: MenuLink, content_targets=None) -> MenuLinkDialog:
    dialog = MenuLinkDialog.__new__(MenuLinkDialog)
    dialog.initial = initial
    dialog.content_targets = content_targets or []
    dialog.result = None
    frame = tk.Frame(root)
    frame.pack()
    dialog.body(frame)
    root.update_idletasks()
    return dialog


def test_defaults_to_internal_pointing_type(root):
    dialog = _make_dialog(root, MenuLink(label="", target=""))
    assert dialog.pointing_type_var.get() == MenuLinkDialog._POINTING_INTERNAL
    assert bool(dialog._picker_combo.grid_info())


def test_external_initial_shows_no_picker(root):
    dialog = _make_dialog(root, MenuLink(label="Ext", target="https://example.org", target_type="external"))
    assert dialog.pointing_type_var.get() == MenuLinkDialog._POINTING_EXTERNAL
    assert not dialog._picker_combo.grid_info()


def test_toggling_pointing_type_shows_and_hides_picker(root):
    dialog = _make_dialog(root, MenuLink(label="", target=""))
    dialog.pointing_type_var.set(MenuLinkDialog._POINTING_EXTERNAL)
    dialog._on_pointing_type_changed()
    root.update_idletasks()
    assert not dialog._picker_combo.grid_info()

    dialog.pointing_type_var.set(MenuLinkDialog._POINTING_INTERNAL)
    dialog._on_pointing_type_changed()
    root.update_idletasks()
    assert bool(dialog._picker_combo.grid_info())


def test_picker_selection_fills_target(root):
    targets = [("Premier billet (billet)", "/billets/premier-billet/index.html")]
    dialog = _make_dialog(root, MenuLink(label="", target=""), content_targets=targets)
    dialog.picker_var.set("Premier billet (billet)")
    dialog._on_picker_changed()
    assert dialog.target_var.get() == "/billets/premier-billet/index.html"


def test_picker_preselects_matching_label_when_editing(root):
    targets = [("Premier billet (billet)", "/billets/premier-billet/index.html")]
    dialog = _make_dialog(
        root,
        MenuLink(label="Un billet", target="/billets/premier-billet/index.html", target_type="internal"),
        content_targets=targets,
    )
    assert dialog.picker_var.get() == "Premier billet (billet)"


def test_apply_produces_internal_link_with_new_tab_false(root):
    dialog = _make_dialog(root, MenuLink(label="", target=""))
    dialog.label_var.set("Accueil")
    dialog.target_var.set("/index.html")
    dialog.apply()
    assert dialog.result == MenuLink(
        label="Accueil", target="/index.html", target_type="internal", enabled=True, new_tab=False
    )


def test_apply_produces_external_link_with_new_tab_false(root):
    dialog = _make_dialog(root, MenuLink(label="", target=""))
    dialog.label_var.set("Wikipedia")
    dialog.pointing_type_var.set(MenuLinkDialog._POINTING_EXTERNAL)
    dialog._on_pointing_type_changed()
    dialog.target_var.set("https://fr.wikipedia.org")
    dialog.apply()
    assert dialog.result == MenuLink(
        label="Wikipedia",
        target="https://fr.wikipedia.org",
        target_type="external",
        enabled=True,
        new_tab=False,
    )


def _make_section_dialog(root: tk.Tk, initial: SideMenuSection, content_targets=None) -> SideSectionDialog:
    dialog = SideSectionDialog.__new__(SideSectionDialog)
    dialog.initial = initial
    dialog.content_targets = content_targets or []
    dialog.result = None
    frame = tk.Frame(root)
    frame.pack()
    dialog.body(frame)
    root.update_idletasks()
    return dialog


def test_section_defaults_to_no_link_when_target_empty(root):
    dialog = _make_section_dialog(root, SideMenuSection(label=""))
    assert dialog.pointing_type_var.get() == SideSectionDialog._POINTING_NONE
    assert not dialog._picker_combo.grid_info()
    assert not dialog._target_entry.grid_info()


def test_section_reload_preselects_pointing_type_from_target_type(root):
    dialog = _make_section_dialog(
        root, SideMenuSection(label="Ext", target="https://example.org", target_type="external")
    )
    assert dialog.pointing_type_var.get() == SideSectionDialog._POINTING_EXTERNAL
    assert bool(dialog._target_entry.grid_info())
    assert not dialog._picker_combo.grid_info()


def test_section_switching_to_none_clears_target(root):
    dialog = _make_section_dialog(
        root, SideMenuSection(label="Ext", target="https://example.org", target_type="external")
    )
    dialog.pointing_type_var.set(SideSectionDialog._POINTING_NONE)
    dialog._on_pointing_type_changed()
    assert dialog.target_var.get() == ""


def test_section_apply_variants(root):
    targets = [("Corpus (page)", "/corpus/index.html")]

    none_dialog = _make_section_dialog(root, SideMenuSection(label=""), content_targets=targets)
    none_dialog.label_var.set("Titre seul")
    none_dialog.apply()
    assert none_dialog.result == SideMenuSection(
        label="Titre seul", enabled=True, target="", target_type="internal", children=[]
    )

    internal_dialog = _make_section_dialog(root, SideMenuSection(label=""), content_targets=targets)
    internal_dialog.label_var.set("Le projet")
    internal_dialog.pointing_type_var.set(SideSectionDialog._POINTING_INTERNAL)
    internal_dialog._on_pointing_type_changed()
    internal_dialog.picker_var.set("Corpus (page)")
    internal_dialog._on_picker_changed()
    internal_dialog.apply()
    assert internal_dialog.result == SideMenuSection(
        label="Le projet", enabled=True, target="/corpus/index.html", target_type="internal", children=[]
    )

    external_dialog = _make_section_dialog(root, SideMenuSection(label=""), content_targets=targets)
    external_dialog.label_var.set("Ressources")
    external_dialog.pointing_type_var.set(SideSectionDialog._POINTING_EXTERNAL)
    external_dialog._on_pointing_type_changed()
    external_dialog.target_var.set("https://example.org")
    external_dialog.apply()
    assert external_dialog.result == SideMenuSection(
        label="Ressources", enabled=True, target="https://example.org", target_type="external", children=[]
    )


def test_section_validate_requires_target_unless_none(root):
    dialog = _make_section_dialog(root, SideMenuSection(label=""))
    dialog.label_var.set("Ressources")
    dialog.pointing_type_var.set(SideSectionDialog._POINTING_EXTERNAL)
    dialog._on_pointing_type_changed()
    dialog.target_var.set("")
    assert dialog.validate() is False

    dialog.target_var.set("https://example.org")
    assert dialog.validate() is True

    dialog.pointing_type_var.set(SideSectionDialog._POINTING_NONE)
    dialog._on_pointing_type_changed()
    assert dialog.validate() is True


def test_section_preserves_children_across_apply(root):
    initial = SideMenuSection(label="Le projet", children=[MenuLink(label="Corpus", target="/corpus/index.html")])
    dialog = _make_section_dialog(root, initial)
    dialog.apply()
    assert dialog.result.children == initial.children


def test_side_menu_editor_get_and_set_sections_preserve_target(root):
    editor = SideMenuEditor(root)
    editor.set_sections(
        [SideMenuSection(label="Le projet", target="/projet/index.html", target_type="internal")]
    )
    sections = editor.get_sections()
    assert sections[0].target == "/projet/index.html"
    assert sections[0].target_type == "internal"


def test_section_numbered_checkbox_defaults_false_and_survives_apply(root):
    dialog = _make_section_dialog(root, SideMenuSection(label=""))
    assert dialog.numbered_var.get() is False
    dialog.label_var.set("Rhétorique")
    dialog.numbered_var.set(True)
    dialog.apply()
    assert dialog.result.numbered is True


def test_section_numbered_checkbox_preloads_from_initial(root):
    dialog = _make_section_dialog(root, SideMenuSection(label="Rhétorique", numbered=True))
    assert dialog.numbered_var.get() is True


def test_section_apply_preserves_subsections(root):
    initial = SideMenuSection(label="Rhétorique", subsections=[SideMenuSubSection(label="Bossuet")])
    dialog = _make_section_dialog(root, initial)
    dialog.apply()
    assert dialog.result.subsections == initial.subsections


def _make_subsection_dialog(
    root: tk.Tk, initial: SideMenuSubSection, content_targets=None
) -> SideSubSectionDialog:
    dialog = SideSubSectionDialog.__new__(SideSubSectionDialog)
    dialog.initial = initial
    dialog.content_targets = content_targets or []
    dialog.result = None
    frame = tk.Frame(root)
    frame.pack()
    dialog.body(frame)
    root.update_idletasks()
    return dialog


def test_subsection_defaults_to_no_link_when_target_empty(root):
    dialog = _make_subsection_dialog(root, SideMenuSubSection(label=""))
    assert dialog.pointing_type_var.get() == SideSubSectionDialog._POINTING_NONE
    assert not dialog._target_entry.grid_info()


def test_subsection_apply_variants(root):
    targets = [("Corpus (page)", "/corpus/index.html")]

    none_dialog = _make_subsection_dialog(root, SideMenuSubSection(label=""), content_targets=targets)
    none_dialog.label_var.set("Bossuet")
    none_dialog.apply()
    assert none_dialog.result == SideMenuSubSection(
        label="Bossuet", enabled=True, target="", target_type="internal", children=[]
    )

    internal_dialog = _make_subsection_dialog(root, SideMenuSubSection(label=""), content_targets=targets)
    internal_dialog.label_var.set("Figures")
    internal_dialog.pointing_type_var.set(SideSubSectionDialog._POINTING_INTERNAL)
    internal_dialog._on_pointing_type_changed()
    internal_dialog.picker_var.set("Corpus (page)")
    internal_dialog._on_picker_changed()
    internal_dialog.apply()
    assert internal_dialog.result.target == "/corpus/index.html"
    assert internal_dialog.result.target_type == "internal"


def test_subsection_apply_preserves_leaf_children(root):
    initial = SideMenuSubSection(
        label="Bossuet", children=[MenuLink(label="Billet A", target="/a/index.html")]
    )
    dialog = _make_subsection_dialog(root, initial)
    dialog.apply()
    assert dialog.result.children == initial.children


def test_side_menu_editor_three_levels_end_to_end(root):
    editor = SideMenuEditor(root)
    editor.set_sections(
        [
            SideMenuSection(
                label="Rhétorique",
                numbered=True,
                subsections=[
                    SideMenuSubSection(
                        label="Bossuet",
                        children=[MenuLink(label="Billet A", target="/a/index.html")],
                    ),
                    SideMenuSubSection(
                        label="Figures",
                        children=[MenuLink(label="Billet B", target="/b/index.html")],
                    ),
                ],
            )
        ]
    )
    editor.section_list.selection_set(0)
    editor._refresh_children()

    assert editor._middle_rows == [("subsection", 0), ("subsection", 1)]

    editor._select_middle_row("subsection", 1)
    editor._refresh_leaves()
    assert [editor.leaf_list.get(i) for i in range(editor.leaf_list.size())] == [
        "[ON] Billet B -> /b/index.html"
    ]

    sections = editor.get_sections()
    assert sections[0].numbered is True
    assert [sub.label for sub in sections[0].subsections] == ["Bossuet", "Figures"]
    assert sections[0].subsections[1].children[0].label == "Billet B"


def test_side_menu_editor_mixes_direct_children_and_subsections(root):
    editor = SideMenuEditor(root)
    editor.set_sections(
        [
            SideMenuSection(
                label="Navigation",
                children=[MenuLink(label="Accueil", target="/index.html")],
                subsections=[SideMenuSubSection(label="Groupe")],
            )
        ]
    )
    editor.section_list.selection_set(0)
    editor._refresh_children()
    assert editor._middle_rows == [("child", 0), ("subsection", 0)]

    editor._select_middle_row("child", 0)
    editor._refresh_leaves()
    assert editor.leaf_list.size() == 0
    assert editor._current_subsection() is None
