from bloggen.config.models import MenuLink, SideMenuSection, SideMenuSubSection
from bloggen.ui.menu_editor import (
    add_side_child,
    add_side_section,
    add_side_subsection,
    add_top_menu_item,
    move_side_child_up,
    move_side_section_down,
    move_side_subsection_down,
    move_side_subsection_up,
    move_top_menu_item_up,
    remove_side_child,
    remove_side_subsection,
    remove_top_menu_item,
    toggle_side_child,
    toggle_side_section,
    toggle_side_subsection,
    toggle_top_menu_item,
    update_side_subsection,
)


def test_top_menu_basic_manipulation():
    items: list[MenuLink] = []
    add_top_menu_item(items, MenuLink(label="Accueil", target="/index.html"))
    add_top_menu_item(items, MenuLink(label="Blog", target="/blog/index.html"))

    assert [item.label for item in items] == ["Accueil", "Blog"]

    move_top_menu_item_up(items, 1)
    assert [item.label for item in items] == ["Blog", "Accueil"]

    toggle_top_menu_item(items, 0)
    assert items[0].enabled is False

    removed = remove_top_menu_item(items, 1)
    assert removed.label == "Accueil"
    assert len(items) == 1


def test_side_menu_basic_manipulation():
    sections: list[SideMenuSection] = []
    first = SideMenuSection(label="Section A")
    second = SideMenuSection(label="Section B")
    add_side_section(sections, first)
    add_side_section(sections, second)

    assert [section.label for section in sections] == ["Section A", "Section B"]
    move_side_section_down(sections, 0)
    assert [section.label for section in sections] == ["Section B", "Section A"]

    section = sections[0]
    add_side_child(section, MenuLink(label="Sous 1", target="/sous-1"))
    add_side_child(section, MenuLink(label="Sous 2", target="/sous-2"))
    move_side_child_up(section, 1)
    assert [child.label for child in section.children] == ["Sous 2", "Sous 1"]

    toggle_side_child(section, 0)
    assert section.children[0].enabled is False

    removed = remove_side_child(section, 1)
    assert removed.label == "Sous 1"


def test_toggle_side_section_preserves_target():
    sections = [SideMenuSection(label="Ext", target="https://example.org", target_type="external")]
    toggle_side_section(sections, 0)
    assert sections[0].enabled is False
    assert sections[0].target == "https://example.org"
    assert sections[0].target_type == "external"


def test_toggle_side_section_preserves_numbered_and_subsections():
    sections = [SideMenuSection(label="Plan", numbered=True, subsections=[SideMenuSubSection(label="A")])]
    toggle_side_section(sections, 0)
    assert sections[0].enabled is False
    assert sections[0].numbered is True
    assert sections[0].subsections[0].label == "A"


def test_side_subsection_basic_manipulation():
    section = SideMenuSection(label="Rhétorique", numbered=True)
    add_side_subsection(section, SideMenuSubSection(label="Bossuet"))
    add_side_subsection(section, SideMenuSubSection(label="Figures"))

    assert [sub.label for sub in section.subsections] == ["Bossuet", "Figures"]
    move_side_subsection_down(section, 0)
    assert [sub.label for sub in section.subsections] == ["Figures", "Bossuet"]

    move_side_subsection_up(section, 1)
    assert [sub.label for sub in section.subsections] == ["Bossuet", "Figures"]

    toggle_side_subsection(section, 0)
    assert section.subsections[0].enabled is False

    removed = remove_side_subsection(section, 1)
    assert removed.label == "Figures"
    assert len(section.subsections) == 1


def test_side_subsection_leaf_children_use_the_same_child_helpers():
    section = SideMenuSection(label="Rhétorique")
    add_side_subsection(section, SideMenuSubSection(label="Bossuet"))
    subsection = section.subsections[0]

    add_side_child(subsection, MenuLink(label="Billet A", target="/a/index.html"))
    add_side_child(subsection, MenuLink(label="Billet B", target="/b/index.html"))
    assert [child.label for child in subsection.children] == ["Billet A", "Billet B"]

    toggle_side_child(subsection, 0)
    assert subsection.children[0].enabled is False

    removed = remove_side_child(subsection, 1)
    assert removed.label == "Billet B"


def test_update_side_subsection_replaces_by_index():
    section = SideMenuSection(label="Rhétorique")
    add_side_subsection(section, SideMenuSubSection(label="Ancien"))
    update_side_subsection(section, 0, SideMenuSubSection(label="Nouveau"))
    assert section.subsections[0].label == "Nouveau"
